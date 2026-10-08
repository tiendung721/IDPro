# services/openai_ci.py
import os
import json
import time
from typing import Optional, Tuple, List, Dict, Any
from openai import OpenAI  # pyre-ignore-all-errors

# =========================
# PROMPTS + HELPERS
# =========================

_PY_HELPERS_CORE = r"""
import os, json, re
import pandas as pd

def _list_data_files(): 
    return sorted([
        fn for fn in os.listdir("/mnt/data")
        if fn.lower().endswith((".xlsx", ".xls", ".csv"))
    ])

def _dedupe_columns(cols):
    seen = {}
    out = []
    for c in cols:
        c = "" if c is None else str(c).strip()
        if c == "":
            out.append("")
            continue
        if c not in seen:
            seen[c] = 1
            out.append(c)
        else:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
    return out

def _clean_col_name(c):
    return "" if c is None else str(c).strip()

def _norm_text(s):
    if pd.isna(s):
        return ""
    return str(s).strip()

def _normalize_for_match(text):
    text = _norm_text(text).lower()
    text = re.sub(r"\s+", " ", text)
    return text

def _series_non_empty_ratio(s: pd.Series) -> float:
    if len(s) == 0:
        return 0.0
    return float((~s.isna() & (s.astype(str).str.strip() != "")).mean())

def _to_numeric_loose(s: pd.Series) -> pd.Series:
    if len(s) == 0:
        return pd.to_numeric(s, errors="coerce")

    s2 = s.astype(str).str.strip()
    s2 = s2.str.replace("\u00A0", "", regex=False)
    s2 = s2.str.replace(" ", "", regex=False)

    both_mask = s2.str.contains(r"\.") & s2.str.contains(r",")
    s2.loc[both_mask] = (
        s2.loc[both_mask]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )

    comma_only = (~both_mask) & s2.str.contains(",", regex=False)
    s2.loc[comma_only] = s2.loc[comma_only].str.replace(",", ".", regex=False)

    s2 = s2.str.replace(r"[^\d\.\-\+]", "", regex=True)
    return pd.to_numeric(s2, errors="coerce")

def _to_datetime_loose(s: pd.Series) -> pd.Series:
    if len(s) == 0:
        return pd.to_datetime(s, errors="coerce")
    return pd.to_datetime(s, errors="coerce", dayfirst=True)

def load_tables_from_manifest(manifest: dict):
    files = _list_data_files()
    if not files:
        raise RuntimeError("Không tìm thấy file dữ liệu trong /mnt/data")

    data_file = files[0]
    data_path = os.path.join("/mnt/data", data_file)

    sheet_name = manifest.get("sheet_name")
    tables = manifest.get("tables") or []
    if not isinstance(tables, list) or len(tables) == 0:
        raise RuntimeError("MANIFEST_JSON không có tables")

    is_csv = data_file.lower().endswith(".csv")
    if is_csv:
        raw = pd.read_csv(data_path, header=None)
    else:
        raw = pd.read_excel(
            data_path,
            sheet_name=sheet_name if sheet_name else 0,
            header=None
        )

    nrows, ncols = raw.shape
    out = {}

    for t in tables:
        tid = t.get("table_id") or ""
        hr = int(t.get("header_row_0based"))
        sr = int(t.get("start_row_0based"))
        er = int(t.get("end_row_0based"))
        sc = 0 if t.get("start_col_0based") is None else int(t.get("start_col_0based"))
        ec = (ncols - 1) if t.get("end_col_0based") is None else int(t.get("end_col_0based"))

        if hr < 0 or sr < 0 or er < 0 or er < sr:
            raise RuntimeError(f"Table {tid}: index hàng không hợp lệ")
        if not (0 <= hr < nrows and 0 <= sr < nrows and 0 <= er < nrows):
            raise RuntimeError(f"Table {tid}: index hàng vượt range nrows={nrows}")
        if not (0 <= sc <= ec <= ncols - 1):
            raise RuntimeError(f"Table {tid}: index cột không hợp lệ")

        header = list(raw.iloc[hr, sc:ec + 1].tolist())
        header = [_clean_col_name(x) for x in header]
        header = _dedupe_columns(header)

        block = raw.iloc[sr:er + 1, sc:ec + 1].copy()
        block.columns = header

        keep_cols = []
        for c in block.columns:
            if str(c).strip() == "":
                continue
            if block[c].isna().all():
                continue
            keep_cols.append(c)

        block = block[keep_cols].copy()
        block.insert(0, "__src_row__", [sr + 1 + i for i in range(len(block))])
        out[tid] = block

    return data_file, sheet_name, out
"""

_PY_HELPERS_PROFILE = r"""
def classify_column_role(col_name: str, series: pd.Series) -> dict:
    name = _normalize_for_match(col_name)
    s = series.copy()

    non_empty_ratio = _series_non_empty_ratio(s)
    num = _to_numeric_loose(s)
    num_ratio = float(num.notna().mean()) if len(s) else 0.0

    dt = _to_datetime_loose(s)
    dt_ratio = float(dt.notna().mean()) if len(s) else 0.0

    unique_count = int(s.nunique(dropna=True))
    unique_ratio = float(unique_count / max(len(s), 1))

    identifier_keywords = ["id", "code", "mã", "ma ", "stt", "sku", "serial", "no", "số chứng từ", "mã hàng"]
    measure_keywords = [
        "doanh thu", "revenue", "sales", "amount", "value", "cost", "price",
        "đơn giá", "gia", "số lượng", "so luong", "quantity", "qty",
        "volume", "total", "tổng", "tax", "thuế", "profit", "lợi nhuận",
        "tiền", "thành tiền", "giá trị"
    ]
    time_keywords = ["date", "day", "month", "year", "ngày", "tháng", "năm", "thoi gian", "thời gian"]
    status_keywords = ["status", "trạng thái", "state"]

    if non_empty_ratio < 0.2:
        return {"role": "dimension", "num_ratio": num_ratio, "dt_ratio": dt_ratio}

    if any(k in name for k in time_keywords) and dt_ratio >= 0.3:
        return {"role": "time", "num_ratio": num_ratio, "dt_ratio": dt_ratio}

    if dt_ratio >= 0.8:
        return {"role": "time", "num_ratio": num_ratio, "dt_ratio": dt_ratio}

    if any(k in name for k in identifier_keywords):
        return {"role": "identifier", "num_ratio": num_ratio, "dt_ratio": dt_ratio}

    if any(k in name for k in status_keywords):
        return {"role": "status", "num_ratio": num_ratio, "dt_ratio": dt_ratio}

    if num_ratio >= 0.9:
        if unique_ratio > 0.9 and len(s) > 20:
            return {"role": "identifier", "num_ratio": num_ratio, "dt_ratio": dt_ratio}
        if name in {"stt", "số thứ tự"}:
            return {"role": "identifier", "num_ratio": num_ratio, "dt_ratio": dt_ratio}
        if any(k in name for k in measure_keywords):
            return {"role": "measure", "num_ratio": num_ratio, "dt_ratio": dt_ratio}
        return {"role": "measure", "num_ratio": num_ratio, "dt_ratio": dt_ratio}

    if num_ratio >= 0.4 and any(k in name for k in measure_keywords):
        return {"role": "measure", "num_ratio": num_ratio, "dt_ratio": dt_ratio}

    return {"role": "dimension", "num_ratio": num_ratio, "dt_ratio": dt_ratio}

def infer_table_role(df: pd.DataFrame, role_map: dict) -> str:
    cols = [c for c in df.columns if c != "__src_row__"]
    measures = [c for c in cols if role_map.get(c) == "measure"]
    dimensions = [c for c in cols if role_map.get(c) == "dimension"]
    identifiers = [c for c in cols if role_map.get(c) == "identifier"]
    times = [c for c in cols if role_map.get(c) == "time"]

    nrows = len(df)

    if len(measures) >= 1 and (len(dimensions) >= 1 or len(times) >= 1):
        return "fact"
    if len(measures) == 0 and len(dimensions) >= 2 and nrows <= 200:
        return "lookup"
    if len(measures) >= 1 and len(dimensions) == 0 and len(times) == 0:
        return "summary"
    if len(identifiers) >= 1 and len(dimensions) >= 1 and len(measures) == 0:
        return "master_data"
    return "unknown"

def detect_semantic_hints(df: pd.DataFrame, role_map: dict) -> list:
    cols = [_normalize_for_match(c) for c in df.columns if c != "__src_row__"]
    joined = " | ".join(cols)
    hints = []

    groups = {
        "sales": ["doanh thu", "revenue", "sales", "bán hàng", "khách hàng", "đơn hàng"],
        "inventory": ["tồn kho", "nhập kho", "xuất kho", "warehouse", "stock"],
        "product": ["sản phẩm", "mặt hàng", "tên hàng", "mã hàng", "sku"],
        "pricing": ["đơn giá", "giá", "price", "cost"],
        "operations": ["vận hành", "ca", "trạm", "thiết bị", "machine"],
        "finance": ["chi phí", "lợi nhuận", "thuế", "cost", "profit", "tax"],
    }

    for hint, keywords in groups.items():
        if any(k in joined for k in keywords):
            hints.append(hint)

    return sorted(set(hints))

def profile_table(table_id: str, df: pd.DataFrame) -> dict:
    work = df.copy()
    cols = [c for c in work.columns if c != "__src_row__"]


    role_map = {}
    numeric_cols = []
    category_cols = []
    dimension_cols = []
    identifier_cols = []
    time_cols = []
    measure_cols = []
    status_cols = []

    for c in cols:
        info = classify_column_role(c, work[c])
        role = info["role"]
        role_map[c] = role

        if role == "measure":
            measure_cols.append(c)
            numeric_cols.append(c)
        elif role == "identifier":
            identifier_cols.append(c)
        elif role == "time":
            time_cols.append(c)
        elif role == "status":
            status_cols.append(c)
            category_cols.append(c)
        elif role == "dimension":
            dimension_cols.append(c)
            category_cols.append(c)

    table_role = infer_table_role(work, role_map)
    semantic_hints = detect_semantic_hints(work, role_map)
    name_info = infer_table_display_name(table_id, work)

    return {
        "table_id": table_id,
        "row_count": int(len(work)),
        "col_count": int(len(cols)),
        "columns": cols,
        "time_cols": time_cols,
        "numeric_cols": numeric_cols,
        "category_cols": category_cols,
        "dimension_cols": dimension_cols,
        "identifier_cols": identifier_cols,
        "measure_cols": measure_cols,
        "status_cols": status_cols,
        "table_role": table_role,
        "semantic_hints": semantic_hints,
        "table_id": table_id,
        "display_name": name_info["display_name"],
        "display_name_source": name_info["display_name_source"],
    }

def build_dataset_profile_from_manifest(manifest: dict):
    data_file, sheet_name, tables = load_tables_from_manifest(manifest)

    prof_tables = []
    quality_flags = []

    for tid, df in tables.items():
        p = profile_table(tid, df)
        prof_tables.append(p)

        if p["row_count"] == 0:
            quality_flags.append({"severity": "warn", "message": f"{tid} không có dòng dữ liệu"})
        if p["col_count"] == 0:
            quality_flags.append({"severity": "warn", "message": f"{tid} không có cột dữ liệu hữu ích"})
        if p["table_role"] == "unknown":
            quality_flags.append({"severity": "info", "message": f"{tid} chưa xác định rõ vai trò bảng"})

    return {
        "data_file": data_file,
        "sheet_name": sheet_name,
        "tables": tables,
        "dataset_profile": {
            "tables": prof_tables,
            "quality_flags": quality_flags,
        }
    }
def _normalize_header_tokens(cols: list[str]) -> str:
    return " | ".join([_normalize_for_match(c) for c in cols if str(c).strip()])

def infer_table_display_name(table_id: str, df: pd.DataFrame, sheet_name: str | None = None) -> dict:
    cols = [c for c in df.columns if c != "__src_row__"]
    joined = _normalize_header_tokens(cols)

    # ưu tiên keyword rõ ràng
    if any(k in joined for k in ["mô tả công việc", "công việc", "task", "job", "work"]):
        if any(k in joined for k in ["dự án", "project"]):
            name = "Công việc theo dự án"
        else:
            name = "Danh sách công việc"
        source = "headers"
    elif any(k in joined for k in ["dự án", "project", "project name", "mã dự án"]):
        name = "Thông tin dự án"
        source = "headers"
    elif any(k in joined for k in ["ngày", "tháng", "năm", "date", "month", "year"]):
        name = "Dữ liệu theo thời gian"
        source = "headers"
    elif any(k in joined for k in ["chi phí", "cost", "giá", "price", "đơn giá", "doanh thu", "revenue"]):
        name = "Dữ liệu chi phí và giá trị"
        source = "headers"
    elif any(k in joined for k in ["trạng thái", "status", "state"]):
        name = "Danh sách theo dõi trạng thái"
        source = "headers"
    elif any(k in joined for k in ["nhân viên", "employee", "owner", "phụ trách"]):
        name = "Thông tin nhân sự phụ trách"
        source = "headers"
    else:
        # fallback theo role hoặc sheet name
        if sheet_name and str(sheet_name).strip():
            name = f"Dữ liệu từ {str(sheet_name).strip()}"
            source = "sheet_name"
        else:
            name = "Bảng dữ liệu chi tiết"
            source = "fallback"

    return {
        "display_name": name,
        "display_name_source": source
    }
"""

INSTRUCTIONS_QA = f"""
Bạn là một chuyên viên phân tích dữ liệu.
Nhiệm vụ của bạn là trả lời các câu hỏi cụ thể của người dùng dựa trên DỮ LIỆU TRONG FILE GỐC (giữ nguyên cấu trúc ban đầu).

YÊU CẦU BẮT BUỘC:
- Ngôn ngữ trả lời: Tiếng Việt.
- Chỉ sử dụng Python (Code Interpreter) để đọc và phân tích dữ liệu.
- Không suy đoán. Mọi kết luận phải dựa trên dữ liệu thực tế.
- Trước khi trả lời, luôn đọc MANIFEST_JSON (được cung cấp trong prompt) để hiểu cấu trúc bảng đã confirm.

DỮ LIỆU & CẤU TRÚC:
- Trong /mnt/data có file Excel/CSV gốc.
- Trong prompt có khối MANIFEST_JSON mô tả các bảng đã confirm:
  + sheet_name (nếu excel)
  + tables: mỗi bảng có table_id (T1..), header_row_0based, start_row_0based, end_row_0based

CÁCH LÀM (BẮT BUỘC):
1) Liệt kê file trong /mnt/data để xác định file dữ liệu.
2) Parse MANIFEST_JSON, sau đó dùng helper load_tables_from_manifest(manifest) để cắt bảng.
3) Mỗi bảng sau khi load sẽ có cột __src_row__ (1-based) tạo TRONG BỘ NHỚ để truy vết dòng gốc.
4) Khi cần tham chiếu dòng: chỉ trả số dòng (ví dụ: 12, 45), KHÔNG in literal "__src_row__".

NGUYÊN TẮC TRẢ LỜI:
- Chỉ trả lời đúng trọng tâm câu hỏi.
- Khi trả lời cho người dùng, ưu tiên nêu tên bảng theo ngữ cảnh nếu có.
- Có thể ghi theo dạng: "Danh sách công việc (T1)" khi cần rõ nguồn.
- Không chỉ viết trần T1/T2 nếu có thể diễn đạt tự nhiên hơn.
- Không bịa thông tin hoặc suy luận vượt quá dữ liệu.
- Trả lời như đang hỗ trợ người dùng phổ thông, không phải lập trình viên hay chuyên viên backend.
- Ưu tiên kết luận ngắn gọn trước, rồi mới giải thích thêm nếu cần.
- Không mô tả quy trình nội bộ như parse file, manifest, pipeline, backend, schema, mapping, detect... trừ khi người dùng hỏi trực tiếp.
- Hạn chế thuật ngữ nghiệp vụ hoặc kỹ thuật. Nếu buộc phải dùng, phải diễn đạt lại bằng ngôn ngữ dễ hiểu.
- Không liệt kê quá nhiều chi tiết kỹ thuật nếu người dùng chỉ hỏi câu đơn giản.
- Ưu tiên dùng tên bảng theo ngữ cảnh tự nhiên. Chỉ nhắc T1/T2 khi thật sự cần truy vết nguồn.
- Nếu câu hỏi có thể trả lời ngắn, không trả lời dài.
- Nếu dữ liệu chưa đủ chắc chắn, nói ngắn gọn theo kiểu dễ hiểu, ví dụ: "Hiện dữ liệu chưa đủ rõ để kết luận chính xác phần này."
- Khi phù hợp, trình bày theo cấu trúc:
  1. Trả lời chính
  2. Căn cứ từ dữ liệu
  3. Lưu ý thêm (nếu có)
- Trả lời dài / phân tích sâu chỉ khi người dùng thực sự yêu cầu.
- Nếu dataset_profile_compact có display_name cho bảng, luôn ưu tiên gọi theo display_name.
- Người dùng không cần biết quá trình xử lý nội bộ.
- Không giải thích cách hệ thống đọc file hoặc phân tích dữ liệu, trừ khi người dùng hỏi trực tiếp về kỹ thuật.
- Tập trung vào kết quả và ý nghĩa của dữ liệu.
- CẤM các từ/cụm từ: manifest, parse, schema, backend, pipeline, detect, mapping, role classification, table extraction (trừ khi người dùng hỏi kỹ thuật).

OUTPUT FORMAT:
Chỉ được trả về duy nhất 1 JSON object hợp lệ với cấu trúc sau:
{{
  "answer_core": "Tóm tắt ngắn gọn phần phân tích dữ liệu của bạn, không cần quá thân thiện, chỉ tập trung vào số liệu và kết luận.",
  "evidence": ["Căn cứ 1", "Căn cứ 2"],
  "limitations": ["Hạn chế dữ liệu 1 (nếu có)"],
  "friendly_answer": "Câu trả lời hoàn chỉnh để hiển thị cho người dùng, viết bằng giọng điệu hỗ trợ, thân thiện, không dùng thuật ngữ phần mềm, tuân thủ độ dài theo yêu cầu.",
  "source_tables": ["T1", "T2"]
}}


{_PY_HELPERS_CORE}
"""

INSTRUCTIONS_REPORT_PLAN = f"""
Bạn là AI phân tích dữ liệu để đề xuất các loại báo cáo có thể sinh ra từ file đã tải lên.

MỤC TIÊU
- Đọc dữ liệu thật từ file gốc theo MANIFEST_JSON.
- Đánh giá toàn bộ report_id trong REPORT_CATALOG_JSON.
- Chỉ chọn các report thật sự có căn cứ từ bảng và cột thực tế.
- Trả về DUY NHẤT 1 JSON object hợp lệ, không markdown, không giải thích ngoài JSON.

BẮT BUỘC
- Phải dùng Python (Code Interpreter).
- Phải parse MANIFEST_JSON thành biến manifest.
- Phải gọi:
  ctx = build_dataset_profile_from_manifest(manifest)
  dataset_profile = ctx["dataset_profile"]
- Chỉ được dùng report_id có trong REPORT_CATALOG_JSON.
- Không suy đoán vượt quá dữ liệu.

CÁCH ĐÁNH GIÁ
1) Phân tích dataset_profile cho từng bảng:
   - table_role
   - row_count, col_count
   - measure_cols
   - dimension_cols, category_cols
   - identifier_cols
   - time_cols
   - semantic_hints

2) Với MỖI report trong REPORT_CATALOG_JSON:
   - chấm fit_score từ 0 đến 1
   - gán fit_level theo:
     - high: >= 0.75
     - medium: >= 0.5 và < 0.75
     - low: > 0 và < 0.5
     - none: = 0
   - decision chỉ là:
     - "selected" nếu có căn cứ rõ từ bảng/cột thật
     - "rejected" nếu chưa đủ căn cứ
   - evidence phải nêu rõ bảng nào, cột nào
   - nếu rejected thì missing_requirements phải nêu lý do cụ thể khi có thể

NGUYÊN TẮC CHỌN REPORT
- Ưu tiên report có căn cứ rõ từ bảng fact hoặc summary.
- Nếu report cần xu hướng thì ưu tiên có time_cols.
- Nếu report cần breakdown thì ưu tiên có dimension/category phù hợp.
- Nếu dữ liệu chủ yếu là lookup/master_data, ít dòng, hoặc thiếu measure thì phải phản ánh trung thực.
- Không chọn report chỉ vì tên nghe có vẻ phù hợp.
- report_options chỉ gồm các report có decision = "selected".
- recommended_default phải là tập con của report_options.

YÊU CẦU CHO report_options
- report_options phải tách rõ 2 lớp:
  1) display: phần hiển thị cho người dùng phổ thông
  2) debug_meta: phần kỹ thuật cho dev theo dõi
- display.title phải thân thiện, dễ hiểu, không dùng từ ngữ kỹ thuật hoặc đặc thù ngành nếu không thật cần.
- display.description phải ngắn gọn, mô tả mục đích báo cáo theo ngôn ngữ phổ thông.
- display.reason phải giải thích vì sao báo cáo phù hợp bằng ngôn ngữ dễ hiểu, tránh nhắc trực tiếp tên bảng/cột, measure/dimension/category, trừ khi thật sự cần để tránh mơ hồ.Nếu cần nhắc đến bảng, hãy dùng tên ngữ cảnh từ dataset_profile.tables[].display_name . Table_id chỉ được xuất hiện trong debug_meta
- Tuyệt đối không dùng các cụm như `nghiệp vụ`, `business`, `business view`, `business-facing`, `logic nghiệp vụ` trong `display.title`, `display.description`, `display.reason`.
- Nếu ý là giúp người đọc theo dõi công việc hoặc trạng thái, hãy diễn đạt bằng các cụm phổ thông như `dễ theo dõi`, `xem nhanh`, `đối chiếu`, `kiểm tra`, `nhóm thông tin`.
- display.recommendation chỉ được là "recommended" hoặc "optional".
- debug_meta.reason_technical phải nêu rõ bảng nào và cột nào làm căn cứ.
- debug_meta.inputs.default nên map vào cột phù hợp nếu đủ chắc chắn; nếu không chắc thì để rỗng.
- debug_meta phải chứa tab_id kỹ thuật khớp catalog để backend/dev dùng tiếp.

JSON OUTPUT BẮT BUỘC
{{
  "version": "1.1",
  "dataset_profile": {{
    "tables": [
      {{
        "table_id": "T1",
        "row_count": 0,
        "col_count": 0,
        "columns": [],
        "time_cols": [],
        "numeric_cols": [],
        "category_cols": [],
        "dimension_cols": [],
        "identifier_cols": [],
        "measure_cols": [],
        "status_cols": [],
        "table_role": "unknown",
        "display_name": "Danh sách công việc",
        "display_name_source": "headers",
        "semantic_hints": []
      }}
    ],
    "quality_flags": [{{"severity": "info|warn|error", "message": "..."}}]
  }},
  "catalog_evaluation": [
    {{
      "report_id": "exec_overview",
      "fit_level": "high|medium|low|none",
      "fit_score": 0.0,
      "decision": "selected|rejected",
      "evidence": ["Bảng T1 có measure_cols: Doanh thu, Số lượng"],
      "candidate_tables": ["T1"],
      "candidate_columns": {{
        "time_cols": [],
        "measure_cols": [],
        "category_cols": [],
        "dimension_cols": [],
        "identifier_cols": []
      }},
      "missing_requirements": []
    }}
  ],
  "report_options": [
    {{
      "report_id": "exec_overview",
      "title": "...",
      "description": "...",
      "tab_id": "performance",
      "reason": "Phù hợp vì dựa trên bảng nào và cột nào",
      "inputs": [
        {{"key":"time_col","type":"string","default":""}},
        {{"key":"measure_col","type":"string","default":""}},
        {{"key":"category_col","type":"string","default":""}},
        {{"key":"top_n","type":"int","default":10}}
      ]
    }}
  ],
  "recommended_default": ["exec_overview"]
}}

KIỂM TRA CUỐI TRƯỚC KHI TRẢ KẾT QUẢ
- JSON hợp lệ.
- Đã đánh giá tất cả report_id trong catalog.
- report_options chỉ chứa report được selected.
- recommended_default là tập con của report_options.
- display phải thân thiện, dễ hiểu cho người dùng phổ thông.
- debug_meta.reason_technical không được chung chung; phải nhắc rõ bảng và cột.

{_PY_HELPERS_CORE}
{_PY_HELPERS_PROFILE}
"""

REPORT_PLAN_PROMPT_HARD_RULES = """
OVERRIDE DISPLAY RULES FOR REPORT PLAN
- These rules override any softer instruction above.
- Always emit `report_options[].display` and `report_options[].debug_meta`.
- Keep technical fields in English only for ids and debug data: `report_id`, `tab_id`, `framework_title`, `debug_meta`, `evidence`, `candidate_tables`, `candidate_columns`, `inputs`.
- All user-facing text must be 100% Vietnamese and easy to understand:
  - `report_options[].display.title`
  - `report_options[].display.description`
  - `report_options[].display.reason`
  - `report_options[].debug_meta.reason_user_safe`
- `display.title` must be 3-8 words, no snake_case, no raw id, no exact copy of `report_id` or `framework_title`.
- `display.description` must be exactly 1 short sentence for normal users.
- `display.reason` must be 1-2 short sentences explaining why this report matches the uploaded file.
- Never use these words in user-facing text: business, dimension, measure, metric, schema, pipeline, backend, parse, detect, auto-generated, logic nghiep vu.
- Never expose `T1`, `T2`, raw table aliases, or raw technical column names in user-facing text.
- If you need to mention a data context, prefer `dataset_profile.tables[].display_name`.
- Keep tone stable and plain. Do not write marketing copy.
- Before printing JSON, self-check every report option against all rules above.
"""

INSTRUCTIONS_DASHBOARD_TABBED_V3_VI = f"""
BẠN LÀ MỘT CHUYÊN GIA TẠO DASHBOARD TỪ DỮ LIỆU THỰC.
Nhiệm vụ của bạn là sinh ra DUY NHẤT 1 JSON object hợp lệ cho dashboard schema `version = "3.1"`.

MỤC TIÊU
- Tạo dashboard tabbed v3.1 ổn định, dễ render, bám chặt dữ liệu thật.
- Chỉ tạo tab cho các `report_id` trong `SELECTION_JSON.selected_report_ids`.
- Mỗi `report_id` được chọn phải xuất hiện đúng 1 lần trong `tabs`.
- Không được thêm report ngoài selection.
- Không được gộp nhiều `report_id` vào cùng một tab.
- Không được trả về markdown, code fence, giải thích, hay bất kỳ văn bản nào ngoài JSON cuối cùng.

ĐẦU VÀO
- `MANIFEST_JSON`: mô tả cách cắt bảng từ file gốc.
- `REPORT_CATALOG_JSON`: catalog báo cáo chuẩn; đây là nguồn sự thật cho `tab_id`, `framework_title` và logic báo cáo.
- `SELECTION_JSON`: danh sách `selected_report_ids` và `params`.
- `PLAN_COMPACT_JSON`: gợi ý report phù hợp và focus table/column.
- `DATASET_PROFILE_COMPACT_JSON`: thông tin bảng, cột, `display_name`.

QUY TRÌNH BẮT BUỘC
1. Parse toàn bộ JSON đầu vào.
2. Dùng Python và `load_tables_from_manifest(manifest)` để đọc dữ liệu thật từ file đã upload.
3. Chuẩn hoá `selected_report_ids`: bỏ phần tử rỗng, bỏ trùng, giữ nguyên thứ tự đầu vào.
4. Tạo map từ `REPORT_CATALOG_JSON.reports` theo `report_id`.
5. Với mỗi `selected_report_id`:
   - Lấy `tab_id` đúng từ catalog.
   - Lấy `framework_title` đúng từ catalog.
   - Ưu tiên dùng `PLAN_COMPACT_JSON` và `DATASET_PROFILE_COMPACT_JSON` để chọn bảng/cột phù hợp.
   - Tính KPI, chart, bảng chi tiết từ dữ liệu thật.
6. Nếu dữ liệu yếu, thiếu, lệch cột, hoặc không đủ đẹp để vẽ nhiều chart:
   - Vẫn phải tạo tab hợp lệ.
   - Giảm số chart, tăng `summary_card`, `narrative_card`, `table`, `insight_block`.
   - Ghi rõ hạn chế trong `data_notes` và `debug_meta.assumptions`.
7. Trước khi in ra JSON cuối cùng, tự kiểm schema bằng Python và chỉ trả kết quả sau khi đã pass kiểm tra.

NGUYÊN TẮC ỔN ĐỊNH
- Ưu tiên output chắc chắn render được hơn output quá tham vọng.
- Ưu tiên layout đơn giản, widget ít nhưng đúng.
- Nếu không chắc chart nào phù hợp, ưu tiên `bar`, `line`, `table`, `summary_card`.
- Nếu đã có 1 chart `bar` làm chart chính, chart phụ nên ưu tiên loại khác như `donut`, `line`, `area`, `table`, `summary_card` khi dữ liệu cho phép; tránh để cả tab chỉ có một kiểu chart lặp lại.
- Không bịa số liệu, không bịa nhóm dữ liệu, không bịa `tables_used`, không bịa filter.
- Chỉ dùng `table_id` ở phần kỹ thuật (`debug_meta`); phần user-facing phải dùng `display_name`.
- Không dùng `T1`, `T2`, `T3` trong `title`, `summary`, `display.title`, `display.subtitle`, `display.highlights`, `display.explanation`, `display.hero_statement`, `display.footer_note`.
- `title` cho người dùng không được trùng nguyên văn với `framework_title`.
- Tất cả text user-facing phải bằng tiếng Việt, ngắn, rõ, ít thuật ngữ.
- Tránh các từ kỹ thuật nếu người dùng phổ thông có thể khó hiểu: KPI, metric, dimension, measure, schema, widget, anomaly, variance, contribution, segmentation, hierarchy, waterfall, sunburst, gauge, combo, fact table.
- Tránh cả các từ/cụm mang màu sắc nội bộ hoặc business như `nghiệp vụ`, `business`, `business view`, `business-facing`, `logic nghiệp vụ`; hãy đổi sang cách nói gần gũi như `công việc`, `trạng thái`, `cách dữ liệu đang vận hành`, `góc nhìn dễ hiểu`.
- Chỉ dùng tiếng Anh nếu dữ liệu gốc hoặc catalog buộc phải giữ nguyên.
- Không được để `NaN`, `Infinity`, `None`, `Timestamp`, hay object không JSON-serializable trong output cuối cùng.

VISUAL SHELL CONTRACT
- `display.shell_id` phải thuộc đúng một trong các giá trị sau:
  - `overview_premium`
  - `comparison_premium`
  - `trend_story`
  - `quality_review`
  - `ranking_board`
  - `ops_command`
  - `analysis_lab`
  - `detail_explorer`

MAPPING MẶC ĐỊNH CHO `shell_id`
- `exec_overview` -> `overview_premium`
- `breakdown_by_category` -> `comparison_premium`
- `data_quality` -> `quality_review`
- `trend_growth` -> `trend_story`
- `performance_ranking` -> `ranking_board`
- `operational_status` -> `ops_command`
- `correlation_distribution` -> `analysis_lab`
- `detailed_transactions` -> `detail_explorer`

MAPPING MẶC ĐỊNH CHO `form_type`
- `exec_overview` -> `overview_form`
- `breakdown_by_category` -> `comparison_form`
- `data_quality` -> `quality_form`
- `trend_growth` -> `trend_form`
- `performance_ranking` -> `comparison_form`
- `operational_status` -> `progress_form`
- `correlation_distribution` -> `comparison_form`
- `detailed_transactions` -> `detail_form`

WIDGET ID NÊN DÙNG
- `kpi_row`
- `hero_main`
- `hero_support_1`
- `hero_support_2`
- `compare_main`
- `compare_secondary`
- `detail_table`
- `detail_secondary`
- `insights`
- `filter_panel`
- `last_updated`

CHỈ DÙNG CÁC WIDGET TYPE SAU
- Non-chart:
  - `summary_card`
  - `stat_list`
  - `narrative_card`
  - `callout`
  - `badge_list`
  - `table`
  - `kpi_row`
  - `insight_block`
  - `filter_panel`
  - `last_updated`
  - `last_updated_card`
  - `last_updated_widget`
- Chart:
  - `line`
  - `area`
  - `stacked_area`
  - `bar`
  - `stacked_bar`
  - `combo_bar_line`
  - `combo`
  - `donut`
  - `pie`
  - `heatmap`
  - `funnel`
  - `scatter`
  - `bubble`
  - `histogram`
  - `box`
  - `violin`
  - `strip`
  - `radar`
  - `polar_bar`
  - `sankey`
  - `treemap`
  - `sunburst`
  - `waterfall`
  - `gauge`

ƯU TIÊN THEO TỪNG `report_id`
- `exec_overview`: 3-5 KPI, 1 chart tổng quan chính, 1-2 card/chart phụ, 1 insight block.
- `trend_growth`: ưu tiên `line`, `area`, `combo_bar_line`; số điểm vừa đủ để đọc.
- `breakdown_by_category`: ưu tiên `bar`, `stacked_bar`, `donut`; dùng top N rõ ràng.
- `performance_ranking`: ưu tiên bar ngang hoặc bảng xếp hạng.
- `operational_status`: ưu tiên `gauge`, `funnel`, `bar`, hoặc summary tiến độ.
- `data_quality`: ưu tiên `summary_card` + `bar`/`table` + `insight_block`.
- `correlation_distribution`: ưu tiên `scatter`, `histogram`, `box`, `violin`; nếu dữ liệu yếu thì quay về `bar`, `table`, `narrative_card`.
- `detailed_transactions`: `table` là trọng tâm; chart chỉ là phụ trợ.

QUY TẮC VỀ KÍCH THƯỚC OUTPUT
- Không tạo dashboard quá dài.
- Mỗi tab nên có:
  - 2-5 KPI nếu có đủ dữ liệu.
  - 1 chart chính.
  - 0-2 chart/card phụ.
  - 1 bảng chi tiết nếu phù hợp.
  - 1 `insight_block`.
- Với chart phân loại dài, ưu tiên top 8-12 nhóm; có thể gom phần còn lại thành `Khác` nếu hợp lý.
- Với chart theo thời gian, ưu tiên 6-24 điểm dễ đọc.
- Với table, ưu tiên khoảng 20-40 dòng đại diện; không cần đổ toàn bộ dữ liệu.
- Với text user-facing, ngắn gọn; tránh đoạn văn dài.

YÊU CẦU CHO `display`
Mỗi tab phải có `display` với đầy đủ các field sau:
- `shell_id`: bắt buộc, đúng contract.
- `form_type`: một trong `overview_form`, `comparison_form`, `trend_form`, `detail_form`, `quality_form`, `progress_form`.
- `density`: chỉ được là `compact`, `comfortable`, hoặc `dense`. Nếu không chắc, dùng `comfortable`.
- `title`: tên tab ngắn, thân thiện, không quá khoảng 8 từ, không trùng `framework_title`.
- `subtitle`: 1 câu ngắn mô tả ý nghĩa tab.
- `recommendation`: `recommended` hoặc `optional`.
- `badge_items`: 1-4 nhãn ngắn.
- `hero_statement`: 1 câu ngắn, dễ hiểu.
- `side_notes`: 0-4 ý ngắn.
- `quick_actions`: 0-3 gợi ý hành động tiếp theo.
- `highlights`: 2-3 ý ngắn.
- `metrics`: 2-5 item, mỗi item có `label`, `value`, `note`.
- `main_section`: có `title` và `description`.
- `explanation`: có đủ:
  - `what_is_happening`
  - `what_to_notice`
  - `what_to_do_next`
- `detail_section_title`: tên phần chi tiết.
- `footer_note`: 1 câu ngắn.

YÊU CẦU CHO `debug_meta`
Mỗi tab phải có `debug_meta` với:
- `report_id`
- `tab_id`
- `framework_title`
- `tables_used`: list object `{{"table_id": "...", "display_name": "..."}}`
- `columns_used`: object gồm `time_cols`, `measure_cols`, `category_cols`, `identifier_cols`
- `assumptions`: list string
- `data_notes`: object
- `filters_raw`: list
- `raw_summary`: string

YÊU CẦU CHO `kpis`
Mỗi KPI nên theo schema:
{{
  "id": "kpi_1",
  "label": "...",
  "value": 123,
  "unit": "",
  "delta": 0.12,
  "delta_label": "...",
  "format": "number|currency|percent|text"
}}
- Nếu không có delta hợp lệ, có thể dùng `delta = 0` và `delta_label = ""`.
- Nếu `widgets["kpi_row"]` tồn tại thì mọi `kpi_ids` trong đó phải tồn tại trong `kpis`.

YÊU CẦU CHO `layout`
- `layout` phải là list các row.
- Mỗi row là list object `{{"id": "...", "width": 1|2|3}}`.
- Mọi `id` xuất hiện trong `layout` phải tồn tại trong `widgets`.
- Nếu dữ liệu yếu, vẫn phải có layout hợp lệ, ví dụ:
  - `[[{{"id":"kpi_row","width":1}}],[{{"id":"hero_main","width":2}}],[{{"id":"detail_table","width":1}}],[{{"id":"insights","width":1}}]]`

YÊU CẦU CHO `widgets`
- Mỗi tab bắt buộc có đủ các key gốc:
  - `kpis`
  - `layout`
  - `widgets`
  - `data_notes`
- Nếu không có dữ liệu cho phần nào, dùng `[]` hoặc `{{}}`, không được bỏ key.
- Chỉ tạo `filter_panel` nếu có bộ lọc thật sự rõ ràng và ít lựa chọn; nếu không, để `filters = []` và không cần widget filter.
- Chỉ tạo chart khi có dữ liệu đủ rõ; nếu data trống hoặc quá yếu, thay bằng `summary_card`, `narrative_card`, `table`.

Các cấu trúc widget ổn định nên ưu tiên:

1. `kpi_row`
{{
  "type": "kpi_row",
  "kpi_ids": ["kpi_1", "kpi_2"]
}}

2. Chart widget
{{
  "type": "bar",
  "title": "...",
  "subtitle": "...",
  "data": [{{"label":"A","value":10}}],
  "encoding": {{"x":"label","y":"value"}}
}}

3. Table widget
{{
  "type": "table",
  "title": "...",
  "columns": ["Cột 1", "Cột 2"],
  "rows": [["A", 10], ["B", 20]]
}}

4. Insight block
{{
  "type": "insight_block",
  "key_findings": ["..."],
  "risks": ["..."],
  "recommendations": ["..."]
}}

5. Summary card
{{
  "type": "summary_card",
  "title": "...",
  "value": "...",
  "note": "...",
  "tone": "neutral|good|warn|accent"
}}

6. Stat list
{{
  "type": "stat_list",
  "title": "...",
  "items": [{{"label":"...","value":"...","note":"..."}}]
}}

7. Narrative / callout
{{
  "type": "narrative_card",
  "title": "...",
  "body": "...",
  "tone": "neutral|good|warn|accent"
}}

YÊU CẦU CHO `data_notes`
Mỗi tab phải có `data_notes` dạng object, tối thiểu gồm:
{{
  "row_counts": {{}},
  "missingness_summary": [],
  "assumptions": []
}}

YÊU CẦU CHO `meta`
`meta` phải có:
- `title`
- `subtitle`
- `time_range`
- `last_updated`
- `tables_used`

Trong đó `tables_used` là list object `{{"table_id": "...", "display_name": "..."}}`.

SCHEMA TỐI THIỂU BẮT BUỘC
{{
  "version": "3.1",
  "meta": {{
    "title": "...",
    "subtitle": "...",
    "time_range": "...",
    "last_updated": "...",
    "tables_used": [
      {{"table_id": "T1", "display_name": "..."}}
    ]
  }},
  "tabs": [
    {{
      "report_id": "...",
      "tab_id": "...",
      "framework_title": "...",
      "title": "...",
      "summary": "...",
      "display": {{
        "shell_id": "...",
        "form_type": "...",
        "density": "comfortable",
        "title": "...",
        "subtitle": "...",
        "recommendation": "recommended",
        "badge_items": [],
        "hero_statement": "...",
        "side_notes": [],
        "quick_actions": [],
        "highlights": [],
        "metrics": [],
        "main_section": {{"title":"...","description":"..."}},
        "explanation": {{
          "what_is_happening": "...",
          "what_to_notice": "...",
          "what_to_do_next": "..."
        }},
        "detail_section_title": "...",
        "footer_note": "..."
      }},
      "debug_meta": {{
        "report_id": "...",
        "tab_id": "...",
        "framework_title": "...",
        "tables_used": [],
        "columns_used": {{
          "time_cols": [],
          "measure_cols": [],
          "category_cols": [],
          "identifier_cols": []
        }},
        "assumptions": [],
        "data_notes": {{}},
        "filters_raw": [],
        "raw_summary": "..."
      }},
      "filters": [],
      "kpis": [],
      "layout": [],
      "widgets": {{}},
      "data_notes": {{
        "row_counts": {{}},
        "missingness_summary": [],
        "assumptions": []
      }}
    }}
  ]
}}

TỰ KIỂM BẰNG PYTHON TRƯỚC KHI IN JSON
- Parse object cuối cùng bằng `json.loads`.
- Assert `version == "3.1"`.
- Assert số tab bằng số `selected_report_ids` sau chuẩn hoá.
- Assert tập `report_id` trong `tabs` khớp 100% với selection và không trùng.
- Assert mỗi tab có `report_id`, `tab_id`, `framework_title`, `title`, `kpis`, `layout`, `widgets`, `data_notes`.
- Assert `tab_id` và `framework_title` khớp catalog của `report_id`.
- Assert `title.strip().lower() != framework_title.strip().lower()`.
- Assert mọi `layout[*][*].id` đều tồn tại trong `widgets`.
- Assert nếu có `widgets["kpi_row"]` thì mọi `kpi_ids` đều tồn tại trong `kpis`.
- Assert không có `NaN`, `Infinity`, `None`, object datetime/pandas, hay bất kỳ kiểu dữ liệu không JSON-safe nào.
- Assert toàn bộ output chỉ là 1 JSON object.

KHI DỮ LIỆU KHÔNG ĐỦ ĐẸP
- Vẫn phải trả về tab hợp lệ.
- Có thể giảm chart xuống còn 1 chart chính hoặc chỉ dùng `summary_card` + `table` + `insight_block`.
- Phải nói rõ hạn chế bằng tiếng Việt dễ hiểu.
- Không được bỏ tab, không được trả về object nửa chừng.

CHỈ IN RA JSON CUỐI CÙNG.

{_PY_HELPERS_CORE}
{_PY_HELPERS_PROFILE}
"""

DASHBOARD_TABBED_V3_HARD_RULES = """
OVERRIDE QUALITY CONTRACT FOR DEMO STABILITY
- These rules override any softer instruction above.
- Every tab must contain at least 3 chart widgets.
- For demo stability, only these widget types count toward the minimum chart count:
  - `bar`
  - `line`
  - `area`
  - `stacked_bar`
  - `stacked_area`
  - `donut`
- The following do NOT count as charts:
  - `table`
  - `summary_card`
  - `stat_list`
  - `narrative_card`
  - `callout`
  - `badge_list`
  - `insight_block`
  - `kpi_row`
  - `filter_panel`
  - `last_updated`
  - `last_updated_card`
  - `last_updated_widget`
- Never reduce below 3 charts, even when data is weak.
- If data is weak, still create 3 simple charts from real data:
  1. count by strongest category or status
  2. top N items by count or numeric total
  3. time trend if a time column exists, otherwise another grouped bar, stacked_bar, area, or donut
- If no reliable measure exists, you may use row count as the value.
- Each tab must include:
  - a KPI area
  - 1 main chart
  - 2 supporting charts
  - 1 `insight_block`
  - 1 detail table or 1 detail support block
- Layout must place at least 1 chart in the first 2 layout rows.
- Keep `display.shell_id` aligned with the default shell mapping for each `report_id`.
- Report skeletons to prefer:
  - `exec_overview`: main overview chart + support breakdown chart + support comparison chart
  - `breakdown_by_category`: main category bar + support donut/bar + support ranking bar
  - `data_quality`: issue overview bar + top missing columns bar + issue split donut/bar + detail table
  - `trend_growth`: main line + support bar + support area/bar
  - `performance_ranking`: main ranking bar + secondary ranking bar + support donut/bar
  - `operational_status`: main status bar/stacked_bar + support donut/bar + support ranking/status bar
  - `correlation_distribution`: use simple stable charts for demo, prefer bar/line/area over exotic charts
  - `detailed_transactions`: keep table, but still include 3 simple charts
- All user-facing display text must stay in friendly Vietnamese.
- Before printing JSON, self-check chart count, layout references, shell_id mapping, insight block presence, and detail section presence.
"""

REPORT_PLAN_REPAIR_INSTRUCTIONS = """
You are repairing an existing report plan JSON.

Goal:
- Fix only user-facing display quality.

Hard constraints:
- Keep these fields unchanged unless missing:
  - `version`
  - `dataset_profile`
  - `catalog_evaluation`
  - `recommended_default`
  - `report_options[].report_id`
  - `report_options[].debug_meta.tab_id`
  - `report_options[].debug_meta.inputs`
  - technical reasons/evidence
- Only rewrite user-facing text fields:
  - `report_options[].display.title`
  - `report_options[].display.description`
  - `report_options[].display.reason`
  - `report_options[].display.recommendation` if invalid
  - `report_options[].debug_meta.reason_user_safe`
  - legacy mirror fields `title`, `description`, `reason` if present
- Keep all user-facing text in Vietnamese.
- Never expose raw ids, `T1/T2`, raw technical columns, or technical jargon.
- `title` must be 3-8 words and user-friendly.
- `description` must be 1 short sentence.
- `reason` must be 1-2 short sentences and specific to the file.
- Return the full repaired JSON object only.
"""

DASHBOARD_TABBED_V3_REPAIR_INSTRUCTIONS = """
You are repairing an existing dashboard spec JSON for demo stability.

Goal:
- Keep the same report coverage.
- Fix layout/widgets/display quality so the spec is stable for rendering.

Hard constraints:
- Keep these fields unchanged unless missing:
  - `version`
  - `meta.tables_used`
  - every tab `report_id`
  - every tab `tab_id`
  - every tab `framework_title`
- You may adjust:
  - `title`
  - `summary`
  - `display`
  - `kpis`
  - `layout`
  - `widgets`
  - `data_notes`
  - `debug_meta`
- Every tab must have at least 3 chart widgets from this allowed set only:
  - `bar`
  - `line`
  - `area`
  - `stacked_bar`
  - `stacked_area`
  - `donut`
- `table`, `summary_card`, `stat_list`, `narrative_card`, `callout`, `badge_list`, `insight_block`, `kpi_row`, `filter_panel`, `last_updated` do not count toward the minimum.
- Every tab must include:
  - KPI area
  - 1 main chart
  - 2 supporting charts
  - 1 `insight_block`
  - 1 detail table or detail support block
- Layout must reference the chart widgets and put at least 1 chart in the first 2 layout rows.
- Keep user-facing text in friendly Vietnamese.
- Return the full repaired JSON object only.
"""

INSTRUCTIONS_BA_DETECTION = f"""
Bạn là AI chuyên nhận diện file BA (Business Analysis) từ file Excel/CSV đã upload.

MỤC TIÊU
- Đọc dữ liệu thật từ file gốc theo MANIFEST_JSON.
- Xác định file có phải BA hay không.
- Xác định bảng nào có khả năng là:
  - scope_items
  - assumptions
  - commercial_drivers
- Trả về DUY NHẤT 1 JSON object hợp lệ.

BẮT BUỘC
- Phải dùng Python.
- Phải parse MANIFEST_JSON thành manifest.
- Phải gọi:
  ctx = build_dataset_profile_from_manifest(manifest)
  dataset_profile = ctx["dataset_profile"]

TIÊU CHÍ NHẬN DIỆN BA
- TRỌNG TÂM: Chỉ nhận là BA (is_ba = true) nếu file chứa yêu cầu phần mềm, tính năng, hoặc danh mục báo giá dự án.
- Ưu tiên các bảng chứa nhiều text mô tả nghiệp vụ hơn là số liệu đo lường.
- Các cột thường có chữ: module, feature, function, requirement, description, remark, qty, complexity, priority.
- Nếu file chứa chủ yếu dữ liệu lịch sử giao dịch, doanh số, kho, nhân sự, điểm số, log lỗi (có các cột ngày tháng, số lượng bán, doanh thu, v.v.), thì ĐÓ KHÔNG PHẢI LÀ FILE BA (is_ba = false).
- CỰC KỲ KHẮT KHE: Nếu là bảng fact giao dịch thuần (chứa measure-time-dimension), bắt buộc document_type = "non_ba" và is_ba = false.

JSON OUTPUT:
{{
  "document_type": "ba_excel|non_ba|unknown",
  "confidence": 0.0,
  "is_ba": false,
  "sheet_candidates": [
    {{
      "sheet_name": "",
      "score": 0.0,
      "scope_table_ids": [],
      "assumption_table_ids": [],
      "driver_table_ids": []
    }}
  ],
  "reasons": [],
  "needs_user_confirmation": true
}}

{_PY_HELPERS_CORE}
{_PY_HELPERS_PROFILE}
"""

INSTRUCTIONS_BA_ANALYSIS = f"""
Bạn là AI chuyên phân tích BA để tạo dữ liệu trung gian cho báo giá.

MỤC TIÊU
- Đọc dữ liệu thật từ file gốc theo MANIFEST_JSON.
- Tạo DUY NHẤT 1 JSON object hợp lệ mô tả:
  - document_summary
  - scope_items
  - commercial_drivers
  - assumptions
  - exclusions
  - unmapped_or_ambiguous_items

BẮT BUỘC
- Phải dùng Python.
- Phải parse MANIFEST_JSON thành manifest.
- Phải đọc dữ liệu thật bằng load_tables_from_manifest(manifest).
- Không được tự bịa quantity, unit, complexity nếu không có căn cứ.
- Mọi scope item phải giữ source_table_id và source_row_numbers.
- KHÔNG ĐƯỢC RÚT GỌN KẾT QUẢ. Bắt buộc trả về TOÀN BỘ array scope_items đầy đủ.
- CHỈ TRẢ VỀ CHUỖI JSON HỢP LỆ, KHÔNG THÊM BẤT KỲ VĂN BẢN NÀO KHÁC (Không giải thích, không viết "Dưới đây là...").

JSON OUTPUT:
{{
  "version": "1.0",
  "document_summary": {{
    "document_type": "ba_excel",
    "project_name": "",
    "customer_name": "",
    "domain": "",
    "solution_type": "",
    "source_file": "",
    "sheet_name": ""
  }},
  "scope_items": [
    {{
      "item_id": "BA-001",
      "source_table_id": "T1",
      "source_row_numbers": [12],
      "module_name": "",
      "feature_name": "",
      "requirement_name": "",
      "description": "",
      "quantity": null,
      "unit": "",
      "complexity": "low|medium|high|unknown",
      "priority": "low|medium|high|unknown",
      "remarks": "",
      "normalized_tags": [],
      "candidate_price_codes": [],
      "mapping_confidence": 0.0
    }}
  ],
  "commercial_drivers": {{
    "users": null,
    "branches": null,
    "sites": null,
    "warehouses": null,
    "stores": null,
    "integrations": null,
    "environments": null
  }},
  "assumptions": [],
  "exclusions": [],
  "data_quality_flags": [],
  "unmapped_or_ambiguous_items": []
}}

{_PY_HELPERS_CORE}
{_PY_HELPERS_PROFILE}
"""

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY")

        base_url = (os.getenv("OPENAI_BASE_URL") or "").strip() or None
        _client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    return _client


def upload_file_for_ci(filename: str, content: bytes) -> str:
    client = get_client()
    f = client.files.create(file=(filename, content), purpose="assistants")
    return f.id


def _obj_get(obj, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _collect_text_candidates(obj) -> List[str]:
    parts: List[str] = []

    if isinstance(obj, str) and obj.strip():
        parts.append(obj.strip())
        return parts

    text_value = _obj_get(obj, "text")
    if isinstance(text_value, str) and text_value.strip():
        parts.append(text_value.strip())
    else:
        nested_value = _obj_get(text_value, "value")
        if isinstance(nested_value, str) and nested_value.strip():
            parts.append(nested_value.strip())

    direct_value = _obj_get(obj, "value")
    if isinstance(direct_value, str) and direct_value.strip():
        parts.append(direct_value.strip())

    logs_value = _obj_get(obj, "logs")
    if isinstance(logs_value, str) and logs_value.strip():
        parts.append(logs_value.strip())

    refusal_value = _obj_get(obj, "refusal")
    if isinstance(refusal_value, str) and refusal_value.strip():
        parts.append(refusal_value.strip())

    return parts


def _model_dump_if_possible(obj):
    if obj is None:
        return None
    model_dump = getattr(obj, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump(mode="python")
        except TypeError:
            try:
                return model_dump()
            except Exception:
                return obj
        except Exception:
            return obj
    return obj


def _collect_text_candidates_deep(obj, depth: int = 0, seen_ids: Optional[set[int]] = None) -> List[str]:
    if obj is None or depth > 5:
        return []

    if seen_ids is None:
        seen_ids = set()

    obj = _model_dump_if_possible(obj)
    obj_id = id(obj)
    if obj_id in seen_ids:
        return []
    seen_ids.add(obj_id)

    parts: List[str] = []
    direct_parts = _collect_text_candidates(obj)
    if direct_parts:
        parts.extend(direct_parts)

    if isinstance(obj, str):
        return parts

    if isinstance(obj, list):
        for item in obj:
            parts.extend(_collect_text_candidates_deep(item, depth + 1, seen_ids))
        return parts

    if isinstance(obj, tuple):
        for item in obj:
            parts.extend(_collect_text_candidates_deep(item, depth + 1, seen_ids))
        return parts

    if isinstance(obj, dict):
        preferred_keys = (
            "output_text",
            "text",
            "value",
            "refusal",
            "logs",
            "content",
            "outputs",
            "summary",
            "result",
            "stdout",
            "stderr",
        )
        for key in preferred_keys:
            if key in obj:
                parts.extend(_collect_text_candidates_deep(obj.get(key), depth + 1, seen_ids))

        for key, value in obj.items():
            if key in preferred_keys:
                continue
            if isinstance(value, (dict, list, tuple)):
                parts.extend(_collect_text_candidates_deep(value, depth + 1, seen_ids))
        return parts

    raw_dict = getattr(obj, "__dict__", None)
    if isinstance(raw_dict, dict) and raw_dict:
        parts.extend(_collect_text_candidates_deep(raw_dict, depth + 1, seen_ids))

    return parts


def _summarize_response_for_debug(resp) -> str:
    status = _obj_get(resp, "status", "unknown")
    error = _obj_get(resp, "error")
    incomplete = _obj_get(resp, "incomplete_details")
    output = _obj_get(resp, "output", []) or []

    item_types: List[str] = []
    for item in output:
        item_type = _obj_get(item, "type", type(item).__name__)
        item_status = _obj_get(item, "status")
        if item_status:
            item_types.append(f"{item_type}:{item_status}")
        else:
            item_types.append(str(item_type))

    debug_bits = [f"status={status}"]
    if item_types:
        debug_bits.append(f"output={item_types}")
    if error:
        debug_bits.append(f"error={error}")
    if incomplete:
        debug_bits.append(f"incomplete={incomplete}")

    return "; ".join(debug_bits)


def _get_incomplete_reason(resp) -> str:
    incomplete = _obj_get(resp, "incomplete_details")
    reason = _obj_get(incomplete, "reason")
    return str(reason or "").strip()


def _get_response_status(resp) -> str:
    return str(_obj_get(resp, "status", "") or "").strip()


def _poll_response_until_terminal(client: OpenAI, response_id: str):
    timeout_seconds = _env_int("OPENAI_CI_POLL_TIMEOUT_SECONDS", 180, 10, 1800)
    poll_interval_ms = _env_int("OPENAI_CI_POLL_INTERVAL_MS", 1000, 200, 10000)
    deadline = time.monotonic() + timeout_seconds

    resp = client.responses.retrieve(response_id)
    while _get_response_status(resp) in {"queued", "in_progress"}:
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "OpenAI response polling timed out: "
                f"{_summarize_response_for_debug(resp)}"
            )
        time.sleep(poll_interval_ms / 1000.0)
        resp = client.responses.retrieve(response_id)

    return resp


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except Exception:
        value = default
    return max(minimum, min(value, maximum))


def _score_text_candidate(text: str) -> int:
    s = (text or "").strip()
    if not s:
        return -1

    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return 100
    except Exception:
        pass

    i = s.find("{")
    j = s.rfind("}")
    if i != -1 and j != -1 and j > i:
        sub = s[i : j + 1]
        try:
            obj = json.loads(sub)
            if isinstance(obj, dict):
                return 90
        except Exception:
            pass
        return 20

    return 0


def _pick_best_text_candidate(candidates: List[str]) -> str:
    best_text = ""
    best_score = -1

    seen = set()
    for raw in candidates:
        text = (raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)

        score = _score_text_candidate(text)
        if score > best_score or (score == best_score and len(text) > len(best_text)):
            best_text = text
            best_score = score

    return best_text


def _dedupe_nonempty_strings(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in values:
        text = (raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _extract_text_from_response(resp) -> str:
    candidates: List[str] = []
    message_parts: List[str] = []
    tool_parts: List[str] = []
    out = _obj_get(resp, "output", []) or []

    txt = getattr(resp, "output_text", None)
    if isinstance(txt, str) and txt.strip():
        candidates.append(txt.strip())
    elif txt is not None:
        candidates.extend(_collect_text_candidates_deep(txt))

    for item in out:
        item_type = _obj_get(item, "type")

        # Case A: item.content là list
        content = _obj_get(item, "content")
        if content:
            for c in content:
                content_texts = _collect_text_candidates(c)
                if not content_texts:
                    content_texts = _collect_text_candidates_deep(c)
                message_parts.extend(content_texts)
                candidates.extend(content_texts)

        # Case B: tool outputs/logs, nhất là code_interpreter_call.outputs[].logs
        outputs = _obj_get(item, "outputs")
        if outputs:
            for out_item in outputs:
                output_texts = _collect_text_candidates(out_item)
                if not output_texts:
                    output_texts = _collect_text_candidates_deep(out_item)
                tool_parts.extend(output_texts)
                candidates.extend(output_texts)

        # Case C: fallback trực tiếp trên item
        direct_texts = _collect_text_candidates(item)
        if not direct_texts:
            direct_texts = _collect_text_candidates_deep(item)
        if direct_texts:
            if item_type == "message":
                message_parts.extend(direct_texts)
            else:
                tool_parts.extend(direct_texts)
            candidates.extend(direct_texts)

    if not candidates and out:
        candidates.extend(_collect_text_candidates_deep(out))

    message_parts = _dedupe_nonempty_strings(message_parts)
    tool_parts = _dedupe_nonempty_strings(tool_parts)
    if message_parts:
        candidates.append("\n".join(message_parts).strip())
    if tool_parts:
        candidates.append("\n".join(tool_parts).strip())

    candidates = _dedupe_nonempty_strings(candidates)
    best_text = _pick_best_text_candidate(candidates)
    if best_text:
        return best_text

    if message_parts:
        return "\n".join(message_parts).strip()
    if tool_parts:
        return "\n".join(tool_parts).strip()

    return ""

def _ask_ci(
    *,
    file_id: str,
    content: str,
    model: str,
    previous_response_id: Optional[str],
    max_output_tokens: int,
) -> Tuple[str, str]:
    client = get_client()

    retries = _env_int("OPENAI_CI_MAX_OUTPUT_RETRIES", 2, 0, 5)
    retry_cap = _env_int("OPENAI_CI_MAX_OUTPUT_TOKENS_CAP", 16000, 1000, 64000)
    budget = int(max_output_tokens)

    def _is_gpt5_reasoning_model(name: str) -> bool:
        s = (name or "").strip().lower()
        return s.startswith("gpt-5")

    last_err = None

    for _attempt in range(retries + 1):
        try:
            request_kwargs = {
                "model": model,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": content},
                            {"type": "input_file", "file_id": file_id},
                        ],
                    }
                ],
                "tools": [
                    {
                        "type": "code_interpreter",
                        "container": {"type": "auto"},
                    }
                ],
                "tool_choice": "required",
                "previous_response_id": previous_response_id,
                "max_output_tokens": budget,
            }

            if _is_gpt5_reasoning_model(model):
                request_kwargs["reasoning"] = {"effort": "low"}
            else:
                request_kwargs["temperature"] = 0
                request_kwargs["top_p"] = 1

            resp = client.responses.create(**request_kwargs)
            response_id = getattr(resp, "id", None)

            if response_id and _get_response_status(resp) in {"queued", "in_progress"}:
                resp = _poll_response_until_terminal(client, response_id)

            text = _extract_text_from_response(resp)
            status = _get_response_status(resp)
            incomplete_reason = _get_incomplete_reason(resp)

            if status == "incomplete" and incomplete_reason == "max_output_tokens":
                if _attempt < retries:
                    budget = min(retry_cap, max(budget * 2, budget + 2000))
                    continue

            if status in {"failed", "cancelled"}:
                raise RuntimeError(
                    "OpenAI response failed before producing usable text: "
                    f"{_summarize_response_for_debug(resp)}"
                )

            if not text:
                raise RuntimeError(
                    "OpenAI response produced no usable text: "
                    f"{_summarize_response_for_debug(resp)}"
                )

            return text, response_id

        except Exception as e:
            last_err = e
            raise

    if last_err:
        raise last_err
    raise RuntimeError("_ask_ci failed without explicit exception")


def _format_recent_turns(recent_turns: Optional[List[Dict[str, Any]]]) -> str:
    turns = recent_turns or []
    lines: List[str] = []
    for i, t in enumerate(turns, 1):
        q = str((t or {}).get("question", "")).strip()
        a = str((t or {}).get("answer", "")).strip()
        if q:
            lines.append(f"Q{i}: {q}")
        if a:
            lines.append(f"A{i}: {a}")
    return "\n".join(lines).strip()


def ask_ci_qa(
    file_id: str,
    question: str,
    model: str,
    previous_response_id: Optional[str],
    manifest_json: str,
    memory_summary: Optional[str] = None,
    recent_turns: Optional[List[Dict[str, Any]]] = None,
    dataset_profile_compact: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    recent_turns_text = _format_recent_turns(recent_turns)

    dataset_profile_text = json.dumps(dataset_profile_compact or {}, ensure_ascii=False)

    content = (
        f"{INSTRUCTIONS_QA}\n\n"
        f"MANIFEST_JSON:\n{manifest_json}\n\n"
        f"DATASET_PROFILE_COMPACT_JSON:\n{dataset_profile_text}\n\n"
        f"QA_MEMORY_SUMMARY:\n{memory_summary or ''}\n\n"
        f"RECENT_QA_TURNS:\n{recent_turns_text}\n\n"
        f"User question: {question}"
    )

    return _ask_ci(
        file_id=file_id,
        content=content,
        model=model,
        previous_response_id=previous_response_id,
        max_output_tokens=1200,
    )


def ask_ci_report_plan(
    file_id: str,
    model: str,
    previous_response_id: Optional[str],
    manifest_json: str,
    report_catalog_json: str,
) -> Tuple[str, str]:
    report_plan_max_tokens = _env_int("REPORT_PLAN_CI_MAX_OUTPUT_TOKENS", 6000, 1000, 32000)

    content = (
        f"{INSTRUCTIONS_REPORT_PLAN}\n\n"
        f"{REPORT_PLAN_PROMPT_HARD_RULES}\n\n"
        f"MANIFEST_JSON:\n{manifest_json}\n\n"
        f"REPORT_CATALOG_JSON:\n{report_catalog_json}\n"
    )

    return _ask_ci(
        file_id=file_id,
        content=content,
        model=model,
        previous_response_id=previous_response_id,
        max_output_tokens=report_plan_max_tokens,
    )


def ask_ci_report_plan_repair(
    file_id: str,
    model: str,
    previous_response_id: Optional[str],
    manifest_json: str,
    report_catalog_json: str,
    current_plan_json: str,
    quality_issues_json: str,
) -> Tuple[str, str]:
    report_plan_max_tokens = _env_int("REPORT_PLAN_CI_MAX_OUTPUT_TOKENS", 6000, 1000, 32000)

    content = (
        f"{REPORT_PLAN_REPAIR_INSTRUCTIONS}\n\n"
        f"{REPORT_PLAN_PROMPT_HARD_RULES}\n\n"
        f"MANIFEST_JSON:\n{manifest_json}\n\n"
        f"REPORT_CATALOG_JSON:\n{report_catalog_json}\n\n"
        f"QUALITY_ISSUES_JSON:\n{quality_issues_json}\n\n"
        f"CURRENT_PLAN_JSON:\n{current_plan_json}\n"
    )

    return _ask_ci(
        file_id=file_id,
        content=content,
        model=model,
        previous_response_id=previous_response_id,
        max_output_tokens=report_plan_max_tokens,
    )


def ask_ci_dashboard_spec_tabbed_v3_from_selection(
    file_id: str,
    model: str,
    previous_response_id: Optional[str],
    manifest_json: str,
    report_catalog_json: str,
    selection_json: str,
    plan_compact_json: str,
    dataset_profile_compact_json: str,
) -> Tuple[str, str]:
    dashboard_max_tokens = _env_int("DASHBOARD_CI_MAX_OUTPUT_TOKENS", 9000, 1000, 32000)

    content = (
        f"{INSTRUCTIONS_DASHBOARD_TABBED_V3_VI}\n\n"
        f"{DASHBOARD_TABBED_V3_HARD_RULES}\n\n"
        f"MANIFEST_JSON:\n{manifest_json}\n\n"
        f"REPORT_CATALOG_JSON:\n{report_catalog_json}\n\n"
        f"SELECTION_JSON:\n{selection_json}\n\n"
        f"PLAN_COMPACT_JSON:\n{plan_compact_json}\n\n"
        f"DATASET_PROFILE_COMPACT_JSON:\n{dataset_profile_compact_json}"
    )

    return _ask_ci(
        file_id=file_id,
        content=content,
        model=model,
        previous_response_id=previous_response_id,
        max_output_tokens=dashboard_max_tokens,
    )


def ask_ci_dashboard_spec_tabbed_v3_repair(
    file_id: str,
    model: str,
    previous_response_id: Optional[str],
    manifest_json: str,
    report_catalog_json: str,
    selection_json: str,
    plan_compact_json: str,
    dataset_profile_compact_json: str,
    current_spec_json: str,
    quality_issues_json: str,
) -> Tuple[str, str]:
    dashboard_max_tokens = _env_int("DASHBOARD_CI_MAX_OUTPUT_TOKENS", 9000, 1000, 32000)

    content = (
        f"{DASHBOARD_TABBED_V3_REPAIR_INSTRUCTIONS}\n\n"
        f"{DASHBOARD_TABBED_V3_HARD_RULES}\n\n"
        f"MANIFEST_JSON:\n{manifest_json}\n\n"
        f"REPORT_CATALOG_JSON:\n{report_catalog_json}\n\n"
        f"SELECTION_JSON:\n{selection_json}\n\n"
        f"PLAN_COMPACT_JSON:\n{plan_compact_json}\n\n"
        f"DATASET_PROFILE_COMPACT_JSON:\n{dataset_profile_compact_json}\n\n"
        f"QUALITY_ISSUES_JSON:\n{quality_issues_json}\n\n"
        f"CURRENT_SPEC_JSON:\n{current_spec_json}\n"
    )

    return _ask_ci(
        file_id=file_id,
        content=content,
        model=model,
        previous_response_id=previous_response_id,
        max_output_tokens=dashboard_max_tokens,
    )

def ask_ci_ba_detection(
    file_id: str,
    model: str,
    previous_response_id: Optional[str],
    manifest_json: str,
) -> Tuple[str, str]:
    max_tokens = _env_int("BA_DETECTION_CI_MAX_OUTPUT_TOKENS", 1800, 500, 8000)
    content = (
        f"{INSTRUCTIONS_BA_DETECTION}\n\n"
        f"MANIFEST_JSON:\n{manifest_json}\n"
    )
    return _ask_ci(
        file_id=file_id,
        content=content,
        model=model,
        previous_response_id=previous_response_id,
        max_output_tokens=max_tokens,
    )


def ask_ci_ba_analysis(
    file_id: str,
    model: str,
    previous_response_id: Optional[str],
    manifest_json: str,
    ba_detection_json: str,
) -> Tuple[str, str]:
    max_tokens = _env_int("BA_ANALYSIS_CI_MAX_OUTPUT_TOKENS", 3500, 1000, 10000)
    style_guide = """
HUONG DAN NGON NGU CHO CAC TRUONG VAN BAN:
- Tat ca noi dung text nguoi dung co the doc duoc phai uu tien viet bang tieng Viet ro rang, de hieu.
- Viet theo goc nhin business hoac nguoi dung cuoi, tranh van phong qua ky thuat hoac qua noi bo CNTT.
- Cac truong module_name, feature_name, requirement_name, description, remarks, assumptions[].text, exclusions[].text va noi dung trong data_quality_flags/unmapped_or_ambiguous_items neu co text phai ngan gon, tu nhien.
- Neu tai lieu goc dung nhieu tu tieng Anh hoac thuat ngu, hay dien dat lai sang tieng Viet don gian nhung van giu dung y nghia.
- Tranh dung cac cum tu noi bo ky thuat nhu mapping, pipeline, schema, parse, detect, backend, normalize trong cac truong van ban hien cho nguoi dung.
- Neu co the, mo ta theo cach "nguoi dung can gi" hoac "he thong can ho tro gi" thay vi mo ta theo ngon ngu chuyen mon.
"""
    content = (
        f"{INSTRUCTIONS_BA_ANALYSIS}\n\n"
        f"{style_guide}\n\n"
        f"MANIFEST_JSON:\n{manifest_json}\n\n"
        f"BA_DETECTION_JSON:\n{ba_detection_json}\n"
    )
    return _ask_ci(
        file_id=file_id,
        content=content,
        model=model,
        previous_response_id=previous_response_id,
        max_output_tokens=max_tokens,
    )

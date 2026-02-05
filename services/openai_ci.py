# services/openai_ci.py
import os
from typing import Optional, Tuple
from openai import OpenAI

# =========================
# PROMPTS (NEW: use original file + MANIFEST_JSON)
# =========================

_PY_HELPERS = r"""
# ===== CI Helper: load tables from original file using MANIFEST_JSON =====
import os, json
import pandas as pd

def _list_data_files():
    files = []
    for fn in os.listdir("/mnt/data"):
        lower = fn.lower()
        if lower.endswith((".xlsx", ".xls", ".csv")):
            files.append(fn)
    return sorted(files)

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

def load_tables_from_manifest(manifest: dict):
    files = _list_data_files()
    if not files:
        raise RuntimeError("Không tìm thấy file .xlsx/.xls/.csv trong /mnt/data")

    # assume only 1 uploaded data file (as designed)
    data_file = files[0]
    data_path = os.path.join("/mnt/data", data_file)

    sheet_name = manifest.get("sheet_name")
    tables = manifest.get("tables") or []
    if not isinstance(tables, list) or len(tables) == 0:
        raise RuntimeError("MANIFEST_JSON không có tables")

    ext = data_file.lower().split(".")[-1]
    is_csv = (ext == "csv")

    # load whole sheet as raw (header=None) for slicing
    if is_csv:
        raw = pd.read_csv(data_path, header=None)
    else:
        raw = pd.read_excel(data_path, sheet_name=sheet_name if sheet_name else 0, header=None)

    out = {}
    for t in tables:
        tid = t.get("table_id") or ""
        hr = int(t.get("header_row_0based"))
        sr = int(t.get("start_row_0based"))
        er = int(t.get("end_row_0based"))

        if hr < 0 or sr < 0 or er < 0 or er < sr:
            raise RuntimeError(f"Table {tid}: index không hợp lệ")

        # header row
        header = list(raw.iloc[hr, :].tolist())
        header = ["" if x is None else str(x).strip() for x in header]
        header = _dedupe_columns(header)

        # data rows (inclusive)
        block = raw.iloc[sr:er+1, :].copy()
        block.columns = header

        # drop entirely empty columns by header name OR all-NaN
        # - also drop columns whose header is empty string
        keep_cols = []
        for c in block.columns:
            if str(c).strip() == "":
                continue
            if block[c].isna().all():
                continue
            keep_cols.append(c)
        block = block[keep_cols].copy()

        # add __src_row__ in memory (1-based row in original file)
        # row_offset: 0..len(block)-1
        block.insert(0, "__src_row__", [sr + 1 + i for i in range(len(block))])

        out[tid] = block

    return data_file, sheet_name, out

# ===== end helpers =====
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
- Nêu rõ bạn đang dựa trên bảng nào (T1/T2/...) và cột nào.
- Không bịa thông tin hoặc suy luận vượt quá dữ liệu.

{_PY_HELPERS}
"""


# =========================
# FINAL_SPEC: JSON report spec for dashboard renderer
# =========================
INSTRUCTIONS_FINAL_SPEC = f"""
Bạn là một AI Agent phân tích dữ liệu và xuất ra **REPORT SPEC** dưới dạng JSON để hệ thống render thành dashboard.

========================
NGỮ CẢNH & DỮ LIỆU
========================
- File trong /mnt/data là FILE GỐC, giữ nguyên cấu trúc.
- Cấu trúc bảng hợp lệ DUY NHẤT được mô tả trong MANIFEST_JSON.
- Chỉ phân tích các bảng trong manifest.

========================
MỤC TIÊU ĐẦU RA
========================
Bạn phải trả về DUY NHẤT một JSON hợp lệ (không kèm markdown, không kèm giải thích).
JSON này sẽ được UI render theo các "slots" cố định:
- header
- kpi_row
- tabs: performance, segment, channel, type, risk
- appendix

========================
YÊU CẦU BẮT BUỘC
========================
- Ngôn ngữ: tiếng Việt (các title/label/insight).
- Chỉ dùng Python (Code Interpreter) để đọc và tính toán.
- Không in dataframe/bảng thô.
- Không bịa dữ liệu.
- Mọi số liệu trong JSON phải xuất phát từ dữ liệu sau khi cắt theo manifest.

========================
SCHEMA JSON (BẮT BUỘC)
========================
{{
  "meta": {{
    "title": str,
    "time_range": str|None,
    "tables": [{{"table_id": str, "rows": int, "cols": int, "guess": str}}],
    "data_quality_note": str
  }},
  "executive_summary": {{
    "key_findings": [str],
    "risks": [str],
    "actions": [str]
  }},
  "kpi_row": [
    {{"id": str, "label": str, "value": float|int|str, "unit": str|None, "delta": str|None, "note": str|None}}
  ],
  "tabs": [
    {{
      "id": "performance"|"segment"|"channel"|"type"|"risk",
      "title": str,
      "blocks": [
        {{
          "type": "line"|"bar"|"pie"|"heatmap"|"table"|"anomaly_list"|"text",
          "title": str,
          "subtitle": str|None,
          "data": [object]|None,
          "encoding": {{"x": str|None, "y": str|None, "color": str|None, "row": str|None, "col": str|None, "value": str|None}}|None,
          "insight": str|None
        }}
      ]
    }}
  ],
  "quality": {{
    "missingness": [{{"table_id": str, "metric": str, "value": float, "note": str}}],
    "confidence": "high"|"medium"|"low"
  }},
  "appendix": [{{"title": str, "table_id": str, "data": [object]}}]
}}

========================
HƯỚNG DẪN LẬP BIỂU ĐỒ (HEURISTICS)
========================
1) Nếu có cột thời gian (date/datetime/Ngày/Tháng/Năm...):
   - tạo block line: metric theo thời gian.
2) Chọn 1-2 dimension phân loại mạnh nhất (ít giá trị, xuất hiện nhiều) để breakdown bằng bar/pie.
3) Nếu có 2 dimension dạng category x category và 1 metric số: tạo heatmap.
4) Luôn tạo ít nhất 1 table "Top N" (N<=20) cho các record đóng góp lớn nhất theo 1 metric số.
5) Tab risk: tạo anomaly_list (top 5-10 điểm bất thường) + 1-2 chỉ số chất lượng dữ liệu.

========================
GIỚI HẠN KÍCH THƯỚC
========================
- Mỗi block "data" tối đa 200 dòng.
- Appendix tổng tối đa 200 dòng.

{_PY_HELPERS}
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


def _ask_ci(file_id: str, content: str, model: str, previous_response_id: Optional[str]) -> Tuple[str, str]:
    client = get_client()
    resp = client.responses.create(
        model=model,
        input=[{"role": "user", "content": content}],
        tools=[{
            "type": "code_interpreter",
            "container": {"type": "auto", "file_ids": [file_id]},
        }],
        tool_choice="auto",
        previous_response_id=previous_response_id,
    )
    return resp.output_text, resp.id


def ask_ci_qa(
    file_id: str,
    question: str,
    model: str,
    previous_response_id: Optional[str],
    manifest_json: str,
) -> Tuple[str, str]:
    content = f"{INSTRUCTIONS_QA}\n\nMANIFEST_JSON:\n{manifest_json}\n\nUser question: {question}"
    return _ask_ci(file_id, content, model, previous_response_id)



def ask_ci_final_spec(
    file_id: str,
    model: str,
    previous_response_id: Optional[str],
    manifest_json: str,
) -> Tuple[str, str]:
    content = f"{INSTRUCTIONS_FINAL_SPEC}\n\nMANIFEST_JSON:\n{manifest_json}\n"
    return _ask_ci(file_id, content, model, previous_response_id)

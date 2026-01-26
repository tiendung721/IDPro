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

INSTRUCTIONS_FINAL = f"""
Bạn là một nhân viên phân tích dữ liệu.
Nhiệm vụ của bạn là lập MỘT BÁO CÁO TỔNG HỢP NGẮN GỌN dưới dạng GẠCH ĐẦU DÒNG để giải thích nội dung file Excel cho người quản lý.

========================
NGỮ CẢNH & DỮ LIỆU
========================
- File trong /mnt/data là FILE GỐC, giữ nguyên cấu trúc ban đầu.
- Cấu trúc bảng hợp lệ DUY NHẤT được mô tả trong MANIFEST_JSON.
- Chỉ được phân tích các bảng trong manifest, không suy đoán ngoài phạm vi này.

========================
NGUYÊN TẮC BẮT BUỘC
========================
- Ngôn ngữ: tiếng Việt.
- Chỉ sử dụng Python (Code Interpreter) để đọc và phân tích dữ liệu.
- Không in bảng, không in dataframe, không in dữ liệu thô.
- Không gán ngành nghề hoặc bối cảnh nếu không có đủ cơ sở từ dữ liệu.
- Không viện dẫn yếu tố bên ngoài dữ liệu.
- __src_row__ chỉ dùng để truy vết nội bộ, KHÔNG in literal "__src_row__".

========================
CÁCH LÀM
========================
- Xác định file dữ liệu gốc trong /mnt/data.
- Parse MANIFEST_JSON để biết danh sách các bảng đã được xác nhận.
- Cắt dữ liệu theo từng bảng đúng ranh giới trong manifest.
- Phân tích từng bảng riêng lẻ trước khi tổng hợp.

========================
ĐỊNH DẠNG BÁO CÁO (BẮT BUỘC)
========================
Báo cáo PHẢI viết dưới dạng gạch đầu dòng.
Mỗi gạch đầu dòng là một ý hoàn chỉnh, rõ ràng.
Không viết thành đoạn văn dài.

========================
NỘI DUNG BÁO CÁO
========================

I. TỔNG QUAN FILE DỮ LIỆU
- File gồm bao nhiêu bảng (theo manifest).
- Mỗi bảng phản ánh loại thông tin gì.
- Quy mô tương đối của từng bảng (ít / vừa / nhiều dòng).

II. Ý NGHĨA DỮ LIỆU
- Mỗi bảng: mỗi dòng đại diện cho đối tượng / sự kiện gì.
- Các nhóm cột chính trong từng bảng:
  - Cột định danh.
  - Cột phân loại.
  - Cột số liệu.
  - Cột thời gian (nếu có).

III. ĐIỂM ĐÁNG CHÚ Ý
- Các phân bố nổi bật trong dữ liệu.
- Nhóm giá trị hoặc nhóm đối tượng chiếm tỷ trọng lớn.
- Các xu hướng rõ ràng (nếu có).
- Các điểm bất thường hoặc khác biệt đáng lưu ý.

IV. PHÁT HIỆN TỔNG HỢP
- Những insight quan trọng nhất rút ra từ toàn bộ dữ liệu.
- Mối liên hệ giữa các bảng (chỉ nêu nếu dữ liệu thể hiện rõ).
- Những điểm có thể ảnh hưởng đến việc theo dõi hoặc phân tích sau này.

V. KẾT LUẬN NGẮN GỌN
- Tóm tắt nhanh bức tranh tổng thể của file dữ liệu.
- Các hướng cần theo dõi hoặc phân tích thêm (mang tính gợi ý, không phải quyết định).

========================
YÊU CẦU CUỐI
========================
- Chỉ sử dụng gạch đầu dòng.
- Không viết văn xuôi.
- Ngắn gọn, súc tích, tập trung vào điều quan trọng nhất.
- Báo cáo phải đọc nhanh và hiểu ngay.
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


def ask_ci_final(
    file_id: str,
    model: str,
    previous_response_id: Optional[str],
    manifest_json: str,
) -> Tuple[str, str]:
    content = f"{INSTRUCTIONS_FINAL}\n\nMANIFEST_JSON:\n{manifest_json}\n"
    return _ask_ci(file_id, content, model, previous_response_id)

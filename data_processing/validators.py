from typing import List, Dict , Optional

class IndexErrorDetail(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def to_zero_based(sections: List[Dict], nrows: int) -> List[Dict]:
    """
    Chỉ đưa về 0‑based khi có DẤU HIỆU 1‑based RÕ RÀNG.
    Tiêu chí: nếu BẤT KỲ chỉ số nào (start/end/header) == nrows (vượt biên 0‑based),
    coi list này là 1‑based và trừ 1 cho cả bộ.
    Ngược lại: GIỮ NGUYÊN (tránh trừ nhầm gây lệch -1).
    """
    if not sections:
        return []

    # phát hiện 1-based: có ít nhất một end/start/header == nrows
    probably_one_based = False
    for s in sections:
        sr = int(s.get("start_row", 0))
        er = int(s.get("end_row", 0))
        hr = int(s.get("header_row", 0))
        if sr == nrows or er == nrows or hr == nrows:
            probably_one_based = True
            break

    out: List[Dict] = []
    for s in sections:
        sr = int(s.get("start_row", 0))
        er = int(s.get("end_row", 0))
        hr = int(s.get("header_row", 0))
        if probably_one_based:
            sr = max(0, sr - 1)
            er = max(0, er - 1)
            hr = max(0, hr - 1)
        out.append({
            "start_row": sr,
            "end_row": er,
            "header_row": hr,
            "label": s.get("label", "")
        })
    return out

def validate_sections_zero_based(sections: List[Dict], nrows: int, ncols: Optional[int] = None) -> List[Dict]:
    """
    Clamp & validate cho 0-based với end_row inclusive.
    Hỗ trợ thêm start_col/end_col (0-based, inclusive).
    - Nếu ncols is None: không validate col, nhưng vẫn pass-through nếu có.
    - Nếu ncols is not None: nếu thiếu col -> mặc định full width [0..ncols-1]
    """
    if not sections:
        raise IndexErrorDetail("SECTIONS_EMPTY", "Không có section nào để xử lý")

    checked: List[Dict] = []
    for s in sections:
        sr = int(s["start_row"])
        er = int(s["end_row"])
        hr = int(s["header_row"])

        if not (0 <= hr <= sr <= er <= nrows - 1):
            raise IndexErrorDetail(
                "INDEX_OUT_OF_RANGE",
                f"header_row={hr}, start_row={sr}, end_row={er}, nrows={nrows}"
            )

        # ---- cols (optional)
        sc = s.get("start_col", None)
        ec = s.get("end_col", None)

        if ncols is not None:
            # default full width if missing
            if sc is None:
                sc = 0
            if ec is None:
                ec = ncols - 1

            sc = int(sc)
            ec = int(ec)

            if not (0 <= sc <= ec <= ncols - 1):
                raise IndexErrorDetail(
                    "COL_OUT_OF_RANGE",
                    f"start_col={sc}, end_col={ec}, ncols={ncols}"
                )
        else:
            # ncols không cung cấp thì chỉ normalize nếu có
            if sc is not None:
                sc = int(sc)
            if ec is not None:
                ec = int(ec)

        checked.append({
            "start_row": sr,
            "end_row": er,
            "header_row": hr,
            "start_col": sc,
            "end_col": ec,
            "label": s.get("label", "")
        })

    return checked


from __future__ import annotations

from typing import List, Dict, Any, Tuple
import pandas as pd
import math


# =========================
# Basic heuristics
# =========================

def _is_empty_cell(x) -> bool:
    if pd.isna(x):
        return True
    s = str(x).strip()
    return s == ""


def _is_header_row(row: pd.Series, min_text_cells: int = 2) -> bool:
    """
    Heuristic header:
    - Có >= min_text_cells ô text (len>=2)
    - Và gần như không phải toàn số (num_cells == 0)
    """
    text_cells = 0
    num_cells = 0
    for cell in row:
        if pd.isna(cell):
            continue
        s = str(cell).strip()
        if s == "":
            continue

        if isinstance(cell, (int, float)) and not isinstance(cell, bool):
            if isinstance(cell, float) and math.isnan(cell):
                continue
            num_cells += 1
        else:
            if len(s) >= 2:
                text_cells += 1

    return text_cells >= min_text_cells and num_cells == 0


def _is_data_row(row: pd.Series, min_non_empty: int = 2) -> bool:
    """Hàng dữ liệu khi có ít nhất min_non_empty ô khác rỗng/NaN."""
    cnt = 0
    for cell in row:
        if pd.isna(cell):
            continue
        s = str(cell).strip()
        if s != "":
            cnt += 1
            if cnt >= min_non_empty:
                return True
    return False


def _has_any_content(row: pd.Series) -> bool:
    for v in row:
        if not _is_empty_cell(v):
            return True
    return False


def _overlaps(sc1: int, ec1: int, sc2: int, ec2: int) -> bool:
    """Check overlap of two inclusive column ranges."""
    return not (ec1 < sc2 or ec2 < sc1)


# =========================
# Vertical gutter logic
# =========================

def _find_vertical_gutters(
    df: pd.DataFrame,
    top: int,
    bottom: int,
    empty_ratio: float = 0.9,
    min_gutter_width: int = 1,
) -> List[Tuple[int, int]]:
    """
    Trả về list các khoảng cột gutter [(g_start, g_end), ...] (inclusive)
    dựa trên tỷ lệ rỗng theo dải hàng [top..bottom].
    """
    top = max(0, top)
    bottom = min(len(df) - 1, bottom)
    if bottom < top:
        return []

    ncols = df.shape[1]
    if ncols <= 0:
        return []

    window = df.iloc[top: bottom + 1, :]

    gutter_mask: List[bool] = []
    for c in range(ncols):
        col = window.iloc[:, c]
        empties = 0
        total = len(col)
        for v in col:
            if _is_empty_cell(v):
                empties += 1
        gutter_mask.append(total > 0 and (empties / total) >= empty_ratio)

    # gom các cột gutter liền nhau thành dải
    gutters: List[Tuple[int, int]] = []
    i = 0
    while i < ncols:
        if not gutter_mask[i]:
            i += 1
            continue
        j = i
        while j < ncols and gutter_mask[j]:
            j += 1
        if (j - i) >= min_gutter_width:
            gutters.append((i, j - 1))
        i = j

    return gutters


def _blocks_from_gutters(ncols: int, gutters: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Convert gutters -> blocks cột chứa dữ liệu: [(start_col, end_col), ...] inclusive.
    """
    if ncols <= 0:
        return []
    if not gutters:
        return [(0, ncols - 1)]

    blocks: List[Tuple[int, int]] = []
    prev_end = -1

    for (gs, ge) in gutters:
        sc = prev_end + 1
        ec = gs - 1
        if ec >= sc:
            blocks.append((sc, ec))
        prev_end = ge

    sc = prev_end + 1
    ec = ncols - 1
    if ec >= sc:
        blocks.append((sc, ec))

    return blocks


# =========================
# Main detector (2D sections)
# =========================

def detect_sections_auto(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Phát hiện section tự động với **0-based** và **end_row inclusive**.

    Fixes:
    - Không đóng section ngay khi gặp dòng trống nếu section chưa bắt đầu data (start_row chưa gặp data).
    - Nếu dòng tại start_row không phải data (bao gồm cả trống), tự động dịch start_row xuống.
    - Không kiểm tra data cho các dòng i < start_row (tránh đóng oan ngay tại header).
    """

    # ---- tunables
    window_rows = 30
    empty_ratio = 0.9
    min_gutter_width = 1
    min_non_empty_data = 2
    min_text_cells_header = 2

    sections: List[Dict[str, Any]] = []
    nrows = len(df)
    if nrows == 0:
        return sections
    ncols = df.shape[1]
    if ncols == 0:
        return sections

    section_id = 1
    active: List[Dict[str, Any]] = []  # each item: header_row, start_row, start_col, end_col

    def _close_one(a: Dict[str, Any], end_row: int):
        nonlocal section_id
        sr = int(a["start_row"])
        hr = int(a["header_row"])
        sc = int(a["start_col"])
        ec = int(a["end_col"])
        if end_row >= sr:
            sections.append({
                "start_row": sr,
                "end_row": end_row,
                "header_row": hr,
                "start_col": sc,
                "end_col": ec,
                "label": f"Section {section_id}",
            })
            section_id += 1

    def _close_all(end_row: int):
        nonlocal active
        if not active:
            return
        for a in active:
            _close_one(a, end_row)
        active = []

    def _try_open_from_header_row(i: int, row_full: pd.Series):
        """
        Mở thêm bảng (col blocks) từ một header row.
        - Nếu block overlap với active hiện có -> bỏ qua (tránh trùng)
        """
        nonlocal active
        bottom = min(i + window_rows, nrows - 1)
        gutters = _find_vertical_gutters(
            df, top=i, bottom=bottom,
            empty_ratio=empty_ratio,
            min_gutter_width=min_gutter_width
        )
        blocks = _blocks_from_gutters(ncols, gutters)

        for (sc, ec) in blocks:
            header_slice = row_full.iloc[sc:ec + 1]
            if not _is_header_row(header_slice, min_text_cells=min_text_cells_header):
                continue

            # tránh mở trùng/chồng cột với active
            conflict = False
            for a in active:
                if _overlaps(sc, ec, int(a["start_col"]), int(a["end_col"])):
                    conflict = True
                    break
            if conflict:
                continue

            active.append({
                "header_row": i,
                "start_row": i + 1,   # sẽ được tự động đẩy xuống nếu gặp trống / không phải data
                "start_col": sc,
                "end_col": ec,
            })

    for i in range(nrows):
        row_full = df.iloc[i]
        row_is_empty = row_full.isna().all() or (not _has_any_content(row_full))

        # 1) Nếu là header row -> thử mở thêm section (kể cả khi đang active)
        if (not row_is_empty) and _is_header_row(row_full, min_text_cells=min_text_cells_header):
            _try_open_from_header_row(i, row_full)

        # 2) Nếu không có active thì không cần xử lý tiếp
        if not active:
            continue

        # 3) Update từng active block
        still_active: List[Dict[str, Any]] = []
        for a in active:
            sc = int(a["start_col"])
            ec = int(a["end_col"])
            sr = int(a["start_row"])

            # 3.1) Chưa tới start_row -> chưa bắt đầu data, giữ nguyên (kể cả dòng trống)
            if i < sr:
                still_active.append(a)
                continue

            # slice theo block cột
            row_slice = row_full.iloc[sc:ec + 1]
            slice_is_empty = row_slice.isna().all() or (not _has_any_content(row_slice))

            # 3.2) Nếu đúng start_row mà dòng này trống hoặc chưa đủ data -> đẩy start_row xuống
            #      (để xử lý header 1 dòng + dòng trống + data, hoặc header 2 dòng, v.v.)
            if i == sr and (slice_is_empty or (not _is_data_row(row_slice, min_non_empty=min_non_empty_data))):
                a["start_row"] = sr + 1
                still_active.append(a)
                continue

            # 3.3) Nếu đã qua start_row (tức là đã vào vùng data) mà dòng này không phải data -> đóng
            if not _is_data_row(row_slice, min_non_empty=min_non_empty_data):
                _close_one(a, i - 1)
                continue

            still_active.append(a)

        active = still_active

    # cuối file: đóng hết
    _close_all(nrows - 1)

    sections.sort(key=lambda s: (s["header_row"], s["start_col"], s["start_row"]))
    return sections


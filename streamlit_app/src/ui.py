import streamlit as st
import pandas as pd
from typing import List, Dict, Any
import math


def _safe_int_1based(x, default_1based: int = 1) -> int:
    """
    Convert value to 1-based int safely.
    Handles None/NaN/''.
    """
    if x is None:
        return default_1based
    if isinstance(x, float) and math.isnan(x):
        return default_1based
    if isinstance(x, str) and x.strip() == "":
        return default_1based

    try:
        v = int(float(x)) 
    except Exception:
        return default_1based

    return max(1, v)


def sections_to_df_1based(sections: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Convert zero-based sections to a 1-based display DataFrame.
    Columns are kept stable for logic: Section, header_row, start_row, end_row, label
    """
    rows = []
    for i, s in enumerate(sections, 1):
        rows.append({
            "Section": i,
            "header_row": int(s.get("header_row", 0)) + 1,
            "start_row": int(s.get("start_row", 0)) + 1,
            "end_row":   int(s.get("end_row", 0)) + 1,
            "label":     s.get("label", ""),
        })
    return pd.DataFrame(rows)


def render_sections_editor(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Basic editor (no add/delete) – kept for backward compatibility.
    """
    df = sections_to_df_1based(sections)
    edited_df = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Section": st.column_config.NumberColumn("Section", disabled=True),
            "header_row": st.column_config.NumberColumn("header_row", min_value=1),
            "start_row": st.column_config.NumberColumn("start_row", min_value=1),
            "end_row": st.column_config.NumberColumn("end_row", min_value=1),
            "label": st.column_config.TextColumn("label"),
        }
    )

    out: List[Dict[str, Any]] = []
    for _, row in edited_df.iterrows():
        hdr = _safe_int_1based(row.get("header_row"), default_1based=1)
        start = _safe_int_1based(row.get("start_row"), default_1based=1)
        end = _safe_int_1based(row.get("end_row"), default_1based=start)
        if end < start:
            end = start

        out.append({
            "header_row": hdr - 1,
            "start_row":  start - 1,
            "end_row":    end - 1,
            "label":      str((row.get("label") or "")).strip(),
        })
    return out


def sections_editor_with_add_delete(
    df_1based: pd.DataFrame,
    key_prefix: str = "sec",
    lang: str = "en",
):
    """
    Editor có checkbox xóa + form tạo section mới (1-based).
    Trả về:
      - edited_zero_df: DataFrame các section (zero-based) sau khi edit (KHÔNG tính cột xóa)
      - del_rows: list indices (0-based) được tick để xóa
      - create_payload: dict (zero-based) từ form tạo mới
    """

    LABELS = {
        "en": {
            "title_list": "**Sections list (1-based)**",
            "title_new": "**Create new section (1-based)**",
            "col_section": "Section",
            "col_header": "header_row",
            "col_start": "start_row",
            "col_end": "end_row",
            "col_label": "label",
            "col_delete": "Delete?",
            "in_start": "start_row",
            "in_end": "end_row",
            "in_header": "header_row",
            "in_label": "label",
        },
        "vi": {
            "title_list": "**Danh sách bảng (1-based)**",
            "title_new": "**Tạo bảng mới (1-based)**",
            "col_section": "STT",
            "col_header": "Dòng tiêu đề",
            "col_start": "Dòng bắt đầu",
            "col_end": "Dòng kết thúc",
            "col_label": "Tên bảng / ghi chú",
            "col_delete": "Xóa?",
            "in_start": "Dòng bắt đầu",
            "in_end": "Dòng kết thúc",
            "in_header": "Dòng tiêu đề",
            "in_label": "Tên bảng / ghi chú",
        },
    }
    L = LABELS.get(lang, LABELS["en"])

    # ===== Sections list =====
    st.markdown(L["title_list"])
    df_show = df_1based.copy()
    df_show["Xóa?"] = False

    edited = st.data_editor(
        df_show,
        num_rows="dynamic",
        use_container_width=True,
        key=f"{key_prefix}_editor",
        column_config={
            "Section": st.column_config.NumberColumn(L["col_section"], disabled=True),
            "header_row": st.column_config.NumberColumn(L["col_header"], min_value=1),
            "start_row": st.column_config.NumberColumn(L["col_start"], min_value=1),
            "end_row": st.column_config.NumberColumn(L["col_end"], min_value=1),
            "label": st.column_config.TextColumn(L["col_label"]),
            "Xóa?": st.column_config.CheckboxColumn(L["col_delete"]),
        },
    )

    # rows tick delete
    del_rows = [i for i, v in enumerate(edited["Xóa?"].tolist()) if v]

    # ===== Create new =====
    st.markdown(L["title_new"])
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])

    # Default start row: next line after current max start_row
    default_new_start = 1
    if not df_1based.empty and "start_row" in df_1based.columns:
        try:
            default_new_start = int(df_1based["start_row"].max()) + 1
        except Exception:
            default_new_start = 1

    with c1:
        new_start = st.number_input(
            L["in_start"],
            min_value=1,
            value=default_new_start,
            key=f"{key_prefix}_ns",
        )
    with c2:
        new_end = st.number_input(
            L["in_end"],
            min_value=int(new_start),
            value=int(new_start),
            key=f"{key_prefix}_ne",
        )
    with c3:
        new_header = st.number_input(
            L["in_header"],
            min_value=int(new_start),
            max_value=int(new_end),
            value=int(new_start),
            key=f"{key_prefix}_nh",
        )
    with c4:
        new_label = st.text_input(
            L["in_label"],
            value="",
            key=f"{key_prefix}_nl",
        )

    create_payload = {
        "start_row": int(new_start - 1),
        "end_row": int(new_end - 1),
        "header_row": int(new_header - 1),
        "label": (new_label or "").strip(),
    }

    # ===== Normalize edited table -> zero-based DataFrame =====
    out = []
    for _, row in edited.iterrows():
        hdr = _safe_int_1based(row.get("header_row"), default_1based=1)
        start = _safe_int_1based(row.get("start_row"), default_1based=1)
        end = _safe_int_1based(row.get("end_row"), default_1based=start)
        if end < start:
            end = start

        out.append({
            "header_row": hdr - 1,
            "start_row": start - 1,
            "end_row": end - 1,
            "label": str((row.get("label") or "")).strip(),
        })

    edited_zero_df = pd.DataFrame(out)
    return edited_zero_df, del_rows, create_payload

import streamlit as st
import pandas as pd
from typing import List, Dict, Any
import math


# =========================
# Utils
# =========================

def _safe_int_1based(x, default_1based: int = 1) -> int:
    """
    Convert value to 1-based int safely.
    Handles None / NaN / ''.
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


def colnum_to_excel(n_1based: int) -> str:
    """1 -> A, 2 -> B, ... 26 -> Z, 27 -> AA ..."""
    n = int(n_1based)
    if n < 1:
        return ""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _normalize_cols_zero_based(s: Dict[str, Any]) -> tuple[int, int]:
    """
    Read start_col/end_col from section dict (0-based) and normalize.
    Backward compatible:
      - if missing or None -> default (0, 0)
    """
    sc = s.get("start_col", None)
    ec = s.get("end_col", None)

    if sc is None:
        sc = 0
    if ec is None:
        ec = sc

    try:
        sc = int(sc)
    except Exception:
        sc = 0
    try:
        ec = int(ec)
    except Exception:
        ec = sc

    if ec < sc:
        ec = sc
    if sc < 0:
        sc = 0
    if ec < 0:
        ec = sc

    return sc, ec


# =========================
# Sections -> DataFrame (1-based)
# =========================

def sections_to_df_1based(sections: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Convert zero-based sections to a 1-based display DataFrame.

    Includes:
      - start_row/end_row/header_row (1-based)
      - start_col/end_col (1-based) for internal editing/convert
      - col_range (A:D) for pretty display
    """
    rows = []
    for i, s in enumerate(sections, 1):
        hr0 = int(s.get("header_row", 0) or 0)
        sr0 = int(s.get("start_row", 0) or 0)
        er0 = int(s.get("end_row", 0) or 0)

        sc0, ec0 = _normalize_cols_zero_based(s)

        # convert to 1-based
        sc1 = sc0 + 1
        ec1 = ec0 + 1

        col_range = f"{colnum_to_excel(sc1)}:{colnum_to_excel(ec1)}"

        rows.append({
            "Section": i,
            "header_row": hr0 + 1,
            "start_row": sr0 + 1,
            "end_row": er0 + 1,

            # internal numeric cols (1-based)
            "start_col": sc1,
            "end_col": ec1,

            # pretty display
            "col_range": col_range,

            "label": s.get("label", ""),
        })

    return pd.DataFrame(rows)


# =========================
# Simple editor (no add/delete)
# =========================

def render_sections_editor(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Basic editor – supports row range + keeps col range (numeric).
    UI shows col_range (A:D). start_col/end_col are hidden/disabled by default.
    """
    df = sections_to_df_1based(sections)

    # Show only nice columns by default
    show_cols = ["Section", "header_row", "start_row", "end_row", "col_range", "label"]
    df_show = df[show_cols].copy()

    edited_df = st.data_editor(
        df_show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Section": st.column_config.NumberColumn("Section", disabled=True),
            "header_row": st.column_config.NumberColumn("header_row", min_value=1),
            "start_row": st.column_config.NumberColumn("start_row", min_value=1),
            "end_row": st.column_config.NumberColumn("end_row", min_value=1),
            "col_range": st.column_config.TextColumn("col_range", disabled=True),
            "label": st.column_config.TextColumn("label"),
        },
    )

    # Map edited rows back to original df to preserve start_col/end_col numeric
    out: List[Dict[str, Any]] = []
    for idx, row in edited_df.iterrows():
        # idx corresponds to df_show index; we can align by position
        # safest: use Section number (1..n) to fetch from df
        sec_no = _safe_int_1based(row.get("Section"), default_1based=1)
        base = df.iloc[sec_no - 1]

        hr = _safe_int_1based(row.get("header_row"), default_1based=int(base["header_row"]))
        sr = _safe_int_1based(row.get("start_row"), default_1based=int(base["start_row"]))
        er = _safe_int_1based(row.get("end_row"), default_1based=sr)
        if er < sr:
            er = sr

        # keep columns from base (numeric)
        sc = _safe_int_1based(base.get("start_col"), default_1based=1)
        ec = _safe_int_1based(base.get("end_col"), default_1based=sc)
        if ec < sc:
            ec = sc

        out.append({
            "header_row": hr - 1,
            "start_row": sr - 1,
            "end_row": er - 1,
            "start_col": sc - 1,
            "end_col": ec - 1,
            "label": str((row.get("label") or "")).strip(),
        })

    return out


# =========================
# Full editor with add/delete
# =========================

def sections_editor_with_add_delete(
    df_1based: pd.DataFrame,
    key_prefix: str = "sec",
    lang: str = "en",
    show_create: bool = True,
    show_titles: bool = True,
):
    """
    Editor có:
      - chỉnh sửa section
      - tick xóa
      - tạo section mới

    UI hiển thị col_range (A:D) thay vì start_col/end_col.
    Output trả về zero-based DataFrame (có start_col/end_col).
    """

    LABELS = {
        "en": {
            "title_list": "**Sections list (1-based)**",
            "title_new": "**Create new section (1-based)**",
            "col_section": "Section",
            "col_header": "header_row",
            "col_start": "start_row",
            "col_end": "end_row",
            "col_range": "Columns (A:D)",
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
            "col_range": "Cột (A:D)",
            "col_label": "Tên bảng / ghi chú",
            "col_delete": "Xóa?",
            "in_start": "Dòng bắt đầu",
            "in_end": "Dòng kết thúc",
            "in_header": "Dòng tiêu đề",
            "in_label": "Tên bảng / ghi chú",
        },
    }
    L = LABELS.get(lang, LABELS["en"])

    # Ensure df_1based has needed columns; if caller passed older df, try to enrich
    if "col_range" not in df_1based.columns:
        # caller likely created df_1based from older function; rebuild from records if possible
        # fallback: create col_range from start_col/end_col if exist
        if "start_col" in df_1based.columns and "end_col" in df_1based.columns:
            df_1based = df_1based.copy()
            df_1based["col_range"] = df_1based.apply(
                lambda r: f"{colnum_to_excel(_safe_int_1based(r.get('start_col')))}:{colnum_to_excel(_safe_int_1based(r.get('end_col'), _safe_int_1based(r.get('start_col'))))}",
                axis=1
            )
        else:
            df_1based = df_1based.copy()
            df_1based["start_col"] = 1
            df_1based["end_col"] = 1
            df_1based["col_range"] = "A:A"

    # ===== Sections list =====
    if show_titles:
        st.markdown(L["title_list"])

    df_show = df_1based.copy()
    df_show["Xóa?"] = False

    # Only show pretty columns
    show_cols = ["Section", "header_row", "start_row", "end_row", "col_range", "label", "Xóa?"]
    df_show = df_show[show_cols].copy()

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
            "col_range": st.column_config.TextColumn(L["col_range"], disabled=True),
            "label": st.column_config.TextColumn(L["col_label"]),
            "Xóa?": st.column_config.CheckboxColumn(L["col_delete"]),
        },
    )

    del_rows = [i for i, v in enumerate(edited["Xóa?"].tolist()) if v]

    # ===== Create new =====
    # Note: create new section via rows only; column range defaults to A:A.
    # Bạn có thể nâng cấp sau để chọn cột khi tạo mới.
    create_payload = {
        "header_row": 0,
        "start_row": 0,
        "end_row": 0,
        "start_col": 0,
        "end_col": 0,
        "label": "",
    }

    if show_create:
        if show_titles:
            st.markdown(L["title_new"])

        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])

        default_start = 1
        if not df_1based.empty:
            try:
                default_start = int(df_1based["start_row"].max()) + 1
            except Exception:
                pass

        with c1:
            ns = st.number_input(L["in_start"], min_value=1, value=default_start, key=f"{key_prefix}_ns")
        with c2:
            ne = st.number_input(L["in_end"], min_value=int(ns), value=int(ns), key=f"{key_prefix}_ne")
        with c3:
            nh = st.number_input(L["in_header"], min_value=int(ns), max_value=int(ne), value=int(ns), key=f"{key_prefix}_nh")
        with c4:
            nl = st.text_input(L["in_label"], value="", key=f"{key_prefix}_nl")

        create_payload = {
            "header_row": int(nh - 1),
            "start_row": int(ns - 1),
            "end_row": int(ne - 1),
            # default col-range A:A
            "start_col": 0,
            "end_col": 0,
            "label": (nl or "").strip(),
        }

    # ===== Normalize edited -> zero-based (preserve numeric cols from df_1based)
    out = []
    for _, row in edited.iterrows():
        sec_no = _safe_int_1based(row.get("Section"), default_1based=1)
        base = df_1based.iloc[sec_no - 1]

        hr = _safe_int_1based(row.get("header_row"), default_1based=int(base.get("header_row", 1)))
        sr = _safe_int_1based(row.get("start_row"), default_1based=int(base.get("start_row", 1)))
        er = _safe_int_1based(row.get("end_row"), default_1based=sr)
        if er < sr:
            er = sr

        # keep cols from base
        sc = _safe_int_1based(base.get("start_col"), default_1based=1)
        ec = _safe_int_1based(base.get("end_col"), default_1based=sc)
        if ec < sc:
            ec = sc

        out.append({
            "header_row": hr - 1,
            "start_row": sr - 1,
            "end_row": er - 1,
            "start_col": sc - 1,
            "end_col": ec - 1,
            "label": str((row.get("label") or "")).strip(),
        })

    edited_zero_df = pd.DataFrame(out)
    return edited_zero_df, del_rows, create_payload
# =========================
# BA Workspace Renderer (Shared)
# =========================

def render_ba_analysis_workspace(sid: str):
    ba_detect = st.session_state.get("ba_detect_result") or {}
    ba_analysis = st.session_state.get("ba_analysis_result") or {}
    quote_preview = st.session_state.get("quotation_preview_result") or {}

    from src import api

    def _to_text(value: Any, empty: str = "-") -> str:
        if value is None:
            return empty
        if isinstance(value, float) and pd.isna(value):
            return empty
        if isinstance(value, (list, tuple, set)):
            parts = [_to_text(x, empty="") for x in value]
            parts = [x for x in parts if x]
            return ", ".join(parts) if parts else empty
        text = str(value).strip()
        if not text or text.lower() in {"unknown", "none", "null", "n/a"}:
            return empty
        return text

    def _level_label(value: Any) -> str:
        labels = {
            "low": "Thấp",
            "medium": "Trung bình",
            "high": "Cao",
            "unknown": "Chưa rõ",
        }
        return labels.get(str(value or "").strip().lower(), _to_text(value, empty="Chưa rõ"))

    def _source_ref(table_id: Any, rows: Any) -> str:
        table_text = _to_text(table_id, empty="")
        row_text = _to_text(rows, empty="")
        if table_text and row_text:
            return f"{table_text} - dòng {row_text}"
        if table_text:
            return table_text
        if row_text:
            return f"Dòng {row_text}"
        return "-"

    def _fallback_scope_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for idx, item in enumerate(items, start=1):
            feature_name = _to_text(item.get("feature_name"), empty="")
            requirement_name = _to_text(item.get("requirement_name"), empty="")
            rows.append({
                "STT": idx,
                "Nhóm nghiệp vụ": _to_text(item.get("module_name"), empty="Chưa rõ"),
                "Chức năng": feature_name or requirement_name or "Chưa rõ",
                "Yêu cầu cụ thể": requirement_name or feature_name or "Chưa rõ",
                "Mô tả dễ hiểu": _to_text(item.get("description"), empty=_to_text(item.get("remarks"), empty="Chưa có mô tả")),
                "Số lượng": item.get("quantity") if item.get("quantity") is not None else "-",
                "Đơn vị": _to_text(item.get("unit")),
                "Độ phức tạp": _level_label(item.get("complexity")),
                "Mức ưu tiên": _level_label(item.get("priority")),
                "Ghi chú": _to_text(item.get("remarks")),
                "Tham chiếu": _source_ref(item.get("source_table_id"), item.get("source_row_numbers")),
            })
        return rows

    def _fallback_driver_rows(items: dict[str, Any]) -> list[dict[str, str]]:
        labels = {
            "users": "Số người dùng",
            "branches": "Số chi nhánh",
            "sites": "Số địa điểm",
            "warehouses": "Số kho",
            "stores": "Số cửa hàng",
            "integrations": "Kết nối tích hợp",
            "environments": "Môi trường vận hành",
        }
        rows = []
        for key, label in labels.items():
            value = _to_text(items.get(key), empty="")
            if value:
                rows.append({"Yếu tố ảnh hưởng báo giá": label, "Giá trị": value})
        for key, value in items.items():
            if key in labels:
                continue
            rendered = _to_text(value, empty="")
            if rendered:
                rows.append({
                    "Yếu tố ảnh hưởng báo giá": key.replace("_", " ").strip().capitalize(),
                    "Giá trị": rendered,
                })
        return rows

    def _fallback_review_rows(items: list[Any]) -> list[dict[str, str]]:
        rows = []
        for idx, item in enumerate(items, start=1):
            if isinstance(item, dict):
                summary = (
                    _to_text(item.get("requirement_name"), empty="")
                    or _to_text(item.get("feature_name"), empty="")
                    or _to_text(item.get("module_name"), empty="")
                    or _to_text(item.get("description"), empty="")
                    or _to_text(item.get("text"), empty="")
                    or "Nội dung cần xem lại"
                )
                note = (
                    _to_text(item.get("reason"), empty="")
                    or _to_text(item.get("remarks"), empty="")
                    or _to_text(item.get("note"), empty="")
                    or "Cần xác nhận thêm từ tài liệu gốc."
                )
                rows.append({
                    "STT": idx,
                    "Nội dung cần làm rõ": summary,
                    "Lý do hoặc ghi chú": note,
                    "Tham chiếu": _source_ref(item.get("source_table_id"), item.get("source_row_numbers")),
                })
            else:
                rows.append({
                    "STT": idx,
                    "Nội dung cần làm rõ": _to_text(item, empty="Nội dung cần xem lại"),
                    "Lý do hoặc ghi chú": "Cần xác nhận thêm từ tài liệu gốc.",
                    "Tham chiếu": "-",
                })
        return rows

    confidence = float(ba_detect.get("confidence") or 0.0)
    sheet_candidates = ba_detect.get("sheet_candidates") or []
    first_sheet = sheet_candidates[0].get("sheet_name", "-") if sheet_candidates else "-"
    scope_items = ba_analysis.get("scope_items") or []
    assumptions = ba_analysis.get("assumptions") or []
    exclusions = ba_analysis.get("exclusions") or []
    drivers = ba_analysis.get("commercial_drivers") or {}
    unmapped = ba_analysis.get("unmapped_or_ambiguous_items") or []

    presentation = ba_analysis.get("presentation") or {}
    overview = presentation.get("overview") or {}
    scope_rows = presentation.get("scope_rows") or _fallback_scope_rows(scope_items)
    driver_rows = presentation.get("commercial_driver_rows") or _fallback_driver_rows(drivers)
    assumption_items = presentation.get("assumption_items") or [_to_text(x.get("text"), empty="") for x in assumptions if _to_text(x.get("text"), empty="")]
    exclusion_items = presentation.get("exclusion_items") or [_to_text(x.get("text"), empty="") for x in exclusions if _to_text(x.get("text"), empty="")]
    review_rows = presentation.get("review_rows") or _fallback_review_rows(unmapped)
    summary_text = overview.get("summary_text") or f"Đã phân tích {len(scope_items)} hạng mục từ tài liệu BA."
    fact_items = overview.get("facts") or [
        {"label": "Hạng mục chính", "value": len(scope_items)},
        {"label": "Giả định", "value": len(assumptions)},
        {"label": "Ngoài phạm vi", "value": len(exclusions)},
        {"label": "Cần làm rõ", "value": len(unmapped)},
    ]
    document_summary = ba_analysis.get("document_summary") or {}
    document_info = overview.get("document_info") or [
        {"label": "Tên dự án", "value": _to_text(document_summary.get("project_name"), empty="Chưa có")},
        {"label": "Khách hàng", "value": _to_text(document_summary.get("customer_name"), empty="Chưa có")},
        {"label": "Lĩnh vực", "value": _to_text(document_summary.get("domain"), empty="Chưa có")},
        {"label": "Loại giải pháp", "value": _to_text(document_summary.get("solution_type"), empty="Chưa có")},
    ]

    st.markdown(
        f"""
<div class="workspace-hero rise-in">
  <div class="workspace-title">Không gian phân tích BA</div>
  <p class="workspace-sub">Tài liệu này đã được nhận diện là <b>Business Analysis</b>. Hệ thống đang chuyển nội dung kỹ thuật thành bản tóm tắt dễ đọc để bạn rà soát trước khi tạo báo giá.</p>
  <div class="flow-chip-row">
    <div class="flow-chip">Loại file: <b>BA Excel</b></div>
    <div class="flow-chip">Độ tin cậy: <b>{confidence:.2f}</b></div>
    <div class="flow-chip">Sheet chính: <b>{first_sheet}</b></div>
    <div class="flow-chip">Luồng: <b>BA -> Analysis -> Quotation</b></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="card card-glow">
  <p class="card-title">Tóm tắt dễ hiểu</p>
  <p class="card-sub">Phần này ưu tiên cách diễn đạt gần với nghiệp vụ để bạn kiểm tra nhanh nội dung tài liệu.</p>
</div>
""",
        unsafe_allow_html=True,
    )
    st.info(summary_text)

    stat_cols = st.columns(len(fact_items) if fact_items else 4)
    for idx, item in enumerate(fact_items):
        with stat_cols[idx]:
            st.metric(_to_text(item.get("label"), empty="Thông tin"), item.get("value", 0))

    info_cols = st.columns(2)
    for idx, item in enumerate(document_info):
        with info_cols[idx % 2]:
            st.markdown(f"**{_to_text(item.get('label'), empty='Thông tin')}**")
            st.caption(_to_text(item.get("value"), empty="Chưa có"))

    c1, c2 = st.columns([1.6, 1.0], gap="large")
    with c1:
        st.markdown(
            """
<div class="card card-glow">
  <p class="card-title">Các hạng mục chính</p>
  <p class="card-sub">Danh sách này đã được đổi nhãn sang tiếng Việt dễ hiểu để bạn rà nhanh từng đầu việc.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if scope_rows:
            st.dataframe(pd.DataFrame(scope_rows), use_container_width=True, height=420)
        else:
            st.info("Chưa có hạng mục nào được tách ra từ tài liệu.")

        st.markdown(
            """
<div class="card card-glow" style="margin-top:14px">
  <p class="card-title">Nội dung cần làm rõ thêm</p>
  <p class="card-sub">Đây là các chỗ tài liệu còn mơ hồ hoặc chưa đủ căn cứ để chốt chắc chắn.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if review_rows:
            st.dataframe(pd.DataFrame(review_rows), use_container_width=True, height=220)
        else:
            st.success("Không có nội dung mơ hồ cần xác nhận thêm.")

    with c2:
        st.markdown(
            """
<div class="card card-glow">
  <p class="card-title">Yếu tố ảnh hưởng báo giá</p>
  <p class="card-sub">Các thông tin này thường tác động trực tiếp đến phạm vi triển khai và chi phí.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if driver_rows:
            st.dataframe(pd.DataFrame(driver_rows), use_container_width=True)
        else:
            st.caption("Chưa có thông tin ảnh hưởng báo giá được tách ra.")

        st.markdown(
            """
<div class="card card-glow" style="margin-top:14px">
  <p class="card-title">Giả định đang dùng</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if assumption_items:
            for text in assumption_items:
                st.markdown(f"- {text}")
        else:
            st.caption("Chưa có giả định nào được ghi nhận.")

        st.markdown(
            """
<div class="card card-glow" style="margin-top:14px">
  <p class="card-title">Phần ngoài phạm vi</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if exclusion_items:
            for text in exclusion_items:
                st.markdown(f"- {text}")
        else:
            st.caption("Chưa có mục ngoài phạm vi nào được ghi nhận.")

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

    st.markdown(
        """
<div class="card card-glow rise-in">
  <p class="card-title">Bước tiếp theo: tạo báo giá</p>
  <p class="card-sub">Sau khi rà soát xong nội dung ở trên, bạn có thể tạo dữ liệu báo giá và xuất file Excel mẫu.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    f1, f2, f3 = st.columns([1.4, 1.4, 2.2])
    with f1:
        customer_name = st.text_input("Tên khách hàng", key="ba_quote_customer_name")
    with f2:
        quotation_no = st.text_input("Số báo giá", key="ba_quote_no")
    with f3:
        currency = st.selectbox("Tiền tệ", ["VND", "USD"], key="ba_quote_currency")

    q1, q2, q3 = st.columns([1.2, 1.2, 2.6])
    with q1:
        btn_quote = st.button("Tạo báo giá", type="primary", key="btn_ba_generate_quote")
    with q2:
        btn_rerun_ba = st.button("Chạy lại phân tích", key="btn_ba_rerun_analysis")
    with q3:
        st.caption("Bạn có thể rà lại các hạng mục ở trên trước khi tạo báo giá.")

    if btn_rerun_ba:
        with st.spinner("Đang phân tích lại tài liệu BA..."):
            rerun_resp = api.ba_analysis(sid)
            if isinstance(rerun_resp, dict) and rerun_resp.get("ok") is False:
                st.error(f"API lỗi ({rerun_resp.get('status_code')}): {rerun_resp.get('error')}")
            else:
                st.session_state["ba_analysis_result"] = rerun_resp
                st.rerun()

    if btn_quote:
        with st.spinner("Đang tạo dữ liệu báo giá..."):
            qresp = api.quotation_generate(
                sid,
                customer_name=customer_name,
                quotation_no=quotation_no,
                currency=currency,
            )
        if isinstance(qresp, dict) and qresp.get("ok") is False:
            st.error(f"API lỗi ({qresp.get('status_code')}): {qresp.get('error')}")
        else:
            st.session_state["quotation_preview_result"] = qresp
            quote_preview = qresp

    if quote_preview:
        st.markdown(
            """
<div class="card card-glow rise-in" style="margin-top:14px">
  <p class="card-title">Xem trước dữ liệu báo giá</p>
  <p class="card-sub">Dữ liệu báo giá đã được dựng xong và sẵn sàng để xuất ra Excel.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        preview = quote_preview.get("quotation_preview") or {}
        line_items = preview.get("line_items") or []
        if line_items:
            st.dataframe(pd.DataFrame(line_items), use_container_width=True, height=300)
        download_path = quote_preview.get("download_path")
        if download_path:
            st.markdown(f"[Tải file báo giá]({api.BASE}{download_path})")

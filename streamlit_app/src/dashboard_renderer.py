import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------
# Styling (dashboard-like cards)
# -----------------------------
def inject_dashboard_css():
    st.markdown(
        """
        <style>
        :root{
            --card-bg: #ffffff;
            --card-border: #e6e6e6;
            --text-muted: #666;
            --text-main: #222;
        }
        .stApp { background: #f7f7f9; }
        section[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #eee; }

        .kpi-card{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 14px 16px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
            height: 100%;
        }
        .kpi-title{
            font-size: 0.85rem;
            color: #444;
            margin-bottom: 6px;
            font-weight: 600;
        }
        .kpi-value{
            font-size: 1.8rem;
            font-weight: 800;
            line-height: 1.1;
            color: #0b5;
            margin-bottom: 2px;
        }
        .kpi-sub{
            font-size: 0.8rem;
            color: var(--text-muted);
        }

        .block{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 10px 12px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
            margin-bottom: 14px;
        }
        .block-title{
            font-size: 1.05rem;
            font-weight: 750;
            color: var(--text-main);
            margin: 0.2rem 0 0.2rem 0;
        }
        .block-subtitle{
            font-size: 0.85rem;
            color: var(--text-muted);
            margin: 0 0 0.8rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def kpi_card(title: str, value: str, sub: str = ""):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def block_start(title: str, subtitle: str | None = None):
    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.markdown(f'<div class="block-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="block-subtitle">{subtitle}</div>', unsafe_allow_html=True)

def block_end():
    st.markdown("</div>", unsafe_allow_html=True)


# -----------------------------
# Utilities
# -----------------------------
def _to_df(data):
    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.DataFrame):
        return data
    if isinstance(data, list):
        return pd.DataFrame(data)
    if isinstance(data, dict):
        # sometimes: {"rows":[...]} or similar
        if "rows" in data and isinstance(data["rows"], list):
            return pd.DataFrame(data["rows"])
        return pd.DataFrame([data])
    return pd.DataFrame()

def _fmt_value(v, unit=None):
    if v is None:
        return "-"
    # format numbers nicer
    try:
        if isinstance(v, (int, float)):
            # keep decimals for floats
            if isinstance(v, float) and abs(v - int(v)) > 1e-9:
                s = f"{v:,.2f}".replace(",", ".")
            else:
                s = f"{int(v):,}".replace(",", ".")
        else:
            s = str(v)
    except Exception:
        s = str(v)
    if unit:
        # keep % like "68.9 %" look
        if str(unit).strip() == "%":
            return f"{s}%"
        return f"{s} {unit}"
    return s

def _safe_encoding(enc: dict | None):
    enc = enc or {}
    return {
        "x": enc.get("x"),
        "y": enc.get("y"),
        "color": enc.get("color"),
        "row": enc.get("row"),
        "col": enc.get("col"),
        "value": enc.get("value"),
    }

def _render_chart(block: dict):
    df = _to_df(block.get("data"))
    enc = _safe_encoding(block.get("encoding"))

    btype = (block.get("type") or "").lower().strip()
    title = block.get("title") or ""
    subtitle = block.get("subtitle")
    insight = block.get("insight")

    block_start(title, subtitle)

    if df.empty:
        st.info("Không có dữ liệu cho biểu đồ này.")
        if insight:
            st.caption(insight)
        block_end()
        return

    # Normalize types (để spec trả line/bar/pie/table vẫn render)
    if btype in ["line", "line_chart"]:
        fig = px.line(df, x=enc["x"], y=enc["y"], color=enc["color"], markers=True)
        st.plotly_chart(fig, use_container_width=True)

    elif btype in ["bar", "bar_chart"]:
        # auto horizontal if x is numeric and y is category
        if enc["x"] and enc["y"] and pd.api.types.is_numeric_dtype(df[enc["x"]]):
            fig = px.bar(df, x=enc["x"], y=enc["y"], orientation="h", color=enc["color"])
        else:
            fig = px.bar(df, x=enc["x"], y=enc["y"], color=enc["color"])
        st.plotly_chart(fig, use_container_width=True)

    elif btype in ["pie", "pie_chart", "donut", "donut_chart"]:
        fig = px.pie(df, names=enc["x"], values=enc["y"], hole=0.55 if btype in ["donut", "donut_chart"] else 0.0)
        st.plotly_chart(fig, use_container_width=True)

    elif btype in ["heatmap", "density_heatmap"]:
        # expects x,y,value or z
        z = enc["value"] or enc["y"]
        fig = px.density_heatmap(df, x=enc["x"], y=enc["y"], z=z, histfunc="sum")
        st.plotly_chart(fig, use_container_width=True)

    elif btype in ["table"]:
        st.dataframe(df, use_container_width=True, hide_index=True)

    elif btype in ["anomaly_list"]:
        # list of dicts
        st.dataframe(df, use_container_width=True, hide_index=True)

    elif btype in ["text"]:
        if insight:
            st.write(insight)
        else:
            st.write(block.get("text") or "")

    else:
        st.warning(f"Block type chưa hỗ trợ: {btype}")
        st.dataframe(df, use_container_width=True, hide_index=True)

    if insight and btype not in ["text"]:
        st.caption(insight)

    block_end()


# -----------------------------
# Main render entry
# -----------------------------
def render_dashboard(spec: dict):
    """
    Render dashboard UI đẹp giống demo (CSS cards + blocks + layout),
    nhưng dữ liệu lấy từ JSON spec.
    Expected keys:
      - meta: {title, time_range, data_quality_note}
      - kpi_row: [{label,value,unit,note}]
      - tabs: [{id,title,blocks:[...]}]
      - executive_summary (optional)
      - appendix (optional)
    """
    inject_dashboard_css()

    meta = spec.get("meta") or {}
    title = meta.get("title") or "BÁO CÁO (Dashboard-style)"
    time_range = meta.get("time_range") or ""
    dq = meta.get("data_quality_note") or ""

    st.title(title)
    if time_range:
        st.caption(time_range)
    if dq:
        st.info(dq)

    # KPI row (up to 4 per row like demo)
    kpis = spec.get("kpi_row") or []
    if isinstance(kpis, list) and len(kpis) > 0:
        # render 4 per row
        for i in range(0, len(kpis), 4):
            row = kpis[i:i+4]
            cols = st.columns(4)
            for j in range(4):
                with cols[j]:
                    if j < len(row):
                        k = row[j] or {}
                        kpi_card(
                            k.get("label") or k.get("id") or f"KPI {i+j+1}",
                            _fmt_value(k.get("value"), k.get("unit")),
                            k.get("note") or "",
                        )
                    else:
                        st.empty()
        st.markdown("")

    # Tabs / pages (giống demo: 5 lens)
    tabs = spec.get("tabs") or []
    if not isinstance(tabs, list) or not tabs:
        st.warning("Spec không có tabs để hiển thị.")
        return

    # Render as Streamlit tabs for nicer UI (thay vì radio)
    tab_titles = [t.get("title") or t.get("id") for t in tabs]
    ui_tabs = st.tabs(tab_titles)

    for ui, t in zip(ui_tabs, tabs):
        with ui:
            blocks = t.get("blocks") or []
            if not blocks:
                st.caption("Không có block trong tab này.")
                continue

            # Layout đẹp: nếu block nhiều, tự chia 2 cột giống demo
            # rule đơn giản: nếu >=2 blocks -> 2 cột; còn lại full width
            if len(blocks) == 1:
                _render_chart(blocks[0])
            else:
                left, right = st.columns(2)
                for idx, b in enumerate(blocks):
                    with (left if idx % 2 == 0 else right):
                        _render_chart(b)

    # Executive summary + appendix
    st.markdown("---")
    ex = spec.get("executive_summary") or {}
    if ex:
        with st.expander("🧾 Executive Summary", expanded=False):
            kf = ex.get("key_findings") or []
            rk = ex.get("risks") or []
            ac = ex.get("actions") or []
            if kf:
                st.markdown("**Key findings**")
                for x in kf:
                    st.markdown(f"- {x}")
            if rk:
                st.markdown("**Risks**")
                for x in rk:
                    st.markdown(f"- {x}")
            if ac:
                st.markdown("**Actions**")
                for x in ac:
                    st.markdown(f"- {x}")

    appendix = spec.get("appendix") or []
    if appendix:
        with st.expander("📎 Appendix", expanded=False):
            for item in appendix:
                block_start(item.get("title") or "Appendix", f"Table: {item.get('table_id') or ''}")
                df = _to_df(item.get("data"))
                if df.empty:
                    st.caption("Không có dữ liệu.")
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True)
                block_end()

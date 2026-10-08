from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import re

# =========================================================
# Premium Design Theme (Apple Pastel / Warm Grid)
# =========================================================
THEME_COLORS = ["#5c7aff", "#45c3b8", "#fabe4c", "#ff7380", "#a668e1", "#ff985c", "#7ceb8b", "#36454F"]
pio.templates["custom_premium"] = go.layout.Template(
    layout=go.Layout(
        colorway=THEME_COLORS,
        font=dict(family="Plus Jakarta Sans, Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"),
        title=dict(font=dict(size=16, color="#111827", family="Space Grotesk, Plus Jakarta Sans, Inter")),
        margin=dict(t=40, b=20, l=20, r=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1)
    )
)
pio.templates.default = "custom_premium"

# =========================================================
# Styling (dashboard-like cards)
# =========================================================
def inject_dashboard_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap');

        :root{
            --card-bg: #ffffff;
            --card-border: #E5E7EB;
            --text-muted: #6B7280;
            --text-main: #111827;
            --app-bg: #F9FAFB;
        }
        .stApp { 
            background: var(--app-bg); 
            font-family: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }
        section[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid var(--card-border); }

        /* KPI card */
        .kpi-card{
            background: linear-gradient(145deg, #ffffff 0%, #FAFAFA 100%);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 20px 24px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03), 0 2px 4px -1px rgba(0,0,0,0.02);
            height: 100%;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .kpi-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -2px rgba(0,0,0,0.03);
        }
        .kpi-title{
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 8px;
            font-weight: 600;
            letter-spacing: 0.05em;
        }
        .kpi-value{
            font-size: 2.25rem;
            font-weight: 600;
            line-height: 1.1;
            color: var(--text-main);
            margin-bottom: 6px;
        }
        .kpi-sub{
            font-size: 0.85rem;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .delta-up { color: #10B981; font-weight: 600; font-size: 1.1rem; }
        .delta-down { color: #EF4444; font-weight: 600; font-size: 1.1rem; }

        /* Generic block card */
        .block{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03), 0 2px 4px -1px rgba(0,0,0,0.02);
            margin-bottom: 24px;
            transition: box-shadow 0.2s ease;
        }
        .block:hover {
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -2px rgba(0,0,0,0.03);
        }
        .block-title{
            font-size: 1rem;
            font-weight: 600;
            color: var(--text-main);
            margin: 0 0 0.25rem 0;
            letter-spacing: -0.01em;
        }
        .block-subtitle{
            font-size: 0.8rem;
            color: var(--text-muted);
            margin: 0 0 1.2rem 0;
        }

        /* Insight list */
        .insight-pill{
            display: inline-block;
            padding: 2px 10px;
            border-radius: 999px;
            border: 1px solid #EAECF0;
            background: #F9FAFB;
            color: #344054;
            font-size: 0.75rem;
            margin-right: 6px;
            margin-bottom: 6px;
            font-weight: 500;
        }
        .dash-shell{
            background:
                radial-gradient(circle at top left, rgba(129, 216, 255, .18), transparent 28%),
                radial-gradient(circle at top right, rgba(94, 122, 255, .10), transparent 24%),
                linear-gradient(180deg, rgba(255,255,255,.94), rgba(255,255,255,.98));
            border: 1px solid rgba(207,216,228,.85);
            border-radius: 26px;
            padding: 20px 22px 10px 22px;
            box-shadow: 0 22px 48px rgba(15, 23, 42, 0.07);
            margin-bottom: 22px;
        }
        .shell-header{
            display:flex;
            align-items:flex-start;
            justify-content:space-between;
            gap:16px;
            margin-bottom:14px;
        }
        .shell-kicker{
            font-size:.74rem;
            text-transform:uppercase;
            letter-spacing:.08em;
            color:#4b5563;
            font-weight:700;
            margin-bottom:6px;
        }
        .shell-title{
            font-size:1.65rem;
            font-weight:700;
            color:#0f172a;
            line-height:1.12;
            margin-bottom:6px;
            font-family:'Space Grotesk','Plus Jakarta Sans',sans-serif;
        }
        .shell-subtitle{
            color:#4b5563;
            font-size:.95rem;
            max-width:780px;
        }
        .shell-badges{
            display:flex;
            flex-wrap:wrap;
            gap:8px;
            justify-content:flex-end;
        }
        .shell-badge{
            padding:7px 12px;
            border-radius:999px;
            background:#f8fafc;
            border:1px solid #dbe4ef;
            color:#1f2937;
            font-size:.82rem;
            font-weight:600;
            white-space:nowrap;
        }
        .hero-statement{
            background: linear-gradient(135deg, rgba(87, 181, 231, .10), rgba(92, 122, 255, .07));
            border: 1px solid rgba(155, 190, 220, .55);
            border-radius: 18px;
            padding: 14px 16px;
            color: #0f172a;
            font-size: .96rem;
            margin: 10px 0 18px 0;
        }
        .summary-card{
            border:1px solid #e2e8f0;
            border-radius:18px;
            background:linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            padding:16px 16px 14px 16px;
            min-height:140px;
            box-shadow:0 10px 24px rgba(15,23,42,.05);
        }
        .summary-card.good{ border-color: rgba(16,185,129,.28); background: linear-gradient(180deg,#ffffff 0%,#f0fdf7 100%); }
        .summary-card.warn{ border-color: rgba(245,158,11,.30); background: linear-gradient(180deg,#ffffff 0%,#fff9ed 100%); }
        .summary-card.accent{ border-color: rgba(92,122,255,.28); background: linear-gradient(180deg,#ffffff 0%,#f2f6ff 100%); }
        .summary-eyebrow{
            font-size:.72rem;
            font-weight:700;
            text-transform:uppercase;
            letter-spacing:.06em;
            color:#64748b;
            margin-bottom:10px;
        }
        .summary-value{
            font-size:1.7rem;
            line-height:1.08;
            font-weight:700;
            color:#0f172a;
            margin-bottom:10px;
        }
        .summary-note{
            font-size:.88rem;
            color:#475569;
            line-height:1.45;
        }
        .narrative-card{
            border:1px solid rgba(203,213,225,.92);
            border-radius:18px;
            background:#ffffff;
            padding:16px;
            box-shadow:0 10px 24px rgba(15,23,42,.04);
            margin-bottom:14px;
        }
        .narrative-card.good{ border-left:4px solid #10b981; }
        .narrative-card.warn{ border-left:4px solid #f59e0b; }
        .narrative-card.accent{ border-left:4px solid #5c7aff; }
        .narrative-title{
            font-size:.86rem;
            font-weight:700;
            color:#0f172a;
            margin-bottom:8px;
        }
        .narrative-body{
            font-size:.9rem;
            color:#475569;
            line-height:1.5;
        }
        .stat-list{
            border:1px solid #e2e8f0;
            border-radius:18px;
            background:#ffffff;
            padding:16px;
            box-shadow:0 10px 24px rgba(15,23,42,.04);
        }
        .stat-list-title{
            font-size:.86rem;
            font-weight:700;
            color:#0f172a;
            margin-bottom:10px;
        }
        .stat-row{
            display:flex;
            justify-content:space-between;
            gap:12px;
            padding:9px 0;
            border-top:1px dashed #e2e8f0;
        }
        .stat-row:first-of-type{ border-top:none; padding-top:0; }
        .stat-label{
            color:#475569;
            font-size:.88rem;
        }
        .stat-value{
            color:#0f172a;
            font-weight:700;
            text-align:right;
            font-size:.9rem;
        }
        .quick-actions{
            display:flex;
            flex-wrap:wrap;
            gap:8px;
            margin-top:10px;
        }
        .quick-action{
            background:#eff6ff;
            color:#1d4ed8;
            border:1px solid rgba(59,130,246,.18);
            border-radius:999px;
            padding:7px 11px;
            font-size:.8rem;
            font-weight:600;
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
    if title:
        st.markdown(f'<div class="block-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="block-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def block_end():
    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# Utilities
# =========================================================
def _to_df(data) -> pd.DataFrame:
    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.DataFrame):
        return data
    if isinstance(data, list):
        return pd.DataFrame(data)
    if isinstance(data, dict):
        if "rows" in data and isinstance(data["rows"], list):
            return pd.DataFrame(data["rows"])
        return pd.DataFrame([data])
    return pd.DataFrame()


def _arrow_safe_df(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    for c in df2.columns:
        if df2[c].dtype == "object":
            df2[c] = df2[c].map(
                lambda x: x.decode("utf-8", "ignore") if isinstance(x, (bytes, bytearray)) else x
            )
            df2[c] = df2[c].astype("string")
    return df2


def _fmt_value(v, unit=None) -> str:
    if v is None:
        return "-"
    try:
        if isinstance(v, (int, float)):
            if isinstance(v, float) and abs(v - int(v)) > 1e-9:
                s = f"{v:,.2f}".replace(",", ".")
            else:
                s = f"{int(v):,}".replace(",", ".")
        else:
            s = str(v)
    except Exception:
        s = str(v)

    if unit:
        if str(unit).strip() == "%":
            return f"{s}%"
        return f"{s} {unit}"
    return s


def _safe_encoding(enc: dict | None) -> dict:
    enc = enc or {}
    return {
        "x": enc.get("x"),
        "y": enc.get("y"),
        "color": enc.get("color"),
        "row": enc.get("row"),
        "col": enc.get("col"),
        "value": enc.get("value"),
    }


def _chart_height(chart_key: str, w: dict, default: int = 320) -> int:
    explicit = w.get("height")
    try:
        if explicit:
            return int(explicit)
    except Exception:
        pass
    key = (chart_key or "").lower()
    wtype = (w.get("type") or "").lower().strip()
    if "_hero" in key or w.get("slot") == "hero" or wtype in {"line", "area", "combo", "combo_bar_line", "sankey"}:
        return 430
    if wtype in {"heatmap", "density_heatmap", "treemap", "sunburst", "radar", "polar_bar"}:
        return 360
    if wtype in {"donut", "pie", "gauge", "funnel"}:
        return 300
    return default


def _apply_premium_layout(fig, *, height: int, show_legend: bool = True, x_grid: bool = False, y_grid: bool = True, unified_hover: bool = False):
    fig.update_layout(
        height=height,
        margin=dict(t=26, b=18, l=14, r=14),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor="rgba(148,163,184,.35)",
            font=dict(color="#0f172a", family="Plus Jakarta Sans, Inter, sans-serif", size=12),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor='rgba(255,255,255,.75)',
            bordercolor='rgba(226,232,240,.65)',
            borderwidth=1,
            font=dict(size=11),
        ),
        showlegend=show_legend,
        hovermode="x unified" if unified_hover else "closest",
    )
    fig.update_xaxes(
        showgrid=x_grid,
        gridcolor='rgba(226,232,240,.45)',
        zeroline=False,
        linecolor='rgba(203,213,225,.7)',
        tickfont=dict(color="#475569"),
        title_font=dict(color="#334155"),
    )
    fig.update_yaxes(
        showgrid=y_grid,
        gridcolor='rgba(226,232,240,.55)',
        zeroline=False,
        linecolor='rgba(203,213,225,.7)',
        tickfont=dict(color="#475569"),
        title_font=dict(color="#334155"),
    )
    return fig


def _theme_sequence(size: int) -> list[str]:
    count = max(int(size or 0), 1)
    return [THEME_COLORS[idx % len(THEME_COLORS)] for idx in range(count)]


def _infer_bar_orientation(w: dict, df: pd.DataFrame, category_key: str | None) -> str:
    explicit = str(w.get("orientation") or "").strip().lower()
    if explicit in {"h", "horizontal"}:
        return "h"
    if explicit in {"v", "vertical"}:
        return "v"
    if not category_key or category_key not in df.columns:
        return "v"
    labels = [str(x or "") for x in df[category_key].head(12).tolist()]
    longest = max((len(label) for label in labels), default=0)
    if longest >= 16 or len(df) >= 7:
        return "h"
    return "v"


# =========================================================
# Widget renderers
# =========================================================
def _render_plotly_chart(w: dict, chart_key: str):
    df = _to_df(w.get("data"))
    enc = _safe_encoding(w.get("encoding"))
    wtype = (w.get("type") or "").lower().strip()
    height = _chart_height(chart_key, w)

    if df.empty:
        st.info("Không có dữ liệu cho biểu đồ này.")
        return

    if wtype in ("donut", "pie"):
        names = enc["x"] or ("label" if "label" in df.columns else df.columns[0])
        values = enc["y"] or (
            "value" if "value" in df.columns else df.columns[1] if len(df.columns) > 1 else df.columns[0]
        )
        fig = px.pie(
            df,
            names=names,
            values=values,
            hole=0.55 if wtype == "donut" else 0.0,
            color_discrete_sequence=_theme_sequence(len(df)),
        )
        fig.update_traces(
            textposition="outside" if len(df) <= 6 else "auto",
            textinfo="percent+label" if len(df) <= 6 else "percent",
            marker=dict(line=dict(color="rgba(255,255,255,.92)", width=2)),
            pull=[0.03 if i == 0 else 0 for i in range(len(df))],
        )
        if wtype == "donut" and values in df.columns:
            total_value = pd.to_numeric(df[values], errors="coerce").fillna(0).sum()
            fig.add_annotation(
                x=0.5,
                y=0.5,
                text=f"<b>{_fmt_value(total_value)}</b><br>Tong",
                showarrow=False,
                font=dict(size=14, color="#0f172a"),
            )
        _apply_premium_layout(fig, height=height, show_legend=True, x_grid=False, y_grid=False)
        st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_pie")
        return

    if wtype in ("line", "area", "stacked_area"):
        x = enc["x"] or (df.columns[0] if len(df.columns) >= 1 else None)
        y = enc["y"] or (df.columns[1] if len(df.columns) >= 2 else None)
        color = enc["color"] if enc["color"] in df.columns else None

        if x and y:
            fig = px.line(df, x=x, y=y, color=color, markers=True)
            if wtype in ("area", "stacked_area"):
                fig.update_traces(mode="lines+markers")
                for trace in fig.data:
                    trace.update(fill="tozeroy", line=dict(width=3), opacity=.82)
            else:
                fig.update_traces(line=dict(width=3, shape="spline"), marker=dict(size=7))
            _apply_premium_layout(fig, height=height, show_legend=True, x_grid=False, y_grid=True, unified_hover=True)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_line")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    if wtype in ("bar", "stacked_bar"):
        x = enc["x"] or (df.columns[0] if len(df.columns) >= 1 else None)
        y = enc["y"] or (df.columns[1] if len(df.columns) >= 2 else None)
        color = enc["color"] if enc["color"] in df.columns else None

        if x and y:
            category_key = x
            value_key = y
            if x in df.columns and pd.api.types.is_numeric_dtype(df[x]) and y in df.columns and not pd.api.types.is_numeric_dtype(df[y]):
                category_key = y
                value_key = x

            orientation = _infer_bar_orientation(w, df, category_key)
            if orientation == "h":
                fig = px.bar(df, x=value_key, y=category_key, color=color, orientation="h")
            else:
                fig = px.bar(df, x=category_key, y=value_key, color=color)

            if wtype == "stacked_bar":
                fig.update_layout(barmode="stack")

            if not color:
                fig.update_traces(
                    marker=dict(
                        color=_theme_sequence(len(df)),
                        line=dict(color="rgba(255,255,255,.75)", width=1),
                    ),
                    opacity=.92,
                )
            else:
                fig.update_traces(marker=dict(line=dict(color="rgba(255,255,255,.75)", width=1)), opacity=.92)

            text_template = "%{x}" if orientation == "h" else "%{y}"
            text_position = "outside" if len(df) <= 10 else "none"
            fig.update_traces(texttemplate=text_template, textposition=text_position, cliponaxis=False)
            fig.update_layout(bargap=0.26)
            if orientation == "h":
                fig.update_yaxes(automargin=True)
            else:
                labels = [str(x or "") for x in df[category_key].head(12).tolist()] if category_key in df.columns else []
                fig.update_xaxes(automargin=True, tickangle=-18 if max((len(label) for label in labels), default=0) >= 10 else 0)
            _apply_premium_layout(fig, height=height, show_legend=bool(color), x_grid=False, y_grid=True)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_bar")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    if wtype == "sparkline_bar":
        x = enc["x"] or (df.columns[0] if len(df.columns) >= 1 else None)
        y = enc["y"] or (df.columns[1] if len(df.columns) >= 2 else None)
        if x and y:
            fig = px.bar(df, x=x, y=y, color_discrete_sequence=["#5c7aff"])
            fig.update_xaxes(visible=False, showgrid=False)
            fig.update_yaxes(visible=False, showgrid=False)
            fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=150)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_sparkline")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    if wtype == "gauge":
        val_col = enc["value"] or enc["y"] or (df.columns[1] if len(df.columns) > 1 else df.columns[0])
        val = df.iloc[0][val_col] if not df.empty else 0
        title_text = w.get("title") or ""
        max_val = w.get("max_value") or (val * 1.5 if val else 100)
        
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = val,
            title = {'text': title_text, 'font': {'size': 14}},
            gauge = {
                'axis': {'range': [None, max_val], 'tickwidth': 1, 'tickcolor': "#6B7280"},
                'bar': {'color': "#5c7aff"},
                'bgcolor': "#F9FAFB",
                'borderwidth': 0,
                'bordercolor': "gray"
            }
        ))
        fig.update_layout(margin=dict(t=18, b=8, l=12, r=12), paper_bgcolor='rgba(0,0,0,0)', font={'color': "#111827", 'family': "Plus Jakarta Sans"})
        st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_gauge")
        return

    if wtype in ("heatmap", "density_heatmap"):
        x = enc["x"]
        y = enc["y"]
        z = enc["value"] or enc["y"]
        if x and y and z and x in df.columns and y in df.columns:
            fig = px.density_heatmap(df, x=x, y=y, z=z, histfunc="sum")
            _apply_premium_layout(fig, height=height, show_legend=False, x_grid=False, y_grid=False)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_heatmap")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    if wtype == "funnel":
        x = enc["x"] or (df.columns[0] if len(df.columns) >= 1 else None)
        y = enc["y"] or (df.columns[1] if len(df.columns) >= 2 else None)
        if x and y:
            fig = px.funnel(df, x=x, y=y)
            fig.update_traces(textinfo="value+percent initial")
            _apply_premium_layout(fig, height=height, show_legend=False, x_grid=False, y_grid=False)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_funnel")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    if wtype in ("sunburst", "treemap"):
        path = w.get("path") or [df.columns[0]]
        values = enc["value"] or enc["y"] or (df.columns[1] if len(df.columns) > 1 else None)
        if path and values:
            if wtype == "sunburst":
                fig = px.sunburst(df, path=path, values=values)
            else:
                fig = px.treemap(df, path=path, values=values)
            fig.update_traces(textinfo="label+percent entry")
            _apply_premium_layout(fig, height=height, show_legend=False, x_grid=False, y_grid=False)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_{wtype}")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    if wtype == "waterfall":
        x = enc["x"] or (df.columns[0] if len(df.columns) >= 1 else None)
        y = enc["y"] or (df.columns[1] if len(df.columns) >= 2 else None)
        if x and y:
            measure = ["relative"] * len(df)
            measure[0] = "absolute"
            measure[-1] = "total"
            fig = go.Figure(go.Waterfall(
                name="Waterfall", orientation="v",
                measure=measure,
                x=df[x],
                textposition="outside",
                text=df[y],
                y=df[y],
                connector={"line":{"color":"rgb(63, 63, 63)"}}
            ))
            _apply_premium_layout(fig, height=height, show_legend=False, x_grid=False, y_grid=True)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_waterfall")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    if wtype in ("scatter", "bubble"):
        x = enc["x"] or (df.columns[0] if len(df.columns) > 0 else None)
        y = enc["y"] or (df.columns[1] if len(df.columns) > 1 else None)
        color = enc["color"] if enc["color"] in df.columns else None
        size = w.get("size") or (df.columns[2] if wtype == "bubble" and len(df.columns) > 2 else None)
        if x and y:
            fig = px.scatter(df, x=x, y=y, color=color, size=size if size in df.columns else None)
            fig.update_traces(marker=dict(line=dict(color="rgba(255,255,255,.75)", width=1)), opacity=.82)
            _apply_premium_layout(fig, height=height, show_legend=bool(color), x_grid=False, y_grid=True)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_scatter")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    if wtype in ("histogram", "box", "violin", "strip"):
        x = enc["x"] or (df.columns[0] if len(df.columns) > 0 else None)
        y = enc["y"] or (df.columns[1] if len(df.columns) > 1 else None)
        color = enc["color"] if enc["color"] in df.columns else None
        if wtype == "histogram" and x:
            fig = px.histogram(df, x=x, color=color)
        elif wtype == "strip" and x and y:
            fig = px.strip(df, x=x, y=y, color=color)
        elif wtype == "box" and x and y:
            fig = px.box(df, x=x, y=y, color=color)
        elif wtype == "violin" and x and y:
            fig = px.violin(df, x=x, y=y, color=color, box=True)
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
            return
        _apply_premium_layout(fig, height=height, show_legend=bool(color), x_grid=False, y_grid=True)
        st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_{wtype}")
        return

    if wtype == "radar":
        theta = w.get("theta") or enc["x"] or (df.columns[0] if len(df.columns) > 0 else None)
        radius = w.get("radius") or enc["y"] or (df.columns[1] if len(df.columns) > 1 else None)
        series_col = enc["color"] if enc["color"] in df.columns else None
        if theta and radius:
            fig = go.Figure()
            if series_col:
                for series_name, part in df.groupby(series_col):
                    fig.add_trace(go.Scatterpolar(
                        r=part[radius],
                        theta=part[theta],
                        fill='toself',
                        name=str(series_name),
                        opacity=.55,
                    ))
            else:
                fig.add_trace(go.Scatterpolar(
                    r=df[radius],
                    theta=df[theta],
                    fill='toself',
                    name=w.get("title") or "Radar",
                    opacity=.55,
                ))
            fig.update_polars(radialaxis=dict(visible=True, gridcolor='rgba(226,232,240,.55)'))
            _apply_premium_layout(fig, height=height, show_legend=True, x_grid=False, y_grid=False)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_radar")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    if wtype == "polar_bar":
        theta = w.get("theta") or enc["x"] or (df.columns[0] if len(df.columns) > 0 else None)
        radius = w.get("radius") or enc["y"] or (df.columns[1] if len(df.columns) > 1 else None)
        color = enc["color"] if enc["color"] in df.columns else None
        if theta and radius:
            fig = px.bar_polar(df, r=radius, theta=theta, color=color)
            _apply_premium_layout(fig, height=height, show_legend=bool(color), x_grid=False, y_grid=False)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_polar")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    if wtype == "sankey":
        source = w.get("source") or ("source" if "source" in df.columns else None)
        target = w.get("target") or ("target" if "target" in df.columns else None)
        value = w.get("value") or enc["value"] or ("value" if "value" in df.columns else None)
        if source and target and value and all(c in df.columns for c in [source, target, value]):
            labels = list(pd.unique(pd.concat([df[source], df[target]], ignore_index=True)))
            index = {label: i for i, label in enumerate(labels)}
            fig = go.Figure(go.Sankey(
                arrangement="snap",
                node=dict(
                    pad=16,
                    thickness=18,
                    line=dict(color="rgba(255,255,255,.75)", width=1),
                    label=[str(x) for x in labels],
                ),
                link=dict(
                    source=[index[x] for x in df[source]],
                    target=[index[x] for x in df[target]],
                    value=df[value],
                ),
            ))
            _apply_premium_layout(fig, height=height, show_legend=False, x_grid=False, y_grid=False)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_sankey")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    if wtype in ("combo", "combo_bar_line"):
        x = enc["x"] or (df.columns[0] if len(df.columns) > 0 else None)
        y1 = enc["y"] or (df.columns[1] if len(df.columns) > 1 else None)
        y2 = w.get("y2") or (df.columns[2] if len(df.columns) > 2 else None)
        if x and y1 and y2:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df[x], y=df[y1], name=y1, yaxis='y1', marker=dict(opacity=.88)))
            fig.add_trace(go.Scatter(x=df[x], y=df[y2], name=y2, yaxis='y2', mode='lines+markers', line=dict(color='#ff7380', width=3, shape='spline')))
            fig.update_layout(
                yaxis=dict(title=y1),
                yaxis2=dict(title=y2, overlaying='y', side='right', showgrid=False),
            )
            _apply_premium_layout(fig, height=height, show_legend=True, x_grid=False, y_grid=True, unified_hover=True)
            st.plotly_chart(fig, use_container_width=True, key=f"{chart_key}_combo")
        else:
            st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)
        return

    st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)


def _render_table_widget(w: dict):
    cols = w.get("columns", [])
    rows = w.get("rows", [])
    if rows and isinstance(rows, list):
        df = pd.DataFrame(rows, columns=cols if cols else None)
    else:
        df = _to_df(w.get("data"))
    if df.empty:
        st.caption("Không có dữ liệu.")
    else:
        st.dataframe(_arrow_safe_df(df), use_container_width=True, hide_index=True)


def _render_insight_widget(w: dict):
    kf = w.get("key_findings") or []
    rk = w.get("risks") or []
    rc = w.get("recommendations") or []

    c1, c2, c3 = st.columns(3, gap="large")

    with c1:
        block_start("Key findings", "Những điểm nổi bật")
        if kf:
            for x in kf:
                st.markdown(f"- {x}")
        else:
            st.caption("(none)")
        block_end()

    with c2:
        block_start("Risks", "Rủi ro / bất thường")
        if rk:
            for x in rk:
                st.markdown(f"- {x}")
        else:
            st.caption("(none)")
        block_end()

    with c3:
        block_start("Recommendations", "Khuyến nghị")
        if rc:
            for x in rc:
                st.markdown(f"- {x}")
        else:
            st.caption("(none)")
        block_end()


def _render_summary_card_widget(w: dict):
    tone = str(w.get("tone") or "neutral").strip().lower()
    title = str(w.get("title") or "Tom tat nhanh").strip()
    value = str(w.get("value") or "-").strip()
    note = str(w.get("note") or "").strip()
    eyebrow = str(w.get("eyebrow") or "Summary").strip()
    st.markdown(
        f"""
        <div class="summary-card {tone}">
            <div class="summary-eyebrow">{eyebrow}</div>
            <div class="summary-value">{value}</div>
            <div class="block-title" style="margin-bottom:8px;">{title}</div>
            <div class="summary-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_stat_list_widget(w: dict):
    title = str(w.get("title") or "Chi so noi bat").strip()
    items = w.get("items") if isinstance(w.get("items"), list) else []
    rows = []
    for item in items[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        note = str(item.get("note") or "").strip()
        if not label and not value:
            continue
        rows.append(
            f"""
            <div class="stat-row">
                <div>
                    <div class="stat-label">{label or "-"}</div>
                    {f'<div class="block-subtitle" style="margin:4px 0 0 0;">{note}</div>' if note else ''}
                </div>
                <div class="stat-value">{value or "-"}</div>
            </div>
            """
        )
    st.markdown(
        f"""
        <div class="stat-list">
            <div class="stat-list-title">{title}</div>
            {''.join(rows) if rows else '<div class="summary-note">Khong co du lieu.</div>'}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_narrative_card_widget(w: dict):
    tone = str(w.get("tone") or "neutral").strip().lower()
    title = str(w.get("title") or "Nhan xet").strip()
    body = str(w.get("body") or w.get("text") or "").strip()
    st.markdown(
        f"""
        <div class="narrative-card {tone}">
            <div class="narrative-title">{title}</div>
            <div class="narrative-body">{body or '-'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_badge_list_widget(w: dict):
    items = w.get("items") if isinstance(w.get("items"), list) else []
    title = str(w.get("title") or "Diem can luu y").strip()
    block_start(title)
    if items:
        st.markdown(
            "".join([f'<span class="insight-pill">{str(item)}</span>' for item in items[:10]]),
            unsafe_allow_html=True,
        )
    else:
        st.caption("Khong co du lieu.")
    block_end()


def _render_filter_panel(container_spec: dict):
    block_start("Bộ lọc", "Slicers (hiển thị theo spec)")
    filters = container_spec.get("filters") or []
    if not filters:
        st.caption("Không có bộ lọc.")
        block_end()
        return

    for f in filters:
        key = f.get("key", "")
        label = f.get("label") or key
        value = f.get("value")
        st.markdown(f"- **{label}**: `{value}`")
    block_end()


def _render_last_updated(meta: dict, w: dict):
    txt = w.get("text") or meta.get("last_updated") or ""
    block_start("Trạng thái", "Last calculated / updated")
    if txt:
        st.info(txt)
    else:
        st.caption("Không có thông tin cập nhật.")
    block_end()


def _render_kpi_row(spec: dict, widgets: dict):
    w = widgets.get("kpi_row")
    if not w or (w.get("type") != "kpi_row"):
        return

    kpi_ids = w.get("kpi_ids", [])
    kpis = {k.get("id"): k for k in (spec.get("kpis") or []) if isinstance(k, dict) and k.get("id")}

    show = kpi_ids[:8] if isinstance(kpi_ids, list) else []
    if not show:
        return

    per_row = 5 if len(show) >= 5 else 4
    for i in range(0, len(show), per_row):
        row = show[i : i + per_row]
        cols = st.columns(per_row, gap="small")
        for j in range(per_row):
            with cols[j]:
                if j < len(row):
                    k = kpis.get(row[j], {}) or {}
                    label = k.get("label") or row[j]
                    value = _fmt_value(k.get("value"), k.get("unit"))
                    note = k.get("delta_label") or k.get("note") or ""
                    delta = k.get("delta")
                    if isinstance(delta, (int, float)):
                        trend_class = "delta-up" if delta > 0 else "delta-down" if delta < 0 else ""
                        trend_char = "⇧" if delta > 0 else "⇩" if delta < 0 else ""
                        note = f'<span class="{trend_class}">{abs(delta)*100:.0f}% {trend_char}</span> ' + (note if note else "")
                    kpi_card(label, value, note)
                else:
                    st.empty()


# =========================================================
# Renderers for v2 / v3
# =========================================================
def _render_dashboard_body(container_spec: dict, tab_key: str = "tab"):
    """
    Render phần thân của một dashboard/container theo Grid Layer
    """
    widgets = container_spec.get("widgets") or {}
    if not isinstance(widgets, dict):
        st.error("Spec.widgets không hợp lệ.")
        return

    _render_kpi_row(container_spec, widgets)
    st.markdown("")

    layout = container_spec.get("layout") or []

    # Kiểm tra format mới: layout là list các list (mỗi phần tử con là 1 row)
    is_grid = False
    if layout and isinstance(layout, list) and isinstance(layout[0], list):
        is_grid = True
    elif layout and isinstance(layout, list) and isinstance(layout[0], dict) and "columns" in layout[0]:
        is_grid = True
        # Parse [{row: 1, columns: [{id: 'w1', width: 2}, {id: 'w2', width: 1}]}] 
        # to [[{id: 'w1', width: 2}, {id: 'w2', width: 1}]]
        layout = [r.get("columns", []) for r in layout]

    if is_grid:
        for row_idx, row in enumerate(layout):
            if not row: continue
            # Normalize width
            widths = [col.get("width") or 1 for col in row]
            st_cols = st.columns(widths, gap="large")
            for col_idx, col_spec in enumerate(row):
                wid = col_spec.get("id")
                w = widgets.get(wid)
                if not w: continue
                with st_cols[col_idx]:
                    wtype = (w.get("type") or "").lower().strip()
                    if wtype == "filter_panel":
                        _render_filter_panel(container_spec)
                    elif wtype in ("last_updated", "last_updated_card", "last_updated_widget"):
                        _render_last_updated(container_spec.get("meta") or {}, w)
                    elif wtype in ("insights", "insight_block"):
                        st.markdown("## Insights")
                        _render_insight_widget(w)
                    elif wtype == "summary_card":
                        _render_summary_card_widget(w)
                    elif wtype == "stat_list":
                        _render_stat_list_widget(w)
                    elif wtype in ("narrative_card", "callout"):
                        _render_narrative_card_widget(w)
                    elif wtype == "badge_list":
                        _render_badge_list_widget(w)
                    elif wtype == "kpi_row":
                        pass # already rendered top
                    else:
                        block_start(w.get("title") or "", w.get("subtitle"))
                        if wtype == "table":
                            _render_table_widget(w)
                        else:
                            _render_plotly_chart(w, chart_key=f"{tab_key}_{wid}_{row_idx}_{col_idx}")
                        if w.get("insight"):
                            st.caption(w.get("insight"))
                        block_end()
    else:
        # Tương thích ngược: Fallback style 2 cột cũ
        main_left, right_panel = st.columns([3, 1], gap="large")

        with main_left:
            chart_like_ids = []
            for wid, w in widgets.items():
                t = (w.get("type") or "").lower().strip()
                if t in ("kpi_row", "filter_panel", "last_updated_card", "insight_block"):
                    continue
                chart_like_ids.append(wid)

            if not chart_like_ids:
                st.warning("Không có widget chart/table để hiển thị.")
            else:
                c1, c2 = st.columns(2, gap="large")
                for idx, wid in enumerate(chart_like_ids):
                    w = widgets.get(wid) or {}
                    title = w.get("title") or ""
                    subtitle = w.get("subtitle")
                    insight = w.get("insight")
                    wtype = (w.get("type") or "").lower().strip()

                    with (c1 if idx % 2 == 0 else c2):
                        if wtype in {"summary_card", "stat_list", "narrative_card", "callout", "badge_list"}:
                            if wtype == "summary_card":
                                _render_summary_card_widget(w)
                            elif wtype == "stat_list":
                                _render_stat_list_widget(w)
                            elif wtype in ("narrative_card", "callout"):
                                _render_narrative_card_widget(w)
                            elif wtype == "badge_list":
                                _render_badge_list_widget(w)
                            if insight:
                                st.caption(insight)
                            continue

                        block_start(title, subtitle)
                        if wtype == "table":
                            _render_table_widget(w)
                        else:
                            _render_plotly_chart(w, chart_key=f"{tab_key}_{wid}_{idx}")
                        if insight:
                            st.caption(insight)
                        block_end()

        with right_panel:
            fp = widgets.get("filter_panel")
            if fp and (fp.get("type") == "filter_panel"):
                _render_filter_panel(container_spec)

            lu = widgets.get("last_updated") or widgets.get("last_updated_card") or widgets.get("last_updated_widget")
            local_meta = container_spec.get("meta") or {}
            if lu and (lu.get("type") == "last_updated_card"):
                _render_last_updated(local_meta, lu)
            elif local_meta.get("last_updated"):
                _render_last_updated(local_meta, {"type": "last_updated_card", "text": local_meta.get("last_updated")})

        ins = widgets.get("insights")
        if ins and (ins.get("type") == "insight_block"):
            st.markdown("## Insights")
            _render_insight_widget(ins)

    dn = container_spec.get("data_notes")
    if dn:
        st.markdown("## Data notes")
        block_start("Ghi chú dữ liệu", "Nguồn/giả định/chất lượng dữ liệu")
        st.json(dn)
        block_end()


_NON_CHART_WIDGET_TYPES = {
    "kpi_row",
    "filter_panel",
    "last_updated",
    "last_updated_card",
    "last_updated_widget",
    "insights",
    "insight_block",
    "table",
    "summary_card",
    "stat_list",
    "narrative_card",
    "callout",
    "badge_list",
}


def _pick_main_widget_ids(widgets: dict) -> list[str]:
    preferred = []
    for wid, w in (widgets or {}).items():
        if not isinstance(w, dict):
            continue
        wtype = (w.get("type") or "").lower().strip()
        if wtype in _NON_CHART_WIDGET_TYPES:
            continue
        preferred.append(wid)
    return preferred[:2]


def _pick_chart_widget_ids(widgets: dict, limit: int | None = None) -> list[str]:
    candidates = []
    for wid, w in (widgets or {}).items():
        if not isinstance(w, dict):
            continue
        wtype = (w.get("type") or "").lower().strip()
        if wtype in _NON_CHART_WIDGET_TYPES:
            continue
        candidates.append(wid)
    priority = [
        "hero_main",
        "compare_main",
        "detail_secondary",
        "compare_secondary",
        "hero_support_1",
        "hero_support_2",
    ]
    out = sorted(
        candidates,
        key=lambda wid: (priority.index(wid) if wid in priority else len(priority), candidates.index(wid)),
    )
    if limit is not None:
        return out[:limit]
    return out


def _pick_support_widget_ids(widgets: dict, limit: int | None = None) -> list[str]:
    candidates = []
    for wid, w in (widgets or {}).items():
        if not isinstance(w, dict):
            continue
        wtype = (w.get("type") or "").lower().strip()
        if wtype in {"summary_card", "stat_list", "narrative_card", "callout", "badge_list"}:
            candidates.append(wid)
    priority = ["hero_support_1", "hero_support_2", "hero_support_3"]
    out = sorted(
        candidates,
        key=lambda wid: (priority.index(wid) if wid in priority else len(priority), candidates.index(wid)),
    )
    if limit is not None:
        return out[:limit]
    return out


def _pick_first_table_widget_id(widgets: dict) -> str | None:
    if isinstance((widgets or {}).get("detail_table"), dict) and ((widgets or {}).get("detail_table", {}).get("type") or "").lower().strip() == "table":
        return "detail_table"
    for wid, w in (widgets or {}).items():
        if isinstance(w, dict) and (w.get("type") or "").lower().strip() == "table":
            return wid
    return None


def _strip_table_alias_in_ui_text(s: str) -> str:
    s = str(s or "").strip()
    s = re.sub(r"\bT\d+\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" ,;:-")
    return s

def _render_display_dashboard_tab(raw_tab: dict, root_meta: dict, tab_key: str):
    display = raw_tab.get("display") if isinstance(raw_tab.get("display"), dict) else {}
    widgets = raw_tab.get("widgets") if isinstance(raw_tab.get("widgets"), dict) else {}

    title = _strip_table_alias_in_ui_text(display.get("title") or raw_tab.get("title") or "Báo cáo")
    subtitle = _strip_table_alias_in_ui_text(display.get("subtitle") or raw_tab.get("summary") or "")
    recommendation = (display.get("recommendation") or "optional").lower()
    badge = "Đề xuất" if recommendation == "recommended" else "Tùy chọn"

    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)
    st.markdown(f"**Loại hiển thị:** {badge}")

    highlights = display.get("highlights") if isinstance(display.get("highlights"), list) else []
    if highlights:
        block_start("Điểm chính cần chú ý")
        for item in highlights[:3]:
            st.markdown(f"- {_strip_table_alias_in_ui_text(item)}")
        block_end()

    metrics = display.get("metrics") if isinstance(display.get("metrics"), list) else []
    if metrics:
        cols = st.columns(min(len(metrics), 4), gap="small")
        for idx, metric in enumerate(metrics[:4]):
            with cols[idx]:
                kpi_card(metric.get("label") or "Chỉ số", str(metric.get("value") or "-"), metric.get("note") or "")

    main_section = display.get("main_section") if isinstance(display.get("main_section"), dict) else {}
    main_widget_ids = _pick_main_widget_ids(widgets)
    if main_section or main_widget_ids:
        block_start(main_section.get("title") or "Nội dung chính", main_section.get("description") or None)
        if main_widget_ids:
            cols = st.columns(len(main_widget_ids), gap="large")
            for idx, wid in enumerate(main_widget_ids):
                with cols[idx]:
                    _render_plotly_chart(widgets.get(wid) or {}, chart_key=f"{tab_key}_{wid}_display")
                    if (widgets.get(wid) or {}).get("insight"):
                        st.caption((widgets.get(wid) or {}).get("insight"))
        else:
            st.caption("Không có nội dung trực quan phù hợp để hiển thị thêm.")
        block_end()

    explanation = display.get("explanation") if isinstance(display.get("explanation"), dict) else {}
    block_start("Diễn giải dễ hiểu")
    what_is_happening = _strip_table_alias_in_ui_text(explanation.get('what_is_happening') or 'Báo cáo này tóm tắt những gì đang xuất hiện trong dữ liệu hiện có.')
    what_to_notice = _strip_table_alias_in_ui_text(explanation.get('what_to_notice') or 'Có một vài điểm cần chú ý thêm khi đọc dữ liệu này.')
    what_to_do_next = _strip_table_alias_in_ui_text(explanation.get('what_to_do_next') or 'Bạn nên xem thêm phần chi tiết để đối chiếu các mục quan trọng.')
    st.markdown(f"**Điều đang diễn ra**\n\n{what_is_happening}")
    st.markdown(f"**Điều cần chú ý**\n\n{what_to_notice}")
    st.markdown(f"**Nên xem tiếp điều gì**\n\n{what_to_do_next}")
    block_end()

    table_wid = _pick_first_table_widget_id(widgets)
    if table_wid:
        block_start(display.get("detail_section_title") or "Chi tiết dữ liệu")
        _render_table_widget(widgets.get(table_wid) or {})
        block_end()

    footer_note = _strip_table_alias_in_ui_text(display.get("footer_note") or "Báo cáo được tổng hợp từ dữ liệu bạn đã tải lên.")
    st.caption(footer_note)

    debug_meta = raw_tab.get("debug_meta") if isinstance(raw_tab.get("debug_meta"), dict) else {}
    if debug_meta:
        with st.expander("🛠 Chú thích kỹ thuật cho dev"):
            st.json(debug_meta)


def _render_widget_core_v2(w: dict, chart_key: str, meta: dict | None = None):
    wtype = (w.get("type") or "").lower().strip()
    if wtype == "table":
        _render_table_widget(w)
    elif wtype == "filter_panel":
        _render_filter_panel({"filters": w.get("filters") or []})
    elif wtype == "summary_card":
        _render_summary_card_widget(w)
    elif wtype == "stat_list":
        _render_stat_list_widget(w)
    elif wtype in ("narrative_card", "callout"):
        _render_narrative_card_widget(w)
    elif wtype == "badge_list":
        _render_badge_list_widget(w)
    elif wtype in ("insights", "insight_block"):
        _render_insight_widget(w)
    elif wtype in ("last_updated", "last_updated_card", "last_updated_widget"):
        _render_last_updated(meta or {}, w)
    else:
        _render_plotly_chart(w, chart_key=chart_key)


def _render_widget_card_v2(w: dict, chart_key: str, meta: dict | None = None):
    wtype = (w.get("type") or "").lower().strip()
    if wtype in {"summary_card", "stat_list", "narrative_card", "callout", "badge_list"}:
        _render_widget_core_v2(w, chart_key=chart_key, meta=meta)
        return

    block_start(w.get("title") or "", w.get("subtitle"))
    _render_widget_core_v2(w, chart_key=chart_key, meta=meta)
    if w.get("insight"):
        st.caption(w.get("insight"))
    block_end()


def _render_display_header_v2(title: str, subtitle: str, badges: list[str], recommendation: str):
    pills = ["De xuat" if recommendation == "recommended" else "Tuy chon"]
    pills.extend([_strip_table_alias_in_ui_text(x) for x in badges[:4]])
    pills_html = "".join([f'<span class="shell-badge">{p}</span>' for p in pills if str(p).strip()])
    st.markdown(
        f"""
        <div class="dash-shell">
            <div class="shell-header">
                <div>
                    <div class="shell-kicker">Dashboard Story</div>
                    <div class="shell-title">{title}</div>
                    <div class="shell-subtitle">{subtitle}</div>
                </div>
                <div class="shell-badges">{pills_html}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_hero_statement_v2(display: dict):
    text = _strip_table_alias_in_ui_text(display.get("hero_statement") or "")
    if text:
        st.markdown(f'<div class="hero-statement">{text}</div>', unsafe_allow_html=True)


def _render_quick_actions_v2(display: dict):
    actions = display.get("quick_actions") if isinstance(display.get("quick_actions"), list) else []
    if not actions:
        return
    chips = "".join([f'<span class="quick-action">{_strip_table_alias_in_ui_text(a)}</span>' for a in actions[:4]])
    st.markdown(f'<div class="quick-actions">{chips}</div>', unsafe_allow_html=True)


def _render_filter_summary_v2(raw_tab: dict):
    filters = raw_tab.get("filters") if isinstance(raw_tab.get("filters"), list) else []
    if not filters:
        return
    block_start("Bo loc dang ap dung", "Pham vi du lieu hien tai")
    chips = []
    for item in filters[:8]:
        if not isinstance(item, dict):
            continue
        label = _strip_table_alias_in_ui_text(item.get("label") or item.get("key") or "Bo loc")
        value = _strip_table_alias_in_ui_text(item.get("value") or "")
        if label and value:
            chips.append(f'<span class="insight-pill">{label}: {value}</span>')
    if chips:
        st.markdown("".join(chips), unsafe_allow_html=True)
    else:
        st.caption("Khong co bo loc dang ap dung.")
    block_end()


def _render_side_note_cards_v2(display: dict, tone: str = "accent"):
    notes = display.get("side_notes") if isinstance(display.get("side_notes"), list) else []
    for idx, note in enumerate(notes[:3], start=1):
        _render_narrative_card_widget(
            {
                "type": "narrative_card",
                "title": f"Goc nhin {idx}",
                "body": _strip_table_alias_in_ui_text(note),
                "tone": tone if idx == 1 else "neutral",
            }
        )


def _render_explanation_cards_v2(display: dict):
    explanation = display.get("explanation") if isinstance(display.get("explanation"), dict) else {}
    cards = [
        ("Dieu dang dien ra", explanation.get("what_is_happening"), "accent"),
        ("Dieu can chu y", explanation.get("what_to_notice"), "warn"),
        ("Nen xem tiep", explanation.get("what_to_do_next"), "good"),
    ]
    cols = st.columns(3, gap="large")
    for idx, (title, body, tone) in enumerate(cards):
        with cols[idx]:
            _render_narrative_card_widget(
                {
                    "type": "narrative_card",
                    "title": title,
                    "body": _strip_table_alias_in_ui_text(body or ""),
                    "tone": tone,
                }
            )


def _render_remaining_widgets_v2(widgets: dict, used_ids: set[str], tab_key: str, meta: dict):
    leftovers = [wid for wid in widgets.keys() if wid not in used_ids and wid != "kpi_row"]
    if not leftovers:
        return
    st.markdown("### Phan tich bo sung")
    cols = st.columns(2, gap="large")
    for idx, wid in enumerate(leftovers[:4]):
        with cols[idx % 2]:
            _render_widget_card_v2(widgets.get(wid) or {}, chart_key=f"{tab_key}_{wid}_extra", meta=meta)


def _render_display_dashboard_tab(raw_tab: dict, root_meta: dict, tab_key: str):
    display = raw_tab.get("display") if isinstance(raw_tab.get("display"), dict) else {}
    widgets = raw_tab.get("widgets") if isinstance(raw_tab.get("widgets"), dict) else {}
    meta = root_meta if isinstance(root_meta, dict) else {}

    title = _strip_table_alias_in_ui_text(display.get("title") or raw_tab.get("title") or "Bao cao")
    subtitle = _strip_table_alias_in_ui_text(display.get("subtitle") or raw_tab.get("summary") or "")
    recommendation = (display.get("recommendation") or "optional").lower()
    shell_id = str(display.get("shell_id") or display.get("form_type") or "overview_premium").strip().lower()
    badges = display.get("badge_items") if isinstance(display.get("badge_items"), list) else []

    _render_display_header_v2(title, subtitle, badges, recommendation)
    _render_hero_statement_v2(display)

    metrics = display.get("metrics") if isinstance(display.get("metrics"), list) else []
    if metrics:
        cols = st.columns(min(len(metrics), 5), gap="small")
        for idx, metric in enumerate(metrics[:5]):
            with cols[idx]:
                kpi_card(metric.get("label") or "Chi so", str(metric.get("value") or "-"), metric.get("note") or "")

    _render_quick_actions_v2(display)
    _render_filter_summary_v2(raw_tab)

    chart_ids = _pick_chart_widget_ids(widgets)
    support_ids = _pick_support_widget_ids(widgets)
    table_wid = _pick_first_table_widget_id(widgets)
    insight_id = next(
        (
            wid for wid, w in widgets.items()
            if isinstance(w, dict) and (w.get("type") or "").lower().strip() in {"insights", "insight_block"}
        ),
        None,
    )

    used_ids: set[str] = set()
    if "filter_panel" in widgets:
        used_ids.add("filter_panel")
    hero_chart = chart_ids[0] if chart_ids else None
    secondary_charts = chart_ids[1:]

    if shell_id in {"overview_premium", "comparison_premium", "ranking_board", "analysis_lab"}:
        left, right = st.columns([1.9, 1.05], gap="large")
        with left:
            if hero_chart:
                used_ids.add(hero_chart)
                _render_widget_card_v2(widgets.get(hero_chart) or {}, chart_key=f"{tab_key}_{hero_chart}_hero", meta=meta)
            else:
                block_start("Tong quan hinh anh")
                st.caption("Chua co bieu do phu hop de hien thi.")
                block_end()
        with right:
            if support_ids:
                for wid in support_ids[:2]:
                    used_ids.add(wid)
                    _render_widget_core_v2(widgets.get(wid) or {}, chart_key=f"{tab_key}_{wid}_side", meta=meta)
            else:
                _render_side_note_cards_v2(display)
        if secondary_charts[:2]:
            cols = st.columns(len(secondary_charts[:2]), gap="large")
            for idx, wid in enumerate(secondary_charts[:2]):
                with cols[idx]:
                    used_ids.add(wid)
                    _render_widget_card_v2(widgets.get(wid) or {}, chart_key=f"{tab_key}_{wid}_secondary", meta=meta)

    elif shell_id in {"trend_story", "ops_command"}:
        if hero_chart:
            used_ids.add(hero_chart)
            _render_widget_card_v2(widgets.get(hero_chart) or {}, chart_key=f"{tab_key}_{hero_chart}_hero", meta=meta)
        if secondary_charts[:2]:
            cols = st.columns(len(secondary_charts[:2]), gap="large")
            for idx, wid in enumerate(secondary_charts[:2]):
                with cols[idx]:
                    used_ids.add(wid)
                    _render_widget_card_v2(widgets.get(wid) or {}, chart_key=f"{tab_key}_{wid}_trend", meta=meta)
        if support_ids:
            cols = st.columns(min(len(support_ids[:3]), 3), gap="large")
            for idx, wid in enumerate(support_ids[:3]):
                with cols[idx]:
                    used_ids.add(wid)
                    _render_widget_core_v2(widgets.get(wid) or {}, chart_key=f"{tab_key}_{wid}_support", meta=meta)
        else:
            _render_explanation_cards_v2(display)

    elif shell_id in {"quality_review", "detail_explorer"}:
        if support_ids:
            cols = st.columns(min(len(support_ids[:3]), 3), gap="large")
            for idx, wid in enumerate(support_ids[:3]):
                with cols[idx]:
                    used_ids.add(wid)
                    _render_widget_core_v2(widgets.get(wid) or {}, chart_key=f"{tab_key}_{wid}_support", meta=meta)
        else:
            _render_side_note_cards_v2(display, tone="warn" if shell_id == "quality_review" else "accent")

        left, right = st.columns([1.7, 1.1], gap="large")
        with left:
            if table_wid:
                used_ids.add(table_wid)
                block_start(display.get("detail_section_title") or "Chi tiet du lieu")
                _render_table_widget(widgets.get(table_wid) or {})
                block_end()
            elif hero_chart:
                used_ids.add(hero_chart)
                _render_widget_card_v2(widgets.get(hero_chart) or {}, chart_key=f"{tab_key}_{hero_chart}_body", meta=meta)
        with right:
            for wid in chart_ids[:2]:
                if wid in used_ids:
                    continue
                used_ids.add(wid)
                _render_widget_card_v2(widgets.get(wid) or {}, chart_key=f"{tab_key}_{wid}_detail", meta=meta)

    if table_wid and table_wid not in used_ids and shell_id not in {"quality_review", "detail_explorer"}:
        used_ids.add(table_wid)
        block_start(display.get("detail_section_title") or "Chi tiet du lieu")
        _render_table_widget(widgets.get(table_wid) or {})
        block_end()

    if insight_id and insight_id not in used_ids:
        used_ids.add(insight_id)
        st.markdown("### Tong hop nhanh")
        _render_insight_widget(widgets.get(insight_id) or {})
    else:
        _render_explanation_cards_v2(display)

    _render_remaining_widgets_v2(widgets, used_ids, tab_key, meta)

    footer_note = _strip_table_alias_in_ui_text(display.get("footer_note") or "Bao cao duoc tong hop tu du lieu tai len.")
    st.caption(footer_note)

    debug_meta = raw_tab.get("debug_meta") if isinstance(raw_tab.get("debug_meta"), dict) else {}
    if debug_meta:
        with st.expander("Thong tin ky thuat cho dev"):
            st.json(debug_meta)


def _build_tab_container(tab_spec: dict, root_meta: dict) -> dict:
    """
    Chuẩn hóa tab spec v3 để tái sử dụng renderer body hiện có.
    """
    local_meta = {
        "title": tab_spec.get("title") or tab_spec.get("report_id") or "Dashboard",
        "subtitle": tab_spec.get("summary") or "",
        "time_range": root_meta.get("time_range") or "",
        "last_updated": root_meta.get("last_updated") or "",
        "tables_used": root_meta.get("tables_used") or [],
    }

    return {
        "meta": local_meta,
        "filters": tab_spec.get("filters") or [],
        "kpis": tab_spec.get("kpis") or [],
        "layout": tab_spec.get("layout") or [],
        "widgets": tab_spec.get("widgets") or {},
        "data_notes": tab_spec.get("data_notes") or {},
    }


def _render_dashboard_v3(spec: dict):
    meta = spec.get("meta") or {}
    title = meta.get("title") or "Dashboard"
    subtitle = meta.get("subtitle") or ""
    time_range = meta.get("time_range") or ""

    st.title(title)
    if subtitle:
        st.caption(subtitle)
    if time_range:
        st.caption(time_range)

    tabs = spec.get("tabs") or []
    if not isinstance(tabs, list) or not tabs:
        st.warning("Spec v3 không có tab nào để hiển thị.")
        st.json(spec)
        return

    labels = []
    normalized_tabs = []

    for idx, tab in enumerate(tabs):
        if not isinstance(tab, dict):
            continue

        label = (
            tab.get("title")
            or tab.get("tab_title")
            or tab.get("report_id")
            or f"Tab {idx + 1}"
        )
        labels.append(label)
        normalized_tabs.append(tab)

    if not normalized_tabs:
        st.warning("Danh sách tabs không hợp lệ.")
        st.json(spec)
        return

    ui_tabs = st.tabs(labels)

    for tab_idx, (ui_tab, raw_tab) in enumerate(zip(ui_tabs, normalized_tabs)):
        with ui_tab:
            raw_tab_id = raw_tab.get("tab_id") or f"tab_{tab_idx}"
            if isinstance(raw_tab.get("display"), dict):
                _render_display_dashboard_tab(raw_tab, meta, tab_key=f"{raw_tab_id}_{tab_idx}")
            else:
                tab_container = _build_tab_container(raw_tab, meta)
                _render_dashboard_body(tab_container, tab_key=f"{raw_tab_id}_{tab_idx}")

# =========================================================
# Main render entry
# =========================================================
def _render_dashboard_v2(spec: dict):
    """
    Fallback support for v2 layout where widgets/kpis are at the root level.
    """
    tab_container = _build_tab_container(spec, spec.get("meta") or {})
    title = tab_container["meta"]["title"] or "Dashboard v2"
    st.title(title)
    _render_dashboard_body(tab_container, tab_key="legacy_v2")

def render_dashboard(spec: dict):
    """
    Hỗ trợ:
    - DashboardSpec v2: version == "2.0"
    - DashboardSpec v3: version == "3.0" hoặc "3.1" 
    """
    inject_dashboard_css()

    if not isinstance(spec, dict):
        st.error("Spec không hợp lệ.")
        return

    version = spec.get("version")

    if version == "2.0":
        _render_dashboard_v2(spec)
        return

    if version in {"3.0", "3.1"}:
        _render_dashboard_v3(spec)
        return

    st.error(f"Spec version không hỗ trợ: {version}")
    st.json(spec)

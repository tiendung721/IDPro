import io
import re
import time
from typing import Any, List, Optional, Tuple

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src import api
from src.auth_guard import require_user_login
from src.dashboard_renderer import render_dashboard
from src.state import init_state
from src.ui import sections_editor_with_add_delete, sections_to_df_1based, render_ba_analysis_workspace


# =========================================================
# Page config + init
# =========================================================
st.set_page_config(page_title="User – AI Agent", layout="wide")
init_state()
require_user_login()


# =========================================================
# Framework injection + Animated shell
# =========================================================
def inject_frameworks():
    components.html(
        """
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" rel="stylesheet">
        <style>
          html, body, [class*="css"] {
            font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial !important;
          }
        </style>
        """,
        height=0,
    )


inject_frameworks()

st.markdown(
    """
    <div class="app-shell-bg"></div>
    <div class="grid-noise"></div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# Premium Theme CSS (enhanced animations)
# =========================================================
st.markdown(
    """
<style>
/* ======================================================
   Layout
====================================================== */
.block-container {
  padding-top: 1.05rem;
  padding-bottom: 3rem;
  max-width: 1360px;
  position: relative;
  z-index: 2;
}

[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stHeader"] { background: rgba(255,255,255,0.0) !important; }
section[data-testid="stSidebar"] > div { padding-top: .75rem; }

/* ======================================================
   Theme variables
====================================================== */
:root{
  --bg0:#070b16;
  --bg1:#0b1220;
  --card: rgba(255,255,255,0.88);
  --card2: rgba(255,255,255,0.80);
  --stroke: rgba(148,163,184,0.30);
  --muted:#64748b;
  --text:#0f172a;
  --brand:#4f46e5;
  --brand2:#06b6d4;
  --ok:#10b981;
  --warn:#f59e0b;
  --bad:#ef4444;
  --shadow: 0 18px 50px rgba(2,6,23,.12);
  --shadow2: 0 12px 28px rgba(2,6,23,.10);
  --r: 18px;
}

/* ======================================================
   Page background
====================================================== */
html, body, .stApp {
  background: #ffffff !important;
}
.app-shell-bg{
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.app-shell-bg::before,
.app-shell-bg::after{
  content:"";
  position:absolute;
  width: 42vw;
  height: 42vw;
  border-radius: 999px;
  filter: blur(82px);
  opacity: .16;
  animation: floatOrb 16s ease-in-out infinite;
}

.app-shell-bg::before{
  top: -10vw;
  left: -8vw;
  background: radial-gradient(circle, rgba(79,70,229,.95) 0%, rgba(79,70,229,.18) 45%, transparent 72%);
}

.app-shell-bg::after{
  right: -10vw;
  top: 6vw;
  background: radial-gradient(circle, rgba(6,182,212,.95) 0%, rgba(6,182,212,.16) 42%, transparent 72%);
  animation-delay: -8s;
}

.grid-noise{
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background-image:
    linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px);
  background-size: 38px 38px;
  mask-image: radial-gradient(circle at 50% 20%, rgba(0,0,0,.9), transparent 80%);
  opacity: .28;
}

/* ======================================================
   Hero
====================================================== */
.hero {
  padding: 1.6rem 1.65rem;
  border-radius: 24px;
  background:
    radial-gradient(1200px circle at 12% 18%, rgba(255,255,255,0.20), transparent 55%),
    radial-gradient(900px circle at 88% 10%, rgba(255,255,255,0.13), transparent 60%),
    linear-gradient(120deg, #4f46e5, #06b6d4);
  color: white;
  margin-bottom: 1rem;
  box-shadow: 0 22px 58px rgba(2,6,23,0.28);
  position: relative;
  overflow: hidden;
  animation: riseSoft .55s ease-out both;
}

.hero:before{
  content:"";
  position:absolute;
  inset:auto -20% -65% auto;
  width: 340px;
  height: 340px;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(255,255,255,.24), transparent 65%);
  animation: bob 5.5s ease-in-out infinite;
  pointer-events:none;
}

.hero:after{
  content:"";
  position:absolute;
  inset:-60px -30px auto -30px;
  height:160px;
  background: radial-gradient(900px circle at 22% 40%, rgba(255,255,255,.22), transparent 60%);
  transform: rotate(-3deg);
  pointer-events:none;
}

.hero h1 {
  font-size: 2.05rem;
  margin: 0 0 .35rem 0;
  letter-spacing: -0.02em;
  font-weight: 900;
}

.hero p { margin: 0; opacity: .96; }

/* ======================================================
   Pills / badges
====================================================== */
.pill {
  display:inline-flex;
  align-items:center;
  gap:.45rem;
  padding:.28rem .68rem;
  border-radius:999px;
  background: rgba(255,255,255,0.16);
  border: 1px solid rgba(255,255,255,0.22);
  margin-right:.45rem;
  font-size:.86rem;
  backdrop-filter: blur(9px);
  transition: transform .18s ease, background .18s ease;
}

.pill:hover {
  transform: translateY(-1px);
  background: rgba(255,255,255,0.22);
}

.pill i {
  animation: bob 3.8s ease-in-out infinite;
}
.pill:nth-child(2) i { animation-delay: .25s; }
.pill:nth-child(3) i { animation-delay: .5s; }
.pill:nth-child(4) i { animation-delay: .75s; }

.badge-soft{
  display:inline-flex;
  align-items:center;
  gap:.42rem;
  padding:.22rem .6rem;
  border-radius:999px;
  border: 1px solid rgba(148,163,184,.42);
  background: rgba(248,250,252,.88);
  color:#334155;
  font-size:.82rem;
}

.badge-ok{ border-color: rgba(16,185,129,.35); background: rgba(236,253,245,.94); }
.badge-warn{ border-color: rgba(245,158,11,.35); background: rgba(255,251,235,.94); }
.badge-bad{ border-color: rgba(239,68,68,.30); background: rgba(254,242,242,.94); }

/* ======================================================
   Cards
====================================================== */
.card,
.rp-card,
div[data-testid="stExpander"],
section[data-testid="stChatMessage"] > div {
  animation: riseSoft .45s ease-out both;
}

.card {
  background: linear-gradient(180deg, var(--card), var(--card2));
  border-radius: var(--r);
  border: 1px solid var(--stroke);
  box-shadow: var(--shadow2);
  padding: 1.05rem 1.1rem;
  backdrop-filter: blur(10px);
  transition: transform .18s ease, box-shadow .22s ease, border-color .22s ease;
}

.card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}

.card-glow{
  position:relative;
  overflow:hidden;
}

.card-glow:before{
  content:"";
  position:absolute;
  inset:-2px -2px auto -2px;
  height:72px;
  background:
    radial-gradient(900px circle at 12% 8%, rgba(99,102,241,.18), transparent 60%),
    radial-gradient(800px circle at 92% 0%, rgba(6,182,212,.14), transparent 62%);
  pointer-events:none;
}

.card-glow:after{
  content:"";
  position:absolute;
  top:0;
  left:0;
  width: 30%;
  height:100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.18), transparent);
  transform: translateX(-140%) skewX(-18deg);
  pointer-events:none;
}

.card-glow:hover:after{
  animation: softSheen 1.05s ease;
}

.card-title {
  font-size: 1.05rem;
  font-weight: 900;
  color: var(--text);
  margin:0;
}

.card-sub {
  color: var(--muted);
  margin:.12rem 0 0 0;
  font-size:.93rem;
}

.hr {
  height: 1px;
  background: rgba(226,232,240,.9);
  margin: 1rem 0;
}

/* ======================================================
   Toolbar
====================================================== */
.toolbar{
  display:flex;
  flex-wrap:wrap;
  gap:.6rem;
  align-items:center;
  justify-content:space-between;
  margin-top:.45rem;
}
.toolbar .left{
  display:flex;
  flex-wrap:wrap;
  gap:.55rem;
  align-items:center;
}
.toolbar .right{
  color: var(--muted);
  font-size:.9rem;
}

/* ======================================================
   Stepper
====================================================== */
.stepper {
  display:flex;
  gap:.55rem;
  flex-wrap:wrap;
  align-items:center;
  margin:.25rem 0 .2rem 0;
}

.step {
  display:inline-flex;
  align-items:center;
  gap:.5rem;
  padding:.36rem .72rem;
  border-radius:999px;
  border: 1px solid rgba(148,163,184,.35);
  background: rgba(248,250,252,.72);
  color:#334155;
  font-size:.86rem;
  transition: all .18s ease;
}

.step:hover {
  transform: translateY(-1px);
}

.step .dot {
  width:10px;
  height:10px;
  border-radius:999px;
  background: rgba(148,163,184,.8);
}

.step.on {
  border-color: rgba(99,102,241,.45);
  background: rgba(238,242,255,.78);
  animation: glowPulse 2.1s ease-in-out infinite;
}

.step.on .dot {
  background: rgba(79,70,229,.9);
}

.step.done {
  border-color: rgba(16,185,129,.45);
  background: rgba(236,253,245,.80);
}

.step.done .dot {
  background: rgba(16,185,129,.9);
}

/* ======================================================
   Report option cards
====================================================== */
.rp-card{
  border-radius: var(--r);
  border: 1px solid var(--stroke);
  background: linear-gradient(180deg, rgba(255,255,255,.94), rgba(255,255,255,.84));
  box-shadow: var(--shadow2);
  padding: 1rem 1.05rem;
  position: relative;
  overflow: hidden;
  transition: transform .14s ease, box-shadow .18s ease, border-color .18s ease;
  min-height: 250px;
  backdrop-filter: blur(10px);
}

.rp-card:hover{
  transform: translateY(-2px);
  box-shadow: var(--shadow);
  border-color: rgba(99,102,241,.40);
}

.rp-card:before{
  content:"";
  position:absolute;
  inset:-2px -2px auto -2px;
  height:66px;
  background:
    radial-gradient(900px circle at 10% 8%, rgba(99,102,241,.18), transparent 60%),
    radial-gradient(800px circle at 92% 0%, rgba(6,182,212,.14), transparent 62%);
  pointer-events:none;
}

.rp-card:after{
  content:"";
  position:absolute;
  top:0;
  left:0;
  width: 28%;
  height:100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.20), transparent);
  transform: translateX(-140%) skewX(-18deg);
  pointer-events:none;
}

.rp-card:hover:after{
  animation: softSheen 1.05s ease;
}

.rp-h {
  margin:0 0 .3rem 0;
  font-weight: 950;
  color:#0f172a;
  font-size: 1.04rem;
  letter-spacing:-0.01em;
}

.rp-meta {
  display:flex;
  flex-wrap:wrap;
  gap:.4rem;
  margin:.15rem 0 .7rem 0;
}

.rp-desc {
  color:#334155;
  font-size:.93rem;
  margin:.2rem 0 .6rem 0;
  min-height: 44px;
}

.rp-reason {
  color:#64748b;
  font-size:.86rem;
  margin: 0;
  line-height: 1.5;
  min-height: 60px;
}

.rp-footer{
  margin-top:.9rem;
  padding-top:.8rem;
  border-top: 1px solid rgba(226,232,240,.95);
}

.rp-state{
  font-size:.86rem;
  color:#475467;
  padding-top:.35rem;
}

/* ======================================================
   Buttons
====================================================== */
div.stButton > button {
  border-radius: 14px !important;
  font-weight: 800 !important;
  transition:
    transform .12s ease,
    box-shadow .18s ease,
    border-color .18s ease,
    background .18s ease !important;
}

div.stButton > button:hover {
  transform: translateY(-1px);
}

div.stButton > button:active {
  transform: translateY(0) scale(.985);
}

div.stButton > button[kind="primary"] {
  border-radius: 14px !important;
  box-shadow: 0 12px 26px rgba(79,70,229,.20) !important;
}

div.stButton > button[kind="primary"]:hover {
  box-shadow: 0 16px 34px rgba(79,70,229,.28) !important;
}

div[class^="st-key-rp_btn_"] button {
  border-radius: 12px !important;
  font-weight: 800 !important;
  min-height: 42px !important;
}

/* ======================================================
   Tabs / Chat
====================================================== */
button[data-baseweb="tab"] {
  font-weight: 800 !important;
  transition: transform .14s ease, background .18s ease !important;
}

button[data-baseweb="tab"]:hover {
  transform: translateY(-1px);
}

section[data-testid="stChatMessage"] > div {
  border-radius: 18px !important;
  border: 1px solid rgba(148,163,184,.20);
  box-shadow: 0 8px 18px rgba(2,6,23,.06);
  animation: riseSoft .35s ease-out both;
}

/* ======================================================
   Utility
====================================================== */
.caption-muted {
  color: var(--muted);
  font-size: .92rem;
  margin:.2rem 0 0 0;
}

.rise-in {
  animation: riseSoft .35s ease-out both;
}

/* ======================================================
   Keyframes
====================================================== */
@keyframes floatOrb {
  0%   { transform: translate3d(0,0,0) scale(1); }
  25%  { transform: translate3d(4vw, 2vw, 0) scale(1.04); }
  50%  { transform: translate3d(0, 5vw, 0) scale(.98); }
  75%  { transform: translate3d(-3vw, 1vw, 0) scale(1.03); }
  100% { transform: translate3d(0,0,0) scale(1); }
}

@keyframes riseSoft {
  from { opacity: 0; transform: translateY(18px) scale(.985); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes glowPulse {
  0%,100% { box-shadow: 0 0 0 rgba(79,70,229,0), var(--shadow2); }
  50%     { box-shadow: 0 0 0 6px rgba(79,70,229,.06), var(--shadow); }
}

@keyframes softSheen {
  0%   { transform: translateX(-140%) skewX(-18deg); }
  100% { transform: translateX(240%) skewX(-18deg); }
}

@keyframes bob {
  0%,100% { transform: translateY(0px); }
  50%     { transform: translateY(-3px); }
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<style>
.workspace-hero {
  border-radius: 22px;
  padding: 20px 22px;
  background: linear-gradient(135deg, #eef4ff 0%, #f7f2ff 45%, #eefaf8 100%);
  border: 1px solid rgba(120,140,180,.18);
  box-shadow: 0 10px 28px rgba(30, 41, 59, .08);
  margin-bottom: 14px;
}
.workspace-title {
  font-size: 1.35rem;
  font-weight: 800;
  color: #24314d;
  margin: 0 0 6px 0;
}
.workspace-sub {
  color: #60708f;
  font-size: 1rem;
  margin: 0;
}
.flow-chip-row {
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-top:12px;
}
.flow-chip {
  background:#ffffffc7;
  border:1px solid rgba(90,110,140,.14);
  border-radius:999px;
  padding:8px 12px;
  font-size:.92rem;
  color:#2f3c57;
}
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# Guards
# =========================================================
if not st.session_state.get("user_name"):
    st.warning("Bạn cần đăng nhập User trước.")
    try:
        st.switch_page("app.py")
    except Exception:
        st.stop()

if not st.session_state.get("user_token"):
    st.warning("Phiên đăng nhập đã hết hoặc chưa có token. Vui lòng đăng nhập lại.")
    st.switch_page("app.py")
    st.stop()

api.set_token(st.session_state["user_token"])


# =========================================================
# Helpers
# =========================================================
def _extract_sections_any_shape(obj: Any) -> List[dict]:
    data = obj if isinstance(obj, dict) else {}
    for key in ("sections", "auto_sections", "confirmed_sections"):
        if isinstance(data.get(key), list):
            return data[key]
    for k in ("data", "preview", "analysis", "result"):
        d = data.get(k)
        if isinstance(d, dict):
            for key in ("sections", "auto_sections", "confirmed_sections"):
                if isinstance(d.get(key), list):
                    return d[key]
    return []


def _file_fingerprint(uploaded_file) -> Optional[Tuple[str, int]]:
    if not uploaded_file:
        return None
    try:
        return (uploaded_file.name, uploaded_file.size)
    except Exception:
        b = uploaded_file.getvalue()
        return (uploaded_file.name, len(b))


def _reset_for_new_upload(keep_login: bool = True):
    _user_name = st.session_state.get("user_name") if keep_login else ""
    _user_token = st.session_state.get("user_token") if keep_login else None
    _user_mode = st.session_state.get("user_mode") if keep_login else "USER"

    for k in [
        "final_spec_result",
        "_preview_fetched",
        "_sections_loaded_from_be",
        "qa_messages",
        "_greeted_after_finalize",
        "finalize_rev",
        "_last_final_rev",
        "_last_final_sid",
        "_last_final_sheet",
        "pending_qa",
        "pending_q",
        "report_plan_result",
        "generated_spec_result",
        "selected_report_ids",
        "_auto_plan_ran",
        "_plan_intro_done_for",
        "_qa_reset_next",
        "document_flow",
        "document_type",
        "routing_result",
        "ba_detect_result",
        "ba_analysis_result",
        "quotation_preview_result",
        "_open_quote_form",
    ]:
        st.session_state.pop(k, None)

    st.session_state["session_id"] = ""
    st.session_state["sections"] = []
    st.session_state["finalized"] = False

    st.session_state["final_spec_result"] = {}
    st.session_state["report_plan_result"] = {}
    st.session_state["generated_spec_result"] = {}
    st.session_state["selected_report_ids"] = []
    st.session_state["_auto_plan_ran"] = False
    st.session_state["document_flow"] = None
    st.session_state["document_type"] = None
    st.session_state["routing_result"] = {}
    st.session_state["ba_detect_result"] = {}
    st.session_state["ba_analysis_result"] = {}
    st.session_state["quotation_preview_result"] = {}
    st.session_state["_open_quote_form"] = False

    st.session_state["_preview_fetched"] = False
    st.session_state["_sections_loaded_from_be"] = False
    st.session_state["qa_messages"] = []
    st.session_state["_greeted_after_finalize"] = False
    st.session_state["_qa_reset_next"] = False

    if keep_login:
        st.session_state["user_name"] = _user_name
        if _user_token:
            st.session_state["user_token"] = _user_token
        st.session_state["user_mode"] = _user_mode


def make_arrow_safe(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    for c in df2.columns:
        if df2[c].dtype == "object":
            df2[c] = df2[c].map(
                lambda x: x.decode("utf-8", "ignore") if isinstance(x, (bytes, bytearray)) else x
            )
            df2[c] = df2[c].astype("string")
    return df2


def _render_local_file_view(uploaded_file, preferred_sheet: Optional[str]):
    if not uploaded_file:
        st.caption("Chọn file để xem nội dung ngay tại đây.")
        return

    raw = uploaded_file.getvalue()
    fname = (uploaded_file.name or "").lower()

    with st.expander("👀 Xem file vừa chọn (local preview)", expanded=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            height = st.slider("Chiều cao vùng xem", 320, 1200, 560, 20, key="local_view_height")
        with c2:
            max_rows = st.number_input("Giới hạn số dòng", 50, 5000, 300, 50, key="local_view_rows")
        with c3:
            st.caption("")

        if fname.endswith((".xlsx", ".xls")):
            try:
                xls = pd.ExcelFile(io.BytesIO(raw))
                sheets = xls.sheet_names or []
                if not sheets:
                    st.warning("Không tìm thấy sheet nào trong file.")
                    return
                default_sheet = preferred_sheet if preferred_sheet in sheets else sheets[0]
                sheet = st.selectbox(
                    "Sheet (local)",
                    sheets,
                    index=sheets.index(default_sheet),
                    key="local_view_sheet",
                )
                df = pd.read_excel(xls, sheet_name=sheet, header=None)
            except Exception as e:
                st.error(f"Không đọc được Excel: {e}")
                return
        elif fname.endswith(".csv"):
            try:
                df = pd.read_csv(io.BytesIO(raw), header=None)
            except Exception as e:
                st.error(f"Không đọc được CSV: {e}")
                return
        else:
            st.warning("Chỉ hỗ trợ xem nhanh .xlsx/.xls/.csv")
            return

        st.caption(f"Kích thước: {df.shape[0]} rows × {df.shape[1]} cols — hiển thị tối đa {int(max_rows)} dòng")
        view_df = make_arrow_safe(df.head(int(max_rows)))
        st.dataframe(view_df, use_container_width=True, height=int(height))

        st.download_button(
            "⬇️ Tải lại file vừa chọn",
            data=raw,
            file_name=uploaded_file.name,
            mime="application/octet-stream",
            key="local_download_input",
        )


def fetch_preview() -> bool:
    sid = (st.session_state.session_id or "").strip()
    sheet = (st.session_state.sheet_name or "").strip() or None
    if not sid:
        st.warning("Chưa có session_id. Hãy upload file trước.")
        return False

    r = api.preview(sid, sheet)
    if isinstance(r, dict) and r.get("ok") is False and r.get("error"):
        st.error(f"{r.get('code')} – {r.get('error')}")
        return False

    data = r.get("data", {}) if isinstance(r, dict) else {}
    sections = _extract_sections_any_shape(r) or _extract_sections_any_shape(data)

    if not sections:
        st.error("Preview OK nhưng không thấy sections.")
        with st.expander("Payload /preview"):
            st.json(r)
        return False

    st.session_state.sections = sections
    st.session_state["_preview_fetched"] = True
    return True


def finalize_sections() -> bool:
    sid = (st.session_state.session_id or "").strip()
    sheet = (st.session_state.sheet_name or "").strip() or None
    payload = st.session_state.get("sections", [])

    if not sid:
        st.warning("Chưa có session_id.")
        return False
    if not payload:
        st.warning("Chưa có sections. Hãy preview trước.")
        return False

    r = api.finalize_sections(sid, payload, sheet)
    ok = isinstance(r, dict) and (r.get("ok") is True or "data" in r or "message" in r)

    if ok:
        st.session_state.finalized = True
        st.session_state.finalize_rev = int(st.session_state.get("finalize_rev", 0)) + 1
        st.session_state.qa_messages = []
        st.session_state["_greeted_after_finalize"] = False
        st.session_state["_qa_reset_next"] = True
        st.session_state["report_plan_result"] = {}
        st.session_state["generated_spec_result"] = {}
        st.session_state["selected_report_ids"] = []
        st.session_state["_auto_plan_ran"] = False
        st.session_state["document_flow"] = None
        st.session_state["document_type"] = None
        st.session_state["routing_result"] = {}
        st.session_state["ba_detect_result"] = {}
        st.session_state["ba_analysis_result"] = {}
        st.session_state["quotation_preview_result"] = {}
        st.session_state["_open_quote_form"] = False
        st.session_state.pop("_plan_intro_done_for", None)
        return True

    st.error(f"{r.get('code')} – {r.get('error')}")
    with st.expander("Resp /confirm_sections"):
        st.json(r)
    return False


def _plan_ok(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("ok") is False:
        return False
    plan = payload.get("plan") or (payload.get("data") or {}).get("plan")
    return isinstance(plan, dict)


def _get_plan(payload: dict) -> Optional[dict]:
    if not isinstance(payload, dict):
        return None
    plan = payload.get("plan") or (payload.get("data") or {}).get("plan")
    return plan if isinstance(plan, dict) else None


def _render_plan_intro(plan_payload: dict, sid: str):
    intro_text = "Sau quá trình phân tích dữ liệu, những loại báo cáo mà tôi có thể cung cấp cho bạn sẽ là:"
    try:
        intro_key = (
            plan_payload.get("response_id")
            or plan_payload.get("cache_key")
            or (plan_payload.get("data") or {}).get("response_id")
            or (plan_payload.get("data") or {}).get("cache_key")
        )
    except Exception:
        intro_key = None
    intro_key = intro_key or f"sid:{sid}"

    slot = st.empty()
    if st.session_state.get("_plan_intro_done_for") != intro_key:
        typed = ""
        for ch in intro_text:
            typed += ch
            slot.markdown(f"💡 **{typed}**▌")
            time.sleep(0.008)
        slot.markdown(f"💡 **{intro_text}**")
        st.session_state["_plan_intro_done_for"] = intro_key
    else:
        slot.markdown(f"💡 **{intro_text}**")


def _toggle_selected_report(rid: str):
    rid = (rid or "").strip()
    if not rid:
        return

    selected = set(st.session_state.get("selected_report_ids", []))
    if rid in selected:
        selected.remove(rid)
    else:
        selected.add(rid)
    st.session_state["selected_report_ids"] = sorted(selected)


def _sanitize_plan_card_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    replacements = (
        ("góc nhìn nghiệp vụ", "góc nhìn dễ hiểu"),
        ("logic nghiệp vụ", "cách dữ liệu đang vận hành"),
        ("ngôn ngữ nghiệp vụ", "cách diễn đạt dễ hiểu"),
        ("nghiệp vụ", "công việc"),
        ("business-facing", "dễ đọc"),
        ("business view", "góc nhìn dễ hiểu"),
        ("business", "người xem"),
    )
    lowered = text.lower()
    for src, dst in replacements:
        lowered = lowered.replace(src, dst)
    lowered = re.sub(r"\s+", " ", lowered).strip(" ,;:-")
    if not lowered:
        return ""
    return lowered[0].upper() + lowered[1:]


def _render_report_option_cards(filtered: list, recommended: set):
    if "selected_report_ids" not in st.session_state:
        st.session_state["selected_report_ids"] = []

    if not st.session_state["selected_report_ids"]:
        default_selected = sorted([
            (o.get("report_id") or "").strip()
            for o in filtered
            if isinstance(o, dict) and (o.get("report_id") or "").strip() in recommended
        ])
        st.session_state["selected_report_ids"] = default_selected

    selected_set = set(st.session_state["selected_report_ids"])
    cols = st.columns(2, gap="large")

    for i, opt in enumerate(filtered):
        rid = (opt.get("report_id") or "").strip()
        display = opt.get("display") or {}
        debug_meta = opt.get("debug_meta") or {}

        title = _sanitize_plan_card_text(display.get("title") or rid or f"report_{i + 1}")
        desc = _sanitize_plan_card_text(display.get("description") or "")
        reason = _sanitize_plan_card_text(display.get("reason") or "")
        recommendation = (display.get("recommendation") or ("recommended" if rid in recommended else "optional")).strip().lower()

        is_reco = recommendation == "recommended" or rid in recommended
        is_selected = rid in selected_set

        border = "rgba(16,185,129,.55)" if is_selected else "rgba(148,163,184,.34)"
        ring = "0 0 0 3px rgba(16,185,129,.16)" if is_selected else "none"
        tick = "Đã chọn" if is_selected else "Chưa chọn"
        tick_cls = "badge-soft badge-ok" if is_selected else "badge-soft"
        reco_cls = "badge-soft badge-ok" if is_reco else "badge-soft"
        reco_txt = "⭐ Đề xuất" if is_reco else "Tùy chọn"
        button_label = "Bỏ chọn" if is_selected else "Chọn báo cáo"

        with cols[i % 2]:
            st.markdown(
                f"""
<div class="rp-card" style="border-color:{border}; box-shadow:{ring}, var(--shadow2);">
  <h4 class="rp-h">{title}</h4>
  <div class="rp-meta">
      <span class="{reco_cls}"><i class="fa-solid fa-star"></i>&nbsp;{reco_txt}</span>
      <span class="{tick_cls}"><i class="fa-solid fa-check"></i>&nbsp;{tick}</span>
  </div>
  <div class="rp-desc">{desc}</div>
  <p class="rp-reason">{reason}</p>
</div>
""",
                unsafe_allow_html=True,
            )

            with st.expander("📝 Xem chú thích mở rộng", expanded=False):
                st.json(
                    {
                        "report_id": rid,
                        "debug_meta": debug_meta,
                    }
                )

            b1, b2 = st.columns([1.2, 1.8])
            with b1:
                st.button(
                    button_label,
                    key=f"rp_btn_{rid}_{i}",
                    use_container_width=True,
                    on_click=_toggle_selected_report,
                    args=(rid,),
                )
            with b2:
                st.markdown(
                    f'<div class="rp-state">Trạng thái hiện tại: <b>{tick}</b></div>',
                    unsafe_allow_html=True,
                )

    return st.session_state["selected_report_ids"]




def _legacy_render_ba_analysis_workspace(sid: str):
    ba_detect = st.session_state.get("ba_detect_result") or {}
    ba_analysis = st.session_state.get("ba_analysis_result") or {}
    quote_preview = st.session_state.get("quotation_preview_result") or {}

    confidence = float(ba_detect.get("confidence") or 0.0)
    sheet_candidates = ba_detect.get("sheet_candidates") or []
    first_sheet = sheet_candidates[0].get("sheet_name", "-") if sheet_candidates else "-"

    st.markdown(
        f"""
<div class="workspace-hero rise-in">
  <div class="workspace-title">🧾 BA Analysis Workspace</div>
  <p class="workspace-sub">File đã được nhận diện là <b>Business Analysis</b>. Hệ thống đang bóc tách scope, assumptions và commercial drivers để chuẩn bị dữ liệu báo giá.</p>
  <div class="flow-chip-row">
    <div class="flow-chip">Loại file: <b>BA Excel</b></div>
    <div class="flow-chip">Confidence: <b>{confidence:.2f}</b></div>
    <div class="flow-chip">Sheet chính: <b>{first_sheet}</b></div>
    <div class="flow-chip">Flow: <b>BA → Analysis → Quotation</b></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    scope_items = ba_analysis.get("scope_items") or []
    assumptions = ba_analysis.get("assumptions") or []
    exclusions = ba_analysis.get("exclusions") or []
    drivers = ba_analysis.get("commercial_drivers") or {}
    unmapped = ba_analysis.get("unmapped_or_ambiguous_items") or []

    c1, c2 = st.columns([1.6, 1.0], gap="large")
    with c1:
        st.markdown(
            """
<div class="card card-glow">
  <p class="card-title">📋 Scope Items</p>
  <p class="card-sub">Danh sách hạng mục BA được bóc tách từ file đã finalize.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if scope_items:
            st.dataframe(pd.DataFrame(scope_items), use_container_width=True, height=420)
        else:
            st.info("Chưa có scope items.")

        st.markdown(
            """
<div class="card card-glow" style="margin-top:14px">
  <p class="card-title">⚠️ Unmapped / Ambiguous</p>
  <p class="card-sub">Các dòng BA còn mơ hồ hoặc chưa đủ căn cứ để map chắc chắn.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if unmapped:
            st.dataframe(pd.DataFrame(unmapped), use_container_width=True, height=220)
        else:
            st.success("Không có item mơ hồ.")

    with c2:
        st.markdown(
            """
<div class="card card-glow">
  <p class="card-title">📈 Commercial Drivers</p>
  <p class="card-sub">Các driver thương mại ảnh hưởng đến báo giá.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        st.json(drivers)

        st.markdown(
            """
<div class="card card-glow" style="margin-top:14px">
  <p class="card-title">📝 Assumptions</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if assumptions:
            for x in assumptions:
                st.write("•", x.get("text", ""))
        else:
            st.caption("Không có assumptions.")

        st.markdown(
            """
<div class="card card-glow" style="margin-top:14px">
  <p class="card-title">🚫 Exclusions</p>
</div>
""",
            unsafe_allow_html=True,
        )
        if exclusions:
            for x in exclusions:
                st.write("•", x.get("text", ""))
        else:
            st.caption("Không có exclusions.")

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

    st.markdown(
        """
<div class="card card-glow rise-in">
  <p class="card-title">🧾 Bước tiếp theo: Quotation</p>
  <p class="card-sub">Dữ liệu BA đã sẵn sàng để dựng dữ liệu báo giá và xuất file Excel mẫu.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    f1, f2, f3 = st.columns([1.4, 1.4, 2.2])
    with f1:
        customer_name = st.text_input("Customer Name", key="ba_quote_customer_name")
    with f2:
        quotation_no = st.text_input("Quotation No", key="ba_quote_no")
    with f3:
        currency = st.selectbox("Currency", ["VND", "USD"], key="ba_quote_currency")

    q1, q2, q3 = st.columns([1.2, 1.2, 2.6])
    with q1:
        btn_quote = st.button("🧾 Tạo báo giá", type="primary", key="btn_ba_generate_quote")
    with q2:
        btn_rerun_ba = st.button("🔄 Chạy lại BA analysis", key="btn_ba_rerun_analysis")
    with q3:
        st.caption("Bạn có thể review scope items trước khi generate quotation.")

    if btn_rerun_ba:
        with st.spinner("Đang phân tích lại BA..."):
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
  <p class="card-title">✨ Quotation Preview</p>
  <p class="card-sub">Dữ liệu báo giá đã được dựng xong và sẵn sàng xuất Excel.</p>
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
            st.markdown(f"[📥 Tải file báo giá]({api.BASE}{download_path})")


# (Đã chuyển sang src.ui.render_ba_analysis_workspace để dùng chung)


def render_report_analysis_workspace_header():
    st.markdown(
        """
<div class="workspace-hero rise-in">
  <div class="workspace-title">🧠 Report Builder Workspace</div>
  <p class="workspace-sub">File này được nhận diện là dữ liệu phân tích. Hệ thống tiếp tục luồng <b>Plan → Select → Generate</b>.</p>
  <div class="flow-chip-row">
    <div class="flow-chip">Loại file: <b>Analytics</b></div>
    <div class="flow-chip">Flow: <b>Plan → Select → Generate</b></div>
    <div class="flow-chip">Manifest: <b>Locked</b></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


# =========================================================
# Header
# =========================================================
user_name = st.session_state.get("user_name", "∅")
user_role = st.session_state.get("user_role", "USER")

st.markdown(
    f"""
<div class="hero">
  <h1>IDPro – Excel Agent </h1>
  <p>
    <span class="pill"><i class="fa-regular fa-user"></i>&nbsp;{user_name}</span>
    <span class="pill"><i class="fa-solid fa-shield-halved"></i>&nbsp;{user_role}</span>
    <span class="pill"><i class="fa-solid fa-chart-column"></i>&nbsp;Report Builder</span>
    <span class="pill"><i class="fa-solid fa-comments"></i>&nbsp;QA Chat</span>
  </p>
</div>
""",
    unsafe_allow_html=True,
)


# =========================================================
# Sidebar
# =========================================================
with st.sidebar:
    st.markdown(
        f"""
<div class="card card-glow">
  <p class="card-title"><i class="fa-solid fa-user-gear"></i>&nbsp;Control Center</p>
  <p class="card-sub">{st.session_state.get("user_name")} · {st.session_state.get("user_role", "USER")}</p>
  <div class="hr"></div>
  <p class="caption-muted">The account is logged in and active now.</p>
</div>
""",
        unsafe_allow_html=True,
    )
    st.write("")
    
    # Nút chuyển về chế độ Auto
    if st.button("⚡ Chuyển sang Chế độ Tự động", use_container_width=True):
        st.switch_page("pages/1_AI_Agent.py")
    
    st.write("")

    if st.button("Logout", key="btn_user_logout_page"):
        st.session_state.user_name = ""
        st.session_state.user_mode = "USER"
        st.session_state.pop("user_token", None)
        _reset_for_new_upload(keep_login=False)
        try:
            st.switch_page("app.py")
        except Exception:
            st.rerun()

    st.divider()
    st.subheader("📤 Upload")

    file = st.file_uploader("Chọn file .xlsx/.xls/.csv", type=["xlsx", "xls", "csv"], key="user_uploader")
    st.text_input("Sheet name (tùy chọn)", key="sheet_name")

    fp = _file_fingerprint(file)

    if fp and st.session_state.get("_last_local_fp") != fp and (st.session_state.get("session_id") or ""):
        st.session_state["_last_local_fp"] = fp
        _reset_for_new_upload(keep_login=True)
        for k in ["local_view_sheet", "local_view_height", "local_view_rows", "local_download_input"]:
            st.session_state.pop(k, None)
    elif fp and st.session_state.get("_last_local_fp") != fp:
        st.session_state["_last_local_fp"] = fp

    _render_local_file_view(file, (st.session_state.get("sheet_name") or "").strip() or None)

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

    if st.button("🚀 Upload & Auto Identify", type="primary", key="btn_user_upload"):
        if not file:
            st.warning("Chưa chọn file.")
        else:
            _reset_for_new_upload(keep_login=True)
            res = api.upload_file(file, st.session_state.get("sheet_name") or None)

            if isinstance(res, dict) and res.get("ok"):
                sid_new = res.get("data", {}).get("session_id") or ""
                if not sid_new:
                    st.error("Upload OK nhưng không nhận được session_id.")
                else:
                    st.session_state.session_id = sid_new
                    st.success("Upload OK.")
                    with st.spinner("Đang preview cấu trúc bảng..."):
                        fetch_preview()
            else:
                st.error(f"{res.get('code')} – {res.get('error')}")
                with st.expander("Resp /upload"):
                    st.json(res)

    sid_sidebar = (st.session_state.session_id or "").strip()
    finalized_sidebar = bool(st.session_state.get("finalized", False))

    st.markdown(
        f"""
<div style="display:flex; gap:.45rem; flex-wrap:wrap; margin-top:.3rem;">
  <span class="badge-soft {'badge-ok' if sid_sidebar else 'badge-warn'}">
    <i class="fa-solid fa-ticket"></i>&nbsp;Session: <b>{sid_sidebar or "∅"}</b>
  </span>
  <span class="badge-soft {'badge-ok' if finalized_sidebar else 'badge-warn'}">
    <i class="fa-solid fa-lock"></i>&nbsp;Finalized: <b>{"YES" if finalized_sidebar else "NO"}</b>
  </span>
</div>
""",
        unsafe_allow_html=True,
    )


# =========================================================
# Main workflow
# =========================================================
sid = (st.session_state.session_id or "").strip()
finalized = bool(st.session_state.get("finalized", False))
has_sections = bool(st.session_state.get("sections"))

if not sid:
    st.info("Bạn hãy Upload file ở sidebar trước.")
    st.stop()

step_upload = bool(sid)
step_preview = bool(has_sections)
step_finalize = bool(finalized)

st.markdown(
    f"""
<div class="card card-glow">
  <p class="card-title">✨ Workflow</p>
  <p class="card-sub">Upload → Preview/Chỉnh sửa → Finalize → Report/QA</p>
  <div class="stepper">
    <span class="step {'done' if step_upload else ''}"><span class="dot"></span>1) Upload</span>
    <span class="step {'done' if step_preview else 'on' if step_upload and not step_preview else ''}"><span class="dot"></span>2) Preview</span>
    <span class="step {'done' if step_finalize else 'on' if step_preview and not step_finalize else ''}"><span class="dot"></span>3) Finalize</span>
    <span class="step {'on' if step_finalize else ''}"><span class="dot"></span>4) Report/QA</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

st.markdown(
    """
<div class="card card-glow">
  <p class="card-title">🧩 Preview & chỉnh sửa cấu trúc</p>
  <p class="card-sub">Hệ thống tự detect các vùng bảng. Bạn có thể chỉnh và finalize để khóa manifest.</p>
</div>
""",
    unsafe_allow_html=True,
)
st.write("")

row1 = st.columns([1, 3, 2])
with row1[0]:
    st.button("🔄 Tải lại preview", on_click=fetch_preview, disabled=not bool(sid), key="btn_user_preview_reload_main")
with row1[1]:
    st.caption("Mẹo: Điều chỉnh start/end/header để Agent cắt bảng chính xác.")

if not st.session_state.get("sections"):
    st.warning("Chưa có bảng. Bấm 'Tải lại preview' hoặc Upload lại.")
    st.stop()

df1 = sections_to_df_1based(st.session_state.get("sections", []))
edited_zero_df, del_rows, _ = sections_editor_with_add_delete(
    df1,
    key_prefix="secx_user_main",
    lang="vi",
    show_titles=False,
    show_create=False,
)

act1, act2, act3 = st.columns([1, 1, 2])

with act1:
    if st.button("✅ Áp dụng thay đổi", key="btn_user_apply_sections_main"):
        payload = edited_zero_df.to_dict(orient="records")
        res = api.sections_replace(sid, payload)
        if isinstance(res, dict) and res.get("ok"):
            st.success("Đã cập nhật bảng.")
            st.session_state["sections"] = res["data"]["sections"]
        else:
            st.error(res)

with act2:
    if st.button("🗑️ Xoá bảng đã chọn", key="btn_user_delete_sections_main"):
        cur = edited_zero_df.to_dict(orient="records")
        keep = [v for i, v in enumerate(cur) if i not in del_rows]
        res = api.sections_replace(sid, keep)
        if isinstance(res, dict) and res.get("ok"):
            st.success("Đã xoá.")
            st.session_state["sections"] = res["data"]["sections"]
        else:
            st.error(res)

with act3:
    with st.expander("➕ Thêm bảng mới (1-based)"):
        c1, c2, c3, c4 = st.columns(4)

        default_new_start = 1
        try:
            if not df1.empty and "start_row" in df1.columns:
                default_new_start = int(df1["start_row"].max()) + 1
        except Exception:
            default_new_start = 1

        with c1:
            new_start = st.number_input("Dòng bắt đầu", min_value=1, value=int(default_new_start), key="secx_user_new_start")
        with c2:
            new_end = st.number_input("Dòng kết thúc", min_value=int(new_start), value=int(new_start), key="secx_user_new_end")
        with c3:
            new_header = st.number_input(
                "Dòng tiêu đề",
                min_value=int(new_start),
                max_value=int(new_end),
                value=int(new_start),
                key="secx_user_new_header",
            )
        with c4:
            new_label = st.text_input("Tên bảng", value="", key="secx_user_new_label")

        create_payload = {
            "start_row": int(new_start - 1),
            "end_row": int(new_end - 1),
            "header_row": int(new_header - 1),
            "label": (new_label or "").strip(),
        }

        if st.button("Thêm bảng mới", key="btn_user_add_section_main"):
            res = api.sections_add(sid, create_payload)
            if isinstance(res, dict) and res.get("ok"):
                st.success("Đã thêm.")
                st.session_state["sections"] = res["data"]["sections"]
            else:
                st.error(res)

confirm_col1, confirm_col2, confirm_col3 = st.columns([1, 1, 2])

with confirm_col1:
    if st.button("🔒 Xác nhận cấu trúc (Finalize)", type="primary", key="btn_user_finalize_main"):
        with st.spinner("Đang finalize sections..."):
            ok = finalize_sections()
        if ok:
            with st.spinner("Đang nhận diện loại file và chọn luồng xử lý phù hợp..."):
                route_resp = api.post_confirm_router(st.session_state.session_id)

            if isinstance(route_resp, dict) and route_resp.get("ok") is False:
                st.error(f"API lỗi ({route_resp.get('status_code')}): {route_resp.get('error')}")
            else:
                st.session_state["routing_result"] = route_resp
                st.session_state["document_flow"] = route_resp.get("route")
                st.session_state["document_type"] = route_resp.get("document_type")
                st.session_state["ba_detect_result"] = route_resp.get("ba_detect_result") or {}
                st.session_state["ba_analysis_result"] = route_resp.get("ba_analysis_result") or {}
                if route_resp.get("report_plan"):
                    st.session_state["report_plan_result"] = {"ok": True, "plan": route_resp.get("report_plan")}
                    st.session_state["_auto_plan_ran"] = True
                if st.session_state.get("document_flow") == "ba":
                    st.toast("Đã nhận diện file BA và tự động chạy BA analysis", icon="🧾")
                else:
                    st.toast("Không phải file BA. Hệ thống đã tự động chạy report plan", icon="📊")
                rerun_fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
                if rerun_fn is None:
                    raise AttributeError("Installed Streamlit version does not support rerun().")
                rerun_fn()

with confirm_col2:
    if st.button("💾 Save Rule", key="btn_user_save_rule"):
        if not st.session_state.get("finalized", False):
            with st.spinner("Đang finalize trước khi lưu rule..."):
                ok = finalize_sections()
            if not ok:
                st.stop()

        with st.spinner("Đang lưu rule..."):
            r2 = api.save_template(
                st.session_state.session_id,
                (st.session_state.get("sheet_name") or "").strip() or None
            )

        if isinstance(r2, dict) and (r2.get("ok") is True or "data" in r2 or "message" in r2):
            st.success("Đã lưu Rule Template.")
        else:
            st.error(f"{r2.get('code')} – {r2.get('error')}")
            with st.expander("Resp /save_template"):
                st.json(r2)

with confirm_col3:
    st.caption("Finalize xong → hệ thống khóa manifest, tự detect loại file và tự chạy đúng luồng BA hoặc Report. Bạn cũng có thể lưu Rule để lần sau nhận diện nhanh hơn.")

st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

st.markdown(
    """
<div class="card card-glow">
  <p class="card-title">📊 Báo cáo & Hỏi đáp</p>
  <p class="card-sub">Sau khi Finalize, hệ thống tự detect loại file và mở đúng workspace BA hoặc Report. QA chat vẫn dùng cùng manifest.</p>
</div>
""",
    unsafe_allow_html=True,
)

if not st.session_state.get("finalized", False):
    st.info("Bạn cần Finalize cấu trúc trước khi hệ thống tự detect và mở workspace phân tích dữ liệu.")
    st.stop()

tab_analysis, tab_qa = st.tabs(["📊 Phân tích dữ liệu", "💬 Chatbot QA"])


# =========================================================
# Analysis workspace tab
# =========================================================
with tab_analysis:
    document_flow = st.session_state.get("document_flow")
    document_type = st.session_state.get("document_type")

    if not document_flow:
        st.markdown(
            """
<div class="workspace-hero rise-in">
  <div class="workspace-title">📊 Phân tích dữ liệu</div>
  <p class="workspace-sub">Sau khi Finalize, hệ thống sẽ tự nhận diện loại file và chạy đúng luồng xử lý phù hợp.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        st.info("Hãy bấm Finalize để hệ thống tự detect và điều hướng.")
        st.stop()

    if document_flow == "ba":
        render_ba_analysis_workspace(sid)
    else:
        render_report_analysis_workspace_header()
        # Report workspace body
        if "report_plan_result" not in st.session_state:
            st.session_state["report_plan_result"] = {}
        if "generated_spec_result" not in st.session_state:
            st.session_state["generated_spec_result"] = {}
        if "selected_report_ids" not in st.session_state:
            st.session_state["selected_report_ids"] = []
        if "_auto_plan_ran" not in st.session_state:
            st.session_state["_auto_plan_ran"] = False

        st.markdown(
            """
        <div class="card card-glow">
          <p class="card-title">🧠 Planning Studio</p>
          <p class="card-sub">Agent tự phân tích dữ liệu để gợi ý các loại báo cáo phù hợp nhất trong workspace hiện tại.</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.write("")

        cA, cB, cC, cD = st.columns([1.2, 1, 1, 2.2])
        with cA:
            btn_plan = st.button("🔎 Phân tích dữ liệu", type="primary", key="btn_plan_run")
        with cB:
            btn_refresh = st.button("♻️ Refresh", key="btn_plan_refresh")
        with cC:
            btn_reset = st.button("🧹 Reset", key="btn_plan_reset")
        with cD:
            st.caption("Auto-run 1 lần khi mở tab. Reset sẽ xoá plan cache của session.")

        plan_payload = st.session_state.get("report_plan_result") or {}
        has_plan = _plan_ok(plan_payload)

        if btn_reset:
            st.session_state["generated_spec_result"] = {}
            st.session_state["_auto_plan_ran"] = False
            st.session_state["selected_report_ids"] = []
            st.session_state.pop("_plan_intro_done_for", None)
            with st.spinner("Reset planner..."):
                st.session_state["report_plan_result"] = api.report_plan(sid, reset=True)
            plan_payload = st.session_state["report_plan_result"]
            has_plan = _plan_ok(plan_payload)

        if btn_refresh:
            with st.spinner("Đang refresh gợi ý..."):
                st.session_state["report_plan_result"] = api.report_plan(sid, reset=False)
            plan_payload = st.session_state["report_plan_result"]
            has_plan = _plan_ok(plan_payload)

        if btn_plan:
            with st.spinner("Đang phân tích dữ liệu (CI)..."):
                st.session_state["report_plan_result"] = api.report_plan(sid, reset=False)
            plan_payload = st.session_state["report_plan_result"]
            has_plan = _plan_ok(plan_payload)

        if (not has_plan) and (not st.session_state.get("_auto_plan_ran", False)):
            st.session_state["_auto_plan_ran"] = True
            with st.spinner("Đang phân tích dữ liệu..."):
                st.session_state["report_plan_result"] = api.report_plan(sid, reset=False)
            plan_payload = st.session_state["report_plan_result"]
            has_plan = _plan_ok(plan_payload)

        if isinstance(plan_payload, dict) and plan_payload.get("ok") is False:
            st.error(f"API lỗi ({plan_payload.get('status_code')}): {plan_payload.get('error')}")
            st.stop()

        if not has_plan:
            st.info("Chưa có plan. Bấm **Phân tích dữ liệu**.")
            st.stop()

        plan = _get_plan(plan_payload) or {}
        options = plan.get("report_options") or []
        recommended = set(plan.get("recommended_default") or [])

        _render_plan_intro(plan_payload, sid)

        with st.expander("🛠 Thông tin kỹ thuật cho dev", expanded=False):
            st.json(
                {
                    "dataset_profile": plan.get("dataset_profile") or {},
                    "catalog_evaluation": plan.get("catalog_evaluation") or [],
                    "recommended_default": plan.get("recommended_default") or [],
                }
            )

        st.markdown("### 🧩 Chọn loại báo cáo muốn tạo")

        filtered = [o for o in options if isinstance(o, dict)]
        if not filtered:
            st.warning("Planner không trả về report_options.")
            st.json(plan)
            st.stop()

        selected_ids = _render_report_option_cards(filtered, recommended)

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

        st.markdown(
            f"""
        <div class="card card-glow">
          <div class="toolbar">
        <div class="left">
          <span class="badge-soft badge-ok"><i class="fa-solid fa-check"></i>&nbsp;Đã chọn <b>{len(selected_ids)}</b> báo cáo</span>
          <span class="badge-soft"><i class="fa-solid fa-layer-group"></i>&nbsp;Tổng <b>{len(filtered)}</b> báo cáo</span>
        </div>
        <div class="right">Generate sẽ tạo dashboard spec theo đúng selection hiện tại.</div>
          </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.write("")

        gen1, gen2 = st.columns([1.25, 3])
        with gen1:
            btn_gen = st.button("🧾 Generate Dashboard", type="primary", key="btn_generate_report")
        with gen2:
            st.caption("Tip: Chọn 1–3 loại báo cáo để dashboard gọn, rõ và dễ đọc hơn.")

        if btn_gen:
            if not selected_ids:
                st.warning("Bạn chưa chọn basocos nào.")
            else:
                with st.spinner("Đang generate dashboard spec (CI)..."):
                    st.session_state["generated_spec_result"] = api.generate_report(
                        sid,
                        selected_report_ids=selected_ids,
                        params={},
                        reset=False,
                    )

        gen_payload = st.session_state.get("generated_spec_result") or {}
        if isinstance(gen_payload, dict) and gen_payload.get("ok") is False:
            st.error(f"API lỗi ({gen_payload.get('status_code')}): {gen_payload.get('error')}")
            st.stop()

        spec = None
        if isinstance(gen_payload, dict):
            data = gen_payload.get("data") if isinstance(gen_payload.get("data"), dict) else None
            spec = (data or {}).get("spec") or gen_payload.get("spec")

        if isinstance(spec, dict) and spec:
            st.markdown(
                """
                <div class="card card-glow rise-in" style="margin: .35rem 0 1rem 0;">
                <p class="card-title">✨ Dashboard đã sẵn sàng</p>
                <p class="card-sub">Bố cục đang được dựng từ spec mới nhất mà agent vừa sinh ra.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_dashboard(spec)
        else:
            st.caption("Chưa có dashboard. Chọn basocos và bấm **Generate Dashboard**.")


# =========================================================
# QA tab
# =========================================================
with tab_qa:
    topA, topB, topC = st.columns([2, 1, 1])
    with topA:
        st.markdown(
            """
<div class="card card-glow">
  <p class="card-title">💬 QA Chat</p>
  <p class="card-sub">Hỏi đáp trên file đã Finalize (dùng cùng manifest).</p>
</div>
""",
            unsafe_allow_html=True,
        )
    with topB:
        if st.button("🧹 Clear chat", key="qa_clear"):
            st.session_state.qa_messages = []
            st.session_state["_greeted_after_finalize"] = False
            st.session_state["_qa_reset_next"] = True
            st.rerun()
    with topC:
        st.caption("Gợi ý: hỏi KPI, xu hướng, top/bottom, dữ liệu thiếu…")

    chips = [
        "Tóm tắt dataset",
        "Top 5 theo category",
        "Xu hướng theo ngày",
        "Cột nào thiếu dữ liệu nhiều nhất?",
    ]
    cchips = st.columns(len(chips))
    for i, txt in enumerate(chips):
        with cchips[i]:
            if st.button(txt, key=f"qa_chip_{i}"):
                if "qa_messages" not in st.session_state:
                    st.session_state.qa_messages = []
                st.session_state.qa_messages.append({"role": "user", "content": txt})
                st.session_state.pending_qa = True
                st.session_state.pending_q = txt
                st.rerun()

    st.caption("Chat QA hỗ trợ bạn hỏi đáp với agent về dữ liệu trong file đã upload.")

    if "qa_messages" not in st.session_state:
        st.session_state.qa_messages = []

    if not st.session_state.get("_greeted_after_finalize", False):
        st.session_state.qa_messages.append(
            {"role": "assistant", "content": "Chào bạn 👋 Bạn muốn hỏi gì về dữ liệu trong file này?"}
        )
        st.session_state["_greeted_after_finalize"] = True

    for m in st.session_state.qa_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    q = st.chat_input("Nhập câu hỏi của bạn...", key="qa_input_user_main_tabs")

    if q:
        st.session_state.qa_messages.append({"role": "user", "content": q})
        st.session_state.pending_qa = True
        st.session_state.pending_q = q
        st.rerun()

    if st.session_state.get("pending_qa"):
        last_user_q = st.session_state.get("pending_q", "")

        with st.spinner("Đang suy nghĩ (CI)..."):
            try:
                reset_chat_now = bool(st.session_state.get("_qa_reset_next", False))
                resp = api.qa(
                    session_id=sid,
                    question=last_user_q,
                    reset_chat=reset_chat_now,
                )
                st.session_state["_qa_reset_next"] = False

                answer = ""
                if isinstance(resp, dict):
                    answer = (resp.get("answer") or "").strip()
                if not answer:
                    answer = "Không nhận được 'answer' từ /qa."
            except Exception as e:
                answer = f"Lỗi gọi /qa: {e}"

        st.session_state.qa_messages.append({"role": "assistant", "content": answer})
        st.session_state.pending_qa = False
        st.session_state.pending_q = ""
        st.rerun()

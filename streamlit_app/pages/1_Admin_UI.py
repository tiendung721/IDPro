import io
import time
from typing import Any, List, Optional, Tuple

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src import api
from src.auth_guard import require_admin_login
from src.dashboard_renderer import render_dashboard
from src.state import init_state
from src.ui import sections_editor_with_add_delete, sections_to_df_1based


# =========================================================
# Page config + init
# =========================================================
st.set_page_config(page_title="Admin – AI Agent", layout="wide")
init_state()
require_admin_login()


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
# Premium Theme CSS (clone from User UI)
# =========================================================
st.markdown(
    """
<style>
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

html, body, .stApp { background: #ffffff !important; }
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
.hero h1 { font-size: 2.05rem; margin: 0 0 .35rem 0; letter-spacing: -0.02em; font-weight: 900; }
.hero p { margin: 0; opacity: .96; }

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
.pill:hover { transform: translateY(-1px); background: rgba(255,255,255,0.22); }
.pill i { animation: bob 3.8s ease-in-out infinite; }
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
.card:hover { transform: translateY(-2px); box-shadow: var(--shadow); }
.card-glow{ position:relative; overflow:hidden; }
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
.card-glow:hover:after{ animation: softSheen 1.05s ease; }
.card-title { font-size: 1.05rem; font-weight: 900; color: var(--text); margin:0; }
.card-sub { color: var(--muted); margin:.12rem 0 0 0; font-size:.93rem; }
.hr { height: 1px; background: rgba(226,232,240,.9); margin: 1rem 0; }
.caption-muted { color: var(--muted); font-size: .92rem; margin:.2rem 0 0 0; }
.rise-in { animation: riseSoft .35s ease-out both; }

.stepper{
  display:flex;
  gap:.65rem;
  flex-wrap:wrap;
  margin-top:.9rem;
}
.step{
  display:inline-flex;
  align-items:center;
  gap:.5rem;
  padding:.5rem .8rem;
  border-radius:999px;
  border:1px solid rgba(148,163,184,.35);
  background: rgba(248,250,252,.92);
  color:#334155;
  font-weight:700;
  font-size:.9rem;
}
.step .dot{
  width:10px;
  height:10px;
  border-radius:999px;
  background:#cbd5e1;
}
.step.done .dot{ background:#10b981; }
.step.on .dot{ background:#4f46e5; box-shadow:0 0 0 5px rgba(79,70,229,.12); }

.toolbar{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:1rem;
  flex-wrap:wrap;
}
.toolbar .left, .toolbar .right{
  display:flex;
  align-items:center;
  gap:.5rem;
  flex-wrap:wrap;
}
.toolbar .right{ color:#64748b; font-size:.9rem; }

.rp-card {
  position:relative;
  overflow:hidden;
  border-radius: 18px;
  border: 1px solid rgba(148,163,184,.34);
  background: linear-gradient(180deg, rgba(255,255,255,.95), rgba(248,250,252,.96));
  padding: 1rem 1rem .95rem 1rem;
  box-shadow: var(--shadow2);
  transition: transform .18s ease, box-shadow .22s ease, border-color .22s ease;
}
.rp-card:hover { transform: translateY(-2px); box-shadow: var(--shadow); border-color: rgba(99,102,241,.40); }
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
.rp-card:hover:after{ animation: softSheen 1.05s ease; }
.rp-h { margin:0 0 .3rem 0; font-weight: 950; color:#0f172a; font-size: 1.04rem; letter-spacing:-0.01em; }
.rp-meta { display:flex; flex-wrap:wrap; gap:.4rem; margin:.15rem 0 .7rem 0; }
.rp-desc { color:#334155; font-size:.93rem; margin:.2rem 0 .6rem 0; min-height: 44px; }
.rp-reason { color:#64748b; font-size:.86rem; margin: 0; line-height: 1.5; min-height: 60px; }
.rp-footer{ margin-top:.9rem; padding-top:.8rem; border-top: 1px solid rgba(226,232,240,.95); }
.rp-state{ font-size:.86rem; color:#475467; padding-top:.35rem; }

.user-table th, .user-table td {
  font-size: .93rem !important;
}

button[data-baseweb="tab"] {
  font-weight: 800 !important;
  transition: transform .14s ease, background .18s ease !important;
}
button[data-baseweb="tab"]:hover { transform: translateY(-1px); }
section[data-testid="stChatMessage"] > div {
  border-radius: 18px !important;
  border: 1px solid rgba(148,163,184,.20);
  box-shadow: 0 8px 18px rgba(2,6,23,.06);
}

div.stButton > button {
  border-radius: 14px !important;
  font-weight: 800 !important;
  transition: transform .12s ease, box-shadow .18s ease, border-color .18s ease, background .18s ease !important;
}
div.stButton > button:hover { transform: translateY(-1px); }
div.stButton > button:active { transform: translateY(0) scale(.985); }
div.stButton > button[kind="primary"] {
  border-radius: 14px !important;
  box-shadow: 0 12px 26px rgba(79,70,229,.20) !important;
}
div.stButton > button[kind="primary"]:hover {
  box-shadow: 0 16px 34px rgba(79,70,229,.28) !important;
}

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


# =========================================================
# Guards
# =========================================================
is_admin = bool(st.session_state.get("admin_logged_in")) and (st.session_state.get("admin_role") or "").upper() == "ADMIN"
if not is_admin:
    st.warning("Bạn cần đăng nhập Admin để vào trang này.")
    try:
        st.switch_page("app.py")
    except Exception:
        st.stop()

admin_token = st.session_state.get("admin_token") or ""
if not admin_token:
    st.warning("Phiên đăng nhập Admin đã hết. Vui lòng đăng nhập lại.")
    try:
        st.switch_page("app.py")
    except Exception:
        st.stop()

api.set_token(admin_token)


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
    _admin_logged_in = st.session_state.get("admin_logged_in") if keep_login else False
    _admin_token = st.session_state.get("admin_token") if keep_login else ""
    _admin_email = st.session_state.get("admin_email") if keep_login else ""
    _admin_role = st.session_state.get("admin_role") if keep_login else ""

    for k in [
        "final_spec_result_admin",
        "_preview_fetched",
        "_sections_loaded_from_be",
        "qa_messages",
        "_greeted_after_finalize",
        "finalize_rev",
        "pending_qa",
        "pending_q",
        "um_cache",
    ]:
        st.session_state.pop(k, None)

    st.session_state["session_id"] = ""
    st.session_state["sections"] = []
    st.session_state["finalized"] = False
    st.session_state["final_spec_result_admin"] = {}
    st.session_state["_preview_fetched"] = False
    st.session_state["_sections_loaded_from_be"] = False
    st.session_state["qa_messages"] = []
    st.session_state["_greeted_after_finalize"] = False

    if keep_login:
        st.session_state["admin_logged_in"] = _admin_logged_in
        st.session_state["admin_token"] = _admin_token
        st.session_state["admin_email"] = _admin_email
        st.session_state["admin_role"] = _admin_role


def make_arrow_safe(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    for c in df2.columns:
        if df2[c].dtype == "object":
            df2[c] = df2[c].map(lambda x: x.decode("utf-8", "ignore") if isinstance(x, (bytes, bytearray)) else x)
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
            height = st.slider("Chiều cao vùng xem", 320, 1200, 560, 20, key="local_view_height_admin")
        with c2:
            max_rows = st.number_input("Giới hạn số dòng", 50, 5000, 300, 50, key="local_view_rows_admin")
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
                sheet = st.selectbox("Sheet (local)", sheets, index=sheets.index(default_sheet), key="local_view_sheet_admin")
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
        st.dataframe(make_arrow_safe(df.head(int(max_rows))), use_container_width=True, height=int(height))
        st.download_button("⬇️ Tải lại file vừa chọn", data=raw, file_name=uploaded_file.name, mime="application/octet-stream", key="local_download_input_admin")


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


def sync_sections_from_be() -> bool:
    sid_now = (st.session_state.get("session_id") or "").strip()
    if not sid_now:
        return False
    r = api.sections_get(sid_now)
    sections = _extract_sections_any_shape(r)
    if not isinstance(sections, list) or not sections:
        return False
    st.session_state.sections = sections
    st.session_state["_sections_loaded_from_be"] = True
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
        st.session_state["final_spec_result_admin"] = {}
        sync_sections_from_be()
        return True

    st.error(f"{r.get('code')} – {r.get('error')}")
    with st.expander("Resp /confirm_sections"):
        st.json(r)
    return False


def _safe_get_spec(spec_payload):
    if isinstance(spec_payload, dict) and not spec_payload.get("ok", True):
        return None
    spec = None
    if isinstance(spec_payload, dict):
        data = spec_payload.get("data") if isinstance(spec_payload.get("data"), dict) else None
        spec = (data or {}).get("spec") or spec_payload.get("spec")
    return spec if isinstance(spec, dict) and spec else None


# =========================================================
# Header
# =========================================================
admin_email = st.session_state.get("admin_email", "∅")
admin_role = (st.session_state.get("admin_role") or "ADMIN").upper()

st.markdown(
    f"""
<div class="hero">
  <h1>IDPro – Excel analysis agent</h1>
  <p>
    <span class="pill"><i class="fa-regular fa-user"></i>&nbsp;{admin_email}</span>
    <span class="pill"><i class="fa-solid fa-shield-halved"></i>&nbsp;{admin_role}</span>
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
  <p class="card-sub">{admin_email} · {admin_role}</p>
  <div class="hr"></div>
  <p class="caption-muted">Admin workspace is logged in and active now.</p>
</div>
""",
        unsafe_allow_html=True,
    )
    st.write("")

    if st.button("Logout", key="btn_admin_logout_page"):
        st.session_state.admin_token = ""
        st.session_state.admin_logged_in = False
        st.session_state.admin_email = ""
        st.session_state.admin_role = ""
        st.session_state.user_mode = "USER"
        st.session_state.pop("user_token", None)
        _reset_for_new_upload(keep_login=False)
        try:
            st.switch_page("app.py")
        except Exception:
            st.rerun()

    st.divider()
    st.subheader("📤 Upload")

    file = st.file_uploader("Chọn file .xlsx/.xls/.csv", type=["xlsx", "xls", "csv"], key="admin_uploader")
    st.text_input("Sheet name (tùy chọn)", key="sheet_name")

    fp = _file_fingerprint(file)
    if fp and st.session_state.get("_last_local_fp_admin") != fp and (st.session_state.get("session_id") or ""):
        st.session_state["_last_local_fp_admin"] = fp
        _reset_for_new_upload(keep_login=True)
        for k in ["local_view_sheet_admin", "local_view_height_admin", "local_view_rows_admin", "local_download_input_admin"]:
            st.session_state.pop(k, None)
    elif fp and st.session_state.get("_last_local_fp_admin") != fp:
        st.session_state["_last_local_fp_admin"] = fp

    _render_local_file_view(file, (st.session_state.get("sheet_name") or "").strip() or None)

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

    if st.button("🚀 Upload & Auto Identify", type="primary", key="btn_admin_upload"):
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
    <i class="fa-solid fa-ticket"></i>&nbsp;Session: <b>{sid_sidebar or '∅'}</b>
  </span>
  <span class="badge-soft {'badge-ok' if finalized_sidebar else 'badge-warn'}">
    <i class="fa-solid fa-lock"></i>&nbsp;Finalized: <b>{'YES' if finalized_sidebar else 'NO'}</b>
  </span>
</div>
""",
        unsafe_allow_html=True,
    )


# =========================================================
# Main tabs
# =========================================================
workspace_tab, users_tab = st.tabs(["📊 Admin Workspace", "👥 User Management"])


# =========================================================
# Workspace (clone User layout)
# =========================================================
with workspace_tab:
    sid = (st.session_state.session_id or "").strip()
    finalized = bool(st.session_state.get("finalized", False))
    has_sections = bool(st.session_state.get("sections"))

    if sid and not st.session_state.get("_sections_loaded_from_be", False):
        sync_sections_from_be()

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
        st.button("🔄 Tải lại preview", on_click=fetch_preview, disabled=not bool(sid), key="btn_admin_preview_reload_main")
    with row1[1]:
        st.caption("Mẹo: Điều chỉnh start/end/header để Agent cắt bảng chính xác.")

    if not st.session_state.get("sections"):
        st.warning("Chưa có bảng. Bấm 'Tải lại preview' hoặc Upload lại.")
        st.stop()

    df1 = sections_to_df_1based(st.session_state.get("sections", []))
    edited_zero_df, del_rows, _ = sections_editor_with_add_delete(
        df1,
        key_prefix="secx_admin_main_clone",
        lang="vi",
        show_titles=False,
        show_create=False,
    )

    act1, act2, act3 = st.columns([1, 1, 2])
    with act1:
        if st.button("✅ Áp dụng thay đổi", key="btn_admin_apply_sections_main_clone"):
            payload = edited_zero_df.to_dict(orient="records")
            res = api.sections_replace(sid, payload)
            if isinstance(res, dict) and res.get("ok"):
                st.success("Đã cập nhật bảng.")
                st.session_state["sections"] = res["data"]["sections"]
                st.session_state["finalized"] = False
                st.session_state["final_spec_result_admin"] = {}
            else:
                st.error(res)

    with act2:
        if st.button("🗑️ Xoá bảng đã chọn", key="btn_admin_delete_sections_main_clone"):
            cur = edited_zero_df.to_dict(orient="records")
            keep = [v for i, v in enumerate(cur) if i not in del_rows]
            res = api.sections_replace(sid, keep)
            if isinstance(res, dict) and res.get("ok"):
                st.success("Đã xoá.")
                st.session_state["sections"] = res["data"]["sections"]
                st.session_state["finalized"] = False
                st.session_state["final_spec_result_admin"] = {}
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
                new_start = st.number_input("Dòng bắt đầu", min_value=1, value=int(default_new_start), key="secx_admin_new_start_clone")
            with c2:
                new_end = st.number_input("Dòng kết thúc", min_value=int(new_start), value=int(new_start), key="secx_admin_new_end_clone")
            with c3:
                new_header = st.number_input("Dòng tiêu đề", min_value=int(new_start), max_value=int(new_end), value=int(new_start), key="secx_admin_new_header_clone")
            with c4:
                new_label = st.text_input("Tên bảng", value="", key="secx_admin_new_label_clone")

            create_payload = {
                "start_row": int(new_start - 1),
                "end_row": int(new_end - 1),
                "header_row": int(new_header - 1),
                "label": (new_label or "").strip(),
            }

            if st.button("Thêm bảng mới", key="btn_admin_add_section_main_clone"):
                res = api.sections_add(sid, create_payload)
                if isinstance(res, dict) and res.get("ok"):
                    st.success("Đã thêm.")
                    st.session_state["sections"] = res["data"]["sections"]
                    st.session_state["finalized"] = False
                    st.session_state["final_spec_result_admin"] = {}
                else:
                    st.error(res)

    confirm_col1, confirm_col2, confirm_col3 = st.columns([1, 1, 2])
    with confirm_col1:
        if st.button("🔒 Xác nhận cấu trúc (Finalize)", type="primary", key="btn_admin_finalize_clone"):
            st.session_state["sections"] = edited_zero_df.to_dict(orient="records")
            with st.spinner("Đang finalize sections..."):
                ok = finalize_sections()
            if ok:
                st.rerun()
    with confirm_col2:
        if st.button("💾 Save Template", key="btn_admin_save_template_clone"):
            st.session_state["sections"] = edited_zero_df.to_dict(orient="records")
            if not st.session_state.get("finalized", False):
                with st.spinner("Đang finalize trước khi lưu template..."):
                    ok = finalize_sections()
                if not ok:
                    st.stop()
            with st.spinner("Đang lưu template..."):
                r2 = api.admin_save_template(sid, (st.session_state.get("sheet_name") or "").strip() or None)
            if isinstance(r2, dict) and (r2.get("ok") is True or "data" in r2 or "message" in r2):
                st.success("Admin đã Confirm & lưu Rule Template.")
            else:
                st.error(f"{r2.get('code')} – {r2.get('error')}")
                with st.expander("Resp /admin/save_template"):
                    st.json(r2)
    with confirm_col3:
        st.caption("Finalize xong → hệ thống khóa manifest. Admin có thể tạo dashboard, chat QA và lưu template.")

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

    st.markdown(
        """
<div class="card card-glow">
  <p class="card-title">📊 Báo cáo & Hỏi đáp</p>
  <p class="card-sub">Admin workspace dùng luồng Final Spec → Dashboard. QA chat dùng cùng manifest đã finalize.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    if not st.session_state.get("finalized", False):
        st.info("Bạn cần Finalize cấu trúc trước khi tạo báo cáo và chat.")
        st.stop()

    tab_report, tab_qa = st.tabs(["📊 Analysis Report", "💬 Chatbot QA"])

    with tab_report:
        st.markdown(
            """
<div class="card card-glow">
  <p class="card-title">🧠 Report Builder</p>
  <p class="card-sub">Admin dùng Final Spec để sinh dashboard hoàn chỉnh từ session hiện tại.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        st.write("")

        cA, cB = st.columns([1.2, 3])
        with cA:
            btn_gen = st.button("🧾 Generate Dashboard", type="primary", key="btn_admin_generate_dashboard")
        with cB:
            st.caption("Flow admin hiện dùng trực tiếp /final_spec để sinh dashboard spec.")

        if btn_gen:
            with st.spinner("Đang tạo Final Spec (CI)..."):
                st.session_state["final_spec_result_admin"] = api.run_final_spec(sid)

        gen_payload = st.session_state.get("final_spec_result_admin") or {}
        if isinstance(gen_payload, dict) and gen_payload.get("ok") is False:
            st.error(f"API lỗi ({gen_payload.get('status_code')}): {gen_payload.get('error')}")
            with st.expander("Resp /final_spec"):
                st.json(gen_payload)
            st.stop()

        spec = _safe_get_spec(gen_payload)
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
            st.caption("Chưa có dashboard. Bấm **Generate Dashboard** để tạo report.")

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
            if st.button("🧹 Clear chat", key="qa_clear_admin_clone"):
                st.session_state.qa_messages = []
                st.session_state["_greeted_after_finalize"] = False
                st.rerun()
        with topC:
            st.caption("Gợi ý: hỏi KPI, xu hướng, top/bottom, dữ liệu thiếu…")

        chips = ["Tóm tắt dataset", "Top 5 theo category", "Xu hướng theo ngày", "Cột nào thiếu dữ liệu nhiều nhất?"]
        cchips = st.columns(len(chips))
        for i, txt in enumerate(chips):
            with cchips[i]:
                if st.button(txt, key=f"qa_chip_admin_{i}"):
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
            st.session_state.qa_messages.append({"role": "assistant", "content": "Chào bạn 👋 Bạn muốn hỏi gì về dữ liệu trong file này?"})
            st.session_state["_greeted_after_finalize"] = True

        for m in st.session_state.qa_messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        q = st.chat_input("Nhập câu hỏi của bạn...", key="qa_input_admin_main_tabs_clone")
        if q:
            st.session_state.qa_messages.append({"role": "user", "content": q})
            st.session_state.pending_qa = True
            st.session_state.pending_q = q
            st.rerun()

        if st.session_state.get("pending_qa"):
            last_user_q = st.session_state.get("pending_q", "")
            with st.spinner("Đang suy nghĩ (CI)..."):
                try:
                    resp = api.qa(session_id=sid, question=last_user_q, reset_chat=False)
                    answer = ""
                    if isinstance(resp, dict):
                        answer = (resp.get("answer") or "").strip()
                    if not answer:
                        answer = "Không nhận được 'answer' từ /qa."
                except Exception as e:
                    answer = f"Lỗi khi gọi /qa: {e}"
            st.session_state.qa_messages.append({"role": "assistant", "content": answer})
            st.session_state.pending_qa = False
            st.session_state.pending_q = ""
            st.rerun()


# =========================================================
# User management
# =========================================================
with users_tab:
    st.markdown(
        """
<div class="card card-glow">
  <p class="card-title">👥 Quản lý user</p>
  <p class="card-sub">Xem danh sách người dùng, cập nhật role/trạng thái và tạo tài khoản mới.</p>
</div>
""",
        unsafe_allow_html=True,
    )
    st.write("")

    top1, top2 = st.columns([1, 3])
    with top1:
        if st.button("🔄 Tải danh sách user", key="um_reload_clone") or "um_cache" not in st.session_state:
            st.session_state["um_cache"] = api.admin_list_users()
    with top2:
        st.caption("Khu vực này giữ logic admin gốc nhưng bọc lại cùng style của User UI.")

    users_resp = st.session_state.get("um_cache", {})
    users = []
    if isinstance(users_resp, dict):
        users = users_resp.get("data", {}).get("users") or users_resp.get("users") or []

    if isinstance(users_resp, dict) and users_resp.get("ok") is False:
        st.error(f"{users_resp.get('code')} – {users_resp.get('error')}")
        with st.expander("Resp /admin/users"):
            st.json(users_resp)
    else:
        st.markdown(
            f"""
<div class="card card-glow">
  <div class="toolbar">
    <div class="left">
      <span class="badge-soft badge-ok"><i class="fa-solid fa-users"></i>&nbsp;Tổng user <b>{len(users)}</b></span>
    </div>
    <div class="right">Chọn 1 user để cập nhật role hoặc trạng thái hoạt động.</div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        st.write("")

        if users:
            df_users = pd.DataFrame(users)
            st.dataframe(make_arrow_safe(df_users), use_container_width=True, height=320)

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
            st.markdown("### ✏️ Chỉnh sửa user")
            uid = st.selectbox(
                "Chọn user để sửa",
                options=[u["id"] for u in users],
                format_func=lambda x: next((f'{u.get("username") or u.get("email") or x} ({u.get("role")})' for u in users if u["id"] == x), str(x)),
                key="um_pick_clone",
            )
            u = next((x for x in users if x["id"] == uid), None)
            if u:
                e1, e2, e3 = st.columns([1, 1, 2])
                with e1:
                    new_role = st.selectbox("Role", ["USER", "ADMIN"], index=(0 if u.get("role") == "USER" else 1), key="um_edit_role_clone")
                with e2:
                    new_active = st.toggle("Active", value=bool(u.get("is_active")), key="um_edit_active_clone")
                with e3:
                    if st.button("💾 Lưu thay đổi", type="primary", key="um_save_clone"):
                        r = api.admin_update_user(uid, role=new_role, is_active=new_active)
                        if isinstance(r, dict) and r.get("ok"):
                            st.success("Đã cập nhật user.")
                            st.session_state.pop("um_cache", None)
                            st.rerun()
                        else:
                            st.error(r)
        else:
            st.info("Chưa có user.")

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
        st.markdown("### ➕ Tạo user mới")

        nu1, nu2, nu3 = st.columns([2, 1, 1])
        with nu1:
            new_username = st.text_input("Username (USER quick)", key="um_new_username_clone")
        with nu2:
            new_role = st.selectbox("Role", ["USER", "ADMIN"], key="um_new_role_clone")
        with nu3:
            new_active = st.toggle("Active", value=True, key="um_new_active_clone")

        admin_new_email = ""
        admin_new_password = ""
        if new_role == "ADMIN":
            st.info("ADMIN bắt buộc có Email + Password (không dùng quick username-only).")
            a1, a2 = st.columns([2, 2])
            with a1:
                admin_new_email = st.text_input("Admin Email", key="um_new_email_clone")
            with a2:
                admin_new_password = st.text_input("Admin Password", type="password", key="um_new_password_clone")
        else:
            st.caption("USER quick: đăng nhập bằng username, không cần mật khẩu.")

        if st.button("🚀 Create user", type="primary", key="um_create_clone"):
            if new_role == "ADMIN":
                if not admin_new_email.strip() or not admin_new_password.strip():
                    st.error("ADMIN bắt buộc có Email và Password.")
                else:
                    payload_username = new_username.strip() if new_username.strip() else None
                    r = api.admin_create_user(
                        username=payload_username,
                        role="ADMIN",
                        is_active=new_active,
                        email=admin_new_email.strip(),
                        password=admin_new_password,
                    )
                    if isinstance(r, dict) and r.get("ok"):
                        st.success("Đã tạo admin mới.")
                        st.session_state.pop("um_cache", None)
                        st.rerun()
                    else:
                        st.error(r)
            else:
                if not new_username.strip():
                    st.error("Username không được rỗng.")
                else:
                    r = api.admin_create_user(username=new_username.strip(), role="USER", is_active=new_active)
                    if isinstance(r, dict) and r.get("ok"):
                        st.success("Đã tạo user mới.")
                        st.session_state.pop("um_cache", None)
                        st.rerun()
                    else:
                        st.error(r)

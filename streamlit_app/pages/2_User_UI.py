import streamlit as st

from src.state import init_state
from src import api
from src.ui import sections_to_df_1based, sections_editor_with_add_delete
from src.dashboard_renderer import render_dashboard

# =========================
# Page config + styles
# =========================
st.set_page_config(page_title="User – AI Agent", layout="wide")
init_state()

st.markdown("""
<style>
/* Layout tighten */
.block-container { padding-top: 1.0rem; padding-bottom: 3rem; }

/* Hero */
.hero {
  padding: 1.6rem 1.7rem;
  border-radius: 18px;
  background: radial-gradient(1200px circle at 10% 10%, rgba(255,255,255,0.22), transparent 55%),
              linear-gradient(120deg, #4f46e5, #06b6d4);
  color: white;
  margin-bottom: 1.2rem;
  box-shadow: 0 18px 40px rgba(0,0,0,0.12);
}
.hero h1 { font-size: 2rem; margin: 0 0 .35rem 0; }
.hero p { margin: 0; opacity: .92; }

/* Chips */
.chip {
  display: inline-block;
  padding: .22rem .55rem;
  border-radius: 999px;
  background: rgba(255,255,255,0.18);
  border: 1px solid rgba(255,255,255,0.25);
  margin-right: .4rem;
  font-size: .85rem;
}

/* KPI cards */
.kpi-grid { margin: .2rem 0 1rem 0; }
.kpi {
  background: #ffffff;
  border-radius: 16px;
  padding: 1rem 1.1rem;
  box-shadow: 0 12px 28px rgba(0,0,0,0.06);
  border: 1px solid #f1f5f9;
}
.kpi .t { font-size: .82rem; color: #64748b; margin-bottom: .25rem; }
.kpi .v { font-size: 1.45rem; font-weight: 700; color: #0f172a; }

/* Report canvas */
.report-canvas {
  background: linear-gradient(180deg, #fafafa, #ffffff);
  padding: 1.25rem 1.25rem;
  border-radius: 20px;
  border: 1px solid #e5e7eb;
  box-shadow: 0 18px 40px rgba(2, 6, 23, 0.06);
}

/* Subtle divider */
.hr {
  height: 1px;
  background: #e5e7eb;
  margin: 1.1rem 0 1.1rem 0;
}
</style>
""", unsafe_allow_html=True)

# =========================
# Guard
# =========================
if not st.session_state.get("user_name"):
    st.warning("Bạn cần đăng nhập User trước.")
    try:
        st.switch_page("app.py")
    except Exception:
        st.stop()
        
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
</style>
""", unsafe_allow_html=True)


if not st.session_state.get("user_token"):
    st.warning("Phiên đăng nhập đã hết hoặc chưa có token. Vui lòng đăng nhập lại.")
    st.switch_page("app.py")
    st.stop()

api.set_token(st.session_state["user_token"])

# =========================
# Header
# =========================
user_name = st.session_state.get("user_name", "∅")
user_role = st.session_state.get("user_role", "USER")

st.markdown(f"""
<div class="hero">
  <h1>AI Agent – Excel analysis with LLM</h1>
  <p>
    <span class="chip">👤 {user_name}</span>
    <span class="chip">🔐 {user_role}</span>
    <span class="chip">📊 Final Spec Dashboard</span>
    <span class="chip">💬 QA Chat</span>
  </p>
</div>
""", unsafe_allow_html=True)

# =========================
# Helpers
# =========================
def _extract_sections_any_shape(obj):
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

def _reset_for_new_upload(keep_login: bool = True):
    # giữ login
    _user_name = st.session_state.get("user_name") if keep_login else ""
    _user_token = st.session_state.get("user_token") if keep_login else None
    _user_mode = st.session_state.get("user_mode") if keep_login else "USER"

    # clear session-related states
    for k in [
        "final_spec_result",
        "_preview_fetched", "_sections_loaded_from_be",
        "qa_messages", "_greeted_after_finalize",
        "finalize_rev", "_last_final_rev", "_last_final_sid", "_last_final_sheet",
        "pending_qa", "pending_q",
    ]:
        st.session_state.pop(k, None)

    st.session_state["session_id"] = ""
    st.session_state["sections"] = []
    st.session_state["finalized"] = False
    st.session_state["final_spec_result"] = {}
    st.session_state["_preview_fetched"] = False
    st.session_state["_sections_loaded_from_be"] = False
    st.session_state["qa_messages"] = []
    st.session_state["_greeted_after_finalize"] = False

    if keep_login:
        st.session_state["user_name"] = _user_name
        if _user_token:
            st.session_state["user_token"] = _user_token
        st.session_state["user_mode"] = _user_mode

def fetch_preview():
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
    return True

def finalize_sections():
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
        return True

    st.error(f"{r.get('code')} – {r.get('error')}")
    with st.expander("Resp /confirm_sections"):
        st.json(r)
    return False

def _safe_get_spec(spec_payload):
    # 1) Nếu API báo lỗi → show rõ
    if isinstance(spec_payload, dict) and not spec_payload.get("ok", True):
        st.error(
            f"API lỗi ({spec_payload.get('status_code')}): "
            f"{spec_payload.get('error')}"
        )
        return None

    # 2) Trích spec
    spec = None
    if isinstance(spec_payload, dict):
        data = spec_payload.get("data") if isinstance(spec_payload.get("data"), dict) else None
        spec = (data or {}).get("spec") or spec_payload.get("spec")

    if isinstance(spec, dict) and spec:
        return spec
    return None

def _estimate_spec_stats(spec: dict):
    # Cố gắng ước lượng số "tabs/blocks" mà không phụ thuộc schema cứng
    tabs = 0
    blocks = 0

    if not isinstance(spec, dict):
        return tabs, blocks

    for k in ("tabs", "pages", "sections"):
        if isinstance(spec.get(k), list):
            tabs = len(spec.get(k))
            for item in spec.get(k):
                if isinstance(item, dict):
                    for kk in ("blocks", "widgets", "charts", "cards", "items"):
                        if isinstance(item.get(kk), list):
                            blocks += len(item.get(kk))

    # fallback: tìm list-level trong root
    if tabs == 0:
        for k, v in spec.items():
            if isinstance(v, list) and len(v) > tabs:
                tabs = len(v)

    return tabs, blocks

# =========================
# Sidebar: Upload + Sheet name ONLY
# =========================
with st.sidebar:
    st.success(f"USER: {st.session_state.get('user_name')}")

    if st.button("Logout", key="btn_user_logout_page"):
        st.session_state.user_name = ""
        st.session_state.user_mode = "USER"
        st.session_state.pop("user_token", None)

        st.session_state.session_id = ""
        st.session_state.sections = []
        st.session_state.finalized = False
        st.session_state.final_spec_result = {}
        st.session_state._preview_fetched = False
        st.session_state._sections_loaded_from_be = False
        for k in ["qa_messages", "finalize_rev", "_last_final_rev", "_last_final_sid", "_last_final_sheet",
                  "_greeted_after_finalize", "final_spec_result", "pending_qa", "pending_q"]:
            st.session_state.pop(k, None)

        try:
            st.switch_page("app.py")
        except Exception:
            st.rerun()

    st.divider()
    st.subheader("Upload")
    file = st.file_uploader("Chọn file .xlsx/.xls/.csv", type=["xlsx", "xls", "csv"], key="user_uploader")
    st.text_input("Sheet name (tùy chọn)", key="sheet_name")

    if st.button("Upload", type="primary", key="btn_user_upload"):
        if not file:
            st.warning("Chưa chọn file.")
        else:
            # reset session for new upload (but keep login)
            _reset_for_new_upload(keep_login=True)

            res = api.upload_file(file, st.session_state.sheet_name or None)
            if isinstance(res, dict) and res.get("ok"):
                sid = res.get("data", {}).get("session_id") or ""
                if not sid:
                    st.error("Upload OK nhưng không nhận được session_id.")
                else:
                    st.session_state.session_id = sid
                    st.success("Upload OK.")
                    # auto preview để tiết kiệm thao tác
                    with st.spinner("Đang phân tích cấu trúc bảng..."):
                        fetch_preview()
            else:
                st.error(f"{res.get('code')} – {res.get('error')}")
                with st.expander("Resp /upload"):
                    st.json(res)

    sid_sidebar = (st.session_state.session_id or "").strip()
    st.caption(f"Session: **{sid_sidebar or '∅'}**")

# =========================
# MAIN: Step 1 & 2 (no tabs)
# =========================
st.subheader("Preview & chỉnh sửa cấu trúc")

sid = (st.session_state.session_id or "").strip()
sheet = (st.session_state.sheet_name or "").strip() or None

row1 = st.columns([1, 3, 2])
with row1[0]:
    st.button("Tải lại preview", on_click=fetch_preview, disabled=not bool(sid), key="btn_user_preview_reload_main")
with row1[1]:
    st.write("Hệ thống tự detect các vùng bảng. Bạn có thể chỉnh trực tiếp trên bảng preview, rồi bấm **Áp dụng thay đổi**.")

if not sid:
    st.info("Bạn hãy Upload file ở sidebar trước.")
    st.stop()

if not st.session_state.get("sections"):
    st.warning("Chưa có bảng. Bấm 'Tải lại preview' hoặc Upload lại.")
    st.stop()

# ===== One unified editable preview (1-based in UI) =====
df1 = sections_to_df_1based(st.session_state.get("sections", []))
edited_zero_df, del_rows, _ = sections_editor_with_add_delete(
    df1,
    key_prefix="secx_user_main",
    lang="vi",
    show_titles=False,
    show_create=False,
)

# ===== Actions =====
act1, act2, act3 = st.columns([1, 1, 2])
with act1:
    if st.button("Áp dụng thay đổi", key="btn_user_apply_sections_main"):
        payload = edited_zero_df.to_dict(orient="records")
        res = api.sections_replace(sid, payload)
        if isinstance(res, dict) and res.get("ok"):
            st.success("Đã cập nhật bảng.")
            st.session_state["sections"] = res["data"]["sections"]
        else:
            st.error(res)

with act2:
    if st.button("Xoá bảng đã chọn", key="btn_user_delete_sections_main"):
        cur = edited_zero_df.to_dict(orient="records")
        keep = [v for i, v in enumerate(cur) if i not in del_rows]
        res = api.sections_replace(sid, keep)
        if isinstance(res, dict) and res.get("ok"):
            st.success("Đã xoá.")
            st.session_state["sections"] = res["data"]["sections"]
        else:
            st.error(res)

with act3:
    with st.expander("Thêm bảng mới (1-based)"):
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
            new_header = st.number_input("Dòng tiêu đề", min_value=int(new_start), max_value=int(new_end), value=int(new_start), key="secx_user_new_header")
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

confirm_col1, confirm_col2 = st.columns([1, 3])
with confirm_col1:
    if st.button("Xác nhận cấu trúc (Finalize)", type="primary", key="btn_user_finalize_main"):
        with st.spinner("Đang finalize sections..."):
            finalize_sections()
with confirm_col2:
    st.write(f"Confirmed: {'✅' if st.session_state.get('finalized') else '—'}")
    st.caption("Sau khi Xác nhận cấu trúc, bạn có thể tạo báo cáo và bắt đầu chat QA.")


# =========================
# STEP 3: TABS (Report / QA)
# =========================
st.subheader("Báo cáo & Hỏi đáp")

if not st.session_state.get("finalized", False):
    st.info("Bạn cần Xác nhận cấu trúc ở bước 2 trước khi tạo báo cáo và chat.")
    st.stop()

tab_report, tab_qa = st.tabs(["📊 Analysis Report", "💬 Chatbot QA"])

# ---------- REPORT TAB ----------
with tab_report:
    # Dashboard spec
    dash_col1, dash_col2 = st.columns([1, 3])
    with dash_col1:
        if st.button("Tạo báo cáo dashboard", type="primary", key="btn_user_run_final_spec"):
            with st.spinner("Đang tạo report spec (CI)..."):
                st.session_state.final_spec_result = api.run_final_spec(sid)

    spec_payload = st.session_state.get("final_spec_result") or {}

    # 1. Nếu API báo lỗi → show rõ
    if isinstance(spec_payload, dict) and not spec_payload.get("ok", True):
        st.error(
            f"API lỗi ({spec_payload.get('status_code')}): "
            f"{spec_payload.get('error')}"
        )
        st.stop()

    # 2. Trích spec
    spec = None
    if isinstance(spec_payload, dict):
        data = spec_payload.get("data") if isinstance(spec_payload.get("data"), dict) else None
        spec = (data or {}).get("spec") or spec_payload.get("spec")

    # 3. Render (KHÔNG EXPANDER)
    if isinstance(spec, dict) and spec:
        render_dashboard(spec)
    else:
        st.caption("Chưa có dashboard report. Bấm **Tạo báo cáo dashboard** để sinh spec và render.")

# ---------- QA TAB ----------
with tab_qa:
    st.caption("Chat QA hỗ trợ bạn hỏi đáp với agent về dữ liệu trong file đã upload.")

    if "qa_messages" not in st.session_state:
        st.session_state.qa_messages = []

    # greeting once (after finalize)
    if not st.session_state.get("_greeted_after_finalize", False):
        st.session_state.qa_messages.append(
            {"role": "assistant", "content": "Chào bạn 👋 Bạn muốn hỏi gì về dữ liệu trong file này?"}
        )
        st.session_state["_greeted_after_finalize"] = True

    # render chat
    for m in st.session_state.qa_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    q = st.chat_input("Nhập câu hỏi của bạn...", key="qa_input_user_main_tabs")

    if q:
        st.session_state.qa_messages.append({"role": "user", "content": q})
        st.session_state.pending_qa = True
        st.session_state.pending_q = q
        st.rerun()

    # If pending => call QA and append assistant answer
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
                answer = f"Lỗi gọi /qa: {e}"

        st.session_state.qa_messages.append({"role": "assistant", "content": answer})
        st.session_state.pending_qa = False
        st.session_state.pending_q = ""
        st.rerun()

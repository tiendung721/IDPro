import streamlit as st
import pandas as pd

from src.state import init_state
from src import api

from src.ui import sections_to_df_1based, sections_editor_with_add_delete
from src.dashboard_renderer import render_dashboard


st.set_page_config(page_title="Admin – AI Agent", layout="wide")
init_state()

st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }

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

# ===== Guard =====
is_admin = bool(st.session_state.get("admin_logged_in")) and (st.session_state.get("admin_role") or "").upper() == "ADMIN"
if not is_admin:
    st.warning("Bạn cần đăng nhập Admin để vào trang này.")
    try:
        st.switch_page("app.py")
    except Exception:
        st.stop()

# admin token
api.set_token(st.session_state.get("admin_token") or "")

admin_email = st.session_state.get("admin_email") or "∅"
admin_role = (st.session_state.get("admin_role") or "∅").upper()

st.markdown(f"""
<div class="hero">
  <h1>AI Agent – Excel analysis with LLM</h1>
  <p>
    <span class="chip">🛡️ {admin_email}</span>
    <span class="chip">🔐 {admin_role}</span>
    <span class="chip">📊 Final Spec Dashboard</span>
    <span class="chip">💬 QA Chat</span>
  </p>
</div>
""", unsafe_allow_html=True)

# =========================
# Helpers: preview sections parsing
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


def sync_sections_from_be():
    sid_now = (st.session_state.get("session_id") or "").strip()
    if not sid_now:
        st.warning("Chưa có session_id.")
        return False
    r = api.sections_get(sid_now)
    sections = _extract_sections_any_shape(r)
    if not isinstance(sections, list) or not sections:
        st.error("Không kéo được sections từ BE.")
        with st.expander("Response GET /sessions/{id}/sections"):
            st.json(r)
        return False
    st.session_state.sections = sections
    st.session_state["_sections_loaded_from_be"] = True
    return True


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

def _safe_get_spec(spec_payload):
    
    if isinstance(spec_payload, dict) and not spec_payload.get("ok", True):
        return None

    spec = None
    if isinstance(spec_payload, dict):
        data = spec_payload.get("data") if isinstance(spec_payload.get("data"), dict) else None
        spec = (data or {}).get("spec") or spec_payload.get("spec")

    if isinstance(spec, dict) and spec:
        return spec
    return None


# =========================
# Sidebar: Upload + Session controls + Logout
# =========================
with st.sidebar:
    st.success("ADMIN đã đăng nhập")
    
    if st.button("Admin Logout", key="btn_admin_logout_page"):
        st.session_state.admin_token = ""
        st.session_state.admin_logged_in = False
        st.session_state.admin_email = ""
        st.session_state.admin_role = ""
        st.session_state.user_mode = "USER"
        st.session_state.pop("user_token", None)
        try:
            st.switch_page("app.py")
        except Exception:
            st.rerun()
            
    st.divider()
    
    st.subheader("Upload")
    file = st.file_uploader("Chọn file .xlsx/.xls/.csv", type=["xlsx", "xls", "csv"])
    st.text_input("Sheet name (tùy chọn)", key="sheet_name")

    if st.button("Gửi file lên BE", key="btn_upload_sidebar"):
        if not file:
            st.warning("Chưa chọn file.")
        else:
            res = api.upload_file(file, st.session_state.sheet_name or None)
            with st.expander("Resp /upload"):
                st.json(res)

            if isinstance(res, dict) and res.get("ok"):
                sid = res.get("data", {}).get("session_id") or ""
                if sid:
                    st.session_state.session_id = sid
                    st.session_state._preview_fetched = False
                    st.session_state["_sections_loaded_from_be"] = False
                    st.session_state.finalized = False

                    # reset report + chat states
                    st.session_state["_greeted_after_finalize"] = False
                    st.session_state.qa_messages = []
                    st.session_state.finalize_rev = 0
                    st.session_state["final_spec_result_admin"] = {}


                    st.success(f"Upload OK. session_id = {sid}")
                else:
                    st.error("Upload OK nhưng không nhận được session_id.")
            else:
                st.error(f"{res.get('code')} – {res.get('error')}")

    st.divider()
    if st.button("Test /health", key="btn_health_sidebar"):
        st.json(api.health())


# =========================
# Tabs
# =========================
tab_ops, tab_users = st.tabs(["Vận hành", "Quản lý user"])

# =========================
# TAB: Vận hành
# =========================
with tab_ops:
    st.subheader("Preview & chỉnh sửa cấu trúc")

    sid = (st.session_state.session_id or "").strip()
    sheet = (st.session_state.sheet_name or "").strip() or None
    st.caption(f"Session: **{sid or '∅'}** | Sheet: **{sheet or 'None'}** | Role: **ADMIN**")

    row1 = st.columns([1, 3, 2])
    with row1[0]:
        st.button("Tải lại preview", on_click=fetch_preview, disabled=not bool(sid), key="btn_admin_preview_reload_main")
    with row1[1]:
        st.write("Hệ thống tự detect các vùng bảng. Bạn có thể chỉnh trực tiếp trên bảng preview, rồi bấm **Áp dụng thay đổi**.")

    if not sid:
        st.info("Hãy Upload file ở sidebar để có session_id trước.")
        st.stop()

    # auto preview once
    if not st.session_state.get("_preview_fetched", False) and sid:
        st.session_state._preview_fetched = True
        fetch_preview()

    # nếu muốn luôn lấy sections từ BE (để đồng bộ) thì sync
    if sid and not st.session_state.get("_sections_loaded_from_be", False):
        try:
            resp = api.sections_get(sid)
            if isinstance(resp, dict) and resp.get("ok"):
                st.session_state["sections"] = resp["data"]["sections"]
                st.session_state["_sections_loaded_from_be"] = True
        except Exception as e:
            st.warning(f"Không tải được sections: {e}")

    if not st.session_state.get("sections"):
        st.warning("Chưa có bảng. Bấm 'Tải lại preview' hoặc Upload lại.")
        st.stop()

    # ===== One unified editable preview (1-based in UI) =====
    df1 = sections_to_df_1based(st.session_state.get("sections", []))
    edited_zero_df, del_rows, _ = sections_editor_with_add_delete(
        df1,
        key_prefix="secx_admin_main",
        lang="vi",
        show_titles=False,
        show_create=False,
    )

    # ===== Actions =====
    row_top = st.columns([1, 1, 2])
    row_bottom = st.columns([1, 1, 2]) 

    # --- TOP ROW: apply / delete / add ---
    with row_top[0]:
        if st.button("Áp dụng thay đổi", key="btn_admin_apply_sections_main", use_container_width=True):
            payload = edited_zero_df.to_dict(orient="records")
            res = api.sections_replace(sid, payload)
            if isinstance(res, dict) and res.get("ok"):
                st.success("Đã cập nhật sections lên BE.")
                st.session_state["sections"] = res["data"]["sections"]
                st.session_state.finalized = False
                st.session_state.qa_messages = []
                st.session_state["_greeted_after_finalize"] = False
            else:
                st.error(res)

    with row_top[1]:
        if st.button("Xoá bảng đã chọn", key="btn_admin_delete_sections_main", use_container_width=True):
            cur = edited_zero_df.to_dict(orient="records")
            keep = [v for i, v in enumerate(cur) if i not in del_rows]
            res = api.sections_replace(sid, keep)
            if isinstance(res, dict) and res.get("ok"):
                st.success("Đã xoá.")
                st.session_state["sections"] = res["data"]["sections"]
                st.session_state.finalized = False
                st.session_state.qa_messages = []
                st.session_state["_greeted_after_finalize"] = False
            else:
                st.error(res)

    with row_top[2]:
        with st.expander("Thêm bảng mới (1-based)", expanded=False):
            c1, c2, c3, c4 = st.columns(4)

            default_new_start = 1
            try:
                if not df1.empty and "start_row" in df1.columns:
                    default_new_start = int(df1["start_row"].max()) + 1
            except Exception:
                default_new_start = 1

            with c1:
                new_start = st.number_input("Dòng bắt đầu", min_value=1, value=int(default_new_start), key="secx_admin_new_start")
            with c2:
                new_end = st.number_input("Dòng kết thúc", min_value=int(new_start), value=int(new_start), key="secx_admin_new_end")
            with c3:
                new_header = st.number_input("Dòng tiêu đề", min_value=int(new_start), max_value=int(new_end), value=int(new_start), key="secx_admin_new_header")
            with c4:
                new_label = st.text_input("Tên bảng", value="", key="secx_admin_new_label")

            create_payload = {
                "start_row": int(new_start - 1),
                "end_row": int(new_end - 1),
                "header_row": int(new_header - 1),
                "label": (new_label or "").strip(),
            }

            if st.button("Thêm bảng mới", key="btn_admin_add_section_main", use_container_width=True):
                res = api.sections_add(sid, create_payload)
                if isinstance(res, dict) and res.get("ok"):
                    st.success("Đã thêm.")
                    st.session_state["sections"] = res["data"]["sections"]
                    st.session_state.finalized = False
                    st.session_state.qa_messages = []
                    st.session_state["_greeted_after_finalize"] = False
                else:
                    st.error(res)

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

    # --- BOTTOM ROW: finalize / save template ---
    with row_bottom[0]:
        if st.button("Finalize sections (Report/QA)", type="primary", key="btn_admin_finalize_main", use_container_width=True):
            edited_payload = edited_zero_df.to_dict(orient="records")
            with st.spinner("Đang finalize sections..."):
                r = api.finalize_sections(sid, edited_payload, sheet)

            ok = isinstance(r, dict) and (r.get("ok") is True or "data" in r or "message" in r)
            if ok:
                st.session_state.finalized = True
                st.session_state.finalize_rev = int(st.session_state.get("finalize_rev", 0)) + 1
                st.session_state.qa_messages = []
                st.session_state["_greeted_after_finalize"] = False
                st.session_state["final_spec_result_admin"] = {}
                st.success("Đã Finalize sections cho session (dùng cho Report/QA).")
                sync_sections_from_be()
                st.rerun()
            else:
                st.error(f"{r.get('code')} – {r.get('error')}")
                with st.expander("Resp /confirm_sections (Finalize)"):
                    st.json(r)

    with row_bottom[1]:
        if st.button("Admin: Confirm & Save Template", key="btn_admin_save_template_main", use_container_width=True):
            if not st.session_state.get("finalized", False):
                edited_payload = edited_zero_df.to_dict(orient="records")
                with st.spinner("Đang finalize trước khi lưu template..."):
                    r1 = api.finalize_sections(sid, edited_payload, sheet)
                with st.expander("Step 1: Finalize before Save Template"):
                    st.json(r1)

            with st.spinner("Đang lưu template..."):
                r2 = api.admin_save_template(sid, sheet)
            with st.expander("Step 2: Resp /admin/save_template"):
                st.json(r2)

            ok2 = isinstance(r2, dict) and (r2.get("ok") is True or "data" in r2 or "message" in r2)
            if ok2:
                st.success("Admin đã Confirm & lưu Rule Template.")
            else:
                st.error(f"{r2.get('code')} – {r2.get('error')}")

    # cột đệm để cân layout
    with row_bottom[2]:
        st.write("")


    # =========================
    # Final Summary + Chatbot (ON-DEMAND FINAL + SPINNER QA)
    # =========================
    st.subheader("Summary/Chatbot")

    is_finalized = bool(st.session_state.get("finalized", False))
    sid = (st.session_state.session_id or "").strip()
    sheet = (st.session_state.sheet_name or "").strip() or None

    if not sid:
        st.info("Hãy Upload file ở sidebar để có session_id trước.")
    elif not is_finalized:
        st.info("Hãy Finalize sections ở bước trên. Sau đó bạn có thể bật chatbot QA.")
    else:
        tab_report_admin, tab_qa_admin = st.tabs(["📊 Analysis Report", "💬 Chatbot QA"])

        # ---------- REPORT TAB ----------
        with tab_report_admin:
            c1, c2 = st.columns([1, 3])
            with c1:
                if st.button("Tạo báo cáo ", type="primary", key="btn_admin_run_final_spec"):
                    with st.spinner("Đang tạo Final Spec (CI)..."):
                        # dùng đúng hàm trong api.py
                        st.session_state["final_spec_result_admin"] = api.run_final_spec(sid)

            payload = st.session_state.get("final_spec_result_admin") or {}

            # show error
            if isinstance(payload, dict) and payload and not payload.get("ok", True):
                st.error(f"API lỗi ({payload.get('status_code')}): {payload.get('error')}")
                with st.expander("Resp /final_spec"):
                    st.json(payload)

            spec = _safe_get_spec(payload)
            if spec:
                render_dashboard(spec)
            else:
                st.caption("Chưa có report. Bấm **Tạo báo cáo dashboard** để sinh spec và render.")

            st.markdown('</div>', unsafe_allow_html=True)

        # ---------- QA TAB ----------
        with tab_qa_admin:
            st.markdown("### Chatbot")
            st.caption("Hỏi trên dữ liệu sau khi đã Finalize sections.")

            if "qa_messages" not in st.session_state:
                st.session_state.qa_messages = []

            if not st.session_state.get("_greeted_after_finalize", False):
                st.session_state.qa_messages.append(
                    {"role": "assistant", "content": "Chào bạn 👋 Bạn muốn hỏi gì về dữ liệu trong file này?"}
                )
                st.session_state["_greeted_after_finalize"] = True

            ctrl1, ctrl2, ctrl3 = st.columns([1, 1, 2])
            with ctrl1:
                reset_chat = st.checkbox("Reset chat", value=False, key="qa_reset_chat_admin")
            with ctrl2:
                debug = st.checkbox("Debug", value=False, key="qa_debug_admin")
            with ctrl3:
                if st.button("Xoá lịch sử chat UI", key="btn_clear_chat_ui_admin"):
                    st.session_state.qa_messages = []
                    st.session_state["_greeted_after_finalize"] = False
                    st.rerun()

            for m in st.session_state.qa_messages:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

            q = st.chat_input("Nhập câu hỏi của bạn...", key="qa_input_admin")
            if q:
                st.session_state.qa_messages.append({"role": "user", "content": q})

                try:
                    with st.spinner("Đang suy nghĩ ( CI )..."):
                        resp = api.qa(session_id=sid, question=q, reset_chat=reset_chat)

                    answer = ""
                    if isinstance(resp, dict):
                        answer = (resp.get("answer") or "").strip()
                    if not answer:
                        answer = "Không nhận được 'answer' từ /qa."

                    if debug:
                        answer += "\n\n---\nDebug response:\n" + str(resp)

                    st.session_state.qa_messages.append({"role": "assistant", "content": answer})
                    st.rerun()
                except Exception as e:
                    st.session_state.qa_messages.append({"role": "assistant", "content": f"Lỗi gọi /qa: {e}"})
                    st.rerun()

# =========================
# TAB: Quản lý user
# =========================
with tab_users:
    st.subheader("Quản lý user")

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        q = st.text_input("Search username/email", key="um_q")
    with c2:
        role = st.selectbox("Role", ["ALL", "USER", "ADMIN"], key="um_role")
    with c3:
        active = st.selectbox("Active", ["ALL", "ACTIVE", "INACTIVE"], key="um_active")
    with c4:
        if st.button("Reload", key="um_reload"):
            st.session_state.pop("um_cache", None)

    if "um_cache" not in st.session_state:
        st.session_state.um_cache = api.admin_list_users(q=q, role=role, active=active)

    resp = st.session_state.um_cache
    users = ((resp.get("data") or {}).get("users")) if isinstance(resp, dict) else []
    users = users or []

    if users:
        df = pd.DataFrame(users)
        st.dataframe(
            df[["id", "username", "role", "is_active", "created_at", "last_login_at"]],
            use_container_width=True,
            hide_index=True
        )

        uid = st.selectbox(
            "Chọn user để sửa",
            options=[u["id"] for u in users],
            format_func=lambda x: next((f'{u["username"]} ({u["role"]})' for u in users if u["id"] == x), x),
            key="um_pick"
        )
        u = next((x for x in users if x["id"] == uid), None)
        if u:
            e1, e2, e3 = st.columns([1, 1, 2])
            with e1:
                new_role = st.selectbox("Role", ["USER", "ADMIN"], index=(0 if u["role"] == "USER" else 1), key="um_edit_role")
            with e2:
                new_active = st.toggle("Active", value=bool(u["is_active"]), key="um_edit_active")
            with e3:
                if st.button("Lưu", type="primary", key="um_save"):
                    r = api.admin_update_user(uid, role=new_role, is_active=new_active)
                    st.json(r)
                    st.session_state.pop("um_cache", None)
                    st.rerun()
    else:
        st.info("Chưa có user.")

    st.markdown("---")
    st.markdown("## Tạo user mới")

    nu1, nu2, nu3 = st.columns([2, 1, 1])
    with nu1:
        new_username = st.text_input("Username (USER quick)", key="um_new_username")
    with nu2:
        new_role = st.selectbox("Role", ["USER", "ADMIN"], key="um_new_role")
    with nu3:
        new_active = st.toggle("Active", value=True, key="um_new_active")

    admin_email = ""
    admin_password = ""

    if new_role == "ADMIN":
        st.info("ADMIN bắt buộc có Email + Password (không dùng quick username-only).")
        a1, a2 = st.columns([2, 2])
        with a1:
            admin_email = st.text_input("Admin Email", key="um_new_email")
        with a2:
            admin_password = st.text_input("Admin Password", type="password", key="um_new_password")
    else:
        st.caption("USER quick: đăng nhập bằng username, không cần mật khẩu.")

    if st.button("Create user", type="primary", key="um_create"):
        if new_role == "ADMIN":
            if not admin_email.strip() or not admin_password.strip():
                st.error("ADMIN bắt buộc có Email và Password.")
            else:
                payload_username = new_username.strip() if new_username.strip() else None
                r = api.admin_create_user(
                    username=payload_username,
                    role="ADMIN",
                    is_active=new_active,
                    email=admin_email.strip(),
                    password=admin_password,
                )
                st.json(r)
                st.session_state.pop("um_cache", None)
                st.rerun()
        else:
            if not new_username.strip():
                st.error("Username không được rỗng.")
            else:
                r = api.admin_create_user(
                    username=new_username.strip(),
                    role="USER",
                    is_active=new_active,
                )
                st.json(r)
                st.session_state.pop("um_cache", None)
                st.rerun()
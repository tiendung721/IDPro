import streamlit as st
import pandas as pd

from src.state import init_state
from src import api

from src.ui import sections_to_df_1based, sections_editor_with_add_delete

st.set_page_config(page_title="Admin – AI Agent", layout="wide")
init_state()

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

st.title("AI Agent – Excel analysis with LLM ")
st.caption(
    f"ADMIN: **{st.session_state.get('admin_email') or '∅'}** | "
    f"Role: **{(st.session_state.get('admin_role') or '∅').upper()}**"
)

# =========================
# Helpers: preview sections parsing (y như app.py cũ)
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


def _extract_report_text(final_payload: dict) -> str:
    if not isinstance(final_payload, dict):
        return ""
    data = final_payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("report"), str):
        return data["report"]
    if isinstance(final_payload.get("report"), str):
        return final_payload["report"]
    return ""


# =========================
# Sidebar: Upload + Session controls + Logout
# =========================
with st.sidebar:
    st.success("ADMIN đã đăng nhập")

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
                    st.session_state.final_result = {}
                    st.session_state["_greeted_after_final"] = False
                    st.session_state.qa_messages = []
                    st.session_state.finalize_rev = 0

                    st.success(f"Upload OK. session_id = {sid}")
                else:
                    st.error("Upload OK nhưng không nhận được session_id.")
            else:
                st.error(f"{res.get('code')} – {res.get('error')}")

    st.divider()
    if st.button("Test /health", key="btn_health_sidebar"):
        st.json(api.health())

    st.divider()
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


# =========================
# Tabs
# =========================
tab_ops, tab_users = st.tabs(["Vận hành", "Quản lý user"])


# =========================
# TAB: Vận hành
# =========================
with tab_ops:
    # --- Preview ---
    st.subheader("Preview")

    sid = (st.session_state.session_id or "").strip()
    sheet = (st.session_state.sheet_name or "").strip() or None
    st.caption(f"Session: **{sid or '∅'}** | Sheet: **{sheet or 'None'}** | Role: **ADMIN**")

    if st.button("Tải lại Preview", key="btn_preview_reload"):
        fetch_preview()

    if not st.session_state.get("_preview_fetched", False) and sid:
        st.session_state._preview_fetched = True
        fetch_preview()

    st.markdown("**Preview sections (1-based)**")
    if st.session_state.get("sections"):
        st.dataframe(
            sections_to_df_1based(st.session_state.sections),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Chưa có sections. Upload file ở sidebar rồi bấm 'Tải lại Preview'.")

    st.markdown("---")

    # --- Sections Editor + Finalize ---
    st.subheader("Chỉnh sửa sections (áp dụng cho session)")
    sid = (st.session_state.get("session_id") or "").strip()

    if sid and not st.session_state.get("_sections_loaded_from_be", False):
        try:
            resp = api.sections_get(sid)
            if isinstance(resp, dict) and resp.get("ok"):
                st.session_state["sections"] = resp["data"]["sections"]
                st.session_state["_sections_loaded_from_be"] = True
        except Exception as e:
            st.warning(f"Không tải được sections: {e}")

    df1 = sections_to_df_1based(st.session_state.get("sections", []))
    edited_zero_df, del_rows, create_payload = sections_editor_with_add_delete(df1, key_prefix="secx_admin")

    colA, colB, colC, colD, colE = st.columns([1, 1, 2, 2, 2])

    with colA:
        if st.button("Áp dụng thay đổi", key="btn_apply_be_crud"):
            payload = edited_zero_df.to_dict(orient="records")
            res = api.sections_replace(sid, payload)
            if isinstance(res, dict) and res.get("ok"):
                st.success("Đã cập nhật sections lên BE.")
                st.session_state["sections"] = res["data"]["sections"]

                # invalidate report + chat
                st.session_state.finalized = False
                st.session_state.final_result = {}
                st.session_state.qa_messages = []
                st.session_state["_greeted_after_final"] = False
            else:
                st.error(res)

    with colB:
        if st.button("Xoá các section đã chọn", key="btn_delete_sections"):
            cur = edited_zero_df.to_dict(orient="records")
            keep = [v for i, v in enumerate(cur) if i not in del_rows]
            res = api.sections_replace(sid, keep)
            if isinstance(res, dict) and res.get("ok"):
                st.success("Đã xoá.")
                st.session_state["sections"] = res["data"]["sections"]

                # invalidate report + chat
                st.session_state.finalized = False
                st.session_state.final_result = {}
                st.session_state.qa_messages = []
                st.session_state["_greeted_after_final"] = False

    with colC:
        if st.button("Thêm section mới", key="btn_add_section"):
            res = api.sections_add(sid, create_payload)
            if isinstance(res, dict) and res.get("ok"):
                st.success("Đã thêm.")
                st.session_state["sections"] = res["data"]["sections"]

                # invalidate report + chat
                st.session_state.finalized = False
                st.session_state.final_result = {}
                st.session_state.qa_messages = []
                st.session_state["_greeted_after_final"] = False

    with colD:
        if st.button("Finalize sections (Report/QA)", type="primary", key="btn_finalize_sections"):
            edited_payload = edited_zero_df.to_dict(orient="records")
            with st.spinner("Đang finalize sections..."):
                r = api.finalize_sections(sid, edited_payload, sheet)

            with st.expander("Resp /confirm_sections (Finalize)"):
                st.json(r)

            ok = isinstance(r, dict) and (r.get("ok") is True or "data" in r or "message" in r)
            if ok:
                st.session_state.finalized = True
                st.session_state.finalize_rev = int(st.session_state.get("finalize_rev", 0)) + 1

                # IMPORTANT: report is on-demand now => clear old report until button pressed
                st.session_state.final_result = {}

                # reset chat ui
                st.session_state.qa_messages = []
                st.session_state["_greeted_after_final"] = False

                st.success("Đã Finalize sections cho session (dùng cho Report/QA).")
                sync_sections_from_be()
                st.rerun()
            else:
                st.error(f"{r.get('code')} – {r.get('error')}")

    with colE:
        if st.button("Admin: Confirm & Save Template", key="btn_admin_save_template"):
            if not st.session_state.finalized:
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

    st.markdown("---")

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
        st.info("Hãy Finalize sections ở bước trên. Sau đó bạn có thể bấm nút để tạo báo cáo tổng hợp và bật chatbot.")
    else:
        # ===== ON-DEMAND FINAL: only run when button pressed =====
        if st.button("Tạo báo cáo tổng hợp", type="primary", key="btn_admin_run_final"):
            with st.spinner("Đang tạo báo cáo tổng hợp (Code Interpreter) ..."):
                try:
                    st.session_state.final_result = api.run_final(sid)
                except Exception as e:
                    st.error(f"Lỗi gọi /final: {e}")
                    st.session_state.final_result = {}

        res = st.session_state.get("final_result") or {}
        report_text = _extract_report_text(res)

        # optional debug
        with st.expander("Payload /final (debug)"):
            st.json(res)

        st.markdown("### Narrative (Báo cáo tổng hợp)")
        if report_text:
            st.markdown(report_text)
        else:
            st.caption("Chưa có báo cáo. Bấm **Tạo báo cáo tổng hợp** để sinh báo cáo (on-demand).")

        st.markdown("---")

        # ===== Chatbot =====
        st.markdown("### Chatbot")
        st.caption("Hỏi trên dữ liệu sau khi đã Finalize sections.")

        if "qa_messages" not in st.session_state:
            st.session_state.qa_messages = []

        # greeting once (không bắt buộc phải có report)
        if not st.session_state.get("_greeted_after_final", False):
            st.session_state.qa_messages.append(
                {"role": "assistant", "content": "Chào bạn 👋 Bạn muốn hỏi gì về dữ liệu trong file này?"}
            )
            st.session_state["_greeted_after_final"] = True


        ctrl1, ctrl2, ctrl3 = st.columns([1, 1, 2])
        with ctrl1:
            reset_chat = st.checkbox("Reset chat", value=False, key="qa_reset_chat_admin")
        with ctrl2:
            debug = st.checkbox("Debug", value=False, key="qa_debug_admin")
        with ctrl3:
            if st.button("Xoá lịch sử chat UI", key="btn_clear_chat_ui_admin"):
                st.session_state.qa_messages = []
                st.session_state["_greeted_after_final"] = False
                st.rerun()

        for m in st.session_state.qa_messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        q = st.chat_input("Nhập câu hỏi của bạn...", key="qa_input_admin")
        if q:
            st.session_state.qa_messages.append({"role": "user", "content": q})

            try:
                # ✅ SPINNER ONLY (no "Đang suy nghĩ..." bubble)
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

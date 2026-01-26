import streamlit as st

from src.state import init_state
from src import api

st.set_page_config(page_title="AI Agent UI", layout="wide")
init_state()
st.title("AI Agent – Excel analysis with LLM")
st.caption("Chọn đăng nhập User hoặc Admin ở sidebar.")

# =========================
# Helpers
# =========================
def _switch_page(path: str):
    """
    Streamlit multipage router.
    Compatible với st.switch_page mới; nếu môi trường cũ sẽ báo hướng dẫn.
    """
    try:
        st.switch_page(path)
    except Exception:
        st.error(
            "Không chuyển trang được (thiếu multipage hoặc Streamlit quá cũ). "
            "Hãy đảm bảo có thư mục streamlit_app/pages/ và nâng Streamlit >= 1.22."
        )
        st.stop()


def goto_admin():
    st.session_state.user_mode = "ADMIN"
    # admin: dùng admin_token
    api.set_token(st.session_state.get("admin_token") or "")
    _switch_page("pages/1_Admin_UI.py")


def goto_user():
    st.session_state.user_mode = "USER"

    username = (st.session_state.get("user_name") or "").strip()
    if not username:
        st.error("Thiếu username.")
        st.stop()

    resp = api.user_login(username)
    if not isinstance(resp, dict) or not resp.get("ok"):
        st.error(resp.get("error") or resp.get("detail") or "user_login failed")
        st.stop()

    token = (resp.get("data") or {}).get("access_token")
    if not token:
        st.error("user_login OK nhưng không có access_token.")
        st.stop()

    st.session_state["user_token"] = token
    api.set_token(token)

    _switch_page("pages/2_User_UI.py")



# =========================
# Sidebar: User + Admin
# =========================
with st.sidebar:
    st.header("User")
    username = st.text_input("Username", key="user_username", placeholder="VD: dung, user01...")

    if st.button("Login", key="btn_enter_user"):
        if not username.strip():
            st.warning("Vui lòng nhập username.")
        else:
            st.session_state.user_name = username.strip()
            st.session_state.session_id = ""
            st.session_state.sections = []
            st.session_state.finalized = False
            st.session_state.final_result = {}
            st.session_state._preview_fetched = False
            st.session_state._sections_loaded_from_be = False
            # các key UI khác có thể tồn tại từ lần trước
            for k in ["qa_messages", "finalize_rev", "_last_final_rev", "_last_final_sid", "_last_final_sheet", "_greeted_after_final"]:
                st.session_state.pop(k, None)

            goto_user()

    st.divider()
    st.header("Admin Login")

    email = st.text_input("Email", key="admin_email_input")
    password = st.text_input("Mật khẩu", type="password", key="admin_password_input")

    if st.button("Login", key="btn_admin_login"):
        resp = api.login(email, password)
        if isinstance(resp, dict) and resp.get("ok") is False:
            st.error(f"{resp.get('code','LOGIN_FAILED')} – {resp.get('error','')}")
        else:
            token = None
            if isinstance(resp, dict):
                token = resp.get("access_token") or resp.get("token")
                data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
                token = token or data.get("access_token") or data.get("token")

            if not token:
                st.error("Login không trả về token (access_token).")
            else:
                role = ""
                if isinstance(resp, dict):
                    role = (resp.get("role") or (resp.get("data") or {}).get("role") or "").upper()

                st.session_state.admin_token = token
                st.session_state.admin_email = email
                st.session_state.admin_role = role or "ADMIN"
                st.session_state.admin_logged_in = True

                goto_admin()

# =========================
# Landing content
# =========================
st.info("Hãy đăng nhập ở sidebar để bắt đầu.")

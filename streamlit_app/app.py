import streamlit as st

from src.state import init_state
from src import api

st.set_page_config(page_title="AI Agent UI", layout="wide")
init_state()

st.title("IDPro – Excel Agent")
st.caption("Chọn đăng nhập User hoặc Admin ở sidebar.")

st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none !important; }
</style>
""", unsafe_allow_html=True)


# =========================
# Helpers
# =========================
def logout_user():
    st.session_state.pop("user_token", None)
    st.session_state.pop("user_name", None)
    # nếu bạn có các state khác liên quan user thì reset thêm ở đây
    st.rerun()

def logout_admin():
    st.session_state.pop("admin_token", None)
    st.session_state.pop("admin_logged_in", None)
    st.session_state.pop("admin_email", None)
    st.session_state.pop("admin_role", None)
    st.rerun()

def is_user_logged_in():
    return bool(st.session_state.get("user_token"))

def is_admin_logged_in():
    return bool(st.session_state.get("admin_token")) and bool(st.session_state.get("admin_logged_in"))


def _switch_page(path: str):
    """
    Streamlit multipage router.
    Compatible với st.switch_page mới; nếu môi trường cũ sẽ báo hướng dẫn.
    """
    try:
        st.switch_page(path)
    except Exception:
        st.error(
            "old Streamlit version không hỗ trợ chuyển trang tự động. "
            "lost file "
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

    _switch_page("pages/1_AI_Agent.py")



# =========================
# Sidebar: User + Admin
# =========================
with st.sidebar:
    st.markdown("### 🔐 Đăng nhập")

    tab_user, tab_admin = st.tabs(["User", "Admin"])

    with tab_user:
        with st.form("login_user", clear_on_submit=False):
            username = st.text_input("Username", placeholder="user01")
            ok = st.form_submit_button("Đăng nhập", use_container_width=True)

        if ok:
            username = (username or "").strip()
            if not username:
                st.error("Nhập username.")
            else:
                resp = api.user_login(username)
                if not isinstance(resp, dict) or not resp.get("ok"):
                    st.error(resp.get("error") or resp.get("detail") or "User login failed.")
                else:
                    token = (resp.get("data") or {}).get("access_token")
                    if not token:
                        st.error("Thiếu access_token.")
                    else:
                        st.session_state["user_token"] = token
                        st.session_state["user_name"] = username
                        st.session_state["user_role"] = "USER"
                        api.set_token(token)
                        st.switch_page("pages/1_AI_Agent.py")

    with tab_admin:
        with st.form("login_admin", clear_on_submit=False):
            email = st.text_input("Email", placeholder="admin@company.com")
            password = st.text_input("Mật khẩu", type="password")
            ok = st.form_submit_button("Đăng nhập", use_container_width=True)

        if ok:
            email = (email or "").strip()
            if not email or not password:
                st.error("Nhập email và mật khẩu.")
            else:
                resp = api.login(email, password)

                # parse token linh hoạt
                if isinstance(resp, dict) and resp.get("ok") is False:
                    st.error(resp.get("error") or "Admin login failed.")
                else:
                    token = None
                    role = "ADMIN"
                    if isinstance(resp, dict):
                        token = resp.get("access_token") or resp.get("token")
                        data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
                        token = token or data.get("access_token") or data.get("token")
                        role = (resp.get("role") or data.get("role") or "ADMIN")

                    if not token:
                        st.error("Login không trả về token.")
                    else:
                        st.session_state["admin_token"] = token
                        st.session_state["admin_logged_in"] = True
                        st.session_state["admin_role"] = role
                        st.session_state["admin_email"] = email
                        api.set_token(token)
                        st.switch_page("pages/1_Admin_UI.py")

# =========================
# Landing content
# =========================
st.info("Hãy đăng nhập ở sidebar để bắt đầu.")

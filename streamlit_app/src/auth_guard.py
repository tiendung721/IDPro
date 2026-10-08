import streamlit as st
import streamlit.components.v1 as components

from src import api


def clear_user_auth() -> None:
    for key in ("user_token", "user_name", "user_role"):
        st.session_state.pop(key, None)


def clear_admin_auth() -> None:
    for key in ("admin_token", "admin_logged_in", "admin_email", "admin_role"):
        st.session_state.pop(key, None)


def _redirect_to_landing(message: str) -> None:
    api.set_token("")
    st.warning(message)
    st.caption("Đang chuyển về màn hình đăng nhập...")

    try:
        st.switch_page("app.py")
    except Exception:
        pass

    components.html(
        """
        <script>
        const rootUrl = window.location.origin + "/";
        window.top.location.replace(rootUrl);
        </script>
        """,
        height=0,
    )
    st.page_link("app.py", label="Về màn hình đăng nhập", icon="↩")
    st.stop()


def require_user_login() -> None:
    user_name = (st.session_state.get("user_name") or "").strip()
    user_token = (st.session_state.get("user_token") or "").strip()

    if not user_name or not user_token:
        clear_user_auth()
        _redirect_to_landing("Bạn cần đăng nhập User trước.")

    api.set_token(user_token)


def require_admin_login() -> None:
    admin_logged_in = bool(st.session_state.get("admin_logged_in"))
    admin_role = (st.session_state.get("admin_role") or "").strip().upper()
    admin_token = (st.session_state.get("admin_token") or "").strip()

    if not admin_logged_in or admin_role != "ADMIN" or not admin_token:
        clear_admin_auth()
        _redirect_to_landing("Bạn cần đăng nhập Admin để vào trang này.")

    api.set_token(admin_token)

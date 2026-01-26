import streamlit as st


def init_state():
    defaults = {
        # ===== USER (no-login) =====
        "user_name": "",         
        "user_mode": "USER",      # "USER" | "ADMIN" (chỉ để hiển thị/logic UI)

        # ===== ADMIN (login) =====
        "admin_logged_in": False,
        "admin_token": "",
        "admin_email": "",
        "admin_role": "",         

        # ===== Backward-compat =====
        "token": "",
        "email": "",
        "role": "",
        "logged_in": False,

        # ===== Working session =====
        "session_id": "",
        "sheet_name": "",
        "sections": [],

        # ===== Preview metadata =====
        "used_rule": False,
        "matched_fingerprint": None,

        # ===== Gate for Report/QA =====
        "finalized": False,
        "final_result": {},
        "_preview_fetched": False,
        "_sections_loaded_from_be": False,
    }

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

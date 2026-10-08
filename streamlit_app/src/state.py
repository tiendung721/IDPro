import streamlit as st


def init_state():
    defaults = {
        # ===== USER (no-login) =====
        "user_name": "",
        "user_token": "",
        "user_role": "",
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

        # ===== Dynamic post-finalize routing =====
        "document_flow": None,          # "ba" | "analytics"
        "document_type": None,          # "ba_excel" | "non_ba" | "unknown"
        "routing_result": {},
        "ba_detect_result": {},
        "ba_analysis_result": {},
        "quotation_preview_result": {},
    }

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

import streamlit as st

from src.state import init_state
from src import api
from src.ui import sections_to_df_1based, sections_editor_with_add_delete

st.set_page_config(page_title="User – AI Agent", layout="wide")
init_state()

# ===== Guard =====
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

st.title("AI Agent – Excel analysis with LLM ")

user_name = st.session_state.get("user_name", "∅")
user_role = st.session_state.get("user_role", "USER")

st.caption(f"Xin chào **{user_name}** | Role: **{user_role}**")

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

def _extract_report_text(final_payload: dict) -> str:
    if not isinstance(final_payload, dict):
        return ""
    data = final_payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("report"), str):
        return data["report"]
    if isinstance(final_payload.get("report"), str):
        return final_payload["report"]
    return ""

def _reset_for_new_upload(keep_login: bool = True):
    # giữ login
    user_name = st.session_state.get("user_name") if keep_login else ""
    user_token = st.session_state.get("user_token") if keep_login else None
    user_mode = st.session_state.get("user_mode") if keep_login else "USER"

    # clear session-related states
    for k in [
        "session_id", "sections", "finalized", "final_result",
        "_preview_fetched", "_sections_loaded_from_be",
        "qa_messages", "_greeted_after_final",
        "finalize_rev", "_last_final_rev", "_last_final_sid", "_last_final_sheet",
    ]:
        st.session_state.pop(k, None)

    st.session_state["session_id"] = ""
    st.session_state["sections"] = []
    st.session_state["finalized"] = False
    st.session_state["final_result"] = {}
    st.session_state["_preview_fetched"] = False
    st.session_state["_sections_loaded_from_be"] = False
    st.session_state["qa_messages"] = []
    st.session_state["_greeted_after_final"] = False

    if keep_login:
        st.session_state["user_name"] = user_name
        if user_token:
            st.session_state["user_token"] = user_token
        st.session_state["user_mode"] = user_mode

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
        st.session_state.final_result = {}
        st.session_state.qa_messages = []
        st.session_state["_greeted_after_final"] = False
        return True

    st.error(f"{r.get('code')} – {r.get('error')}")
    with st.expander("Resp /confirm_sections"):
        st.json(r)
    return False

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
        st.session_state.final_result = {}
        st.session_state._preview_fetched = False
        st.session_state._sections_loaded_from_be = False
        for k in ["qa_messages", "finalize_rev", "_last_final_rev", "_last_final_sid", "_last_final_sheet", "_greeted_after_final"]:
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
                    st.success(f"Upload OK.")
                    # auto preview để tiết kiệm thao tác
                    with st.spinner("Đang phân tích cấu trúc bảng..."):
                        fetch_preview()
            else:
                st.error(f"{res.get('code')} – {res.get('error')}")
                with st.expander("Resp /upload"):
                    st.json(res)

    sid = (st.session_state.session_id or "").strip()
    st.caption(f"Session: **{sid or '∅'}**")

# =========================
# MAIN WINDOW: Preview -> Confirm -> Final -> Chat (NO TABS)
# =========================
st.subheader("1) Preview cấu trúc")
sid = (st.session_state.session_id or "").strip()
sheet = (st.session_state.sheet_name or "").strip() or None

row1 = st.columns([1, 3, 2])
with row1[0]:
    st.button("Tải lại preview", on_click=fetch_preview, disabled=not bool(sid), key="btn_user_preview_reload_main")
with row1[1]:
    st.write("Hệ thống tự detect các vùng bảng. Kiểm tra lại trước khi Confirm.")
with row1[2]:
    st.write(f"Confirmed: {'✅' if st.session_state.get('finalized') else '—'}")

if not sid:
    st.info("Bạn hãy Upload file ở sidebar trước.")
    st.stop()

if st.session_state.get("sections"):
    df_prev = sections_to_df_1based(st.session_state.sections).rename(columns={
    "Section": "STT Bảng",
    "header_row": "Dòng tiêu đề",
    "start_row": "Dòng bắt đầu",
    "end_row": "Dòng kết thúc",
    "label": "Tên bảng / ghi chú",
    })
    st.dataframe(df_prev, use_container_width=True, hide_index=True)
else:
    st.warning("Chưa có bảng. Bấm 'Tải lại preview' hoặc Upload lại.")
    st.stop()

st.markdown("---")

st.subheader("2) Chỉnh sửa bảng (tuỳ chọn) & Xác nhận cấu trúc")
with st.expander("Tuỳ chọn nâng cao: chỉnh sửa bảng, thêm/xoá bảng"):
    df1 = sections_to_df_1based(st.session_state.get("sections", []))
    edited_zero_df, del_rows, create_payload = sections_editor_with_add_delete(
    df1, key_prefix="secx_user_main", lang="vi"
    )
    st.caption("Nếu không cần chỉnh, bạn bỏ qua và bấm Xác nhận ngay phía dưới.")

    adv1, adv2, adv3 = st.columns([1, 1, 2])
    with adv1:
        if st.button("Áp dụng thay đổi", key="btn_user_apply_sections_main"):
            payload = edited_zero_df.to_dict(orient="records")
            res = api.sections_replace(sid, payload)
            if isinstance(res, dict) and res.get("ok"):
                st.success("Đã cập nhật bảng.")
                st.session_state["sections"] = res["data"]["sections"]
            else:
                st.error(res)   

    with adv2:
        if st.button("Xoá bảng đã chọn", key="btn_user_delete_sections_main"):
            cur = edited_zero_df.to_dict(orient="records")
            keep = [v for i, v in enumerate(cur) if i not in del_rows]
            res = api.sections_replace(sid, keep)
            if isinstance(res, dict) and res.get("ok"):
                st.success("Đã xoá.")
                st.session_state["sections"] = res["data"]["sections"]

    with adv3:
        if st.button("Thêm bảng mới", key="btn_user_add_section_main"):
            res = api.sections_add(sid, create_payload)
            if isinstance(res, dict) and res.get("ok"):
                st.success("Đã thêm.")
                st.session_state["sections"] = res["data"]["sections"]

confirm_col1, confirm_col2 = st.columns([1, 3])
with confirm_col1:
    if st.button("Xác nhận cấu trúc (Finalize)", type="primary", key="btn_user_finalize_main"):
        with st.spinner("Đang finalize sections..."):
            finalize_sections()
with confirm_col2:
    st.caption("Sau khi Xác nhận cấu trúc, bạn có thể tạo báo cáo và bắt đầu chat QA.")

st.markdown("---")

st.subheader("3) Báo cáo & Hỏi đáp")

if not st.session_state.get("finalized", False):
    st.info("Bạn cần Xác nhận cấu trúc ở bước 2 trước khi tạo báo cáo và chat.")
    st.stop()

# Run final (on-demand)
if st.button("Tạo báo cáo tổng hợp", type="primary", key="btn_user_run_final_main"):
    with st.spinner("Đang suy nghĩ ( CI )..."):
        st.session_state.final_result = api.run_final(sid)

res = st.session_state.get("final_result") or {}
report_text = _extract_report_text(res)

if report_text:
    with st.expander("📄 Báo cáo tổng hợp (mở/đóng)", expanded=False):
        st.markdown(report_text)
else:
    st.caption("Chưa có báo cáo. Bạn có thể bấm **Tạo báo cáo tổng hợp** (không bắt buộc trước khi chat nếu /qa đã đủ context).")

st.markdown("### Chat")

if "qa_messages" not in st.session_state:
    st.session_state.qa_messages = []

# greeting once
if not st.session_state.get("_greeted_after_final", False):
    st.session_state.qa_messages.append(
        {"role": "assistant", "content": "Chào bạn 👋 Bạn muốn hỏi gì về dữ liệu trong file này?"}
    )
    st.session_state["_greeted_after_final"] = True

# render chat
for m in st.session_state.qa_messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# chat input (ChatGPT-like) + thinking message
q = st.chat_input("Nhập câu hỏi của bạn...", key="qa_input_user_main_no_tabs")

if q:
    st.session_state.qa_messages.append({"role": "user", "content": q})
    st.session_state.pending_qa = True
    st.session_state.pending_q = q
    st.rerun()

# If pending => call QA and append assistant answer (no "thinking" bubble)
if st.session_state.get("pending_qa"):
    last_user_q = st.session_state.get("pending_q", "")

    with st.spinner("Đang suy nghĩ ( CI )..."):
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

import io
import time
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src import api
from src.auth_guard import require_user_login
from src.dashboard_renderer import render_dashboard, inject_dashboard_css
from src.state import init_state
from src.ui import render_ba_analysis_workspace

# =========================================================
# Page Setup
# =========================================================
st.set_page_config(page_title="AI Agent - Automated Flow", layout="wide")
init_state()
require_user_login()
inject_dashboard_css()

# =========================================================
# Custom Premium Styling (Glassmorphism & Animations)
# =========================================================
def inject_agent_styles():
    st.markdown("""
    <style>
    [data-testid="stSidebarNav"] {
        display: none !important;
    }
    [data-testid="stSidebarNavSeparator"] {
        display: none !important;
    }
    [data-testid="stHeader"] {
        background: rgba(255, 255, 255, 0) !important;
    }
    section[data-testid="stSidebar"] > div {
        padding-top: 0.75rem;
    }

    /* Premium Orb Background */
    .agent-bg {
        position: fixed;
        inset: 0;
        z-index: -1;
        background: #ffffff;
        overflow: hidden;
    }
    .agent-bg::before {
        content: "";
        position: absolute;
        width: 60vw;
        height: 60vw;
        top: -20vw;
        left: -10vw;
        background: radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, transparent 70%);
        filter: blur(80px);
        animation: rotateBg 20s linear infinite;
    }
    .agent-bg::after {
        content: "";
        position: absolute;
        width: 50vw;
        height: 50vw;
        bottom: -10vw;
        right: -10vw;
        background: radial-gradient(circle, rgba(6, 182, 212, 0.12) 0%, transparent 70%);
        filter: blur(80px);
        animation: rotateBg 25s linear reverse infinite;
    }

    @keyframes rotateBg {
        from { transform: rotate(0deg) scale(1); }
        to { transform: rotate(360deg) scale(1.1); }
    }

    /* Glassmorphism Cards */
    .glass-card {
        background: rgba(255, 255, 255, 0.65);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.35);
        border-radius: 24px;
        padding: 24px;
        box-shadow: 0 10px 32px rgba(0, 0, 0, 0.04);
        margin-bottom: 24px;
        transition: all 0.3s ease;
    }
    .glass-card:hover {
        background: rgba(255, 255, 255, 0.75);
        transform: translateY(-2px);
        box-shadow: 0 15px 45px rgba(0, 0, 0, 0.06);
    }

    /* Agent Identity Hero */
    .agent-hero {
        text-align: center;
        padding: 40px 20px;
        margin-bottom: 20px;
    }
    .agent-title {
        font-size: 3rem;
        font-weight: 800;
        background: linear-gradient(135deg, #4f46e5, #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.04em;
    }
    .agent-subtitle {
        color: #64748b;
        font-size: 1.1rem;
        margin-top: 10px;
    }

    /* Activity Log styling effect */
    .activity-log {
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        background: #0f172a;
        color: #94a3b8;
        padding: 16px;
        border-radius: 14px;
        font-size: 0.85rem;
        line-height: 1.6;
        border: 1px solid rgba(255,255,255,0.1);
        max-height: 200px;
        overflow-y: auto;
    }
    .activity-line {
        border-left: 2px solid #4f46e5;
        padding-left: 10px;
        margin-bottom: 4px;
    }
    .activity-line.done { border-left-color: #10b981; color: #e2e8f0; }
    
    /* Discovery Section */
    .discovery-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.5rem;
        font-weight: 700;
        color: #1e293b;
        margin-top: 40px;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .discovery-title::after {
        content: "";
        flex: 1;
        height: 1px;
        background: linear-gradient(90deg, #e2e8f0, transparent);
    }

    /* Button Styling */
    div.stButton > button {
        border-radius: 12px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }

    .agent-wait-note {
        margin-top: 14px;
        padding: 14px 18px;
        border-radius: 16px;
        border: 1px solid rgba(79, 70, 229, 0.18);
        background: linear-gradient(135deg, rgba(255, 244, 229, 0.96), rgba(239, 246, 255, 0.96));
        box-shadow: 0 10px 30px rgba(79, 70, 229, 0.08);
        color: #334155;
        animation: notePulse 2.6s ease-in-out infinite;
    }
    .agent-wait-note strong {
        display: inline-block;
        margin-bottom: 4px;
        color: #b45309;
        font-size: 0.98rem;
    }
    .agent-wait-note span {
        color: #475569;
        font-size: 0.95rem;
        line-height: 1.55;
    }
    @keyframes notePulse {
        0%, 100% { transform: translateY(0); box-shadow: 0 10px 30px rgba(79, 70, 229, 0.08); }
        50% { transform: translateY(-1px); box-shadow: 0 14px 34px rgba(79, 70, 229, 0.12); }
    }

    .agent-qa-card {
        margin-bottom: 14px;
        padding: 20px 22px;
    }
    .agent-qa-card h4 {
        margin: 0 0 8px 0;
        font-size: 1.15rem;
        color: #0f172a;
    }
    .agent-qa-card p {
        margin: 0;
        color: #64748b;
        line-height: 1.6;
    }
    .agent-qa-hint {
        color: #64748b;
        font-size: 0.9rem;
        margin: 6px 0 14px 0;
    }
    
    </style>
    <div class="agent-bg"></div>
    """, unsafe_allow_html=True)

inject_agent_styles()

# =========================================================
# Core Logic: Automated Flow
# =========================
def reset_agent_flow():
    keys_to_reset = [
        "session_id", "sections", "finalized", "routing_result",
        "document_flow", "document_type", "report_plan_result",
        "generated_spec_result", "selected_report_ids", "ba_analysis_result",
        "agent_qa_messages", "agent_pending_qa", "agent_pending_q",
        "agent_qa_reset_next", "agent_qa_session_id"
    ]
    for k in keys_to_reset:
        st.session_state.pop(k, None)
    st.session_state["flow_completed"] = False

def _ensure_agent_qa_state(session_id):
    if st.session_state.get("agent_qa_session_id") == session_id:
        return

    st.session_state["agent_qa_session_id"] = session_id
    st.session_state["agent_qa_messages"] = []
    st.session_state["agent_pending_qa"] = False
    st.session_state["agent_pending_q"] = ""
    st.session_state["agent_qa_reset_next"] = True

def _queue_agent_qa(question):
    question = (question or "").strip()
    if not question:
        return

    messages = st.session_state.setdefault("agent_qa_messages", [])
    messages.append({"role": "user", "content": question})
    st.session_state["agent_pending_qa"] = True
    st.session_state["agent_pending_q"] = question

def render_agent_qa(session_id, route):
    _ensure_agent_qa_state(session_id)

    messages = st.session_state.setdefault("agent_qa_messages", [])
    is_ba_flow = route == "ba"

    if not messages:
        greeting = (
            "Chào bạn. Tôi có thể tóm tắt phạm vi, mức ưu tiên, rủi ro và các yếu tố ảnh hưởng báo giá từ file này."
            if is_ba_flow
            else "Chào bạn. Tôi có thể giải thích dashboard, tóm tắt dataset và trả lời nhanh các câu hỏi về file này."
        )
        messages.append({"role": "assistant", "content": greeting})

    qa_description = (
        "Hỏi về phạm vi nghiệp vụ, hạng mục ưu tiên, rủi ro hoặc các yếu tố có thể ảnh hưởng đến báo giá."
        if is_ba_flow
        else "Hỏi về dashboard vừa tạo, xu hướng dữ liệu, điểm bất thường hoặc những chỉ số cần chú ý."
    )
    qa_suggestions = (
        [
            "Tóm tắt phạm vi nghiệp vụ",
            "Hạng mục ưu tiên cao là gì?",
            "Yếu tố nào ảnh hưởng báo giá nhiều nhất?",
            "Rủi ro nào cần cảnh báo sớm?",
        ]
        if is_ba_flow
        else [
            "Tóm tắt dataset này",
            "Biểu đồ nào đáng chú ý nhất?",
            "Top 5 nhóm chính là gì?",
            "Cột nào thiếu dữ liệu nhiều nhất?",
        ]
    )

    st.markdown('<div class="discovery-title">💬 Hỏi đáp nhanh với agent</div>', unsafe_allow_html=True)

    info_col, action_col = st.columns([4, 1])
    with info_col:
        st.markdown(
            f"""
            <div class="glass-card agent-qa-card">
                <h4>Chat QA trực tiếp trên file đã xử lý</h4>
                <p>{qa_description}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with action_col:
        st.caption("Manifest đã finalize nên agent có thể trả lời bám theo file.")
        if st.button("🧹 Xóa chat", key="agent_qa_clear", use_container_width=True):
            st.session_state["agent_qa_messages"] = []
            st.session_state["agent_pending_qa"] = False
            st.session_state["agent_pending_q"] = ""
            st.session_state["agent_qa_reset_next"] = True
            st.rerun()

    st.markdown(
        '<div class="agent-qa-hint">Gợi ý nhanh: bấm một câu hỏi mẫu hoặc nhập câu hỏi của bạn ở ô chat bên dưới.</div>',
        unsafe_allow_html=True,
    )

    chip_cols = st.columns(2)
    for idx, text in enumerate(qa_suggestions):
        with chip_cols[idx % 2]:
            if st.button(text, key=f"agent_qa_chip_{idx}", use_container_width=True):
                _queue_agent_qa(text)
                st.rerun()

    for message in st.session_state.get("agent_qa_messages", []):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    q = st.chat_input("Nhập câu hỏi về file này...", key="agent_qa_input")
    if q:
        _queue_agent_qa(q)
        st.rerun()

    if st.session_state.get("agent_pending_qa"):
        last_user_q = st.session_state.get("agent_pending_q", "")
        answer = ""

        with st.spinner("Agent đang đọc lại dữ liệu và soạn câu trả lời..."):
            try:
                reset_chat_now = bool(st.session_state.get("agent_qa_reset_next", False))
                resp = api.qa(
                    session_id=session_id,
                    question=last_user_q,
                    reset_chat=reset_chat_now,
                )
                st.session_state["agent_qa_reset_next"] = False

                if isinstance(resp, dict):
                    answer = (resp.get("answer") or "").strip()
                    if not answer:
                        answer = (resp.get("error") or "").strip()
                if not answer:
                    answer = "Không nhận được câu trả lời từ module QA."
            except Exception as e:
                answer = f"Lỗi khi gọi QA: {e}"

        st.session_state["agent_qa_messages"].append({"role": "assistant", "content": answer})
        st.session_state["agent_pending_qa"] = False
        st.session_state["agent_pending_q"] = ""
        st.rerun()

def run_automated_flow(file, sheet_name):
    if not file:
        st.warning("Vui lòng tải tệp lên trước.")
        return

    with st.status("🤖 **Agent đang thực hiện quy trình tự động...**", expanded=True) as status:
        # LOGGING Helper
        log_placeholder = st.empty()
        logs = []
        def add_log(msg, done=False):
            prefix = "✅" if done else "⏳"
            logs.append(f"{prefix} {msg}")
            
            lines_html = []
            for l in logs:
                cls = "activity-line done" if "✅" in l else "activity-line"
                lines_html.append(f'<div class="{cls}">{l}</div>')
            
            full_html = f'<div class="activity-log">{"".join(lines_html)}</div>'
            log_placeholder.markdown(full_html, unsafe_allow_html=True)

        # STEP 1: UPLOAD
        add_log("Đang tải tệp lên hệ thống...")
        res_upload = api.upload_file(file, sheet_name or None)
        if not res_upload.get("ok"):
            st.error(f"Lỗi Upload: {res_upload.get('error')}")
            return
        
        sid = res_upload.get("data", {}).get("session_id")
        st.session_state.session_id = sid
        add_log(f"Tải tệp thành công. Session ID: `{sid[:8]}...`", done=True)

        # STEP 2: PREVIEW
        add_log("Đang phân tích cấu trúc dữ liệu và bảng biểu...")
        res_preview = api.preview(sid, sheet_name or None)
        if not res_preview.get("ok"):
            st.error(f"Lỗi Preview: {res_preview.get('error')}")
            return
        
        sections = res_preview.get("data", {}).get("sections") or []
        if not sections:
            add_log("⚠️ Không tìm thấy bảng biểu rõ ràng. Đang thử chế độ dự phòng...")
        
        st.session_state.sections = sections
        add_log(f"Đã nhận diện {len(sections)} vùng bảng.", done=True)

        # STEP 3: FINALIZE
        add_log("Đang khóa cấu trúc bảng và chuẩn bị định tuyến...")
        res_finalize = api.finalize_sections(sid, sections, sheet_name or None)
        if not res_finalize.get("ok"):
            st.error(f"Lỗi Finalize: {res_finalize.get('error')}")
            return
        
        st.session_state.finalized = True
        add_log("Đã khóa cấu trúc thành công.", done=True)

        # STEP 4: ROUTE
        add_log("Đang nhận diện loại tài liệu và đề xuất luồng xử lý...")
        res_route = api.post_confirm_router(sid)
        if not res_route.get("ok") and res_route.get("ok") is not None:
             st.error(f"Lỗi Router: {res_route.get('error')}")
             return
        
        route = res_route.get("route")
        st.session_state.document_flow = route
        st.session_state.routing_result = res_route
        add_log(f"Đã xác định luồng: **{route.upper() if route else 'UNKNOWN'}**", done=True)

        # STEP 5: ACTION BRANCH
        if route == "ba":
            add_log("Luồng Business Analysis: Đang chiết xuất Scope Items & Commercial Drivers...")
            res_ba = api.ba_analysis(sid)
            st.session_state.ba_analysis_result = res_ba
            add_log("Hoàn thành phân tích BA.", done=True)
        else:
            add_log("Luồng Analytics: Đang xây dựng sơ đồ báo cáo (Report Plan)...")
            plan = res_route.get("report_plan") or {}
            if not plan:
                res_plan = api.report_plan(sid)
                plan = res_plan.get("plan") or {}
            
            st.session_state.report_plan_result = {"ok": True, "plan": plan}
            add_log("Đã lập kế hoạch báo cáo.", done=True)

            # AUTO GENERATE
            recommended = plan.get("recommended_default") or []
            if recommended:
                add_log(f"Tự động chọn {len(recommended)} báo cáo tiêu chí. Đang xây dựng Dashboard...")
                res_gen = api.generate_report(sid, recommended)
                st.session_state.generated_spec_result = res_gen
                st.session_state.selected_report_ids = recommended
                add_log("Dashboard đã sẵn sàng!", done=True)
            else:
                add_log("Không có báo cáo đề xuất mặc định. Vui lòng chọn thủ công trong tab khám phá.")

        status.update(label="✨ **Quy trình hoàn tất!**", state="complete", expanded=False)
        st.session_state["flow_completed"] = True
        time.sleep(0.5)
        st.rerun()

# =========================================================
# Layout
# =========================
st.markdown('<div class="agent-hero"><div class="agent-title">IDPro AI Agent</div><div class="agent-subtitle">Hãy tải file lên để bắt đầu trải nghiệm phân tích tự động hoàn toàn</div></div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ Cấu hình luồng")
    file = st.file_uploader("Tải lên file Excel/CSV", type=["xlsx", "xls", "csv"], key="agent_uploader")
    sheet = st.text_input("Tên Sheet (tùy chọn)", key="agent_sheet")
    
    st.divider()
    if st.button("🚀 Reset", use_container_width=True):
        reset_agent_flow()
        st.rerun()

    st.write("")
    st.markdown("---")
    if st.button("🛠️ Chế độ Chuyên gia (Sửa tay)", use_container_width=True):
        st.switch_page("pages/2_User_UI.py")

# Main Logic UI
if not st.session_state.get("session_id"):
    if file:
        st.info("Bấm nút bên dưới để bắt đầu tự động phân tích file của bạn.")
        if st.button("⚡ Bắt đầu Phân tích Tự động", type="primary", use_container_width=True):
            run_automated_flow(file, sheet)
        st.markdown(
            """
            <div class="agent-wait-note">
                <strong>⏳ Lưu ý nhỏ nhưng khá to:</strong><br>
                <span>Agent đang xử lý tác vụ nặng nên có thể cần khoảng 10 phút. Hãy kiên nhẫn chờ một chút, AI không ngủ gật đâu, nó chỉ đang bê cả kho Excel vào não thôi.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown("""
        <div class="glass-card" style="text-align:center;">
            <h3>👋 Chào mừng bạn!</h3>
            <p>Tôi là trợ lý AI chuyên về xử lý dữ liệu Excel. Chỉ cần chọn file ở sidebar, tôi sẽ tự động xử lý mọi thứ cho bạn.</p>
            <div style="font-size: 4rem; margin: 20px 0;">📊</div>
        </div>
        """, unsafe_allow_html=True)
else:
    # HIỂN THỊ KẾT QUẢ TRONG TABS
    route = st.session_state.get("document_flow")
    
    tab_result, tab_qa = st.tabs(["📊 Kết quả Phân tích", "💬 Hỏi đáp Agent"])
    
    with tab_result:
        if route == "ba":
            render_ba_analysis_workspace(st.session_state.session_id)
        else:
            # Render Analytics Result
            gen_payload = st.session_state.get("generated_spec_result") or {}
            spec = gen_payload.get("data", {}).get("spec") or gen_payload.get("spec")
            
            if spec:
                render_dashboard(spec)
            
            # DISCOVERY SECTION
            plan_data = st.session_state.get("report_plan_result", {}).get("plan", {})
            options = plan_data.get("report_options", [])
            selected_ids = set(st.session_state.get("selected_report_ids", []))
            
            optional_reports = [o for o in options if o.get("report_id") not in selected_ids]
            
            if optional_reports:
                st.markdown('<div class="discovery-title">🔍 Khám phá thêm các góc nhìn khác</div>', unsafe_allow_html=True)
                
                cols = st.columns(2)
                for i, opt in enumerate(optional_reports):
                    with cols[i % 2]:
                        with st.container():
                            st.markdown(f"""
                            <div class="glass-card">
                                <h4 style="margin:0 0 8px 0;">{opt.get('display', {}).get('title')}</h4>
                                <p style="font-size:0.9rem; color:#64748b; margin-bottom:12px;">{opt.get('display', {}).get('description')}</p>
                            </div>
                            """, unsafe_allow_html=True)
                            if st.button(f"➕ Thêm báo cáo này", key=f"add_{opt.get('report_id')}"):
                                new_selection = list(selected_ids) + [opt.get('report_id')]
                                with st.spinner("Đang cập nhật Dashboard..."):
                                    res_gen = api.generate_report(st.session_state.session_id, new_selection)
                                    st.session_state.generated_spec_result = res_gen
                                    st.session_state.selected_report_ids = new_selection
                                    st.rerun()

    with tab_qa:
        if st.session_state.get("finalized"):
            render_agent_qa(st.session_state.session_id, route)
        else:
            st.info("Vui lòng đợi quy trình tự động hoàn tất để bắt đầu hỏi đáp.")

st.markdown('<div style="text-align:center; color:#94a3b8; font-size:0.8rem; margin-top:40px;">IDPro AI Agent v1.0 • Built with 🧠 and Streamlit</div>', unsafe_allow_html=True)

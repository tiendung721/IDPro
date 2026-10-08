from fastapi import APIRouter, HTTPException

from common.session_store import SessionStore
from services.ba_service import build_quotation_render_json
from services.quotation_excel_builder import render_quotation_excel

router = APIRouter()


@router.post("/quotation_generate")
def quotation_generate(payload: dict):
    session_id = payload.get("session_id")
    customer_name = payload.get("customer_name", "")
    quotation_no = payload.get("quotation_no", "")
    currency = payload.get("currency", "VND")

    if not session_id:
        raise HTTPException(status_code=400, detail="Thiếu session_id")

    store = SessionStore.get_instance()
    sess = store.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Không tìm thấy session")
    if not getattr(sess, "ba_analysis", None):
        raise HTTPException(status_code=400, detail="Cần chạy ba_analysis trước")

    quotation_json = build_quotation_render_json(
        ba_analysis=sess.ba_analysis,
        customer_name=customer_name,
        quotation_no=quotation_no,
        currency=currency,
    )

    output_path, output_filename = render_quotation_excel(quotation_json)

    sess.quotation_preview = quotation_json
    sess.quotation_output_path = output_path
    sess.quotation_output_filename = output_filename
    store.upsert(sess)

    return {
        "quotation_preview": quotation_json,
        "download_path": f"/outputs/{output_filename}",
        "filename": output_filename,
    }
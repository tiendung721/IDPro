from fastapi import APIRouter, HTTPException

from common.session_store import SessionStore
from common.ai_model_config import get_ba_analysis_model
from services.ba_service import run_ba_analysis
from services.openai_ci import upload_file_for_ci

router = APIRouter()


@router.post("/ba_analysis")
def ba_analysis(payload: dict):
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Thiếu session_id")

    store = SessionStore.get_instance()
    sess = store.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Không tìm thấy session")

    manifest_path = getattr(sess, "sections_manifest_path", None) or getattr(sess, "manifest_path", None)
    if not manifest_path:
        raise HTTPException(status_code=400, detail="Session chưa confirm sections")

    if not getattr(sess, "ba_detection", None):
        raise HTTPException(status_code=400, detail="Cần chạy ba_detect hoặc post_confirm_router trước")

    ba_detection = sess.ba_detection or {}
    if not bool(ba_detection.get("is_ba", False)):
        raise HTTPException(
            status_code=409,
            detail="File này không phải BA. Hãy dùng luồng report_plan/post_confirm_router."
        )

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_json = f.read()

    if not sess.openai_file_id:
        file_path = getattr(sess, "file_path", None)
        if not file_path:
            raise HTTPException(status_code=400, detail="Session không có file_path")
        try:
            with open(file_path, "rb") as f:
                content = f.read()

            import os
            filename = getattr(sess, "original_filename", None) or os.path.basename(file_path)

            sess.openai_file_id = upload_file_for_ci(filename, content)
            store.upsert(sess)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Upload file lên OpenAI lỗi: {e}")

    model = get_ba_analysis_model()

    try:
        result = run_ba_analysis(
            file_id=sess.openai_file_id,
            model=model,
            manifest_json=manifest_json,
            ba_detection=ba_detection,
            previous_response_id=None,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BA analysis lỗi: {e}")

    sess.ba_analysis = result["result"]
    store.upsert(sess)
    return result["result"]
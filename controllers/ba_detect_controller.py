from fastapi import APIRouter, HTTPException

from common.session_store import SessionStore
from common.ai_model_config import get_ba_detect_model
from services.ba_service import run_ba_detection
from services.openai_ci import upload_file_for_ci

router = APIRouter()


@router.post("/ba_detect")
def ba_detect(payload: dict):
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

    model = get_ba_detect_model()

    try:
        result = run_ba_detection(
            file_id=sess.openai_file_id,
            model=model,
            manifest_json=manifest_json,
            previous_response_id=None,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BA detect lỗi: {e}")

    sess.ba_detection = result["result"]
    store.upsert(sess)
    return result["result"]
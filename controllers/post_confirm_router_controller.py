from fastapi import APIRouter, HTTPException

from common.session_store import SessionStore
from services.openai_ci import upload_file_for_ci, ask_ci_report_plan
from services.ba_service import run_ba_detection, run_ba_analysis
from common.ai_model_config import (
    get_ba_detect_model,
    get_ba_analysis_model,
    get_report_plan_model,
)

router = APIRouter()


def _read_manifest_text(manifest_path: str) -> str:
    with open(manifest_path, "r", encoding="utf-8") as f:
        return f.read()


def _load_report_catalog_json() -> str:
    path = "rule_memory/report_catalog_v1.json"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_json_object(text: str) -> dict:
    import json
    s = (text or "").strip()
    try:
        return json.loads(s)
    except Exception:
        i = s.find("{")
        j = s.rfind("}")
        if i != -1 and j != -1 and j > i:
            return json.loads(s[i:j+1])
        raise


@router.post("/post_confirm_router")
def post_confirm_router(payload: dict):
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Thiếu session_id")

    store = SessionStore.get_instance()
    sess = store.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Không tìm thấy session")

    manifest_path = getattr(sess, "sections_manifest_path", None)
    if not manifest_path:
        raise HTTPException(
            status_code=400,
            detail="Session chưa confirm sections hoặc chưa có sections_manifest_path"
        )

    manifest_json = _read_manifest_text(manifest_path)

    if not getattr(sess, "openai_file_id", None):
        file_path = getattr(sess, "file_path", None)
        if not file_path:
            raise HTTPException(status_code=400, detail="Session không có file_path")
        try:
            with open(file_path, "rb") as f:
                content = f.read()

            filename = getattr(sess, "original_filename", None)
            if not filename:
                import os
                filename = os.path.basename(file_path)

            sess.openai_file_id = upload_file_for_ci(filename, content)
            store.upsert(sess)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Upload file lên OpenAI lỗi: {e}")

    model_ba_detect = get_ba_detect_model()
    model_ba_analysis = get_ba_analysis_model()
    model_report_plan = get_report_plan_model()

    # 1) Detect BA (Tác vụ nhẹ -> dùng model detect riêng)
    try:
        detect_out = run_ba_detection(
            file_id=sess.openai_file_id,
            model=model_ba_detect,
            manifest_json=manifest_json,
            previous_response_id=None,
        )
        ba_detect = detect_out["result"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BA detect lỗi: {e}")

    # Nên dùng 1 field thống nhất, nhưng giữ tạm cả 2 cho tương thích
    sess.ba_detection = ba_detect
    sess.ba_detect_result = ba_detect
    sess.document_type = ba_detect.get("document_type", "unknown")

    if bool(ba_detect.get("is_ba")):
        try:
            analysis_out = run_ba_analysis(
                file_id=sess.openai_file_id,
                model=model_ba_analysis,
                manifest_json=manifest_json,
                ba_detection=ba_detect,
                previous_response_id=None,
            )
            ba_analysis = analysis_out["result"]
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"BA analysis lỗi: {e}")

        sess.document_flow = "ba"
        sess.ba_analysis = ba_analysis
        sess.ba_analysis_result = ba_analysis
        sess.report_plan = None
        store.upsert(sess)

        return {
            "route": "ba",
            "document_type": sess.document_type,
            "ba_detect_result": ba_detect,
            "ba_analysis_result": ba_analysis,
        }

    # 2) Non-BA -> report plan như cũ (Tác vụ logic nặng -> dùng model report plan riêng)
    try:
        report_catalog_json = _load_report_catalog_json()
        raw_text, _response_id = ask_ci_report_plan(
            file_id=sess.openai_file_id,
            model=model_report_plan,
            previous_response_id=None,
            manifest_json=manifest_json,
            report_catalog_json=report_catalog_json,
        )
        report_plan_raw = _parse_json_object(raw_text)
        from controllers.report_plan_controller import (
            _normalize_report_plan,
            _build_report_plan_compact,
            _build_dataset_profile_compact,
        )
        import json
        
        report_plan = _normalize_report_plan(report_plan_raw, report_catalog_json)
        catalog_obj = json.loads(report_catalog_json)
        report_plan_compact = _build_report_plan_compact(report_plan, catalog_obj)
        dataset_profile_compact = _build_dataset_profile_compact(report_plan)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Report plan lỗi: {e}")

    sess.document_flow = "analytics"
    sess.report_plan = report_plan
    sess.report_plan_compact = report_plan_compact
    sess.dataset_profile_compact = dataset_profile_compact
    store.upsert(sess)

    return {
        "route": "analytics",
        "document_type": sess.document_type,
        "ba_detect_result": ba_detect,
        "report_plan": report_plan,
    }
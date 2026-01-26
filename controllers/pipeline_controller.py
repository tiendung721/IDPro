from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from common.auth import Actor, get_actor
from common.session_store import SessionStore
from services.openai_ci import ask_ci_final, upload_file_for_ci

router = APIRouter()
store = SessionStore.get_instance()


class FinalRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    reset: bool = False


def _owner_key_from_actor(actor: Actor) -> str:
    kind = actor.get("kind")
    if kind == "admin" and actor.get("id"):
        return f"admin:{actor['id']}"
    if kind == "user" and actor.get("id"):
        return f"user:{actor['id']}"
    raise HTTPException(status_code=401, detail="Unauthorized")


def _assert_owner(session_data: Any, actor: Actor) -> None:
    expected = _owner_key_from_actor(actor)
    actual = getattr(session_data, "owner_key", None)
    if actual != expected:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập session này.")


@router.post("/final")
def final(req: FinalRequest, actor: Actor = Depends(get_actor)) -> Dict[str, Any]:
    # 1) Load session + ownership
    data = store.get(req.session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại.")
    _assert_owner(data, actor)

    # 2) Ensure confirmed + manifest exists
    if not getattr(data, "confirmed", False):
        raise HTTPException(status_code=400, detail="Session chưa confirm sections. Hãy gọi /confirm_sections trước.")

    raw_path: Optional[str] = getattr(data, "file_path", None)
    if not raw_path:
        raise HTTPException(status_code=500, detail="Session thiếu file gốc (file_path).")

    manifest_path: Optional[str] = getattr(data, "sections_manifest_path", None)
    if not manifest_path:
        raise HTTPException(
            status_code=400,
            detail="Chưa có sections_manifest.json. Hãy gọi /confirm_sections trước.",
        )

    # 3) Reset final continuity if requested
    if req.reset:
        data.final_prev_response_id = None
        store.upsert(data)

    # 4) Ensure OpenAI file_id (reuse with QA)
    if not getattr(data, "openai_file_id", None):
        try:
            with open(raw_path, "rb") as f:
                content = f.read()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Không đọc được file gốc: {e}")

        try:
            fid = upload_file_for_ci(os.path.basename(raw_path), content)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Upload file gốc lên OpenAI thất bại: {e}")

        data.openai_file_id = fid
        data.qa_prev_response_id = None
        data.final_prev_response_id = None
        store.upsert(data)

    # 5) Read manifest text
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_text = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không đọc được sections_manifest.json: {e}")

    # 6) Ask CI for final narrative
    model = (os.getenv("FINAL_CI_MODEL") or "gpt-4.1").strip()

    try:
        report_text, resp_id = ask_ci_final(
            file_id=data.openai_file_id,
            model=model,
            previous_response_id=getattr(data, "final_prev_response_id", None),
            manifest_json=manifest_text,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI Code Interpreter lỗi: {e}")

    # 7) Persist continuity
    data.final_prev_response_id = resp_id
    store.upsert(data)

    return {
        "report": report_text,
        "openai_file_id": data.openai_file_id,
        "response_id": resp_id,
    }

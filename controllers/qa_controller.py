# controllers/qa_controller.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from common.auth import Actor, get_actor
from common.session_store import SessionStore
from services.openai_ci import ask_ci_qa, upload_file_for_ci

router = APIRouter()
store = SessionStore.get_instance()


# -------------------------
# Request / Response models
# -------------------------
class QARequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    reset_chat: bool = False


class QAResponse(BaseModel):
    answer: str
    openai_file_id: str
    response_id: str


# -------------------------
# Ownership helpers
# -------------------------
def _owner_key_from_actor(actor: Actor) -> str:
    kind = actor.get("kind")
    if kind == "admin" and actor.get("id"):
        return f"admin:{actor['id']}"
    if kind == "user" and actor.get("id"):
        return f"user:{actor['id']}"
    raise HTTPException(status_code=401, detail="Unauthorized")


def _assert_owner(session_data: Any, actor: Actor) -> None:
    """
    Deny access if caller is not the owner.
    """
    expected = _owner_key_from_actor(actor)
    actual = getattr(session_data, "owner_key", None)
    if actual != expected:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập session này.")


# -------------------------
# Core endpoint
# -------------------------
@router.post("/qa", response_model=QAResponse)
def qa(req: QARequest, actor: Actor = Depends(get_actor)) -> Dict[str, Any]:
    # 1) Load session + ownership
    data = store.get(req.session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại.")
    _assert_owner(data, actor)

    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question không được rỗng.")

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

    # 3) Optional: reset chat continuity
    if req.reset_chat:
        data.qa_prev_response_id = None
        store.upsert(data)

    # 4) Ensure OpenAI file_id (upload 1 lần / session)
    # Nếu confirm_sections thay đổi, controller confirm phải set data.openai_file_id = None (invalidate)
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
        data.qa_prev_response_id = None  # reset continuity on new file
        store.upsert(data)

    # 5) Read manifest text (pass into CI prompt)
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_text = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không đọc được sections_manifest.json: {e}")

    # 6) Ask Code Interpreter via Responses API
    model = (os.getenv("QA_CI_MODEL") or "gpt-4.1").strip()

    try:
        answer, resp_id = ask_ci_qa(
            file_id=data.openai_file_id,
            question=question,
            model=model,
            previous_response_id=getattr(data, "qa_prev_response_id", None),
            manifest_json=manifest_text,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI Code Interpreter lỗi: {e}")

    # 7) Persist continuity
    data.qa_prev_response_id = resp_id
    store.upsert(data)

    return {
        "answer": answer,
        "openai_file_id": data.openai_file_id,
        "response_id": resp_id,
    }

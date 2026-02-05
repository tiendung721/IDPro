from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from common.auth import Actor, get_actor
from common.session_store import SessionStore
import json

from services.openai_ci import ask_ci_final_spec, upload_file_for_ci

router = APIRouter()
store = SessionStore.get_instance()


class FinalSpecRequest(BaseModel):
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



def _parse_json_loose(text: str) -> Dict[str, Any]:
    """Parse JSON robustly from CI output.
    CI đôi khi trả thừa whitespace hoặc text phụ. Hàm này cố gắng:
    - json.loads trực tiếp
    - nếu fail: lấy substring từ ký tự '{' đầu tiên tới '}' cuối cùng rồi parse.
    """
    if not isinstance(text, str):
        raise ValueError("final_spec output is not a string")
    s = text.strip()
    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            raise ValueError("JSON root must be an object")
        return obj
    except Exception:
        pass

    i = s.find("{")
    j = s.rfind("}")
    if i == -1 or j == -1 or j <= i:
        raise ValueError("Không tìm thấy JSON object trong output")
    sub = s[i : j + 1]
    obj = json.loads(sub)
    if not isinstance(obj, dict):
        raise ValueError("JSON root must be an object")
    return obj


@router.post("/final_spec")
def final_spec(req: FinalSpecRequest, actor: Actor = Depends(get_actor)) -> Dict[str, Any]:
    """Return dashboard-ready JSON report spec.

    Lưu ý:
    - Dùng chung file_id với QA/final.
    - Dùng continuity riêng (final_spec_prev_response_id) để không trộn với final narrative.
    """
    data = store.get(req.session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại.")
    _assert_owner(data, actor)

    if not getattr(data, "confirmed", False):
        raise HTTPException(status_code=400, detail="Session chưa confirm sections. Hãy gọi /confirm_sections trước.")

    raw_path: Optional[str] = getattr(data, "file_path", None)
    if not raw_path:
        raise HTTPException(status_code=500, detail="Session thiếu file gốc (file_path).")

    manifest_path: Optional[str] = getattr(data, "sections_manifest_path", None)
    if not manifest_path:
        raise HTTPException(status_code=400, detail="Chưa có sections_manifest.json. Hãy gọi /confirm_sections trước.")

    if req.reset:
        data.final_spec_prev_response_id = None
        store.upsert(data)

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
        data.final_spec_prev_response_id = None
        store.upsert(data)

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_text = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không đọc được sections_manifest.json: {e}")

    model = (os.getenv("FINAL_SPEC_CI_MODEL") or os.getenv("FINAL_CI_MODEL") or "gpt-4.1").strip()

    try:
        raw_out, resp_id = ask_ci_final_spec(
            file_id=data.openai_file_id,
            model=model,
            previous_response_id=getattr(data, "final_spec_prev_response_id", None),
            manifest_json=manifest_text,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI Code Interpreter lỗi: {e}")

    try:
        spec = _parse_json_loose(raw_out)
    except Exception as e:
        # không crash hẳn: trả raw để debug
        raise HTTPException(status_code=502, detail=f"final_spec không parse được JSON: {e}. Raw (truncated): {(raw_out or '')[:1200]}")

    data.final_spec_prev_response_id = resp_id
    store.upsert(data)

    return {
        "spec": spec,
        "openai_file_id": data.openai_file_id,
        "response_id": resp_id,
    }


 

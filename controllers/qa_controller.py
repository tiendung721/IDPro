# controllers/qa_controller.py
from __future__ import annotations

import os
import json
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from common.auth import Actor, get_actor
from common.session_store import SessionStore
from common.ai_model_config import get_qa_model
from services.openai_ci import ask_ci_qa, upload_file_for_ci

router = APIRouter()
store = SessionStore.get_instance()

MAX_QA_RECENT_TURNS = 3
MAX_QA_SUMMARY_CHARS = 1500


# -------------------------
# Request / Response models
# -------------------------
class QARequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    reset_chat: bool = False


class QAResponse(BaseModel):
    answer: str
    answer_style: str = "friendly"
    confidence_note: Optional[str] = None
    source_tables: List[str] = []
    openai_file_id: str
    response_id: str

def normalize_user_answer(text: str) -> str:
    s = (text or "").strip()
    replacements = {
        "MANIFEST_JSON": "cấu trúc dữ liệu đã xác nhận",
        "manifest": "cấu trúc dữ liệu đã xác nhận",
        "parse": "đọc",
        "schema": "cấu trúc dữ liệu",
        "backend": "hệ thống",
        "pipeline": "quy trình xử lý",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    s = s.replace("Không tìm thấy", "Hiện chưa thấy")
    s = s.replace("không hợp lệ", "chưa phù hợp")
    return s

def _parse_json_loose(text: str) -> Dict[str, Any]:
    s = str(text or "").strip()
    if not s:
        return {}
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(s[i:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


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
    expected = _owner_key_from_actor(actor)
    actual = getattr(session_data, "owner_key", None)
    if actual != expected:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập session này.")


# -------------------------
# Memory helpers
# -------------------------
def _qa_max_thread_turns() -> int:
    raw = (os.getenv("QA_MAX_THREAD_TURNS") or "4").strip()
    try:
        value = int(raw)
    except Exception:
        value = 4
    return max(1, min(value, 8))


def _trim_text(s: str, limit: int) -> str:
    s = (s or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit]


def compress_answer_for_memory(answer_json: dict, fallback_answer: str = "") -> str:
    if answer_json:
        core = str(answer_json.get("answer_core", "")).strip()
        if not core:
            core = str(answer_json.get("friendly_answer", "")).strip()
    else:
        core = fallback_answer.strip()
    return _trim_text(core or "Đã trả lời.", 250)


def _append_recent_turns(
    turns: Optional[List[Dict[str, str]]],
    question: str,
    answer_json: dict,
    fallback_answer: str = "",
) -> List[Dict[str, str]]:
    current = list(turns or [])
    compressed = compress_answer_for_memory(answer_json, fallback_answer)
    current.append(
        {
            "question": _trim_text(question, 400),
            "answer": compressed,
        }
    )
    return current[-MAX_QA_RECENT_TURNS:]


def _build_memory_summary(
    old_summary: Optional[str],
    recent_turns: Optional[List[Dict[str, str]]],
) -> str:
    parts: List[str] = []

    old_summary = (old_summary or "").strip()
    if old_summary:
        parts.append(_trim_text(old_summary, 700))

    for i, t in enumerate(recent_turns or [], 1):
        q = str((t or {}).get("question", "")).strip()
        a = str((t or {}).get("answer", "")).strip()
        if q:
            parts.append(f"Q{i}: {q}")
        if a:
            parts.append(f"A{i}: {a}")

    merged = "\n".join(parts).strip()
    return _trim_text(merged, MAX_QA_SUMMARY_CHARS)


def _reset_qa_memory(data: Any) -> None:
    data.qa_prev_response_id = None
    data.qa_thread_turn_count = 0
    data.qa_memory_summary = None
    data.qa_recent_turns = []


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
        raise HTTPException(
            status_code=400,
            detail="Session chưa confirm sections. Hãy gọi /confirm_sections trước.",
        )

    raw_path: Optional[str] = getattr(data, "file_path", None)
    if not raw_path:
        raise HTTPException(status_code=500, detail="Session thiếu file gốc (file_path).")

    manifest_path: Optional[str] = getattr(data, "sections_manifest_path", None)
    if not manifest_path:
        raise HTTPException(
            status_code=400,
            detail="Chưa có sections_manifest.json. Hãy gọi /confirm_sections trước.",
        )

    # 3) Optional: reset chat continuity + memory
    if req.reset_chat:
        _reset_qa_memory(data)
        store.upsert(data)

    # 4) Ensure OpenAI file_id (upload 1 lần / session)
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
        _reset_qa_memory(data)  # file mới -> reset continuity + memory
        store.upsert(data)

    # 5) Read manifest text
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_text = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không đọc được sections_manifest.json: {e}")

    # 6) Decide whether to continue the OpenAI thread
    max_thread_turns = _qa_max_thread_turns()
    current_turns = int(getattr(data, "qa_thread_turn_count", 0) or 0)

    if current_turns >= max_thread_turns:
        prev_response_id = None
        current_turns = 0
    else:
        prev_response_id = getattr(data, "qa_prev_response_id", None)

    memory_summary = getattr(data, "qa_memory_summary", None)
    recent_turns = getattr(data, "qa_recent_turns", []) or []

    # 7) Ask Code Interpreter via Responses API
    model = get_qa_model()

    try:
        raw_answer, resp_id = ask_ci_qa(
            file_id=data.openai_file_id,
            question=question,
            model=model,
            previous_response_id=prev_response_id,
            manifest_json=manifest_text,
            memory_summary=memory_summary,
            recent_turns=recent_turns,
            dataset_profile_compact=data.dataset_profile_compact,
        )
        
        parsed_out = _parse_json_loose(raw_answer)
        friendly_ans = parsed_out.get("friendly_answer") or raw_answer
        friendly_ans = normalize_user_answer(friendly_ans)
        
        limitations = parsed_out.get("limitations") or []
        evidence = parsed_out.get("evidence") or []
        source_tables = parsed_out.get("source_tables") or []
        confidence_note = " | ".join(limitations) if limitations else None

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI Code Interpreter lỗi: {e}")

    # 8) Persist bounded continuity + app memory
    new_recent_turns = _append_recent_turns(recent_turns, question, parsed_out, raw_answer)
    new_summary = _build_memory_summary(memory_summary, new_recent_turns)

    data.qa_prev_response_id = resp_id
    data.qa_thread_turn_count = current_turns + 1
    data.qa_recent_turns = new_recent_turns
    data.qa_memory_summary = new_summary
    store.upsert(data)

    return {
        "answer": friendly_ans,
        "answer_style": "friendly" if parsed_out.get("friendly_answer") else "raw",
        "confidence_note": confidence_note,
        "source_tables": source_tables if isinstance(source_tables, list) else [str(source_tables)],
        "openai_file_id": data.openai_file_id,
        "response_id": resp_id,
    }
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from common.session_store import SessionStore
from common.models import Section as SectionModel
from common.auth import get_actor, Actor
from data_processing.validators import validate_sections_zero_based, IndexErrorDetail

router = APIRouter()
store = SessionStore.get_instance()


class SectionIn(BaseModel):
    start_row: int
    end_row: int
    header_row: int
    label: Optional[str] = ""


class SectionsPayload(BaseModel):
    sections: List[SectionIn]


def _owner_key_from_actor(actor: Actor) -> str:
    kind = actor.get("kind")
    if kind == "admin" and actor.get("id"):
        return f"admin:{actor['id']}"
    if kind == "user" and actor.get("id"):
        return f"user:{actor['id']}"
    raise HTTPException(status_code=401, detail="Unauthorized")


def _assert_owner(data, actor: Actor) -> None:
    expected_owner = _owner_key_from_actor(actor)
    if getattr(data, "owner_key", None) != expected_owner:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập session này")


def _section_to_dict(s: SectionModel) -> Dict[str, Any]:
    return s.model_dump() if hasattr(s, "model_dump") else dict(getattr(s, "__dict__", {}))


def _get_working_sections_models(data) -> List[SectionModel]:
    # Ưu tiên confirmed_sections, fallback auto_sections
    secs = getattr(data, "confirmed_sections", None) or getattr(data, "auto_sections", None) or []
    out: List[SectionModel] = []
    for s in secs:
        if isinstance(s, SectionModel):
            out.append(s)
        elif hasattr(s, "model_dump"):
            out.append(SectionModel(**s.model_dump()))
        elif isinstance(s, dict):
            out.append(SectionModel(**s))
        else:
            out.append(SectionModel(**dict(getattr(s, "__dict__", {}))))
    return out


@router.get("/sessions/{session_id}/sections")
def get_sections(session_id: str, actor: Actor = Depends(get_actor)):
    data = store.get(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    _assert_owner(data, actor)

    sections = _get_working_sections_models(data)
    return {"ok": True, "data": {"sections": [_section_to_dict(s) for s in sections]}}


@router.put("/sessions/{session_id}/sections")
def replace_sections(session_id: str, payload: SectionsPayload, actor: Actor = Depends(get_actor)):
    data = store.get(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    _assert_owner(data, actor)

    secs_dict = [s.model_dump() for s in payload.sections]
    try:
        validate_sections_zero_based(secs_dict, nrows=10**9)
    except IndexErrorDetail as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    data.confirmed_sections = [SectionModel(**s) for s in secs_dict]
    store.upsert(data)

    return {"ok": True, "data": {"sections": [_section_to_dict(s) for s in data.confirmed_sections]}}


@router.post("/sessions/{session_id}/sections")
def add_section(session_id: str, section: SectionIn, actor: Actor = Depends(get_actor)):
    data = store.get(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    _assert_owner(data, actor)

    working = _get_working_sections_models(data)
    working.append(SectionModel(**section.model_dump()))

    try:
        validate_sections_zero_based([_section_to_dict(s) for s in working], nrows=10**9)
    except IndexErrorDetail as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    data.confirmed_sections = working
    store.upsert(data)
    return {"ok": True, "data": {"sections": [_section_to_dict(s) for s in working]}}


@router.delete("/sessions/{session_id}/sections/{index}")
def delete_section(session_id: str, index: int, actor: Actor = Depends(get_actor)):
    data = store.get(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    _assert_owner(data, actor)

    working = _get_working_sections_models(data)
    if not (0 <= index < len(working)):
        raise HTTPException(status_code=404, detail="index out of range")

    del working[index]

    try:
        validate_sections_zero_based([_section_to_dict(s) for s in working], nrows=10**9)
    except IndexErrorDetail as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    data.confirmed_sections = working
    store.upsert(data)
    return {"ok": True, "data": {"sections": [_section_to_dict(s) for s in working]}}

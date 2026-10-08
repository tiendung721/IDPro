# controllers/section_confirm_controller.py
from __future__ import annotations

import os
import time
from typing import Dict, List, Optional, Any, Tuple

import pandas as pd
from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel

from common.session_store import SessionStore
from common.models import Section
from common.auth import get_actor, Actor

from data_processing.validators import (
    to_zero_based,
    validate_sections_zero_based,
    IndexErrorDetail,
)

from data_processing.rule_memory import get_fingerprint, get_fingerprint_v2
from data_processing.chat_memory import memory

from services.artifacts import write_manifest

router = APIRouter()
store = SessionStore.get_instance()


# -------------------------
# Request models
# -------------------------
class SectionIn(BaseModel):
    header_row: int
    start_row: int
    end_row: int
    label: Optional[str] = None
    start_col: Optional[int] = None
    end_col: Optional[int] = None


class ConfirmRequest(BaseModel):
    session_id: str
    sheet_name: Optional[str] = None
    sections: Optional[List[SectionIn]] = None


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


def _assert_owner(data: Any, actor: Actor) -> None:
    expected_owner = _owner_key_from_actor(actor)
    if getattr(data, "owner_key", None) != expected_owner:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập session này")


# -------------------------
# Excel/CSV reader (header=None)
# -------------------------
def _read_df(file_path: str, sheet_name: Optional[str] = None) -> Tuple[pd.DataFrame, Optional[str]]:
    ext = (file_path or "").lower().split(".")[-1]
    if ext == "csv":
        return pd.read_csv(file_path, header=None), None

    resolved = sheet_name
    if resolved is None or str(resolved).strip() == "":
        xls = pd.ExcelFile(file_path)
        resolved = xls.sheet_names[0] if xls.sheet_names else 0

    df = pd.read_excel(file_path, sheet_name=resolved, header=None)

    try:
        if isinstance(resolved, int):
            xls = pd.ExcelFile(file_path)
            resolved = xls.sheet_names[resolved]
    except Exception:
        pass

    return df, (str(resolved) if resolved is not None else None)


# -------------------------
# Section picker
# -------------------------
def _pick_sections_from_input_or_session(
    sections_in: Optional[List[Dict]],
    session_obj: Any,
) -> List[Dict]:
    if sections_in and len(sections_in) > 0:
        return sections_in

    auto_sections = getattr(session_obj, "auto_sections", None)
    if auto_sections and len(auto_sections) > 0:
        return [
            s.model_dump() if hasattr(s, "model_dump") else getattr(s, "__dict__", {})
            for s in auto_sections
        ]

    confirmed_sections = getattr(session_obj, "confirmed_sections", None)
    if confirmed_sections and len(confirmed_sections) > 0:
        out: List[Dict] = []
        for s in confirmed_sections:
            if hasattr(s, "model_dump"):
                out.append(s.model_dump())
            elif isinstance(s, dict):
                out.append(dict(s))
            else:
                out.append(dict(getattr(s, "__dict__", {})))
        if out:
            return out

    raise HTTPException(
        status_code=400,
        detail="Thiếu 'sections' và session cũng không có auto_sections.",
    )


def _reset_qa_state(data: Any) -> None:
    data.qa_prev_response_id = None
    data.qa_thread_turn_count = 0
    data.qa_memory_summary = None
    data.qa_recent_turns = []


def _reset_input_derived_state(data: Any) -> None:
    data.openai_file_id = None
    data.manifest_hash = None
    data.dataset_profile_compact = None


def _reset_plan_state(data: Any) -> None:
    data.report_plan = None
    data.report_plan_compact = None
    data.report_plan_cache_key = None
    data.report_plan_similarity_key = None
    data.report_plan_version = None
    data.report_catalog_version = None


def _reset_report_state(data: Any) -> None:
    data.selected_reports = None
    data.generated_dashboard_spec = None
    data.generated_dashboard_summary = None
    data.report_generation_context_key = None
    data.report_generation_version = None
    data.generate_prev_response_id = None


# -------------------------
# Endpoint
# -------------------------
@router.post("/confirm_sections")
def confirm_sections(
    payload: ConfirmRequest = Body(...),
    actor: Actor = Depends(get_actor),
):
    session_id: str = payload.session_id
    sheet_name: Optional[str] = payload.sheet_name
    sections_in: Optional[List[Dict]] = [s.model_dump() for s in payload.sections] if payload.sections else None

    if not session_id:
        raise HTTPException(status_code=422, detail="session_id là bắt buộc")

    data = store.get(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    _assert_owner(data, actor)
    mem_user_id = _owner_key_from_actor(actor)

    if getattr(data, "confirming", False):
        raise HTTPException(status_code=409, detail="Confirm đang chạy. Vui lòng thử lại sau.")

    setattr(data, "confirming", True)
    store.upsert(data)

    try:
        # 1) Read raw df (header=None) + resolve sheet_name
        try:
            df_raw, resolved_sheet = _read_df(data.file_path, sheet_name=sheet_name)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Không đọc được file: {e}")

        if df_raw.shape[0] == 0:
            raise HTTPException(status_code=400, detail="File/sheet rỗng")

        # 2) Compute fingerprint (best-effort)
        fp_used: Optional[str] = None
        try:
            fp_used = get_fingerprint_v2(df_raw, sheet_name=resolved_sheet)
        except Exception:
            try:
                fp_used = get_fingerprint(df_raw, sheet_name=resolved_sheet)
            except TypeError:
                fp_used = get_fingerprint(df_raw)

        if fp_used:
            try:
                data.fingerprint = fp_used
                store.upsert(data)
            except Exception:
                pass

        # 3) Pick sections from payload or session
        sections_raw: List[Dict] = _pick_sections_from_input_or_session(sections_in, data)

        # 4) Validate sections to 0-based
        index_base = "zero"
        try:
            sections_zb = validate_sections_zero_based(
                sections_raw,
                nrows=df_raw.shape[0],
                ncols=df_raw.shape[1],
            )
        except IndexErrorDetail as ie_primary:
            try:
                sections_try = to_zero_based(sections_raw, nrows=df_raw.shape[0])
                sections_zb = validate_sections_zero_based(
                    sections_try,
                    nrows=df_raw.shape[0],
                    ncols=df_raw.shape[1],
                )
                index_base = "one->zero_auto"
            except Exception:
                return {"ok": False, "code": ie_primary.code, "error": str(ie_primary)}

        # 5) Persist confirmed sections + confirmed flag
        data.confirmed_sections = [Section(**s) for s in sections_zb]
        data.confirmed = True

        # 6) Write sections_manifest.json
        manifest = {
            "source_file": os.path.basename(data.file_path),
            "file_path": data.file_path,
            "sheet_name": resolved_sheet,
            "index_base": "zero",
            "tables": [
                {
                    "table_id": f"T{i+1}",
                    "sheet": resolved_sheet,
                    "header_row_0based": s["header_row"],
                    "start_row_0based": s["start_row"],
                    "end_row_0based": s["end_row"],
                    "label": s.get("label"),
                    "start_col_0based": s.get("start_col", 0),
                    "end_col_0based": s.get("end_col", df_raw.shape[1] - 1),
                }
                for i, s in enumerate(sections_zb)
            ],
        }

        manifest_path = write_manifest(session_id, manifest, filename="sections_manifest.json")
        data.sections_manifest_path = manifest_path
        data.confirmed_sheet_name = resolved_sheet

        # 7) Data/sections changed => invalidate all downstream AI state
        _reset_input_derived_state(data)
        _reset_qa_state(data)

        data.final_prev_response_id = None
        data.final_spec_prev_response_id = None

        _reset_plan_state(data)
        _reset_report_state(data)

        store.upsert(data)

        # 8) Memory record (best-effort)
        try:
            memory.add_record(
                mem_user_id,
                {
                    "event": "confirm",
                    "session_id": session_id,
                    "sections_count": len(sections_zb),
                    "index_base": index_base,
                    "timestamp": int(time.time()),
                    "fingerprint": fp_used,
                    "sheet_name": resolved_sheet,
                },
            )
        except Exception:
            pass

        # 9) Return compatible response shape
        return {
            "ok": True,
            "code": "CONFIRM_OK",
            "data": {
                "count": len(sections_zb),
                "sections": sections_zb,
                "fingerprint": fp_used,
                "index_base": index_base,
                "sheet_name": resolved_sheet,
                "manifest_path": manifest_path,
            },
        }

    finally:
        try:
            setattr(data, "confirming", False)
            store.upsert(data)
        except Exception:
            pass
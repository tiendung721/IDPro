from __future__ import annotations

from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import time
import pandas as pd

from common.auth import require_admin_actor, get_actor, Actor
from common.session_store import SessionStore

from data_processing.rule_memory import save_rule_for_fingerprint, get_fingerprint, get_fingerprint_v2
from data_processing.validators import validate_sections_zero_based, to_zero_based, IndexErrorDetail

router = APIRouter()
store = SessionStore.get_instance()


class SaveTemplateReq(BaseModel):
    session_id: str
    sheet_name: Optional[str] = None
    template_name: Optional[str] = None


def _read_df(file_path: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    ext = (file_path or "").lower().split(".")[-1]
    if ext == "csv":
        return pd.read_csv(file_path, header=None)

    resolved_sheet_name = sheet_name
    if resolved_sheet_name is None or str(resolved_sheet_name).strip() == "":
        try:
            xls = pd.ExcelFile(file_path)
            if xls.sheet_names:
                resolved_sheet_name = xls.sheet_names[0]
        except Exception:
            resolved_sheet_name = 0

    return pd.read_excel(file_path, sheet_name=resolved_sheet_name, header=None)


def _build_overrides_from_sections(sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build overrides rule (fallback) từ confirmed sections.

    sections là list dict 0-based, có start_row/end_row/header_row/label.
    """
    overrides: Dict[str, Any] = {"sections": []}

    hdrs = {int(s["header_row"]) for s in sections if s.get("header_row") is not None}
    if len(hdrs) == 1:
        overrides["header_row"] = int(list(hdrs)[0])

    for idx, s in enumerate(sections, start=1):
        fields: Dict[str, Any] = {
            "start_row": int(s["start_row"]),
            "end_row": int(s["end_row"]),
            "header_row": int(s["header_row"]),
        }
        if s.get("label"):
            fields["label"] = s["label"]

        overrides["sections"].append(
            {"selector": {"by": "index", "value": f"S{idx}"}, "fields": fields}
        )

    return overrides


def _admin_owner_key(admin: Actor) -> str:
    return f"admin:{admin['id']}"

def _owner_key_from_actor(actor: Actor) -> str:
    kind = actor.get("kind")
    if kind == "admin" and actor.get("id"):
        return f"admin:{actor['id']}"
    if kind == "user" and actor.get("id"):
        return f"user:{actor['id']}"
    raise HTTPException(status_code=401, detail="Actor không hợp lệ")


@router.post("/admin/save_template")
def save_template(payload: SaveTemplateReq = Body(...), admin: Actor = Depends(require_admin_actor)):
    """ADMIN ONLY.

    Lưu template chuẩn vào rule_memory dưới user_id = 'default_user'

    Policy:
    - Admin chỉ được save template từ session thuộc chính admin (owner_key=admin:<admin_id>)
    - Session của user sẽ bị 403 
    """
    data = store.get(payload.session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    expected_owner = _admin_owner_key(admin)
    if getattr(data, "owner_key", None) != expected_owner:
        raise HTTPException(status_code=403, detail="Bạn không phải owner của session này")

    if not getattr(data, "confirmed", False):
        raise HTTPException(status_code=400, detail="Session chưa confirm_sections")

    df = _read_df(data.file_path, sheet_name=payload.sheet_name)
    if df.shape[0] == 0:
        raise HTTPException(status_code=400, detail="File/sheet rỗng")

    confirmed_sections = getattr(data, "confirmed_sections", None) or []
    if not confirmed_sections:
        raise HTTPException(status_code=400, detail="Không có confirmed_sections trong session")

    secs = [
        s.model_dump() if hasattr(s, "model_dump") else dict(getattr(s, "__dict__", {}))
        for s in confirmed_sections
    ]

    # Validate 0-based
    try:
        secs = validate_sections_zero_based(secs, nrows=df.shape[0])
    except IndexErrorDetail:
        secs = to_zero_based(secs, nrows=df.shape[0])
        secs = validate_sections_zero_based(secs, nrows=df.shape[0])

    # Fingerprint (template key) - ưu tiên v2
    fp: Optional[str] = None
    try:
        fp = get_fingerprint_v2(df, sheet_name=payload.sheet_name)
    except Exception:
        try:
            fp = get_fingerprint(df, sheet_name=payload.sheet_name)
        except TypeError:
            fp = get_fingerprint(df)

    if not fp:
        raise HTTPException(status_code=500, detail="Không tạo được fingerprint")

    overrides = _build_overrides_from_sections(secs)

    rule_doc = {
        "version": int(time.time()),
        "updated_at": int(time.time()),
        "template_name": payload.template_name or "Template",
        "overrides": overrides,
    }

    # Save as GLOBAL template owner
    save_rule_for_fingerprint(fp, rule_doc, user_id="default_user")

    # update session meta (optional)
    data.is_known = True
    data.matched_fingerprint = fp
    data.matched_template_owner = "default_user"
    store.upsert(data)

    return {
        "ok": True,
        "code": "TEMPLATE_SAVED",
        "data": {
            "fingerprint": fp,
            "template_owner": "default_user",
            "template_name": rule_doc["template_name"],
            "rule_version": rule_doc["version"],
        },
    }

@router.post("/save_template")
def save_template_for_actor(payload: SaveTemplateReq = Body(...), actor: Actor = Depends(get_actor)):
    """
    Cho phép mọi tài khoản đã đăng nhập lưu template
    nhưng chỉ trên session của chính mình.
    """
    data = store.get(payload.session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    expected_owner = _owner_key_from_actor(actor)
    if getattr(data, "owner_key", None) != expected_owner:
        raise HTTPException(status_code=403, detail="Bạn không phải owner của session này")

    if not getattr(data, "confirmed", False):
        raise HTTPException(status_code=400, detail="Session chưa confirm_sections")

    df = _read_df(data.file_path, sheet_name=payload.sheet_name)
    if df.shape[0] == 0:
        raise HTTPException(status_code=400, detail="File/sheet rỗng")

    confirmed_sections = getattr(data, "confirmed_sections", None) or []
    if not confirmed_sections:
        raise HTTPException(status_code=400, detail="Không có confirmed_sections trong session")

    secs = [
        s.model_dump() if hasattr(s, "model_dump") else dict(getattr(s, "__dict__", {}))
        for s in confirmed_sections
    ]

    try:
        secs = validate_sections_zero_based(secs, nrows=df.shape[0])
    except IndexErrorDetail:
        secs = to_zero_based(secs, nrows=df.shape[0])
        secs = validate_sections_zero_based(secs, nrows=df.shape[0])

    fp: Optional[str] = None
    try:
        fp = get_fingerprint_v2(df, sheet_name=payload.sheet_name)
    except Exception:
        try:
            fp = get_fingerprint(df, sheet_name=payload.sheet_name)
        except TypeError:
            fp = get_fingerprint(df)

    if not fp:
        raise HTTPException(status_code=500, detail="Không tạo được fingerprint")

    overrides = _build_overrides_from_sections(secs)

    rule_doc = {
        "version": int(time.time()),
        "updated_at": int(time.time()),
        "template_name": payload.template_name or "Template",
        "overrides": overrides,
    }

    # Tạm thời vẫn lưu global để không phải sửa luồng extractor hiện tại
    save_rule_for_fingerprint(fp, rule_doc, user_id="default_user")

    data.is_known = True
    data.matched_fingerprint = fp
    data.matched_template_owner = "default_user"
    store.upsert(data)

    return {
        "ok": True,
        "code": "TEMPLATE_SAVED",
        "data": {
            "fingerprint": fp,
            "template_owner": "default_user",
            "template_name": rule_doc["template_name"],
            "rule_version": rule_doc["version"],
        },
    }
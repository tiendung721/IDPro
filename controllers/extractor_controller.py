from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Optional, List, Tuple, Dict
import os, shutil, uuid
import pandas as pd
import glob
import hashlib

from common.auth import get_actor, Actor 
from common.roles import Role

from data_processing.section_detector import detect_sections_auto
from data_processing.rule_memory import get_rule_for_fingerprint, get_fingerprint, get_fingerprint_v2
from data_processing.rule_based_extractor import extract_sections_with_rule

from common.session_store import SessionStore
from common.models import SessionData, Section
from data_processing.validators import to_zero_based, validate_sections_zero_based, IndexErrorDetail

router = APIRouter()
UPLOAD_DIR = "uploaded_files"
RULE_DIR = "rule_memory"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RULE_DIR, exist_ok=True)

store = SessionStore.get_instance()


def _calc_file_hash(path: str, algo: str = "sha256", chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _read_df(file_path: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """
    Luôn trả về đúng 1 DataFrame.
    - CSV -> DataFrame (header=None)
    - Excel:
        + Nếu sheet_name truyền vào: đọc đúng sheet đó.
        + Nếu không truyền: đọc sheet đầu tiên.
    """
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
            resolved_sheet_name = 0  # fallback

    return pd.read_excel(file_path, sheet_name=resolved_sheet_name, header=None)


def _idx_from_sid(value: str) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip().upper()
    if s.startswith("S"):
        s = s[1:]
    try:
        idx = int(s) - 1
        return idx if idx >= 0 else None
    except Exception:
        return None


def apply_overrides_to_sections(sections: List[Dict], overrides: Dict) -> List[Dict]:
    """Áp overrides **0-based** lên danh sách sections đã autodetect."""
    if not overrides:
        return sections

    # Global header override
    if overrides.get("header_row") is not None:
        try:
            hdr = int(overrides["header_row"])
            for s in sections:
                s["header_row"] = hdr
        except Exception:
            pass

    # Per-section overrides
    for ent in (overrides.get("sections", []) or []):
        sel = ent.get("selector", {}) or {}
        fields = ent.get("fields", {}) or {}
        by = sel.get("by")
        val = sel.get("value")

        candidates: List[int] = []
        if by == "index":
            idx = _idx_from_sid(val)
            if idx is not None and 0 <= idx < len(sections):
                candidates = [idx]
        elif by == "label":
            for i, s in enumerate(sections):
                if str(s.get("label", "")).strip() == str(val).strip():
                    candidates.append(i)
        else:
            continue

        for i in candidates:
            for k, v in fields.items():
                if k in ("start_row", "end_row", "header_row"):
                    try:
                        v = int(v)
                    except Exception:
                        pass
                sections[i][k] = v

    return sections


def _fingerprints_for(df: pd.DataFrame, sheet_name: Optional[str]) -> List[str]:
    """
    Ưu tiên fingerprint V2 (nội dung sample) để match template chính xác.
    Fallback fingerprint V1 để tương thích rule cũ.
    """
    fps: List[str] = []

    # V2 with sheet
    try:
        fps.append(get_fingerprint_v2(df, sheet_name=sheet_name))
    except Exception:
        pass

    # V2 no sheet
    try:
        fps.append(get_fingerprint_v2(df, sheet_name=None))
    except Exception:
        pass

    # V1 with sheet (backward)
    try:
        fps.append(get_fingerprint(df, sheet_name=sheet_name))
    except TypeError:
        pass
    except Exception:
        pass

    # V1 no sheet
    try:
        fps.append(get_fingerprint(df))
    except Exception:
        pass

    seen, out = set(), []
    for fp in fps:
        if fp and fp not in seen:
            seen.add(fp)
            out.append(fp)
    return out


def _find_rule_for(
    df: pd.DataFrame,
    sheet_name: Optional[str],
    user_id: str,
) -> Tuple[Optional[dict], Optional[str], Optional[str], Optional[str]]:
    """
    Tìm rule theo thứ tự: (user_id, fp_with_sheet) -> (user_id, fp_no_sheet) -> (default_user, ...)
    Trả về: (rule, matched_fp, matched_uid, rule_kind)
    """
    fp_list = _fingerprints_for(df, sheet_name)

    # Try user_id first
    for fp in fp_list:
        try:
            rule = get_rule_for_fingerprint(fp, user_id=user_id)
            if rule:
                kind = "overrides" if (isinstance(rule, dict) and "overrides" in rule) else "structured"
                return rule, fp, user_id, kind
        except Exception:
            pass

    # Fallback to default_user
    if user_id != "default_user":
        for fp in fp_list:
            try:
                rule = get_rule_for_fingerprint(fp, user_id="default_user")
                if rule:
                    kind = "overrides" if (isinstance(rule, dict) and "overrides" in rule) else "structured"
                    return rule, fp, "default_user", kind
            except Exception:
                pass

    return None, None, None, None


def _list_rule_files_for_user(user_id: str) -> List[str]:
    """Liệt kê các file rule hiện có cho user (debug)."""
    pattern = os.path.join(RULE_DIR, f"{user_id}_*.json")
    return [os.path.basename(p) for p in glob.glob(pattern)]


def _owner_key_from_actor(actor: Actor) -> str:
    """JWT-only ownership.

    - admin => admin:<admin_id>
    - user  => user:<user_id>
    """
    kind = actor.get("kind")
    if kind == "admin" and actor.get("id"):
        return f"admin:{actor['id']}"
    if kind == "user" and actor.get("id"):
        return f"user:{actor['id']}"
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    actor: Actor = Depends(get_actor),
):
    """
    User allowed (JWT role USER) - includes guest JWT (/auth/guest)
    Admin allowed (JWT role ADMIN)
    Ownership check (switch-mode):
    - admin: expected owner_key = admin:<admin_id>
    - user : expected owner_key = user:<user_id>
    """

    owner_key = _owner_key_from_actor(actor)

    # map to informational fields (legacy/UI)
    user_id = actor.get("id")
    role = actor.get("role") or (Role.ADMIN.value if actor.get("kind") == "admin" else Role.USER.value)

    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".xlsx", ".xls", ".csv"]:
        raise HTTPException(status_code=400, detail="Chỉ nhận .xlsx/.xls/.csv")

    session_id = str(uuid.uuid4())
    saved_path = os.path.join(UPLOAD_DIR, f"{session_id}{ext}")

    # 1) save file
    try:
        with open(saved_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi lưu file: {e}")

    # 2) compute file_hash
    try:
        file_hash = _calc_file_hash(saved_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi tính file_hash: {e}")

    # 3) upsert session
    store.upsert(
    SessionData(
        session_id=session_id,
        user_id=user_id,
        owner_key=owner_key,
        role=role,
        file_path=saved_path,
        file_hash=file_hash,

        normalized_xlsx_path=None,
        openai_file_id=None,
        qa_prev_response_id=None,
        final_prev_response_id=None,

        confirmed=False,
        confirming=False,
        )
    )


    return {
        "ok": True,
        "code": "UPLOAD_OK",
        "data": {"session_id": session_id, "file_path": saved_path, "file_hash": file_hash},
    }


@router.post("/preview")
def preview(
    session_id: str = Form(...),
    sheet_name: Optional[str] = Form(None),
    actor: Actor = Depends(get_actor),
):

    """
    Public user allowed (no JWT) via X-ANON-ID
    Admin allowed (JWT)
    Ownership check (switch-mode):
       - admin: expected owner_key = admin:<admin_id>
       - user : expected owner_key = user:<user_id>
       - anon : expected owner_key = anon:<anon_id>
    """
    data = store.get(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    expected_owner = _owner_key_from_actor(actor)

    # ownership check (compare to SessionData.owner_key)
    if getattr(data, "owner_key", None) != expected_owner:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập session này")

    df = _read_df(data.file_path, sheet_name=sheet_name)
    if df.shape[0] == 0:
        raise HTTPException(status_code=400, detail="File/sheet rỗng")

    # ALWAYS match template via default_user (admin-owned template)
    rule, matched_fp, matched_uid, rule_kind = _find_rule_for(df, sheet_name, "default_user")

    used_rule = False
    try:
        if rule:
            if rule_kind == "overrides":
                base_sections = detect_sections_auto(df)  # 0-based
                before = [dict(x) for x in base_sections]
                sections = apply_overrides_to_sections(base_sections, rule.get("overrides", {}))
                used_rule = True
                overrides_effective = (sections != before)
            else:
                # structured rule
                if isinstance(rule, dict) and isinstance(rule.get("sections"), list) and rule.get("type") == "structured":
                    sections = rule["sections"]
                    used_rule = len(sections) > 0
                    overrides_effective = None
                else:
                    sections = extract_sections_with_rule(df, rule) or []
                    used_rule = len(sections) > 0
                    overrides_effective = None
        else:
            sections = detect_sections_auto(df)
            overrides_effective = None
    except Exception:
        sections = detect_sections_auto(df)
        used_rule = False
        overrides_effective = None

    # validate 0-based
    try:
        sections = to_zero_based(sections, nrows=df.shape[0])
        sections = validate_sections_zero_based(sections, nrows=df.shape[0])
    except IndexErrorDetail as ie:
        return {"ok": False, "code": ie.code, "error": str(ie)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sections không hợp lệ: {e}")

    # persist session
    data.auto_sections = [Section(**s) for s in sections]
    data.used_rule = bool(used_rule)

    # fingerprints + match info
    try:
        fps = _fingerprints_for(df, sheet_name)
        data.fingerprint = matched_fp or (fps[-1] if fps else None)
    except Exception:
        pass

    data.is_known = bool(rule)
    data.matched_fingerprint = matched_fp
    data.matched_template_owner = matched_uid  # expected "default_user"
    store.upsert(data)

    rule_files_for_user = _list_rule_files_for_user(matched_uid or "default_user")
    source = "rule" if used_rule else "autodetect"

    return {
        "ok": True,
        "code": "PREVIEW_OK",
        "data": {
            "session_id": session_id,
            "is_known": bool(rule),
            "fingerprints_tried": _fingerprints_for(df, sheet_name),
            "matched_fingerprint": matched_fp,
            "matched_user_id": matched_uid,
            "rule_kind": rule_kind,
            "rule_files_for_user": rule_files_for_user,
            "used_rule": used_rule,
            "sections_source": source,
            "index_base": "zero",
            "sections": sections,
            "nrows": int(df.shape[0]),
            "overrides_effective": (overrides_effective if rule_kind == "overrides" else None),
        },
    }

# streamlit_app/src/api.py
import os
import mimetypes
import httpx
from typing import Optional, List, Dict, Any, Union
from dotenv import load_dotenv

load_dotenv()
BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# -----------------------
# Auth / identity headers
# -----------------------
_TOKEN: str = ""

def set_token(token: str):
    """Set JWT token for admin/user mode."""
    global _TOKEN
    _TOKEN = (token or "").strip()

def _headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    h: Dict[str, str] = {"Accept": "application/json"}
    if _TOKEN:
        h["Authorization"] = f"Bearer {_TOKEN}"
    if extra:
        h.update(extra)
    return h


# -----------------------
# HTTP helpers (one place)
# -----------------------
DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

def _extract_error_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            if "detail" in data:
                return str(data["detail"])
            if "error" in data:
                return str(data["error"])
            if "message" in data:
                return str(data["message"])
            if data.get("ok") is False and data.get("error"):
                return str(data.get("error"))
    except Exception:
        pass

    txt = (resp.text or "").strip()
    if txt:
        return txt[:800]
    return f"HTTP {resp.status_code}"

def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    files: Any = None,
    timeout: Optional[Union[float, httpx.Timeout]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    url = f"{BASE}{path}"
    t = timeout if timeout is not None else DEFAULT_TIMEOUT

    try:
        with httpx.Client(timeout=t, headers=_headers(extra_headers)) as c:
            r = c.request(method, url, params=params, json=json, data=data, files=files)
    except httpx.TimeoutException as e:
        return {"ok": False, "code": "TIMEOUT", "error": f"Timeout calling {path}: {e}"}
    except httpx.RequestError as e:
        return {"ok": False, "code": "REQUEST_ERROR", "error": f"Network error calling {path}: {e}"}

    if r.status_code >= 400:
        return {"ok": False, "code": "HTTP_ERROR", "status_code": r.status_code, "error": _extract_error_message(r)}

    try:
        parsed = r.json()
        if isinstance(parsed, dict):
            parsed.setdefault("ok", True)
        return parsed if isinstance(parsed, dict) else {"ok": True, "code": "OK", "data": parsed}
    except Exception:
        return {"ok": True, "code": "NO_JSON", "data": None}

def _get(path: str, *, params: Optional[Dict[str, Any]] = None, timeout=None) -> Dict[str, Any]:
    return _request("GET", path, params=params, timeout=timeout)

def _post(path: str, *, json: Optional[Dict[str, Any]] = None, data=None, files=None, params=None, timeout=None) -> Dict[str, Any]:
    return _request("POST", path, params=params, json=json, data=data, files=files, timeout=timeout)

def _put(path: str, *, json: Optional[Dict[str, Any]] = None, data=None, timeout=None) -> Dict[str, Any]:
    return _request("PUT", path, json=json, data=data, timeout=timeout)

def _delete(path: str, *, params=None, timeout=None) -> Dict[str, Any]:
    return _request("DELETE", path, params=params, timeout=timeout)


# ---------- Auth ----------
def login(email: str, password: str) -> Dict[str, Any]:
    return _post("/auth/login", json={"email": email, "password": password})

def me() -> Dict[str, Any]:
    return _get("/auth/me")


# ---------- Core ----------
def upload_file(file, sheet_name: Optional[str] = None) -> Dict[str, Any]:
    filename = getattr(file, "name", "upload.bin")
    data_bytes = file.getvalue()
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    files = {"file": (filename, data_bytes, content_type)}
    form: Dict[str, Any] = {}
    if sheet_name:
        form["sheet_name"] = sheet_name
    return _post("/upload", files=files, data=form)

def preview(session_id: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
    form: Dict[str, Any] = {"session_id": session_id, "id": session_id}
    if sheet_name:
        form["sheet_name"] = sheet_name
    return _post("/preview", data=form)

# FE gọi /confirm_sections nhưng UI hiển thị là Finalize (confirm cấu trúc)
def finalize_sections(session_id: str, sections: List[Dict[str, Any]], sheet_name: Optional[str] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {"session_id": session_id, "id": session_id, "sections": sections}
    if sheet_name:
        body["sheet_name"] = sheet_name
    # confirm có thể chạy lâu → tăng timeout
    return _post("/confirm_sections", json=body, timeout=httpx.Timeout(180.0, connect=10.0))

def admin_save_template(session_id: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {"session_id": session_id}
    if sheet_name:
        body["sheet_name"] = sheet_name
    return _post("/admin/save_template", json=body)


def run_final_spec(session_id: str, reset: bool = False) -> Dict[str, Any]:
    return _post(
        "/final_spec",
        json={"session_id": session_id, "reset": bool(reset)},
        timeout=httpx.Timeout(connect=10.0, read=600.0, write=600.0, pool=600.0),
    )

def health() -> Dict[str, Any]:
    return _get("/health")


# ---------- Sections CRUD ----------
def sections_get(session_id: str) -> Dict[str, Any]:
    return _get(f"/sessions/{session_id}/sections")

def sections_replace(session_id: str, sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _put(f"/sessions/{session_id}/sections", json={"sections": sections})

def sections_add(session_id: str, section: Dict[str, Any]) -> Dict[str, Any]:
    return _post(f"/sessions/{session_id}/sections", json=section)

def sections_delete(session_id: str, index: int) -> Dict[str, Any]:
    return _delete(f"/sessions/{session_id}/sections/{index}")


# ---------- QA (CI) ----------
def qa(session_id: str, question: str, reset_chat: bool = False, base_url: str | None = None) -> Dict[str, Any]:
    url_base = (base_url or BASE).rstrip("/")
    payload = {"session_id": session_id, "question": question, "reset_chat": reset_chat}

    try:
        with httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0), headers=_headers()) as c:
            r = c.post(f"{url_base}/qa", json=payload)
    except httpx.TimeoutException as e:
        return {"ok": False, "code": "TIMEOUT", "error": f"Timeout calling /qa: {e}"}
    except httpx.RequestError as e:
        return {"ok": False, "code": "REQUEST_ERROR", "error": f"Network error calling /qa: {e}"}

    if r.status_code >= 400:
        return {"ok": False, "code": "HTTP_ERROR", "status_code": r.status_code, "error": _extract_error_message(r)}

    try:
        parsed = r.json()
        if isinstance(parsed, dict):
            parsed.setdefault("ok", True)
        return parsed if isinstance(parsed, dict) else {"ok": True, "code": "OK", "data": parsed}
    except Exception:
        return {"ok": False, "code": "BAD_JSON", "error": (r.text or "")[:800]}


# ---------- Admin/User ----------
def user_login(username: str):
    return _post("/auth/user_login", json={"username": username})

def admin_list_users(q: str = "", role: str = "ALL", active: str = "ALL"):
    return _get("/admin/users", params={"q": q, "role": role, "active": active})

def admin_create_user(username=None, role="USER", is_active=True, email=None, password=None):
    return _post("/admin/users", json={
        "username": username,
        "role": role,
        "is_active": bool(is_active),
        "email": email,
        "password": password,
    })

def admin_update_user(user_id: str, role: str | None = None, is_active: bool | None = None):
    payload = {}
    if role is not None:
        payload["role"] = role
    if is_active is not None:
        payload["is_active"] = is_active
    return _request("PATCH", f"/admin/users/{user_id}", json=payload)

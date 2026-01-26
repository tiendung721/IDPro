from __future__ import annotations
from typing import Optional, TypedDict, Literal

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from common.security import decode_token
from common.roles import Role
from data_processing.user_store import UserStore

bearer_required = HTTPBearer(auto_error=True)
bearer_optional = HTTPBearer(auto_error=False)


class Actor(TypedDict, total=False):
    """Tác nhân gọi API (JWT-only).

    kind:
      - "user": JWT hợp lệ, role != ADMIN
      - "admin": JWT hợp lệ, role == ADMIN
    """
    kind: Literal["user", "admin"]

    id: str
    email: str
    role: str


def _load_user_from_token(token: str) -> Optional[dict]:
    """Decode token -> load user from store.

    Return dict: {"id","email","role"} or None if invalid/not found.

    NOTE:
    - Với user guest (/auth/guest), user_id sẽ không tồn tại trong UserStore.
      => Trả về user tối thiểu dựa trên token payload.
    """
    try:
        payload = decode_token(token)
    except Exception:
        return None

    user_id = payload.get("sub")
    role = payload.get("role")
    if not user_id or not role:
        return None

    role = str(role).upper()

    # Guest user: không có trong UserStore => cho qua
    # (Guest token do backend cấp, vẫn là JWT hợp lệ)
    store = UserStore()
    user = store.get_by_id(user_id)
    if not user:
        return {"id": str(user_id), "email": "", "role": role}

    return {"id": str(user["id"]), "email": user.get("email", ""), "role": str(user.get("role", role)).upper()}


# ========= Existing strict auth (kept for backward compatibility) =========
def get_current_user(cred: HTTPAuthorizationCredentials = Depends(bearer_required)):
    token = cred.credentials
    user = _load_user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def require_admin(user=Depends(get_current_user)):
    if (user.get("role") or "").upper() != Role.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ========= Switch-mode auth (JWT-only now) =========
def get_actor(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer_optional),
) -> Actor:
    """
        - role == ADMIN -> actor.kind = "admin"
        - role != ADMIN -> actor.kind = "user"
    """
    if not cred or not cred.credentials:
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    user = _load_user_from_token(cred.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    role = (user.get("role") or "").upper()
    kind: Literal["user", "admin"] = "admin" if role == Role.ADMIN.value else "user"
    return {"kind": kind, "id": str(user["id"]), "email": user.get("email", ""), "role": role}


def require_admin_actor(actor: Actor = Depends(get_actor)) -> Actor:
    """Admin-only for switch-mode routes."""
    if actor.get("kind") != "admin" or (actor.get("role") or "").upper() != Role.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin only")
    return actor

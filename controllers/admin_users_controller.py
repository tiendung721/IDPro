from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid

from data_processing.user_store import UserStore
from common.auth import require_admin 
import common.security as security

router = APIRouter(prefix="/admin", tags=["admin-users"])

class CreateUserReq(BaseModel):
    role: str = "USER"
    is_active: bool = True

    # USER quick
    username: Optional[str] = None

    # ADMIN
    email: Optional[str] = None
    password: Optional[str] = None


class UpdateUserReq(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/users")
def list_users(q: str = "", role: str = "ALL", active: str = "ALL", _=Depends(require_admin)):
    store = UserStore()
    users = store.list_users(q=q, role=role, active=active)
    return {"ok": True, "data": {"users": users}}

@router.post("/users")
def create_user(payload: CreateUserReq, _=Depends(require_admin)):
    store = UserStore()
    role = (payload.role or "USER").upper().strip()
    user_id = str(uuid.uuid4())

    # =========================
    # ADMIN: email + password
    # =========================
    if role == "ADMIN":
        email = (payload.email or "").strip()
        password = (payload.password or "").strip()

        if not email or not password:
            raise HTTPException(status_code=400, detail="ADMIN requires email and password")

        if store.get_by_email(email):
            raise HTTPException(status_code=409, detail="email_exists")

        try:
            password_hash = security.hash_password(password)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        store.create_admin(
            user_id=user_id,
            email=email,
            password_hash=password_hash,
            role="ADMIN",
        )

        u = store.get_by_id(user_id)
        return {"ok": True, "data": {"user": u}}

    # =========================
    # USER: username-only
    # =========================
    username = (payload.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username_required")

    if store.get_by_username(username):
        raise HTTPException(status_code=409, detail="username_exists")

    store.create_user_username_only(
        user_id=user_id,
        username=username,
        role="USER",
        is_active=(1 if payload.is_active else 0),
    )

    u = store.get_by_id(user_id)
    return {"ok": True, "data": {"user": u}}


@router.patch("/users/{user_id}")
def update_user(user_id: str, payload: UpdateUserReq, _=Depends(require_admin)):
    store = UserStore()
    u0 = store.get_by_id(user_id)
    if not u0:
        raise HTTPException(status_code=404, detail="user_not_found")

    store.update_user(
        user_id,
        role=(payload.role.upper() if payload.role else None),
        is_active=(1 if payload.is_active is True else 0) if payload.is_active is not None else None,
    )
    u = store.get_by_id(user_id)
    return {"ok": True, "data": {"user": u}}

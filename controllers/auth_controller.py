import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from common.roles import Role

from data_processing.user_store import UserStore

import common.security as security

router = APIRouter()

class LoginIn(BaseModel):
    email: EmailStr
    password: str

@router.post("/auth/login")
def login(payload: LoginIn):
    """
    Login chuẩn bằng email/password.
    - Admin: dùng endpoint này như hiện tại.
    - User có mật khẩu cũng có thể login ở đây nếu user_store có.
    """
    # Import lazy để tránh circular import / lỗi import-time
    
    store = UserStore()
    user = store.get_by_email(payload.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if (user.get("role") or "").upper() != Role.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin access only")

    if not security.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    role = (user.get("role") or Role.USER.value).upper()

    token = security.create_access_token({"sub": user["id"], "role": role})
    return {
        "ok": True,
        "code": "LOGIN_OK",
        "data": {
            "access_token": token,
            "token_type": "bearer",
            "role": role,
            "user_id": user["id"],
        },
    }


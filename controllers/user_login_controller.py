from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid

from data_processing.user_store import UserStore
from common.security import create_access_token

router = APIRouter()

class UsernameLoginRequest(BaseModel):
    username: str

@router.post("/auth/user_login")
def user_login(payload: UsernameLoginRequest):
    username = (payload.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username_required")

    store = UserStore()
    u = store.get_by_username(username)
    if not u:
        raise HTTPException(status_code=404, detail="user_not_found")
    if int(u.get("is_active") or 0) != 1:
        raise HTTPException(status_code=403, detail="user_inactive")

    token = create_access_token({
        "sub": u["id"],
        "username": u["username"],
        "role": u["role"],
        "kind": "USER",
    })
    store.touch_login(u["id"])

    return {"ok": True, "data": {"access_token": token, "user": u}}

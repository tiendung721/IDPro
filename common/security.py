import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
from jose import jwt, JWTError
BCRYPT_MAX_PASSWORD_BYTES = 72

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_SUPER_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "720"))

def _normalize_password(password: str) -> str:
    return (password or "").strip()


def _password_to_bytes(password: str) -> bytes:
    return _normalize_password(password).encode("utf-8")


def _password_exceeds_bcrypt_limit(password_bytes: bytes) -> bool:
    return len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES


def hash_password(password: str) -> str:
    password_bytes = _password_to_bytes(password)
    if _password_exceeds_bcrypt_limit(password_bytes):
        raise ValueError(f"Password too long for bcrypt (max {BCRYPT_MAX_PASSWORD_BYTES} bytes).")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = _password_to_bytes(password)
    password_hash = (password_hash or "").strip()

    if not password_hash:
        return False

    # bcrypt only supports 72 input bytes; longer values should fail auth,
    # not crash the API with a 500.
    if _password_exceeds_bcrypt_limit(password_bytes):
        return False

    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False

def create_access_token(payload: Dict[str, Any], expires_minutes: Optional[int] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode = dict(payload)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise ValueError("Invalid token") from e

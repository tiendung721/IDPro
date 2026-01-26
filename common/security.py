import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import jwt, JWTError
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_SUPER_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "720"))

def hash_password(password: str) -> str:
    password = password.strip()  
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password too long for bcrypt (max 72 bytes).")
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

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

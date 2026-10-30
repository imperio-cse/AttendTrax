# =============================================================================
# auth.py  –  Password hashing + JWT token logic
# =============================================================================
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from config import get_settings


def hash_password(plain: str) -> str:
    pwd_bytes = plain.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    cfg = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=cfg.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, cfg.SECRET_KEY, algorithm=cfg.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    cfg = get_settings()
    try:
        return jwt.decode(token, cfg.SECRET_KEY, algorithms=[cfg.ALGORITHM])
    except JWTError:
        return None


def get_hardcoded_user(username: str) -> Optional[dict]:
    cfg = get_settings()
    u = username.strip().lower()
    if u == cfg.ADMIN_USERNAME.strip().lower():
        return {
            "user_id": 1,
            "name": cfg.ADMIN_NAME,
            "username": cfg.ADMIN_USERNAME,
            "role": "SUPER_ADMIN",
            "department_id": None,
            "class_id": "",
        }
    if u == "principal":
        return {
            "user_id": 2,
            "name": "Dr. Devaraju (Principal)",
            "username": "principal",
            "role": "SUPER_ADMIN",
            "department_id": None,
            "class_id": "",
        }
    if u == "viceprincipal":
        return {
            "user_id": 3,
            "name": "Dr. Basker (Vice Principal)",
            "username": "viceprincipal",
            "role": "SUPER_ADMIN",
            "department_id": None,
            "class_id": "",
        }
    return None

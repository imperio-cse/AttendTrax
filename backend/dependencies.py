# =============================================================================
# dependencies.py  –  FastAPI dependency injection helpers
# Supports Enterprise RBAC (SQL Database + Google Sheets fallback)
# =============================================================================
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from auth import decode_token, get_hardcoded_user
from config import get_settings
from database import get_session_factory
from models import User, Student
from sheets import get_user_by_username, get_student_by_regnum

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad token payload.")

    cfg = get_settings()

    # ── 1. Hardcoded Enterprise Accounts (Principal, VP, HODs, Admin) ────────
    hardcoded = get_hardcoded_user(username)
    if hardcoded:
        return {
            "UserID": str(hardcoded["user_id"]),
            "user_id": hardcoded["user_id"],
            "Name": hardcoded["name"],
            "full_name": hardcoded["name"],
            "Username": hardcoded["username"],
            "sub": hardcoded["username"],
            "PasswordHash": "",
            "Role": hardcoded["role"],
            "role": hardcoded["role"],
            "department_id": hardcoded["department_id"],
            "ClassID": hardcoded.get("class_id", ""),
            "class_id": hardcoded.get("class_id", ""),
        }

    # ── 2. Primary: Look up in Relational SQL Database ───────────────────────
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(User).where(User.username == username)
            res = await session.execute(stmt)
            user_obj = res.scalar_one_or_none()
            if user_obj:
                cls_id = ""
                if user_obj.role == "STUDENT":
                    s_stmt = select(Student.class_id).where(Student.user_id == user_obj.id)
                    s_res = await session.execute(s_stmt)
                    c_id = s_res.scalar_one_or_none()
                    if c_id:
                        cls_id = str(c_id)

                return {
                    "UserID": str(user_obj.id),
                    "user_id": user_obj.id,
                    "Name": user_obj.full_name,
                    "full_name": user_obj.full_name,
                    "Username": user_obj.username,
                    "sub": user_obj.username,
                    "Role": user_obj.role.upper(),
                    "role": user_obj.role.upper(),
                    "department_id": user_obj.department_id,
                    "ClassID": cls_id,
                    "class_id": cls_id,
                }
    except Exception:
        pass

    # ── 3. Fallback: Legacy Google Sheets lookup ─────────────────────────────
    user = get_user_by_username(username)
    if not user:
        student = get_student_by_regnum(username)
        if student:
            reg_val = str(student.get("RegNo", ""))
            return {
                "UserID": reg_val,
                "user_id": reg_val,
                "Name": str(student.get("Name", "")),
                "full_name": str(student.get("Name", "")),
                "Username": reg_val,
                "sub": reg_val,
                "Role": "STUDENT",
                "role": "STUDENT",
                "ClassID": str(student.get("ClassID", "")),
                "class_id": str(student.get("ClassID", "")),
                "PasswordHash": "",
                "department_id": 1,
            }
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    role_val = str(user.get("Role", "")).upper()
    user_id_val = str(user.get("UserID", ""))
    return {
        **user,
        "user_id": user_id_val,
        "UserID": user_id_val,
        "role": role_val,
        "Role": role_val,
        "sub": user.get("Username", username),
        "department_id": 1,
    }


def require_role(*roles: str):
    async def checker(current_user: dict = Depends(get_current_user)):
        user_role = (current_user.get("role") or current_user.get("Role") or "").upper()
        allowed = [r.upper() for r in roles]

        # Hierarchy: SUPER_ADMIN and ADMIN have access to all admin/faculty/warden management endpoints
        if user_role in ["SUPER_ADMIN", "ADMIN"]:
            if any(r in ["SUPER_ADMIN", "ADMIN", "DEPT_ADMIN", "CLASS_INCHARGE", "FACULTY", "WARDEN"] for r in allowed):
                return current_user

        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access restricted to roles: {', '.join(roles)}. Current role: {user_role}",
            )
        return current_user
    return checker

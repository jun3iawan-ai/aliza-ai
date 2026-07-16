from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.database import conn, cursor
from api.passwords import hash_password, password_needs_upgrade, verify_password
from api.security import AuthenticatedUser, create_access_token, require_admin

router = APIRouter(prefix="/auth", tags=["Auth"])

# =========================
# USER MODEL
# =========================

class User(BaseModel):
    username: str
    password: str



# =========================
# REGISTER
# =========================

@router.post("/register")
def register(
    user: User,
    _current_user: Annotated[AuthenticatedUser, Depends(require_admin)],
):

    # cek username sudah ada
    cursor.execute(
        "SELECT id FROM users WHERE username=%s",
        (user.username,)
    )

    existing = cursor.fetchone()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Username already exists"
        )

    password_hash = hash_password(user.password)

    cursor.execute(
        "INSERT INTO users (username,password) VALUES (%s,%s)",
        (user.username, password_hash)
    )

    conn.commit()

    return {
        "status": "success",
        "message": "User created"
    }


# =========================
# LOGIN
# =========================

@router.post("/login")
def login(user: User):
    cursor.execute(
        "SELECT id, username, role, password FROM users WHERE username=%s",
        (user.username,)
    )

    result = cursor.fetchone()

    if not result or not verify_password(user.password, result.get("password")):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    user_id = result["id"]

    if password_needs_upgrade(result["password"]):
        upgraded_hash = hash_password(user.password)
        try:
            cursor.execute(
                "UPDATE users SET password=%s WHERE id=%s",
                (upgraded_hash, user_id),
            )
            conn.commit()
        except Exception:
            rollback = getattr(conn, "rollback", None)
            if callable(rollback):
                try:
                    rollback()
                except Exception:
                    pass
            raise

    token = create_access_token(
        user_id=user_id,
        username=result["username"],
        role=result["role"],
    )

    return {
        "status": "success",
        "token": token,
        "user_id": user_id
    }

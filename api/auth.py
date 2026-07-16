from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.database import conn, cursor
from api.security import AuthenticatedUser, create_access_token, require_admin
import hashlib

router = APIRouter(prefix="/auth", tags=["Auth"])

# =========================
# USER MODEL
# =========================

class User(BaseModel):
    username: str
    password: str


# =========================
# HASH PASSWORD
# =========================

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()


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

    password_hash = hash_password(user.password)

    cursor.execute(
        "SELECT id, username, role FROM users WHERE username=%s AND password=%s",
        (user.username, password_hash)
    )

    result = cursor.fetchone()

    if not result:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    user_id = result["id"]

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

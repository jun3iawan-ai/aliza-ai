import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from core.database import conn, cursor
from api.passwords import hash_password, password_needs_upgrade, verify_password
from api.rate_limit import RateLimiter
from api.security import AuthenticatedUser, create_access_token, require_admin

router = APIRouter(prefix="/auth", tags=["Auth"])

# =========================
# USER MODEL
# =========================

class AuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value):
        return value.strip() if isinstance(value, str) else value


class LoginRequest(AuthRequest):
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(AuthRequest):
    password: str = Field(min_length=12, max_length=128)


LOGIN_IP_RATE_LIMITER = RateLimiter(limit=20, window_seconds=60)
LOGIN_USERNAME_RATE_LIMITER = RateLimiter(limit=5, window_seconds=60)
REGISTER_RATE_LIMITER = RateLimiter(limit=10, window_seconds=60)
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _check_login_rate_limit(request: Request | None, username: str) -> None:
    if request is None:
        return
    client_ip = _client_ip(request)
    LOGIN_IP_RATE_LIMITER.check(("login-ip", client_ip))
    LOGIN_USERNAME_RATE_LIMITER.check(
        ("login-username", client_ip, username.strip().casefold())
    )


# =========================
# REGISTER
# =========================

@router.post("/register")
def register(
    user: RegisterRequest,
    _current_user: Annotated[AuthenticatedUser, Depends(require_admin)],
    request: Request = None,
):
    if request is not None:
        REGISTER_RATE_LIMITER.check(("register", _current_user.user_id))

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
def login(user: LoginRequest, request: Request = None):
    _check_login_rate_limit(request, user.username)

    cursor.execute(
        "SELECT id, username, role, password FROM users WHERE username=%s",
        (user.username,)
    )

    result = cursor.fetchone()

    if not result:
        verify_password(user.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    if not verify_password(user.password, result.get("password")):
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

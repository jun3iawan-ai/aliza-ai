import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


JWT_SECRET_ENV_VAR = "JWT_SECRET"
JWT_ALGORITHM = "HS256"
JWT_MIN_SECRET_LENGTH = 32
ACCESS_TOKEN_EXPIRE_HOURS = 24

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: int
    username: str | None
    role: str


def get_jwt_secret() -> str:
    raw_secret = os.getenv(JWT_SECRET_ENV_VAR)
    if raw_secret is None:
        raise RuntimeError("JWT signing secret is not configured.")

    secret = raw_secret.strip()
    if not secret:
        raise RuntimeError("JWT signing secret is not configured.")
    if len(secret) < JWT_MIN_SECRET_LENGTH:
        raise RuntimeError("JWT signing secret must be at least 32 characters.")
    return secret


def validate_jwt_configuration() -> None:
    get_jwt_secret()


def create_access_token(
    *,
    user_id: int,
    username: str | None,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer.")
    if username is not None and (not isinstance(username, str) or not username.strip()):
        raise ValueError("username must be a non-empty string when provided.")
    if not isinstance(role, str) or not role.strip():
        raise ValueError("role must be a non-empty string.")

    now = datetime.now(timezone.utc)
    expires_at = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "role": role,
        "iat": now,
        "exp": expires_at,
    }
    if username is not None:
        payload["username"] = username

    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_access_token(token: str) -> AuthenticatedUser:
    if not isinstance(token, str) or not token.strip():
        raise _unauthorized()

    try:
        payload = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "user_id", "role", "exp"]},
        )
    except jwt.PyJWTError:
        raise _unauthorized() from None

    user_id = payload.get("user_id")
    subject = payload.get("sub")
    username = payload.get("username")
    role = payload.get("role")

    valid_user_id = (
        isinstance(user_id, int)
        and not isinstance(user_id, bool)
        and user_id > 0
        and isinstance(subject, str)
        and subject == str(user_id)
    )
    valid_username = username is None or (
        isinstance(username, str) and bool(username.strip())
    )
    valid_role = isinstance(role, str) and bool(role.strip())
    if not valid_user_id or not valid_username or not valid_role:
        raise _unauthorized()

    return AuthenticatedUser(user_id=user_id, username=username, role=role)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    return decode_access_token(credentials.credentials)


async def require_admin(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )
    return current_user

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.database import conn, cursor
import hashlib
import jwt
import datetime

router = APIRouter()

SECRET_KEY = "ALIZA_SECRET_KEY"
ALGORITHM = "HS256"


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
# CREATE JWT TOKEN
# =========================

def create_token(user_id: int):

    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return token


# =========================
# REGISTER
# =========================

@router.post("/register")
def register(user: User):

    # cek username sudah ada
    cursor.execute(
        "SELECT id FROM users WHERE username=?",
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
        "INSERT INTO users (username,password) VALUES (?,?)",
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
        "SELECT id FROM users WHERE username=? AND password=?",
        (user.username, password_hash)
    )

    result = cursor.fetchone()

    if not result:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    user_id = result[0]

    token = create_token(user_id)

    return {
        "status": "success",
        "token": token,
        "user_id": user_id
    }
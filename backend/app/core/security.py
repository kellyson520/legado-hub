import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


ALGORITHM = "HS256"
ACCESS_AUD = "access"
REFRESH_AUD = "refresh"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(payload: dict) -> str:
    data = payload.copy()
    data["sub"] = str(data["sub"])
    data["aud"] = ACCESS_AUD
    data["exp"] = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(data, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(payload: dict) -> str:
    data = payload.copy()
    data["sub"] = str(data["sub"])
    data["aud"] = REFRESH_AUD
    data["jti"] = secrets.token_hex(16)
    data["exp"] = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(data, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, object]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM], audience=ACCESS_AUD)
    except JWTError:
        return {}


def decode_refresh_token(token: str) -> dict[str, object]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM], audience=REFRESH_AUD)
    except JWTError:
        return {}


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"lh_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, hashed_key: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key), hashed_key)

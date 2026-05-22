from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pydantic import BaseModel

from recipebox.config import settings

password_hasher = PasswordHash.recommended()


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: str | None = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def create_access_token(email: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)  # type: ignore[no-untyped-call]


def decode_access_token(token: str) -> TokenData | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])  # type: ignore[no-untyped-call]
        email: str | None = payload.get("sub")
        return TokenData(email=email)
    except jwt.PyJWTError:
        return None

from datetime import UTC, datetime, timedelta

import jwt
from httpx import AsyncClient

from recipebox.config import settings

# helpers


async def register(client: AsyncClient, email: str = "user@example.com", password: str = "secret") -> None:
    await client.post("/auth/register", json={"email": email, "password": password})


async def login(client: AsyncClient, email: str = "user@example.com", password: str = "secret") -> str:
    response = await client.post("/auth/login", data={"username": email, "password": password})
    return response.json().get("access_token", "")


def expired_token(email: str) -> str:
    payload = {"sub": email, "exp": datetime.now(UTC) - timedelta(minutes=1)}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)  # type: ignore[no-untyped-call]


# --- register ---


class TestRegister:
    async def test_returns_201(self, client: AsyncClient) -> None:
        response = await client.post("/auth/register", json={"email": "a@example.com", "password": "secret"})
        assert response.status_code == 201

    async def test_returns_user_without_password_hash(self, client: AsyncClient) -> None:
        response = await client.post("/auth/register", json={"email": "a@example.com", "password": "secret"})
        data = response.json()
        assert data["email"] == "a@example.com"
        assert "hashed_password" not in data

    async def test_duplicate_email_returns_409(self, client: AsyncClient) -> None:
        await register(client)
        response = await client.post("/auth/register", json={"email": "user@example.com", "password": "other"})
        assert response.status_code == 409

    async def test_invalid_email_format_returns_422(self, client: AsyncClient) -> None:
        response = await client.post("/auth/register", json={"email": "notanemail", "password": "secret"})
        assert response.status_code == 422


# --- login ---


class TestLogin:
    async def test_returns_200_with_token(self, client: AsyncClient) -> None:
        await register(client)
        response = await client.post("/auth/login", data={"username": "user@example.com", "password": "secret"})
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"

    async def test_wrong_password_returns_401(self, client: AsyncClient) -> None:
        await register(client)
        response = await client.post("/auth/login", data={"username": "user@example.com", "password": "wrong"})
        assert response.status_code == 401

    async def test_unregistered_email_returns_401(self, client: AsyncClient) -> None:
        response = await client.post("/auth/login", data={"username": "ghost@example.com", "password": "secret"})
        assert response.status_code == 401


# --- /me ---


class TestMe:
    async def test_returns_200_with_valid_token(self, client: AsyncClient) -> None:
        await register(client)
        token = await login(client)
        response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

    async def test_returns_correct_user(self, client: AsyncClient) -> None:
        await register(client)
        token = await login(client)
        response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.json()["email"] == "user@example.com"

    async def test_no_token_returns_401(self, client: AsyncClient) -> None:
        response = await client.get("/auth/me")
        assert response.status_code == 401

    async def test_invalid_token_returns_401(self, client: AsyncClient) -> None:
        response = await client.get("/auth/me", headers={"Authorization": "Bearer thisisnotatoken"})
        assert response.status_code == 401

    async def test_expired_token_returns_401(self, client: AsyncClient) -> None:
        await register(client)
        token = expired_token("user@example.com")
        response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

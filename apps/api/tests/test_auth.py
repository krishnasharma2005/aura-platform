"""Signup/login flow tests."""

from httpx import AsyncClient


async def test_signup_creates_user_and_returns_tokens(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/signup",
        json={"email": "new@example.com", "password": "hunter2pass", "name": "New User"},
    )
    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_signup_rejects_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "hunter2pass", "name": "Dup"}
    first = await client.post("/api/v1/auth/signup", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/signup", json=payload)
    assert second.status_code == 409
    assert "error" in second.json()


async def test_login_succeeds_with_correct_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "login@example.com", "password": "correcthorse", "name": "Login"},
    )
    response = await client.post("/api/v1/auth/login", json={"email": "login@example.com", "password": "correcthorse"})
    assert response.status_code == 200
    assert "access_token" in response.json()


async def test_login_fails_with_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "wrongpw@example.com", "password": "correcthorse", "name": "WrongPw"},
    )
    response = await client.post("/api/v1/auth/login", json={"email": "wrongpw@example.com", "password": "nope"})
    assert response.status_code == 401
    assert response.json()["error"] == "Incorrect email or password."


async def test_me_requires_authentication(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401

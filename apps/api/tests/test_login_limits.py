"""Slowing down password guessing: the three failure buckets, what clears them,
and what they must never do (reveal which accounts exist, or lock out recovery).

Different callers are simulated with X-Forwarded-For, which the app only honours
when TRUST_PROXY_HEADERS is on — exactly as it would behind a real proxy."""

import pytest
from httpx import AsyncClient

from src.api.v1 import auth as auth_module
from src.core.config import get_settings
from src.identity import login_limits

PASSWORD = "correct-horse-battery"


async def _signup(client: AsyncClient, email: str = "owner@example.com") -> None:
    response = await client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "name": "Owner"})
    assert response.status_code == 201, response.text


async def _login(client: AsyncClient, email: str, password: str, ip: str | None = None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers=headers)


@pytest.fixture
def behind_a_proxy(monkeypatch):
    monkeypatch.setattr(get_settings(), "TRUST_PROXY_HEADERS", True, raising=False)


async def test_five_wrong_passwords_pause_sign_in_even_for_the_right_one(client):
    await _signup(client)

    for _ in range(5):
        assert (await _login(client, "owner@example.com", "wrong-password-here")).status_code == 401
    blocked = await _login(client, "owner@example.com", PASSWORD)  # correct, but too late

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert "Too many sign-in attempts" in blocked.json()["error"]
    assert "Forgot password" in blocked.json()["error"]  # points at the way back in


async def test_the_pause_does_not_reveal_whether_a_guess_was_right(client):
    await _signup(client)
    for _ in range(5):
        await _login(client, "owner@example.com", "wrong-password-here")

    right = await _login(client, "owner@example.com", PASSWORD)
    wrong = await _login(client, "owner@example.com", "another-wrong-one")

    assert (right.status_code, right.json()) == (wrong.status_code, wrong.json())


async def test_a_good_sign_in_resets_the_count(client):
    await _signup(client)
    for _ in range(4):
        await _login(client, "owner@example.com", "wrong-password-here")

    assert (await _login(client, "owner@example.com", PASSWORD)).status_code == 200
    for _ in range(4):  # another four wrong ones are still fine: the count started over
        assert (await _login(client, "owner@example.com", "wrong-password-here")).status_code == 401


async def test_unknown_addresses_are_limited_exactly_like_real_ones(client):
    for _ in range(5):
        assert (await _login(client, "ghost@example.com", "whatever-password")).status_code == 401

    assert (await _login(client, "ghost@example.com", "whatever-password")).status_code == 429


async def test_unknown_addresses_still_cost_a_password_check(client, monkeypatch):
    """So "no such account" can't be told from "wrong password" by how quickly it answers."""
    checks: list[str] = []
    real = auth_module.verify_password
    monkeypatch.setattr(auth_module, "verify_password", lambda plain, hashed: checks.append(plain) or real(plain, hashed))

    await _login(client, "ghost@example.com", "whatever-password")

    assert checks == ["whatever-password"]


async def test_someone_elsewhere_is_not_locked_out_by_one_ips_failures(client, behind_a_proxy):
    await _signup(client)
    for _ in range(5):
        await _login(client, "owner@example.com", "wrong-password-here", ip="203.0.113.7")
    assert (await _login(client, "owner@example.com", PASSWORD, ip="203.0.113.7")).status_code == 429

    elsewhere = await _login(client, "owner@example.com", PASSWORD, ip="198.51.100.9")

    assert elsewhere.status_code == 200


async def test_guessing_one_account_from_many_ips_is_still_caught(client, behind_a_proxy, monkeypatch):
    monkeypatch.setattr(get_settings(), "AUTH_LOGIN_MAX_FAILURES", 2, raising=False)  # per-address cap = 8
    await _signup(client)

    for i in range(8):  # each IP only fails once, so no single IP bucket fills
        assert (await _login(client, "owner@example.com", "wrong-password-here", ip=f"192.0.2.{i + 1}")).status_code == 401
    spread = await _login(client, "owner@example.com", PASSWORD, ip="192.0.2.200")

    assert spread.status_code == 429


async def test_one_ip_trying_many_accounts_is_caught(client, behind_a_proxy, monkeypatch):
    monkeypatch.setattr(get_settings(), "AUTH_LOGIN_MAX_FAILURES", 2, raising=False)  # per-IP cap = 12

    for i in range(12):
        assert (await _login(client, f"person{i}@example.com", "guess-guess-guess", ip="203.0.113.50")).status_code == 401
    spraying = await _login(client, "someone-new@example.com", "guess-guess-guess", ip="203.0.113.50")

    assert spraying.status_code == 429


async def test_the_lockout_never_blocks_asking_for_a_reset_link(client, monkeypatch):
    sent: list[str] = []

    async def _record(to, subject, body):
        sent.append(to)

    monkeypatch.setattr("src.api.v1.auth.send_email_safely", _record)
    await _signup(client)
    for _ in range(5):
        await _login(client, "owner@example.com", "wrong-password-here")
    assert (await _login(client, "owner@example.com", PASSWORD)).status_code == 429

    response = await client.post("/api/v1/auth/forgot-password", json={"email": "owner@example.com"})

    assert response.status_code == 200
    assert sent == ["owner@example.com"]


async def test_if_the_limiter_is_down_people_can_still_sign_in(client, monkeypatch):
    await _signup(client)

    def _redis_is_down():
        raise ConnectionError("redis is down")

    monkeypatch.setattr(login_limits, "get_redis", _redis_is_down)

    assert (await _login(client, "owner@example.com", PASSWORD)).status_code == 200
    assert (await _login(client, "owner@example.com", "wrong-password-here")).status_code == 401  # and wrong ones are still refused


async def test_signups_from_one_ip_are_capped(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "AUTH_SIGNUP_IP_LIMIT", 2, raising=False)

    first = await client.post("/api/v1/auth/signup", json={"email": "a1@example.com", "password": PASSWORD, "name": "A"})
    second = await client.post("/api/v1/auth/signup", json={"email": "a2@example.com", "password": PASSWORD, "name": "A"})
    third = await client.post("/api/v1/auth/signup", json={"email": "a3@example.com", "password": PASSWORD, "name": "A"})

    assert (first.status_code, second.status_code) == (201, 201)
    assert third.status_code == 429
    assert int(third.headers["Retry-After"]) > 0

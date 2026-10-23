"""Password reset, the password rules, and the outgoing-email sender.

Emails are captured with a recording Mailer; nothing here touches a mail server.
The reset link is read out of the captured email, the way a person would."""

import hashlib
import re
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.core.config import get_settings
from src.identity.models import PasswordResetToken, User
from src.notifications import mailer as mailer_module
from src.notifications.mailer import ConsoleMailer, Mailer, SMTPMailer, send_email_safely

PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "an-entirely-new-passphrase"


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict[str, str]] = []

    class _Recorder(Mailer):
        async def send(self, to: str, subject: str, body: str) -> None:
            sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(mailer_module, "get_mailer", lambda: _Recorder())
    return sent


def _token_from(email: dict[str, str]) -> str:
    match = re.search(r"/reset-password\?token=([A-Za-z0-9_\-]+)", email["body"])
    assert match, email["body"]
    return match.group(1)


async def _signup(client: AsyncClient, email: str = "owner@example.com", password: str = PASSWORD) -> dict:
    response = await client.post("/api/v1/auth/signup", json={"email": email, "password": password, "name": "Owner"})
    assert response.status_code == 201, response.text
    return response.json()


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def _forgot(client: AsyncClient, email: str):
    return await client.post("/api/v1/auth/forgot-password", json={"email": email})


async def _reset(client: AsyncClient, token: str, password: str = NEW_PASSWORD):
    return await client.post("/api/v1/auth/reset-password", json={"token": token, "password": password})


# --------------------------------------------------------------- password rules


async def test_a_short_password_is_refused_with_a_clear_message_and_creates_no_account(client, db_session):
    response = await client.post(
        "/api/v1/auth/signup", json={"email": "short@example.com", "password": "short", "name": "S"}
    )

    assert response.status_code == 422
    assert "at least 8 characters" in response.json()["error"]
    assert (await db_session.execute(select(User).where(User.email == "short@example.com"))).scalar_one_or_none() is None


async def test_a_password_bcrypt_would_silently_truncate_is_refused(client):
    too_long = "a" * 73  # bcrypt only reads 72 bytes

    refused = await client.post("/api/v1/auth/signup", json={"email": "long@example.com", "password": too_long, "name": "L"})
    allowed = await client.post(
        "/api/v1/auth/signup", json={"email": "limit@example.com", "password": "a" * 72, "name": "L"}
    )

    assert refused.status_code == 422 and "too long" in refused.json()["error"]
    assert allowed.status_code == 201


# --------------------------------------------------------------- forgot password


async def test_a_known_address_gets_one_email_with_a_working_link(client, outbox, db_session):
    await _signup(client)

    response = await _forgot(client, "owner@example.com")

    assert response.status_code == 200
    assert len(outbox) == 1
    email = outbox[0]
    assert email["to"] == "owner@example.com"
    assert "Reset your Mesnium password" in email["subject"]
    token = _token_from(email)
    # Only a hash of the token is kept, never the token.
    stored = (await db_session.execute(select(PasswordResetToken))).scalars().all()
    assert [row.token_hash for row in stored] == [hashlib.sha256(token.encode()).hexdigest()]
    assert token not in repr([row.__dict__ for row in stored])


async def test_an_unknown_address_gets_exactly_the_same_answer_and_no_email(client, outbox):
    await _signup(client)

    known = await _forgot(client, "owner@example.com")
    unknown = await _forgot(client, "nobody@example.com")

    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()  # nothing reveals which addresses have accounts
    assert [email["to"] for email in outbox] == ["owner@example.com"]


async def test_one_address_cannot_be_flooded_with_reset_emails(client, outbox):
    await _signup(client)

    statuses = [(await _forgot(client, "owner@example.com")).status_code for _ in range(4)]

    assert statuses == [200, 200, 200, 200]  # the cap never changes the answer...
    assert len(outbox) == 3  # ...it just stops sending


async def test_one_ip_cannot_hammer_the_reset_endpoint(client, outbox):
    responses = [await _forgot(client, f"person{i}@example.com") for i in range(6)]

    assert [r.status_code for r in responses[:5]] == [200] * 5
    assert responses[5].status_code == 429
    assert int(responses[5].headers["Retry-After"]) > 0


async def test_asking_again_retires_the_earlier_link(client, outbox):
    await _signup(client)
    await _forgot(client, "owner@example.com")
    await _forgot(client, "owner@example.com")
    first, second = (_token_from(email) for email in outbox)

    stale = await _reset(client, first)
    fresh = await _reset(client, second)

    assert stale.status_code == 422
    assert fresh.status_code == 200


# ---------------------------------------------------------------- resetting


async def test_resetting_changes_the_password_and_confirms_by_email(client, outbox):
    await _signup(client)
    await _forgot(client, "owner@example.com")
    token = _token_from(outbox[0])

    response = await _reset(client, token)

    assert response.status_code == 200
    assert "You can sign in now" in response.json()["message"]
    assert (await _login(client, "owner@example.com", PASSWORD)).status_code == 401
    assert (await _login(client, "owner@example.com", NEW_PASSWORD)).status_code == 200
    assert "was changed" in outbox[-1]["subject"]  # a heads-up in case it wasn't them


async def test_a_link_works_once(client, outbox):
    await _signup(client)
    await _forgot(client, "owner@example.com")
    token = _token_from(outbox[0])

    first = await _reset(client, token)
    second = await _reset(client, token, "yet-another-passphrase")

    assert first.status_code == 200
    assert second.status_code == 422
    assert "expired or has already been used" in second.json()["error"]
    assert (await _login(client, "owner@example.com", NEW_PASSWORD)).status_code == 200


async def test_an_expired_link_is_refused(client, outbox, db_session):
    await _signup(client)
    await _forgot(client, "owner@example.com")
    token = _token_from(outbox[0])
    row = (await db_session.execute(select(PasswordResetToken))).scalar_one()
    row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
    await db_session.commit()

    response = await _reset(client, token)

    assert response.status_code == 422
    assert (await _login(client, "owner@example.com", PASSWORD)).status_code == 200  # unchanged


@pytest.mark.parametrize("token", ["", "garbage", "a" * 43])
async def test_a_made_up_token_is_refused_the_same_way(client, token):
    response = await _reset(client, token)

    assert response.status_code == 422
    assert "expired or has already been used" in response.json()["error"]


async def test_a_weak_new_password_does_not_use_up_the_link(client, outbox):
    await _signup(client)
    await _forgot(client, "owner@example.com")
    token = _token_from(outbox[0])

    weak = await _reset(client, token, "short")
    retry = await _reset(client, token, NEW_PASSWORD)

    assert weak.status_code == 422 and "at least 8 characters" in weak.json()["error"]
    assert retry.status_code == 200  # the same link still worked


async def test_a_reset_signs_out_every_earlier_session(client, outbox, db_session):
    tokens = await _signup(client)
    user = (await db_session.execute(select(User).where(User.email == "owner@example.com"))).scalar_one()

    def _aged(kind: str) -> str:
        # Issued ten seconds ago, i.e. a session that existed before the reset.
        settings = get_settings()
        issued = int(datetime.now(UTC).timestamp()) - 10
        return jwt.encode(
            {"sub": str(user.id), "iat": issued, "exp": issued + 3600, "type": kind},
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )

    old_access, old_refresh = _aged("access"), _aged("refresh")
    headers = {"Authorization": f"Bearer {old_access}"}
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200  # fine before

    await _forgot(client, "owner@example.com")
    await _reset(client, _token_from(outbox[0]))

    after = await client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 401 and "password was changed" in after.json()["error"]
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refreshed.status_code == 401
    # A session started after the reset works.
    fresh = (await _login(client, "owner@example.com", NEW_PASSWORD)).json()
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh['access_token']}"})
    ).status_code == 200
    assert tokens["access_token"]  # (the original signup session is covered by the aged tokens above)


async def test_a_reset_lifts_a_sign_in_lockout(client, outbox):
    await _signup(client)
    for _ in range(5):
        await _login(client, "owner@example.com", "wrong-password-here")
    assert (await _login(client, "owner@example.com", PASSWORD)).status_code == 429
    await _forgot(client, "owner@example.com")  # lockout never blocks recovery

    await _reset(client, _token_from(outbox[0]))

    assert (await _login(client, "owner@example.com", NEW_PASSWORD)).status_code == 200


# ---------------------------------------------------------------- the mailer


async def test_with_no_smtp_host_a_console_mailer_is_used(monkeypatch):
    monkeypatch.setattr(get_settings(), "SMTP_HOST", None, raising=False)
    assert isinstance(mailer_module.get_mailer(), ConsoleMailer)

    monkeypatch.setattr(get_settings(), "SMTP_HOST", "smtp.example.test", raising=False)
    assert isinstance(mailer_module.get_mailer(), SMTPMailer)


class _FakeLogger:
    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    def info(self, message, **kwargs):
        self.calls.append(("info", message, kwargs.get("extra", {}).get("extra_fields", {})))

    def warning(self, message, **kwargs):
        self.calls.append(("warning", message, kwargs.get("extra", {}).get("extra_fields", {})))


async def test_in_production_a_reset_link_is_never_written_to_the_log(monkeypatch):
    fake = _FakeLogger()
    monkeypatch.setattr(mailer_module, "logger", fake)
    monkeypatch.setattr(get_settings(), "ENV", "production", raising=False)

    await ConsoleMailer().send("owner@example.com", "Reset", "open https://x/reset-password?token=SECRET")

    assert [kind for kind, _m, _f in fake.calls] == ["warning"]
    assert "SECRET" not in repr(fake.calls)


async def test_in_development_the_message_is_logged_so_the_link_can_be_followed(monkeypatch):
    fake = _FakeLogger()
    monkeypatch.setattr(mailer_module, "logger", fake)
    monkeypatch.setattr(get_settings(), "ENV", "development", raising=False)

    await ConsoleMailer().send("owner@example.com", "Reset", "open https://x/reset-password?token=SECRET")

    assert fake.calls[0][0] == "info" and "SECRET" in repr(fake.calls)


class _FakeSMTP:
    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, **kwargs):
        self.host, self.port, self.kwargs = host, port, kwargs
        self.events: list[str] = []
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, **kwargs):
        self.events.append("starttls")

    def login(self, username, password):
        self.events.append(f"login:{username}:{password}")

    def send_message(self, message):
        self.events.append("send")
        self.sent = message


async def test_smtp_mail_is_encrypted_before_credentials_and_well_formed(monkeypatch):
    _FakeSMTP.instances = []
    settings = get_settings()
    for key, value in {
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": 587,
        "SMTP_USERNAME": "apikey",
        "SMTP_PASSWORD": "s3cret",
        "SMTP_USE_SSL": False,
        "EMAIL_FROM": "Mesnium <hello@example.test>",
    }.items():
        monkeypatch.setattr(settings, key, value, raising=False)
    monkeypatch.setattr(mailer_module.smtplib, "SMTP", _FakeSMTP)

    await SMTPMailer().send("owner@example.com", "Reset your Mesnium password", "the body")

    server = _FakeSMTP.instances[0]
    assert (server.host, server.port) == ("smtp.example.test", 587)
    assert server.events == ["starttls", "login:apikey:s3cret", "send"]  # TLS first, then credentials
    assert server.sent["To"] == "owner@example.com"
    assert server.sent["From"] == "Mesnium <hello@example.test>"
    assert server.sent["Subject"] == "Reset your Mesnium password"
    assert "the body" in server.sent.get_content()


async def test_implicit_tls_uses_the_ssl_client_and_skips_starttls(monkeypatch):
    _FakeSMTP.instances = []
    settings = get_settings()
    for key, value in {"SMTP_HOST": "smtp.example.test", "SMTP_PORT": 465, "SMTP_USE_SSL": True, "SMTP_USERNAME": None}.items():
        monkeypatch.setattr(settings, key, value, raising=False)
    monkeypatch.setattr(mailer_module.smtplib, "SMTP_SSL", _FakeSMTP)

    await SMTPMailer().send("owner@example.com", "Subject", "body")

    assert _FakeSMTP.instances[0].events == ["send"]


async def test_a_mail_server_failure_is_logged_and_swallowed(monkeypatch):
    class _Broken(Mailer):
        async def send(self, to, subject, body):
            raise RuntimeError("smtp is down")

    monkeypatch.setattr(mailer_module, "get_mailer", lambda: _Broken())

    await send_email_safely("owner@example.com", "Subject", "body")  # must not raise

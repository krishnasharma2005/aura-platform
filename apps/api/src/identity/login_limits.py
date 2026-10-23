"""Slowing down password guessing.

Three counters of *failed* sign-ins, each over a sliding-by-expiry window:

* one email address from one IP    — the common case: someone guessing a password
* one email address from anywhere  — a distributed guess at a single account (4x)
* one IP across all addresses      — one machine spraying a list of emails (6x)

They are checked **before** the password is looked at, so while a bucket is full a
correct password is refused too — otherwise the lockout would tell an attacker
whether a guess was right. Unknown email addresses count exactly like known ones,
so the limit can't be used to find out which addresses have accounts.

The trade-off to be aware of: the per-email bucket lets someone who knows an
address deliberately burn that account's allowance. That is why "forgot password"
is never subject to these counters — the owner of the address can always get back
in through their inbox.

If Redis can't be reached the check is skipped and an error is logged. Sign-in
itself doesn't need Redis, and refusing everyone because a cache is down would
turn a minor outage into a total one.
"""

import hashlib

from src.core.config import get_settings
from src.core.exceptions import RateLimitedError
from src.core.logging import get_logger
from src.memory.short_term import get_redis

logger = get_logger(__name__)

_PER_EMAIL_MULTIPLIER = 4
_PER_IP_MULTIPLIER = 6


def digest(value: str) -> str:
    # Addresses are hashed so they don't sit in Redis in the clear.
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:32]


def _buckets(email: str, ip: str) -> list[tuple[str, int]]:
    limit = get_settings().AUTH_LOGIN_MAX_FAILURES
    return [
        (f"authfail:pair:{digest(email)}:{ip}", limit),
        (f"authfail:email:{digest(email)}", limit * _PER_EMAIL_MULTIPLIER),
        (f"authfail:ip:{ip}", limit * _PER_IP_MULTIPLIER),
    ]


def _wait_message(seconds: int) -> str:
    minutes = max(1, -(-seconds // 60))
    unit = "minute" if minutes == 1 else "minutes"
    return (
        f"Too many sign-in attempts. Please wait about {minutes} {unit} and try again — "
        "or use “Forgot password” to reset it."
    )


async def ensure_allowed(email: str, ip: str) -> None:
    """Raises RateLimitedError if this attempt should be refused outright."""
    try:
        redis = get_redis()
        for key, limit in _buckets(email, ip):
            if int(await redis.get(key) or 0) >= limit:
                retry_after = max(int(await redis.ttl(key)), 1)
                raise RateLimitedError(_wait_message(retry_after), retry_after=retry_after)
    except RateLimitedError:
        raise
    except Exception as exc:  # pragma: no cover - infrastructure failure path
        logger.error("login_limit_check_unavailable", exc_info=exc)


async def record_failure(email: str, ip: str) -> None:
    window = get_settings().AUTH_LOGIN_WINDOW_SECONDS
    try:
        redis = get_redis()
        for key, _limit in _buckets(email, ip):
            if await redis.incr(key) == 1:
                await redis.expire(key, window)
    except Exception as exc:  # pragma: no cover - infrastructure failure path
        logger.error("login_limit_record_unavailable", exc_info=exc)


async def clear_failures(email: str, ip: str) -> None:
    """A successful sign-in (or a completed password reset) wipes this address's
    counters. The per-IP bucket is left alone: one good login from a shared
    office IP shouldn't erase the evidence of someone spraying from it."""
    pair, per_email, _per_ip = (key for key, _limit in _buckets(email, ip))
    try:
        await get_redis().delete(pair, per_email)
    except Exception as exc:  # pragma: no cover - infrastructure failure path
        logger.error("login_limit_clear_unavailable", exc_info=exc)

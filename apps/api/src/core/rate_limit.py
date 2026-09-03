"""Redis-backed fixed-window rate limiting.

Used by the public web-chat endpoint — the only unauthenticated surface in the
product, and therefore the only place where "someone can call this a million
times" is a real cost and abuse problem.

Fails *closed*: if Redis can't be reached we cannot know how many requests an
IP has made, and the public endpoint needs Redis for conversation memory
anyway, so refusing is both safer and no less functional than allowing. That
case raises `RateLimiterUnavailable` rather than returning False, so the caller
can tell a genuine "you're going too fast" apart from an outage and not accuse
a customer of something the infrastructure did.
"""

import time

from src.core.logging import get_logger
from src.memory.short_term import get_redis

logger = get_logger(__name__)


class RateLimiterUnavailable(Exception):
    """The limiter itself couldn't be consulted. Treat as a refusal."""


async def allow(bucket: str, limit: int, window_seconds: int) -> bool:
    """True when this call is within `limit` for the current window."""
    window = int(time.time()) // window_seconds
    key = f"ratelimit:{bucket}:{window}"
    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
    except Exception as exc:  # pragma: no cover - infrastructure failure path
        logger.error("rate_limit_unavailable", exc_info=exc, extra={"extra_fields": {"bucket": bucket}})
        raise RateLimiterUnavailable(bucket) from exc
    return count <= limit

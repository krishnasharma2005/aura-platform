"""Redis-backed short-term (working) memory: recent conversation turns, scoped
by conversation_id, with a TTL so stale conversations expire automatically."""

import json
from typing import Any

from redis.asyncio import Redis

from src.core.config import get_settings

_TTL_SECONDS = 60 * 60 * 24  # 24h of inactivity before a conversation's turns expire
_MAX_TURNS = 50

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _key(org_id: str, conversation_id: str) -> str:
    # Namespaced by org_id so two orgs can never read/overwrite each other's
    # conversation memory, even if their client-supplied conversation_ids collide.
    return f"conversation:{org_id}:{conversation_id}:turns"


async def append_turn(org_id: str, conversation_id: str, role: str, content: str) -> None:
    """Appends a single turn ({role, content}) to the conversation's turn list."""
    redis = get_redis()
    key = _key(org_id, conversation_id)
    turn = json.dumps({"role": role, "content": content})
    await redis.rpush(key, turn)
    await redis.ltrim(key, -_MAX_TURNS, -1)
    await redis.expire(key, _TTL_SECONDS)


async def get_turns(org_id: str, conversation_id: str, limit: int = _MAX_TURNS) -> list[dict[str, Any]]:
    """Returns the most recent `limit` turns, oldest first."""
    redis = get_redis()
    key = _key(org_id, conversation_id)
    raw_turns = await redis.lrange(key, -limit, -1)
    return [json.loads(t) for t in raw_turns]


async def clear_conversation(org_id: str, conversation_id: str) -> None:
    redis = get_redis()
    await redis.delete(_key(org_id, conversation_id))

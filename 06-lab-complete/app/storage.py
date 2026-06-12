"""Redis-backed storage helpers used by every app instance."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis

from app.config import settings


redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def ping_redis() -> bool:
    try:
        return bool(redis_client.ping())
    except redis.RedisError:
        return False


def _history_key(user_id: str) -> str:
    return f"history:{user_id}"


def get_history(user_id: str) -> list[dict[str, Any]]:
    rows = redis_client.lrange(_history_key(user_id), 0, -1)
    return [json.loads(row) for row in rows]


def append_history(user_id: str, role: str, content: str) -> list[dict[str, Any]]:
    key = _history_key(user_id)
    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    pipe = redis_client.pipeline()
    pipe.rpush(key, json.dumps(message))
    pipe.ltrim(key, -settings.max_history_messages, -1)
    pipe.expire(key, settings.history_ttl_seconds)
    pipe.execute()
    return get_history(user_id)


def clear_history(user_id: str) -> int:
    return int(redis_client.delete(_history_key(user_id)))

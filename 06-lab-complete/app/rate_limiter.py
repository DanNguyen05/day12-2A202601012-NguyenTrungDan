"""Redis sliding-window rate limiter."""
import time
import uuid

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.storage import redis_client


WINDOW_SECONDS = 60


def _rate_key(user_id: str) -> str:
    return f"rate:{user_id}"


def check_rate_limit(user_id: str) -> dict:
    """Record one request and raise 429 if the user is over quota."""
    now = time.time()
    key = _rate_key(user_id)
    member = f"{now}:{uuid.uuid4().hex}"
    cutoff = now - WINDOW_SECONDS

    try:
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        _, current_count = pipe.execute()

        if int(current_count) >= settings.rate_limit_per_minute:
            oldest = redis_client.zrange(key, 0, 0, withscores=True)
            retry_after = WINDOW_SECONDS
            if oldest:
                retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now))
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": settings.rate_limit_per_minute,
                    "window_seconds": WINDOW_SECONDS,
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(settings.rate_limit_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )

        pipe = redis_client.pipeline()
        pipe.zadd(key, {member: now})
        pipe.expire(key, WINDOW_SECONDS * 2)
        pipe.execute()

        remaining = settings.rate_limit_per_minute - int(current_count) - 1
        return {
            "limit": settings.rate_limit_per_minute,
            "remaining": max(0, remaining),
            "window_seconds": WINDOW_SECONDS,
        }
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Rate limiter storage unavailable") from exc

"""Redis-backed monthly budget guard."""
from datetime import datetime, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.storage import redis_client


PRICE_PER_1K_INPUT_TOKENS = 0.00015
PRICE_PER_1K_OUTPUT_TOKENS = 0.0006


def estimate_cost(input_tokens: int, output_tokens: int = 0) -> float:
    input_cost = input_tokens / 1000 * PRICE_PER_1K_INPUT_TOKENS
    output_cost = output_tokens / 1000 * PRICE_PER_1K_OUTPUT_TOKENS
    return round(input_cost + output_cost, 8)


def _budget_key(user_id: str) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"budget:{user_id}:{month}"


def check_budget(user_id: str, estimated_cost: float = 0.0) -> dict:
    """Raise 402 when the user's monthly budget would be exceeded."""
    key = _budget_key(user_id)
    try:
        current = float(redis_client.hget(key, "cost_usd") or 0.0)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Budget storage unavailable") from exc

    if current + estimated_cost > settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Monthly budget exceeded",
                "used_usd": round(current, 6),
                "attempted_usd": round(estimated_cost, 6),
                "budget_usd": settings.monthly_budget_usd,
            },
        )

    return {
        "used_usd": round(current, 6),
        "budget_usd": settings.monthly_budget_usd,
        "remaining_usd": round(settings.monthly_budget_usd - current, 6),
    }


def record_usage(user_id: str, input_tokens: int, output_tokens: int) -> dict:
    key = _budget_key(user_id)
    cost = estimate_cost(input_tokens, output_tokens)
    try:
        pipe = redis_client.pipeline()
        pipe.hincrby(key, "requests", 1)
        pipe.hincrby(key, "input_tokens", input_tokens)
        pipe.hincrby(key, "output_tokens", output_tokens)
        pipe.hincrbyfloat(key, "cost_usd", cost)
        pipe.expire(key, 32 * 24 * 3600)
        pipe.execute()
        return get_usage(user_id)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Budget storage unavailable") from exc


def get_usage(user_id: str) -> dict:
    key = _budget_key(user_id)
    try:
        raw = redis_client.hgetall(key)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Budget storage unavailable") from exc

    used = float(raw.get("cost_usd", 0.0) or 0.0)
    return {
        "user_id": user_id,
        "requests": int(raw.get("requests", 0) or 0),
        "input_tokens": int(raw.get("input_tokens", 0) or 0),
        "output_tokens": int(raw.get("output_tokens", 0) or 0),
        "cost_usd": round(used, 6),
        "budget_usd": settings.monthly_budget_usd,
        "remaining_usd": round(max(0.0, settings.monthly_budget_usd - used), 6),
    }

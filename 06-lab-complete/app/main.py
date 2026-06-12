"""Production-ready AI agent for Day 12 deployment lab."""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, estimate_cost, get_usage, record_usage
from app.rate_limiter import check_rate_limit
from app.storage import append_history, clear_history, get_history, ping_redis
from utils.mock_llm import ask as llm_ask


logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger("day12-agent")

START_TIME = time.time()
INSTANCE_ID = os.getenv("INSTANCE_ID", f"agent-{uuid.uuid4().hex[:8]}")
GRACEFUL_SHUTDOWN_SIGNAL = "SIGTERM"
_is_ready = False
_request_count = 0
_error_count = 0


def log_event(event: str, **fields: object) -> None:
    payload = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        "instance_id": INSTANCE_ID,
        **fields,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()) * 2)


def _answer_with_context(question: str, history: list[dict]) -> str:
    """Small deterministic context layer on top of the mock LLM."""
    question_lower = question.lower()
    name_pattern = re.compile(r"\bmy name is\s+([A-Za-z][A-Za-z .'-]{0,60})", re.IGNORECASE)

    if "what is my name" in question_lower or "remember my name" in question_lower:
        for message in reversed(history):
            if message.get("role") != "user":
                continue
            match = name_pattern.search(str(message.get("content", "")))
            if match:
                name = match.group(1).strip().rstrip(".?!")
                return f"Your name is {name}. I kept it in the Redis-backed conversation history."
        return "I do not know your name yet. Tell me with a message like: My name is Alice."

    match = name_pattern.search(question)
    if match:
        name = match.group(1).strip().rstrip(".?!")
        return f"Nice to meet you, {name}. I saved that in your Redis conversation history."

    return llm_ask(question)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _is_ready
    log_event(
        "startup",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        redis_url=settings.redis_url,
    )
    _is_ready = True
    yield
    _is_ready = False
    log_event("graceful_shutdown", message="Application lifespan shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 2)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Instance-ID"] = INSTANCE_ID
        log_event(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response
    except Exception:
        _error_count += 1
        raise


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field(default="default-user", min_length=1, max_length=80)


class AskResponse(BaseModel):
    user_id: str
    question: str
    answer: str
    model: str
    served_by: str
    history_messages: int
    rate_limit: dict
    usage: dict
    timestamp: str


@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "instance_id": INSTANCE_ID,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "history": "GET /history/{user_id} (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
            "metrics": "GET /metrics (requires X-API-Key)",
        },
    }


@app.get("/ask", tags=["Agent"])
def ask_requires_auth(_api_key: str = Depends(verify_api_key)):
    return {"message": "Use POST /ask with JSON body containing question and user_id."}


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(body: AskRequest, request: Request, _api_key: str = Depends(verify_api_key)):
    if not ping_redis():
        raise HTTPException(status_code=503, detail="Redis is required for stateless operation")

    rate_info = check_rate_limit(body.user_id)
    input_tokens = _estimate_tokens(body.question)
    check_budget(body.user_id, estimate_cost(input_tokens, 0))

    history_before = get_history(body.user_id)
    append_history(body.user_id, "user", body.question)
    answer = _answer_with_context(body.question, history_before)
    output_tokens = _estimate_tokens(answer)
    check_budget(body.user_id, estimate_cost(input_tokens, output_tokens))
    append_history(body.user_id, "assistant", answer)
    usage = record_usage(body.user_id, input_tokens, output_tokens)
    history_after = get_history(body.user_id)

    log_event(
        "agent_call",
        user_id=body.user_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        client=str(request.client.host) if request.client else "unknown",
    )

    return AskResponse(
        user_id=body.user_id,
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        served_by=INSTANCE_ID,
        history_messages=len(history_after),
        rate_limit=rate_info,
        usage=usage,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/history/{user_id}", tags=["Agent"])
def history(user_id: str, _api_key: str = Depends(verify_api_key)):
    return {"user_id": user_id, "messages": get_history(user_id)}


@app.delete("/history/{user_id}", tags=["Agent"])
def delete_history(user_id: str, _api_key: str = Depends(verify_api_key)):
    deleted = clear_history(user_id)
    return {"user_id": user_id, "deleted": bool(deleted)}


@app.get("/health", tags=["Operations"])
def health():
    redis_ok = ping_redis()
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": {
            "process": "ok",
            "redis": "ok" if redis_ok else "unavailable",
            "llm": "mock" if not settings.openai_api_key else settings.llm_model,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Application is not ready")
    if not ping_redis():
        raise HTTPException(status_code=503, detail="Redis is not ready")
    return {"ready": True, "instance_id": INSTANCE_ID}


@app.get("/metrics", tags=["Operations"])
def metrics(user_id: str = "default-user", _api_key: str = Depends(verify_api_key)):
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "instance_id": INSTANCE_ID,
        "usage": get_usage(user_id),
    }


if __name__ == "__main__":
    log_event("server_start", host=settings.host, port=settings.port)
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )

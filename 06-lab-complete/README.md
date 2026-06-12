# Lab 12 Complete Production Agent

This folder contains the final Day 12 production-ready AI agent.

## Features

- FastAPI REST API with `POST /ask`
- API key authentication through `X-API-Key`
- Redis-backed conversation history
- Redis-backed sliding-window rate limit: 10 requests/min/user
- Redis-backed monthly cost guard: $10/month/user
- `GET /health` liveness check
- `GET /ready` readiness check
- Structured JSON logging
- Graceful shutdown through Uvicorn lifespan handling
- Multi-stage Dockerfile with non-root runtime user
- Docker Compose stack with Nginx, 3 scalable agent replicas, and Redis
- Railway and Render deployment configs

## Local Run

```powershell
docker compose up -d --build --scale agent=3
```

The Nginx load balancer exposes the agent at:

```text
http://localhost:8080
```

## Test Commands

Health:

```powershell
curl.exe http://localhost:8080/health
```

Readiness:

```powershell
curl.exe http://localhost:8080/ready
```

Authentication should be required:

```powershell
curl.exe http://localhost:8080/ask
```

Expected: HTTP `401`.

Ask with API key:

```powershell
Invoke-WebRequest `
  -Uri http://localhost:8080/ask `
  -Method POST `
  -Headers @{ "X-API-Key" = "dev-key-change-me" } `
  -ContentType "application/json" `
  -Body '{"user_id":"test","question":"Hello"}'
```

Conversation history:

```powershell
Invoke-WebRequest `
  -Uri http://localhost:8080/ask `
  -Method POST `
  -Headers @{ "X-API-Key" = "dev-key-change-me" } `
  -ContentType "application/json" `
  -Body '{"user_id":"alice","question":"My name is Alice"}'

Invoke-WebRequest `
  -Uri http://localhost:8080/ask `
  -Method POST `
  -Headers @{ "X-API-Key" = "dev-key-change-me" } `
  -ContentType "application/json" `
  -Body '{"user_id":"alice","question":"What is my name?"}'
```

Rate limit:

```powershell
for ($i=1; $i -le 12; $i++) {
  Invoke-WebRequest `
    -Uri http://localhost:8080/ask `
    -Method POST `
    -Headers @{ "X-API-Key" = "dev-key-change-me" } `
    -ContentType "application/json" `
    -Body "{`"user_id`":`"rate-test`",`"question`":`"Request $i`"}"
}
```

Expected: first 10 requests return `200`; later requests return `429`.

## Production Readiness Check

```powershell
$env:PYTHONIOENCODING = "utf-8"
python check_production_ready.py
```

Verified result:

```text
20/20 checks passed (100%)
```

## Deployment

Use either:

- `railway.toml` for Railway
- `render.yaml` for Render Blueprint with Redis

Required environment variables:

- `PORT`
- `ENVIRONMENT=production`
- `AGENT_API_KEY`
- `REDIS_URL`
- `RATE_LIMIT_PER_MINUTE=10`
- `MONTHLY_BUDGET_USD=10.0`
- `OPENAI_API_KEY` optional; mock LLM works without it

See the root `DEPLOYMENT.md` for public URL test commands and cloud deployment steps.

# Deployment Information

## Public URL

Pending cloud deployment:

```text
https://<your-service>.railway.app
```

The production app is ready for Railway or Render, but the final public URL requires logging in to the student's Railway/Render account.

## Platform

Recommended: Render Blueprint or Railway.

Prepared config files:

- Railway: `06-lab-complete/railway.toml`
- Render: `06-lab-complete/render.yaml`

## Local Production Verification

Run from `06-lab-complete/`:

```powershell
docker compose up -d --build --scale agent=3
```

Verified locally:

```text
GET /health -> 200
GET /ready -> 200
GET /ask without API key -> 401
POST /ask without API key -> 401
POST /ask with API key -> 200
Invalid request body -> 422
Rate limit after 10 requests/min/user -> 429
SIGTERM shutdown -> graceful_shutdown log emitted
Final image size -> 166 MB
```

## Test Commands

Replace the URL after cloud deployment:

```powershell
$URL = "https://<your-service>.railway.app"
$KEY = "your-production-api-key"
```

### Health Check

```powershell
curl.exe "$URL/health"
```

Expected:

```json
{"status":"ok"}
```

### Readiness Check

```powershell
curl.exe "$URL/ready"
```

Expected:

```json
{"ready":true}
```

### Authentication Required

```powershell
curl.exe "$URL/ask"
```

Expected: HTTP `401`.

### API Test With Authentication

```powershell
Invoke-WebRequest `
  -Uri "$URL/ask" `
  -Method POST `
  -Headers @{ "X-API-Key" = $KEY } `
  -ContentType "application/json" `
  -Body '{"user_id":"test","question":"Hello"}'
```

Expected: HTTP `200` with an AI agent response.

### Conversation History Test

```powershell
Invoke-WebRequest `
  -Uri "$URL/ask" `
  -Method POST `
  -Headers @{ "X-API-Key" = $KEY } `
  -ContentType "application/json" `
  -Body '{"user_id":"alice","question":"My name is Alice"}'

Invoke-WebRequest `
  -Uri "$URL/ask" `
  -Method POST `
  -Headers @{ "X-API-Key" = $KEY } `
  -ContentType "application/json" `
  -Body '{"user_id":"alice","question":"What is my name?"}'
```

Expected: response mentions `Alice`.

### Rate Limiting Test

```powershell
for ($i=1; $i -le 12; $i++) {
  Invoke-WebRequest `
    -Uri "$URL/ask" `
    -Method POST `
    -Headers @{ "X-API-Key" = $KEY } `
    -ContentType "application/json" `
    -Body "{`"user_id`":`"rate-test`",`"question`":`"Request $i`"}"
}
```

Expected: first 10 requests return `200`; later requests return `429`.

## Environment Variables Set

Required on Railway/Render:

- `PORT`
- `ENVIRONMENT=production`
- `AGENT_API_KEY`
- `REDIS_URL`
- `RATE_LIMIT_PER_MINUTE=10`
- `MONTHLY_BUDGET_USD=10.0`
- `APP_NAME`
- `APP_VERSION`
- `OPENAI_API_KEY` optional because the app can run with mock LLM
- `ALLOWED_ORIGINS`

## Railway Deployment Steps

```powershell
cd 06-lab-complete
npm i -g @railway/cli
railway login
railway init
railway add redis
railway variables set ENVIRONMENT=production
railway variables set AGENT_API_KEY=<strong-secret-key>
railway variables set RATE_LIMIT_PER_MINUTE=10
railway variables set MONTHLY_BUDGET_USD=10.0
railway up
railway domain
```

After `railway domain`, replace the placeholder URL at the top of this file.

## Render Deployment Steps

1. Push the repository to GitHub.
2. Go to Render Dashboard.
3. New -> Blueprint.
4. Connect this GitHub repository.
5. Choose `06-lab-complete/render.yaml`.
6. Confirm the web service and Redis service.
7. Deploy and copy the public URL.
8. Replace the placeholder URL at the top of this file.

## Screenshots

Add these after cloud deployment:

- `screenshots/dashboard.png`: Railway/Render service running.
- `screenshots/health.png`: public `/health` request returns `200`.
- `screenshots/api-test.png`: public `/ask` request with `X-API-Key` returns `200`.
- `screenshots/rate-limit.png`: rate limit returns `429`.

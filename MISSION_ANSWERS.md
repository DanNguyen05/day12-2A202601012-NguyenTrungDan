# Day 12 Lab - Mission Answers

Student: Nguyen Trung Dan  
Student ID: 2A202601012  
Repository: https://github.com/DanNguyen05/day12-2A202601012-NguyenTrungDan

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

In `01-localhost-vs-production/develop/app.py`, the main production anti-patterns are:

1. API keys and database credentials are hardcoded in source code.
2. The port is fixed in code instead of being read from environment variables.
3. Debug behavior is suitable for local development, not production.
4. There is no `/health` endpoint for platform health checks.
5. There is no `/ready` endpoint to tell a load balancer when the app can receive traffic.
6. Logging uses local-style output instead of structured JSON logs.
7. The app does not handle graceful shutdown explicitly.
8. Configuration is not separated by environment, so dev/staging/production are hard to operate safely.

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
| --- | --- | --- | --- |
| Config | Hardcoded values | Environment variables | Keeps secrets out of Git and allows different settings per environment |
| Secrets | API/database secrets in code | `.env.example` only; real secrets from env | Prevents accidental credential leaks |
| Port | Fixed port | `PORT` env var | Cloud platforms usually inject the port dynamically |
| Health check | Missing | `GET /health` | Platform can restart unhealthy containers |
| Readiness check | Missing | `GET /ready` | Load balancer sends traffic only when dependencies are ready |
| Logging | `print()` / plain logs | JSON structured logs | Easier to search, parse, and monitor in production |
| Shutdown | Abrupt stop | Graceful shutdown through ASGI lifespan/SIGTERM handling | In-flight requests can finish cleanly |
| Error handling | Basic | HTTP status codes and clear details | Clients and graders can detect failures correctly |

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. Base image in the basic Dockerfile: `python:3.11`. It includes a full Python runtime and is easy to understand but large.
2. Working directory: `/app`. This is where the application files are copied and executed inside the container.
3. `requirements.txt` is copied before application code so Docker can cache the dependency install layer. If only source code changes, dependencies do not need to reinstall.
4. `CMD` gives the default command for the container and can be overridden. `ENTRYPOINT` is the fixed executable and is harder to override.

### Exercise 2.3: Image size comparison

| Image | Build style | Size |
| --- | --- | --- |
| Basic `02-docker/develop` | Single-stage, full `python:3.11` base | Expected much larger because it keeps the full base image and build/runtime layers together |
| Final `06-lab-complete` | Multi-stage, `python:3.11-slim`, non-root runtime | 166 MB measured with `docker images 06-lab-complete-agent` |

Multi-stage builds are smaller because build tools are used only in the builder stage. The runtime image contains only Python, installed packages, and application code.

### Exercise 2.4: Docker Compose architecture

The final stack uses this architecture:

```text
Client -> Nginx on localhost:8080 -> 3 FastAPI agent containers -> Redis
```

Services:

- `nginx`: reverse proxy and load balancer.
- `agent`: FastAPI AI agent. It can be scaled with `docker compose up -d --scale agent=3`.
- `redis`: shared state store for conversation history, rate limit counters, and monthly budget usage.

## Part 3: Cloud Deployment

### Exercise 3.1: Railway or Render deployment

The repo includes both deployment configs:

- Railway: `06-lab-complete/railway.toml`
- Render: `06-lab-complete/render.yaml`

Public URL: pending account login and deploy step.

Local production-equivalent verification was completed through Docker Compose:

```powershell
cd 06-lab-complete
docker compose up -d --build --scale agent=3
curl.exe http://localhost:8080/health
curl.exe http://localhost:8080/ready
```

Both `/health` and `/ready` returned HTTP `200` locally.

### Exercise 3.2: `render.yaml` vs `railway.toml`

| File | Purpose | Main difference |
| --- | --- | --- |
| `railway.toml` | Railway deployment metadata | Defines Docker builder, start command, healthcheck path, and restart policy |
| `render.yaml` | Render blueprint | Defines both web service and Redis service, including generated API key and Redis connection string |

Railway is faster for simple prototypes. Render blueprint is more explicit because it can define the web service and Redis dependency in one file.

### Exercise 3.3: Cloud Run CI/CD

`cloudbuild.yaml` describes a CI/CD pipeline: build container image, run checks, push the image, then deploy. `service.yaml` describes Cloud Run runtime settings such as container resources, environment variables, autoscaling, and health checks.

## Part 4: API Security

### Exercise 4.1: API key authentication

The final project checks API keys in `06-lab-complete/app/auth.py`.

- Client must send header `X-API-Key`.
- Missing or invalid key returns HTTP `401`.
- The real key comes from `AGENT_API_KEY`, not hardcoded source code.
- Key rotation is done by changing `AGENT_API_KEY` in the cloud environment and redeploying/restarting the service.

Local test result:

```text
POST /ask without X-API-Key -> 401
GET /ask without X-API-Key -> 401
POST /ask with X-API-Key -> 200
```

### Exercise 4.2: JWT authentication

JWT means JSON Web Token. A user logs in once, receives a signed token, and then sends it as `Authorization: Bearer <token>`. The server verifies the signature and expiry without checking the database on every request.

The final project uses API key authentication because that is enough for the assignment's public API protection requirement. The `04-api-gateway/production` example demonstrates the JWT version.

### Exercise 4.3: Rate limiting

The final project implements Redis-backed sliding-window rate limiting in `06-lab-complete/app/rate_limiter.py`.

- Limit: 10 requests per minute per `user_id`.
- Storage: Redis sorted set, not local memory.
- Exceeded limit: HTTP `429`.

Local test result:

```text
12 requests for user_id=rate_test -> 200,200,200,200,200,200,200,200,200,200,429,429
```

### Exercise 4.4: Cost guard implementation

The final project implements a Redis-backed monthly cost guard in `06-lab-complete/app/cost_guard.py`.

Approach:

1. Estimate input/output tokens.
2. Convert tokens to estimated USD cost.
3. Store monthly usage in Redis key `budget:{user_id}:{YYYY-MM}`.
4. Reject requests with HTTP `402` if estimated monthly usage would exceed `$10`.
5. Expire monthly budget keys after 32 days.

## Part 5: Scaling & Reliability

### Exercise 5.1: Health and readiness checks

Implemented endpoints:

- `GET /health`: returns process status, uptime, Redis status, model mode, and total request count.
- `GET /ready`: returns `200` only if the app is ready and Redis is reachable.

Local result:

```text
GET /health -> 200
GET /ready -> 200
```

### Exercise 5.2: Graceful shutdown

The Docker runtime uses `exec python -m uvicorn ...` so PID 1 receives SIGTERM correctly. Uvicorn then runs FastAPI lifespan shutdown.

Local SIGTERM log proof:

```text
INFO:     Shutting down
INFO:day12-agent:{"event": "graceful_shutdown", ...}
INFO:     Application shutdown complete.
```

### Exercise 5.3: Stateless design

The final app does not store conversation history, rate limit counters, or budget counters in process memory. It stores them in Redis:

- Conversation history: Redis list `history:{user_id}`
- Rate limit: Redis sorted set `rate:{user_id}`
- Cost guard: Redis hash `budget:{user_id}:{YYYY-MM}`

This means any agent instance can answer the next request for the same user.

### Exercise 5.4: Load balancing

The final stack runs:

```powershell
docker compose up -d --scale agent=3
```

Nginx receives traffic on `localhost:8080` and forwards requests to the `agent` service. Docker DNS resolves the scaled agent replicas.

### Exercise 5.5: Test stateless design

Conversation history test:

```text
POST /ask {"user_id":"alice_test","question":"My name is Alice"} -> 200
POST /ask {"user_id":"alice_test","question":"What is my name?"} -> "Your name is Alice..."
GET /history/alice_test -> 4 messages stored in Redis
```

This proves state is preserved outside the individual FastAPI process.

## Part 6: Final Project Summary

Final implementation path: `06-lab-complete/`

Completed requirements:

- REST API agent with `POST /ask`
- Conversation history by `user_id`
- Multi-stage Dockerfile
- Environment-variable configuration
- API key authentication
- Redis-backed rate limiting at 10 req/min/user
- Redis-backed cost guard at $10/month/user
- Health and readiness checks
- Graceful shutdown
- Stateless design with Redis
- Structured JSON logs
- Nginx load-balanced Docker Compose stack
- Railway and Render deployment config files

Local verification:

```text
python -m compileall 06-lab-complete/app 06-lab-complete/utils -> passed
python 06-lab-complete/check_production_ready.py -> 20/20 checks passed
docker compose up -d --build --scale agent=3 -> stack healthy
Final Docker image size -> 166 MB
```

---
name: dev_env
description: Standard operating procedures for running, debugging, and configuring the KaizenCodes local and Docker development environment. Covers port management, CORS, .env validation, Docker, and database modes.
---

# KaizenCodes Dev Environment Skill (`dev_env`)

## 🎯 Purpose
Use this skill to start the application, resolve environment configuration issues, debug CORS errors, switch database modes, or investigate Docker container problems.

---

## 🚀 Starting the Application

### Option A: Local Development (Recommended for coding)
Open two terminal tabs from the project root:

**Terminal 1 — Backend:**
```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
```
API docs available at: `http://localhost:8000/docs`

**Terminal 2 — Frontend:**
```bash
cd frontend && npm run dev
```
App available at: `http://localhost:3001` (or `3000` if port `3001` is in use)

### Option B: Docker Compose (Recommended for integration testing)
```bash
# Start all services
docker-compose up -d --build

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Stop all services
docker-compose down
```

### Option C: Docker with DynamoDB Local
```bash
docker-compose --profile dynamo up -d --build
```
DynamoDB local UI available at: `http://localhost:8001`

---

## 🔌 Port Reference

| Service | Local Port | Docker Port |
|:---|:---|:---|
| Backend (FastAPI) | `8000` | `8000` |
| Frontend (Next.js) | `3001` | `3001` |
| DynamoDB Local | `8001` | `8001` |

### Port Collision Fix:
If port `8000` or `3001` is already in use:
```bash
# Find the process using the port
lsof -i :8000
# Kill it
kill -9 <PID>
```

---

## 🌐 CORS Configuration

CORS is configured in `backend/app/main.py` via regex and an explicit allowlist.

**Current allowed origins:**
```python
allow_origin_regex = r"^https?:\/\/(localhost|127\.0\.0\.1)(:[0-9]+)?$"
```
This means **any** `localhost` port is allowed automatically. If a new port is needed beyond localhost (e.g., a staging URL), add it to `allow_origins` list in `main.py`.

**Debugging CORS:**
1. Check the browser Network tab → look for a failing preflight `OPTIONS` request.
2. Verify the `Origin` header matches the regex above.
3. Confirm `allow_credentials=True` is set (required for JWT cookies).

---

## 🔑 Environment Variables (`.env`)

### `.env` file validation checklist:
```bash
# Check what .env values are active
cat backend/.env
cat .env  # root-level env used by docker-compose
```

| Variable | Required | Purpose |
|:---|:---|:---|
| `OPENROUTER_API_KEY` | ✅ For AI Sensei hints | OpenRouter API key for `google/gemini-2.5-flash` |
| `QUESTIONS_DIR` | ✅ | Path to questions folder (`./questions`) |
| `DATABASE_PATH` | ✅ | SQLite DB path (`./kaizencodes.db`) |
| `APP_ENV` | ✅ | `development` or `production` |
| `JWT_SECRET` | ✅ | Secret key for JWT signing — **change in production** |
| `USE_DYNAMODB` | Optional | `false` (SQLite mode) or `true` (AWS DynamoDB mode) |
| `DYNAMODB_ENDPOINT_URL` | Optional | `http://localhost:8001` for local DynamoDB |
| `AWS_REGION` | Optional | `us-east-1` |
| `COGNITO_USER_POOL_ID` | Optional | For AWS Cognito auth |
| `COGNITO_CLIENT_ID` | Optional | For AWS Cognito auth |

---

## 🗄️ Database Modes

### Mode 1: SQLite (Default — local dev)
```bash
# .env setting:
USE_DYNAMODB=false
DATABASE_PATH=./kaizencodes.db
```
The SQLite file `kaizencodes.db` is auto-created by `init_db()` on startup.

### Mode 2: DynamoDB Local (for auth testing)
```bash
# .env setting:
USE_DYNAMODB=true
DYNAMODB_ENDPOINT_URL=http://localhost:8001
```
Start DynamoDB Local first: `docker-compose --profile dynamo up -d dynamodb-local`
The table `KaizenCodes_Data` is auto-created by `init_dynamodb_table()` on startup.

---

## 🐳 Docker Troubleshooting

### Rebuild after code changes:
```bash
docker-compose up -d --build
```

### View live container logs:
```bash
docker-compose logs -f backend
docker-compose logs -f frontend
```

### Exec into a running container:
```bash
docker exec -it kaizencodes-backend /bin/bash
docker exec -it kaizencodes-frontend /bin/sh
```

### Full reset (clears containers and volumes):
```bash
docker-compose down -v
docker-compose up -d --build
```

---

## ✅ Quick Health Check
After starting the app, verify everything is running correctly:
```bash
# Backend health
curl http://localhost:8000/health
# Expected: {"status": "ok"}

# Questions endpoint
curl http://localhost:8000/api/v1/questions | python3 -m json.tool | head -20

# Frontend (just check it loads)
open http://localhost:3001
```

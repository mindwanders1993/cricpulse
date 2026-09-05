---
name: dev_env
description: Standard operating procedures for running, debugging, and configuring the CricPulse local development server, Ingestion CLI, Docker container, and Cloud Run deployment.
---

# CricPulse Dev Environment Skill (`dev_env`)

## 🎯 Purpose
Use this skill to launch the local FastAPI microservice, run DE ingestion pipelines, configure environment variables, manage Docker containers, or diagnose deployment configurations.

All commands run from the **project root**: `/Users/mrrobot/Desktop/Projects/cricpulse`.

---

## 🚀 Starting the Application

### Option A: Local API Server (Recommended for development)
```bash
# Using helper script:
bash scripts/run_local.sh

# Or directly with Uvicorn:
source .venv/bin/activate && uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **Health Probe**: `http://localhost:8000/health`
- **Readiness Probe**: `http://localhost:8000/ready`

### Option B: Headless Ingestion CLI
```bash
# Ingest full Cricsheet dataset & player registers:
source .venv/bin/activate && python -m src.cli ingest-all

# Ingest only match data:
source .venv/bin/activate && python -m src.cli ingest-matches

# Ingest only player registers:
source .venv/bin/activate && python -m src.cli ingest-registers

# Build Kimball Star Schema & Analytical Marts:
source .venv/bin/activate && python -m src.cli build-schema
```

### Option C: Docker Container (Emulate Cloud Run)
```bash
# Build image
docker build -t cricpulse-api .

# Run container (port 8080 matches Cloud Run standard)
docker run -p 8080:8080 -e APP_ENV=development cricpulse-api

# Check container health
curl http://localhost:8080/health
```

---

## 🔌 Port Reference

| Service | Port | Description |
|:---|:---|:---|
| Local Uvicorn | `8000` | Local FastAPI development server with hot-reload |
| Docker / Cloud Run | `8080` | Containerized HTTP entrypoint |

### Port Collision Fix:
If port `8000` is already in use:
```bash
lsof -i :8000
kill -9 <PID>
```

---

## 🔑 Environment Variables Configuration

CricPulse uses Pydantic `BaseSettings` defined in `src/config.py`. Settings can be specified via `.env` or system environment variables:

| Variable | Default | Required | Purpose |
|:---|:---|:---|:---|
| `APP_ENV` | `development` | Optional | `development`, `test`, or `production` |
| `GEMINI_API_KEY` | None | For live LLM | Google Gemini API key. Mock mode activates automatically if unset. |
| `SYNC_SECRET_TOKEN` | None | For sync webhook | Secret token verified in `X-Sync-Token` header for `/api/v1/internal/sync-daily` |
| `DATA_DIR` | `data/` | Optional | Root path for local data storage and raw extracts |
| `PUBLISHED_DIR` | `data/published/` | Optional | Directory holding immutable `cricket_latest.duckdb` snapshot |
| `PARQUET_DIR` | `data/parquet/` | Optional | Partitioned Gold Parquet exports directory |
| `LOG_LEVEL` | `INFO` | Optional | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## ☁️ Google Cloud Run Deployment

Deploy container to Cloud Run using the deployment script:
```bash
# Ensure gcloud CLI is authenticated
gcloud auth login
gcloud auth configure-docker us-central1-docker.pkg.dev

# Deploy with custom or default project settings:
GCP_PROJECT_ID="kaizencodes-prod" GCP_REGION="us-central1" bash scripts/deploy.sh
```

---

## ✅ Quick Health Verification
```bash
# 1. Health Probe
curl -s http://localhost:8000/health | python3 -m json.tool

# 2. Readiness Probe (verifies 13 DuckDB tables)
curl -s http://localhost:8000/ready | python3 -m json.tool

# 3. Batting Career Leaderboard
curl -s "http://localhost:8000/api/v1/analytics/leaderboards/batting?match_type=T20&limit=3" | python3 -m json.tool
```

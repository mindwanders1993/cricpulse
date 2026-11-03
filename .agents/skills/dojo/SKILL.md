---
name: dojo
description: Dōjō (道場) — The CricPulse local environment: the FastAPI service, the ingestion CLI, the data directory, Docker, settings and Cloud Run. Activate on "dojo", "run the server", "start the app", "env", "which port".
---

# `dojo` — the local environment

All commands run from the project root with `.venv` active: `source .venv/bin/activate`.

## The service

```bash
bash scripts/run_local.sh                      # uvicorn src.api.app:app --reload on :8000
curl -s localhost:8000/health | python3 -m json.tool
curl -s localhost:8000/ready  | python3 -m json.tool      # the snapshot's tables
open http://localhost:8000/docs                 # Swagger; the chat page is at /
```

| Service | Port |
|---|---|
| Local uvicorn | 8000 |
| Docker / Cloud Run | 8080 |

Port in use: `lsof -i :8000` then `kill <PID>`.

## The pipeline

```bash
python -m src.cli ingest-all          # Cricsheet matches and registers → data/
python -m src.cli build-schema        # Gold star schema and marts → the snapshot
```

M0b replaces these with one nightly entry point; until it lands, the CLI above is current. Storage is a directory
(`settings.data_dir`, default `./data`); never a GCS call.

## Settings (`src/config.py`, Pydantic BaseSettings, `.env` or environment)

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` · `test` · `production` |
| `GEMINI_API_KEY` / `OPENROUTER_API_KEY` | live LLM; unset = deterministic mock mode |
| `DATA_DIR` | the storage root |
| `LOG_LEVEL` | `DEBUG` … `ERROR` |

`src/config.py` is the source of truth; M0b adds `tmp_dir`, `snapshot_path`, `nightly_archive`, `keep_snapshots`,
`keep_raw_days`. Never read or print `.env`.

## Docker and cloud

```bash
docker build -t cricpulse-api . && docker run -p 8080:8080 -e APP_ENV=development cricpulse-api
GCP_PROJECT_ID=<project> GCP_REGION=us-central1 bash scripts/deploy.sh    # the owner runs gcloud commands
```

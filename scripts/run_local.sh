#!/usr/bin/env bash
# ==============================================================================
# CricPulse — Local Development Server Launcher
# ==============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "🏏 Starting CricPulse API Server on http://127.0.0.1:8000..."
# Local OSS plan, card R.2: binds 127.0.0.1, instead of 0.0.0.0, so only this laptop can reach it
exec uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

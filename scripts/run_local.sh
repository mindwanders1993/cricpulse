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
exec uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

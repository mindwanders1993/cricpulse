# CricPulse - Headless Data Engineering Ingestion & Lakehouse Pipeline
FROM python:3.11-slim as base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and source
COPY pyproject.toml .
COPY src/ ./src/
COPY conf/ ./conf/

# Install python package and dependencies
RUN pip install --upgrade pip && pip install .

# Default command runs incremental sync
ENTRYPOINT ["python", "-m", "src.publisher.main"]
CMD ["run", "--mode", "incremental"]

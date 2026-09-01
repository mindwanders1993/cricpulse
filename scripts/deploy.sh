#!/usr/bin/env bash
# ==============================================================================
# CricPulse — Local Cloud Run Deployment Helper Script
# ==============================================================================
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-kaizencodes-prod}"
REGION="${GCP_REGION:-us-central1}"
GAR_REPO="cricpulse"
SERVICE_NAME="cricpulse-api"
IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${GAR_REPO}/${SERVICE_NAME}:latest"

echo "🏏 Starting CricPulse Cloud Run Deployment..."
echo "📍 Project: ${PROJECT_ID} | Region: ${REGION}"

# 1. Build and push container
echo "📦 Building container image: ${IMAGE_TAG}"
docker build -t "${IMAGE_TAG}" .

echo "🚀 Pushing image to Google Artifact Registry..."
docker push "${IMAGE_TAG}"

# 2. Deploy to Cloud Run
echo "☁️ Deploying service to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
    --image="${IMAGE_TAG}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --platform=managed \
    --allow-unauthenticated \
    --min-instances=0 \
    --max-instances=5 \
    --memory=1Gi \
    --cpu=1 \
    --port=8080 \
    --set-env-vars="APP_ENV=production"

echo "✅ CricPulse API deployed successfully!"

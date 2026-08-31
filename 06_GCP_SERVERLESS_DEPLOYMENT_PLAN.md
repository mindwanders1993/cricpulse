# 06 — GCP Serverless Deployment & Hosting Plan

> **Target Platform**: Google Cloud Platform (GCP) — 100% Serverless, Scale-to-Zero ($0 to $3/month).

---

## 1. GCP Architecture & Resource Topology

The **Cricket Intelligence Platform** runs natively inside your existing KaizenCodes GCP project, sharing the same scale-to-zero serverless footprint:

```
                               ┌────────────────────────────────────────┐
                               │       KaizenCodes Web Client           │
                               │   (Firebase Hosting / Next.js)         │
                               └──────────────────┬─────────────────────┘
                                                  │ HTTPS / WSS
                                                  ▼
                               ┌────────────────────────────────────────┐
                               │        Google Cloud Run                │
                               │        (cricket-api Microservice)      │
                               │        Scales 0 → 10 Nodes             │
                               └──────────┬──────────────────┬──────────┘
                                          │                  │
                      ┌───────────────────┴───────┐   ┌──────┴────────────────────┐
                      ▼                           ▼   ▼                           ▼
       ┌───────────────────────────────┐ ┌───────────────────────────┐ ┌───────────────────────────┐
       │ Google Cloud Storage (GCS)    │ │ In-Memory DuckDB Engine   │ │ Google Gemini API         │
       │ gs://kaizencodes-cricket-data │ │ (Fast Vectorized Queries) │ │ (Gemini 2.0 Flash)        │
       └───────────────────────────────┘ └───────────────────────────┘ └───────────────────────────┘
```

---

## 2. Cloud Run Service Specifications (`cricket-api`)

| Parameter | Configuration | Technical Rationale |
| :--- | :--- | :--- |
| **Service Name** | `cricket-api` | Standalone microservice identifier. |
| **Region** | `us-central1` | Colocated with GCS bucket for **0ms latency & $0 egress**. |
| **CPU** | `1 vCPU` | Efficient vectorized DuckDB operations. |
| **Memory** | `2 GiB` | Ample headroom for DuckDB memory-mapped query execution. |
| **Min Instances** | `0` | **Scale-to-zero when idle ($0.00/hr).** |
| **Max Instances** | `10` | Automatic autoscaling during tournament traffic spikes. |
| **Concurrency** | `80` | Handles up to 80 concurrent user requests per container instance. |
| **Timeout** | `300s` | Ample time for multi-step tactical agent simulations. |

---

## 3. Step-by-Step GCP Deployment Commands

### Step 1: Create GCS Storage Bucket
```bash
gcloud storage buckets create gs://kaizencodes-cricket-data \
  --location=us-central1 \
  --uniform-bucket-level-access
```

### Step 2: Deploy `cricket-api` Microservice to Cloud Run
```bash
gcloud run deploy cricket-api \
  --source ./apps/cricket-api \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --concurrency 80 \
  --set-env-vars="\
APP_ENV=production,\
GCP_PROJECT_ID=your-gcp-project-id,\
GCS_BUCKET=kaizencodes-cricket-data,\
GEMINI_API_KEY=your-gemini-api-key,\
SYNC_SECRET_TOKEN=your-internal-cron-secret,\
ALLOWED_ORIGINS=https://kaizencodes.com,https://your-firebase-app.web.app"
```

### Step 3: Configure Cloud Scheduler for Daily Incremental Ingestion
```bash
gcloud scheduler jobs create http cricket-daily-delta-sync \
  --schedule="0 2 * * *" \
  --time-zone="UTC" \
  --uri="https://cricket-api-xxxx-uc.a.run.app/api/v1/internal/sync-daily" \
  --http-method=POST \
  --headers="X-Sync-Token=your-internal-cron-secret"
```

---

## 4. Comprehensive Monthly Hosting Cost Review

Because of GCP's generous **Always Free Tier**, the entire platform operates at virtually zero cost:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        MONTHLY GCP COST BREAKDOWN & ESTIMATE                           │
├────────────────────────────────┬───────────────────────────┬───────────────────────────┤
│ GCP Service Component          │ Idle / Dev / Demo         │ Moderate Traffic (10k q/m)│
├────────────────────────────────┼───────────────────────────┼───────────────────────────┤
│ 1. Cloud Storage (GCS)         │ $0.00 (under 5 GB free)   │ ~$0.04 / month            │
│ 2. Ingestion (Cloud Run Job)   │ $0.00 (under 180k vCPU-s) │ ~$0.10 / month            │
│ 3. Cloud Scheduler             │ $0.00 (3 free jobs/mo)    │ $0.00                     │
│ 4. Serving API (Cloud Run)     │ $0.00 (under 2M req free) │ ~$1.00 – $2.00 / month    │
│ 5. Frontend UI (Firebase)      │ $0.00 (under 10 GB free)  │ ~$0.20 / month            │
│ 6. GenAI Tokens (Gemini Flash) │ $0.15 – $0.50 / month     │ ~$1.50 – $3.00 / month    │
├────────────────────────────────┼───────────────────────────┼───────────────────────────┤
│ 💰 TOTAL NET MONTHLY COST      │ +$0.50 – $1.00 / month    │ +$3.00 – $5.50 / month    │
└────────────────────────────────┴───────────────────────────┴───────────────────────────┘
```

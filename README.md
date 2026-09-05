# 🏏 CricPulse — Next-Gen Cricket Lakehouse & Generative Multi-Agent Platform

> **Tagline**: *Real-Time Telemetry, Delivery-Grain Lakehouse & Generative Intelligence for Cricket*  
> **Target Environment**: Google Cloud Platform (GCP Serverless) / 100% Decoupled Architecture  
> **Cost Profile**: Scale-to-Zero Compute ($0 to $3 / month)

---

## 📌 Executive Summary

**CricPulse** is an open-source, serverless data lakehouse and generative intelligence platform engineered to ingest, normalize, model, and serve 21,000+ historical cricket matches, ball-by-ball deliveries, and player registries from [Cricsheet](https://cricsheet.org). 

This redesigned architecture addresses the limitations of monolithic, heavy data stacks by cleanly separating the platform into **three independent, failure-isolated subsystems** communicating over an **Immutable Object Storage Data Bus (GCS / Parquet / DuckDB)**:

1. **Subsystem 1: Headless & Ephemeral DE Ingestion Pipeline** (Polars + DuckDB Python)
2. **Subsystem 2: AI-Ready Data Preparation & Semantic Layer** (YAML Metrics + Entity Resolution + Schema Annotator)
3. **Subsystem 3: Generative Multi-Agent Intelligence Engine** (FastAPI `cricket-api` + Gemini 2.0 Flash + Text-to-SQL with AST Guardrails)

---

## 🏛️ High-Level System Architecture

```mermaid
flowchart TD
    %% EXTERNAL SOURCE
    Cricsheet["Cricsheet.org (Raw JSON matches & Register CSVs)"]

    %% CURRENT STORAGE (local filesystem, single container volume)
    subgraph StorageBus["CURRENT DATA BUS (Local Filesystem inside the container)"]
        Ledger["data/ledger.db (SQLite - SHA-256 idempotency ledger)"]
        DuckDBSnap["data/published/cricket_latest.duckdb (Zero-Lock Serving DB)"]
        Parquet["data/parquet/gold/ (Gold Parquet exports)"]
    end
    GCSPlanned["gs://kaizencodes-cricket-data/ (Planned GCS Data Bus - not yet wired)"]
    StorageBus -.->|target migration| GCSPlanned

    %% SUBSYSTEM 1: DE PIPELINE
    subgraph Subsystem1["SUBSYSTEM 1: HEADLESS DE INGESTION PIPELINE (same image, run as Cloud Run Job)"]
        direction TB
        Downloaders["MatchDownloader / RegisterDownloader"]
        Parsers["Polars Parsers (match_parser, register_parser)"]
        Builder["loader.py - builds DuckDB star schema (6 dims / 5 facts / 7 marts)"]
        Publisher["publisher.py - quality_gates.py, then promote snapshot"]

        Cricsheet --> Downloaders --> Parsers --> Builder --> Publisher
        Publisher --> Ledger
        Publisher -->|atomic promote| DuckDBSnap
        Publisher -->|export| Parquet
    end

    %% SUBSYSTEM 2: AI-READY PREPARATION (in-process library, not a service)
    subgraph Subsystem2["SUBSYSTEM 2: AI-READY SEMANTIC LAYER (in-process Python library)"]
        direction TB
        Sem["semantic_catalog.yaml + catalog.py (Canonical Metric Formulas)"]
        Crosswalk["resolver.py - 3-tier Entity Resolution (exact / alias / fuzzy, in DuckDB)"]
        GoldenSQL["golden_queries.py - Few-Shot SQL Store"]
    end

    %% SUBSYSTEM 3: GEN AI MICROSERVICE
    subgraph Subsystem3["SUBSYSTEM 3: GENERATIVE AI MICROSERVICE (Cloud Run service: cricpulse-api)"]
        direction TB
        API["FastAPI app.py (health / analytics / ai / internal routes)"]
        Supervisor["SupervisorAgent - regex + LLM-fallback intent router"]

        subgraph Agents["Agent Swarm (custom Python, no LangGraph)"]
            A1["text_to_sql.py (guardrails.py sqlglot AST checks - read-only SELECT, gold.* allowlist)"]
            A2["tactical_scout.py"]
            A3["narrative_storyteller.py"]
        end

        MemDB["DuckDB connection opened read-only from snapshot (app.state.db)"]
        Gemini["Gemini 2.0 Flash REST API (generativelanguage.googleapis.com)"]
        SyncHook["/api/v1/internal/sync-daily webhook (X-Sync-Token auth)"]

        API --> Supervisor --> Agents
        Agents <--> Sem & Crosswalk & GoldenSQL
        Agents --> MemDB
        Agents -->|LLM calls| Gemini
        DuckDBSnap -.->|read snapshot at startup| MemDB
        API --> SyncHook
    end

    %% RUNTIME INTEGRATION LOOP
    Scheduler["Cloud Scheduler"] -->|triggers| SyncHook
    SyncHook -.->|re-runs pipeline synchronously, then hot-swaps connection| Subsystem1
    SyncHook -.-> MemDB

    %% CLIENT / CONSUMPTION
    Client["API Consumers (Web/BI clients)"] -->|HTTPS| API

    %% DEPLOYMENT
    subgraph Deploy["CI/CD (GitHub Actions)"]
        direction LR
        CI["ci.yml: ruff + pytest (Python 3.11-3.13)"]
        CD["deploy.yml: build image on push to main"]
        AR["Google Artifact Registry"]
        SM["GCP Secret Manager (GEMINI_API_KEY, SYNC_SECRET_TOKEN)"]
        CI --> CD --> AR --> Subsystem3
        SM -.->|injected env| Subsystem3
    end
```

---

## 📑 Design Document Index

| Document | Title & Scope | Key Topics Covered |
| :--- | :--- | :--- |
| [`01_SYSTEM_ARCHITECTURE.md`](./01_SYSTEM_ARCHITECTURE.md) | **End-to-End System Architecture** | Decoupling strategy, microservice boundaries, failure isolation, sequence diagrams. |
| [`02_DATA_ENGINEERING_PIPELINE.md`](./02_DATA_ENGINEERING_PIPELINE.md) | **Data Engineering & Lakehouse Pipeline** | Cricsheet extraction, Polars normalization, revision ledger, idempotency, Parquet layouts. |
| [`03_DATA_MODEL_AND_CONTRACTS.md`](./03_DATA_MODEL_AND_CONTRACTS.md) | **Dimensional Data Model & Contracts** | Star schema (6 Dims, 5 Facts, 7 Marts), Mermaid ERDs, multi-wicket grain rules. |
| [`04_AI_READY_SEMANTIC_LAYER.md`](./04_AI_READY_SEMANTIC_LAYER.md) | **AI-Ready Semantic & Metric Layer** | Canonical YAML metrics, entity resolution crosswalk, schema catalog & Golden SQLs. |
| [`05_GENERATIVE_AI_MULTI_AGENTS.md`](./05_GENERATIVE_AI_MULTI_AGENTS.md) | **Generative AI & Multi-Agent Engine** | Text-to-SQL agent, SQL AST guardrails, self-correction reflection loops, tactical scouting. |
| [`06_GCP_SERVERLESS_DEPLOYMENT_PLAN.md`](./06_GCP_SERVERLESS_DEPLOYMENT_PLAN.md) | **GCP Serverless Deployment & Hosting** | Cloud Run `cricket-api`, GCS, Cloud Scheduler, Scale-to-Zero, monthly cost review ($0–$3/mo). |
| [`07_API_AND_INTEGRATION_SPEC.md`](./07_API_AND_INTEGRATION_SPEC.md) | **API & Frontend Integration Specs** | OpenAPI specifications, `/api/v1/analytics/*`, `/api/v1/ai/*`, Next.js React integration. |

---

## 🎯 Key Architectural Differentiators

1. **True Scale-to-Zero ($0.00 Idle Cost)**: Eliminates 24/7 idle infrastructure (MWAA Airflow, dedicated database clusters, always-on Spark nodes).
2. **Zero Database Lock Conflicts**: Each subsystem operates on immutable DuckDB/Parquet snapshots or in-memory instances.
3. **Deterministic AI Analytics**: LLMs never guess math or query raw files; queries pass through AST security guardrails and canonical YAML business formulas.
4. **Instant Sub-50ms Analytical Queries**: In-memory DuckDB queries 21,000+ matches in milliseconds.

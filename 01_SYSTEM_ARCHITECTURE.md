# 01 — System Architecture & Decoupling Blueprint

> **Status**: Approved Architecture  
> **Target Environment**: Google Cloud Platform (GCP Serverless) / Cloud-Agnostic Object Storage  
> **Cost Profile**: $0 to $3 / month (Scale-to-Zero)

---

## 1. Architectural Philosophy: Decoupled & Micro-Subsystem Design

Legacy data platforms suffer from heavy coupling: monolithic Airflow schedulers crashing when tasks fail, DuckDB database file locks when multiple readers and writers clash, and high idle server costs ($150–$400/mo).

The redesigned **Cricket Intelligence Platform** decouples the ecosystem into **three independently versioned, independently deployed subsystems** connected via an **Immutable Storage Data Bus**.

```mermaid
flowchart LR
    subgraph S1["Subsystem 1: DE Pipeline"]
        direction TB
        P1["Polars Ingest Worker"]
        P2["DuckDB Transform & DQ"]
    end

    subgraph Bus["Immutable Data Bus (GCS / R2)"]
        direction TB
        B1["raw/ JSON & CSVs"]
        B2["curated/ Parquet Files"]
        B3["published/ cricket_latest.duckdb"]
    end

    subgraph S2["Subsystem 2: BI & Dashboards"]
        direction TB
        D1["Evidence.dev / Next.js"]
        D2["Read-Only DuckDB Engine"]
    end

    subgraph S3["Subsystem 3: GenAI Microservice"]
        direction TB
        A1["FastAPI (cricket-api)"]
        A2["Gemini 2.0 Flash Multi-Agents"]
        A3["sqlglot AST Guardrails"]
    end

    S1 -->|1. Write Snapshots & Parquets| Bus
    Bus -.->|2. Read Snapshots (Zero Lock)| S2
    Bus -.->|3. Read Snapshots & DDLs| S3
```

---

## 2. Core Subsystems Specification

### 2.1 Subsystem 1: Headless & Ephemeral DE Ingestion Pipeline
- **Execution Model**: Headless container executed via **Cloud Scheduler + Cloud Run Job** (or GitHub Actions).
- **Runtime**: Ephemeral (~15 seconds daily for incremental delta; ~2–3 minutes for 21,000+ match backfill).
- **Core Engine**: **Polars + DuckDB Python** (replaces heavy Spark & Java runtimes).
- **Contract with Data Bus**: Produces partitioned, columnar Parquet files and builds a single, validated `published/cricket_latest.duckdb` file.

### 2.2 Subsystem 2: AI-Ready Data & Semantic Layer
- **Components**:
  - **YAML Metric Definitions**: Single source of truth for cricket calculations (Strike Rate, Economy, Dot Ball %, Clutch Index).
  - **Entity Resolution Engine**: Resolves Cricsheet abbreviations (`V Kohli`, `RG Sharma`) to canonical full identities (`Virat Kohli`, `Rohit Sharma`) and cross-site IDs (ESPNcricinfo, Cricbuzz).
  - **Schema Catalog & Golden SQL Registry**: Pre-parsed DDLs and 50+ hand-curated few-shot SQL queries for agent in-context learning.

### 2.3 Subsystem 3: Generative AI Microservice (`cricket-api`)
- **Service Type**: Standalone Serverless Container on **Google Cloud Run**.
- **Scaling**: Scales from **0 to 10 instances** on-demand; **$0.00/hr when idle**.
- **Core Engine**: **FastAPI** + **Embedded In-Memory DuckDB** + **sqlglot AST Guardrails** + **Gemini 2.0 Flash**.
- **Roles**:
  - Validates and executes natural language Text-to-SQL queries with a 3-turn self-correction loop.
  - Generates tactical opponent scouting reports and matchup simulations.
  - Serves public REST analytics endpoints (`/api/v1/players`, `/api/v1/matches`, `/api/v1/leaderboards`).

---

## 3. End-to-End Operational Workflows

### 3.1 Daily Ingestion & Snapshot Publication Flow

```mermaid
sequenceDiagram
    autonumber
    participant CS as Cloud Scheduler (02:00 UTC)
    participant Worker as Cloud Run Job (Polars Worker)
    participant Cricsheet as Cricsheet.org
    participant GCS as Google Cloud Storage (Data Bus)
    participant DB as control.match_file_audit

    CS->>Worker: 1. Trigger daily execution
    Worker->>Cricsheet: 2. Download recently_added_2_json.zip (~30 matches)
    Worker->>GCS: 3. Store raw ZIP in raw/
    Worker->>Worker: 4. Extract and compute SHA-256 hashes
    Worker->>Worker: 5. Filter out already processed matches
    Worker->>Worker: 6. Explode JSON into Deliveries, Wickets, Matches (Polars)
    Worker->>Worker: 7. Run Data Quality assertions (Grain, Referrals, Null checks)
    Worker->>GCS: 8. Write updated Parquet files to curated/parquet/
    Worker->>GCS: 9. Build and upload published/cricket_YYYY_MM_DD.duckdb
    Worker->>GCS: 10. Update pointer published/cricket_latest.duckdb
    Worker-->>CS: 11. Complete execution (~15s) -> Container shuts down
```

---

### 3.2 Generative Text-to-SQL & Multi-Agent Query Flow

```mermaid
sequenceDiagram
    autonumber
    participant User as KaizenCodes User (UI)
    participant API as Cloud Run (cricket-api)
    participant Supervisor as Supervisor Agent (LangGraph)
    participant LLM as Gemini 2.0 Flash
    participant AST as sqlglot Guardrail
    participant DuckDB as In-Memory DuckDB Engine

    User->>API: 1. "Who has the best death overs economy in IPL 2024 (min 50 balls)?"
    API->>Supervisor: 2. Parse user intent & dispatch to TextToSQLAgent
    Supervisor->>LLM: 3. Send Prompt (User Query + YAML Metrics + DDLs + Few-Shot SQLs)
    LLM-->>Supervisor: 4. Returns Generated SQL Query
    Supervisor->>AST: 5. Validate SQL Abstract Syntax Tree (AST)
    alt Destructive Query (DROP, DELETE, UPDATE, ATTACH)
        AST-->>Supervisor: 6a. Security Violation Error
        Supervisor-->>User: Return Security Rejection
    else Valid Read-Only SELECT
        AST->>DuckDB: 6b. Execute SELECT query on DuckDB
        alt Query Execution Error
            DuckDB-->>Supervisor: 7a. Syntax / Execution Error Stack Trace
            Supervisor->>LLM: 7b. Self-Correction Loop (Error + Original SQL)
            LLM-->>Supervisor: 7c. Returns Repaired SQL
            Supervisor->>DuckDB: 7d. Re-execute Repaired SQL
        end
        DuckDB-->>Supervisor: 8. Return Result RecordSet (Rows & Columns)
        Supervisor->>LLM: 9. Synthesize Natural Language Insight + Visualization Spec
        LLM-->>Supervisor: 10. Final Answer Payload
        Supervisor-->>API: 11. Format REST/WebSocket Response
        API-->>User: 12. Deliver Insight + Interactive Data Table + Chart
    end
```

---

## 4. Key Architectural Invariants & Guardrails

1. **Zero Database Lock Conflicts**:
   - The DE Ingestion worker **never writes** to a shared database file that is being read by live users. It generates a new timestamped snapshot file (`cricket_2026_08_30.duckdb`), validates it, and updates the `latest` pointer.
   - `cricket-api` loads snapshots in **read-only mode** or mounts them into RAM.
2. **Immutable Bronze & Revision Dedup**:
   - Bronze match data is append-only with composite primary key `(match_id, revision)`.
   - Silver and Gold consumers filter on `MAX(revision)` per `match_id`, guaranteeing idempotency and auditability.
3. **AST SQL Execution Guardrails**:
   - Every SQL query generated by LLM agents is parsed via `sqlglot`.
   - Allowed: `SELECT`, `WITH` (CTEs), `JOIN`, `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, `LIMIT`.
   - Strictly Forbidden: `DROP`, `DELETE`, `INSERT`, `UPDATE`, `ALTER`, `CREATE`, `ATTACH`, `COPY`, `PRAGMA`, `EXPORT`.

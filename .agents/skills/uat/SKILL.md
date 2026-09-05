---
name: uat
description: Autonomous User Acceptance Testing (UAT) Orchestrator for CricPulse. Executes the automated 8-scenario end-to-end API, lakehouse, AST security, and multi-agent test harness via scripts/run_uat.py.
---

# 🏏 CricPulse Autonomous UAT Skill (`uat`)

## 🎯 Purpose
Execute, monitor, and diagnose comprehensive end-to-end User Acceptance Testing across the entire CricPulse lakehouse, semantic catalog, and GenAI multi-agent API. Activate this skill when:
- Running final pre-PR verification loops.
- Verifying end-to-end integration after modifying API endpoints or agent workflows.
- Testing DuckDB lakehouse querying, AST security guardrails, and leaderboards under realistic client traffic.

All commands run from the **project root**: `/Users/mrrobot/Desktop/Projects/cricpulse`.

---

## 🚀 Running UAT

### Run the full UAT harness:
```bash
source .venv/bin/activate && python scripts/run_uat.py
```

The harness automatically:
1. Locates or builds a validated DuckDB lakehouse (`data/published/cricket_latest.duckdb` or `data/uat_test.duckdb` from fixtures).
2. Boots an in-process FastAPI `TestClient`.
3. Executes 8 end-to-end scenarios sequentially.
4. Renders a formatted Rich summary table with PASS/FAIL status and latency timings.

---

## 📋 The 8 UAT Scenarios

| # | Scenario Name | Endpoint / Action | Success Invariant |
|:---|:---|:---|:---|
| **1** | **Health & Readiness** | `GET /health`, `GET /ready` | HTTP 200; registers 13 Kimball dimensions, facts, and analytical marts. |
| **2** | **Batting Leaderboard** | `GET /api/v1/analytics/leaderboards/batting` | HTTP 200; validates top batters with career runs, strike rates, dot %. |
| **3** | **Bowling Leaderboard** | `GET /api/v1/analytics/leaderboards/bowling` | HTTP 200; bowling economy strictly excludes byes & leg-byes. |
| **4** | **Text-to-SQL & AST Guardrail** | `POST /api/v1/ai/query` | Executes valid `SELECT`/CTE queries against `gold.*`; strictly blocks DDL (`DROP`, `ALTER`), DML (`DELETE`, `UPDATE`), and multi-statement injection. |
| **5** | **Tactical Matchup Scout** | `POST /api/v1/ai/scout` | Resolves batter vs bowler entities across phases (Powerplay, Middle, Death) with recommended tactical directives. |
| **6** | **Narrative Storyteller** | `POST /api/v1/ai/story` | Generates match headline, narrative prose, and optional Vega-Lite / chart specification. |
| **7** | **Supervisor Intent Router** | `POST /api/v1/ai/chat` | Intelligently routes conversational cricket prompts to the correct sub-agent (`TextToSqlAgent`, `TacticalScoutAgent`, or `NarrativeStorytellerAgent`). |
| **8** | **Scheduled Sync Webhook** | `POST /api/v1/internal/sync-daily` | Validates `X-Sync-Token` authentication (returns 401 on missing token, 200 on valid secret). |

---

## 🔍 Defect Diagnosis & Remediation Protocol

If a UAT scenario fails:
1. **Scenario 1-3 (Analytics/Readiness)**: Verify DuckDB snapshot schema exists in `data/published/cricket_latest.duckdb`. If corrupted, rebuild with `python -m src.cli build-schema`.
2. **Scenario 4 (AST Security)**: Inspect `src/ai/guardrails.py`. Ensure tables referenced in generated SQL are prefixed with `gold.` and exist in the catalog allowlist.
3. **Scenario 5-7 (AI Agents)**: Check `src/ai/supervisor.py` regex or intent classifications. Check fallback mock outputs in `src/ai/text_to_sql.py`, `src/ai/tactical_scout.py`, and `src/ai/narrative_storyteller.py`.
4. **Scenario 8 (Sync Webhook)**: Check `src/api/routes/internal.py` header parsing and `SYNC_SECRET_TOKEN` setting.

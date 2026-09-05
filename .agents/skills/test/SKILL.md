---
name: test
description: A dedicated QA orchestration skill for CricPulse. Covers the 36+ pytest test suite, subsystem isolation, coverage reporting, and test fixtures.
---

# CricPulse Test Orchestration Skill (`test`)

## 🎯 Purpose
Run, diagnose, and manage the CricPulse automated test suite across all 3 subsystems (Headless DE Pipeline, Semantic Layer, GenAI Microservice). Activate this skill when:
- Running tests during Phase 2 (Build) quality gates.
- Debugging unit, integration, or contract test failures.
- Checking test coverage before a PR.
- Validating changes against test fixtures.

All commands are run from the **project root**: `/Users/mrrobot/Desktop/Projects/cricpulse`.

---

## 🧪 Running Pytest

### Run full suite:
```bash
source .venv/bin/activate && pytest
```

### Run with coverage report:
```bash
source .venv/bin/activate && pytest --cov=src --cov-report=term-missing
```

### Run specific subsystem or test module:
```bash
# GenAI Microservice & Multi-Agent Swarm
source .venv/bin/activate && pytest tests/test_api_and_agents.py -v

# Headless DE Pipeline (Parsers & Star Schema Loader)
source .venv/bin/activate && pytest tests/test_loader_and_schema.py tests/test_match_parser.py -v

# Semantic Catalog & 3-Tier Entity Resolver
source .venv/bin/activate && pytest tests/test_semantic.py -v

# Idempotency Ledger & Downloader
source .venv/bin/activate && pytest tests/test_ledger.py tests/test_downloaders.py -v
```

### Run specific test by expression:
```bash
source .venv/bin/activate && pytest -k "test_guardrail" -v
```

---

## 📋 Test Inventory & Subsystem Mapping

| Subsystem | Test File | Key Coverage Areas |
|:---|:---|:---|
| **Subsystem 1: DE Pipeline** | `tests/test_downloaders.py` | Cricsheet archive download, YAML exclusion |
| | `tests/test_match_parser.py` | Polars match parser, season normalization, phase calculation |
| | `tests/test_register_parser.py` | People/names CSV parsing, key unpivoting |
| | `tests/test_ledger.py` | SQLite SHA-256 audit ledger idempotency |
| | `tests/test_loader_and_schema.py` | DuckDB Star Schema (6 dims, 5 facts, 7 marts) |
| | `tests/test_publisher.py` | Atomic snapshot promotion, gold parquet exports |
| **Subsystem 2: Semantic Layer** | `tests/test_semantic.py` | YAML catalog loading, 3-tier entity resolution, golden queries |
| **Subsystem 3: GenAI Microservice** | `tests/test_api_and_agents.py` | AST guardrails, Text-to-SQL, Tactical Scout, Storyteller, Supervisor, API endpoints |
| **Shared Core** | `tests/test_config.py` | Pydantic BaseSettings and directory resolution |

---

## 🛡️ Test Fixtures & Mocking

- **Fixtures Directory**: `tests/fixtures/`
  - `sample_t20.json` & `sample_test.json`: Representative match JSONs from Cricsheet.
  - `sample_people.csv` & `sample_names.csv`: Cricsheet player register samples.
- **LLM Mocking**: In test environments or when `GEMINI_API_KEY` is unset, `src.ai.text_to_sql`, `src.ai.tactical_scout`, and `src.ai.narrative_storyteller` automatically activate mock mode with deterministic outputs, allowing 100% offline verification.
- **Database Isolation**: Ingestion tests use in-memory DuckDB (`:memory:`) or temporary `.duckdb` files that are cleaned up after each test.

---

## 🔍 Common Issues & Remediation

### Code style or lint failures (Ruff):
```bash
source .venv/bin/activate && ruff check --fix src tests scripts && ruff format src tests scripts
```

### Stale cache:
```bash
rm -rf .pytest_cache && pytest
```

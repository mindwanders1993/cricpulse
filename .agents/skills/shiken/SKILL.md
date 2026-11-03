---
name: shiken
description: Shiken (試験) — Test execution and test integrity for CricPulse. Runs the pytest suite, the subsystem slices and, from M2, the evaluation set; strictly forbids deleting, weakening or skipping a test. Activate on "pytest", "run the tests", "shiken", "run the evals".
---

# `shiken` — tests and test integrity

> **Objective:** prove a change with the suite while protecting the suite itself.

## Golden rules

1. **Never weaken an existing test:** no deletion of a failing test, no relaxed assertion, no `pytest.skip`,
   `xfail` or `-k` exclusion to get green.
2. **A failing test means the implementation is wrong** until proven otherwise with evidence.
3. **Every fix and every feature ships with a test** in the project's style (`tests/test_<area>.py`, fixtures from
   `tests/fixtures/`, temp directories for anything on disk).
4. **Mocks stop at the network.** The LLM is mocked when `GEMINI_API_KEY` / `OPENROUTER_API_KEY` is unset; DuckDB,
   Polars and the file system are real, in temp directories.
5. **No test touches `data/`.** A test that needs a snapshot builds one from fixtures.

## Commands

```bash
source .venv/bin/activate
python -m pytest -q                                   # full suite
python -m pytest tests/test_api_and_agents.py -q      # GenAI service: guard, agents, routes
python -m pytest tests/test_loader_and_schema.py tests/test_match_parser.py -q   # pipeline
python -m pytest tests/test_semantic.py -q            # catalog, resolver, golden queries
python -m pytest -k "guardrail" -v                    # by expression
python -m pytest --cov=src --cov-report=term-missing  # coverage
```

Lint before tests: `ruff check src tests && ruff format --check src tests`.

## The evaluation set (from M2)

`evals/` holds question → expected answer pairs in two classes: **lookup** (an exact number) and **judgement** (a
defensible answer graded against an analyst's). A module from M2 on may not reduce the pass count. The report is the
Definition of Done row 4 (`docs/04` §4). Until the harness exists, say "evals: not yet".

## Report

Which command, which database (temp or fixture), how many passed, how many failed, the exit code. A failure is quoted
with its assertion, not summarised.

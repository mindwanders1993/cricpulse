---
name: build
description: Use this skill after a plan is approved. It executes the Loop Engineering process (Build -> Test -> Reflect) until the code is 100% verified.
---

# Phase 2: Loop Engineering (Build, Test, Reflect)

When activated, execute these steps iteratively until successful:

1. **Build**: Implement the agreed-upon plan using surgical code edits.

2. **Test (Quality Gate)**: Run the following from the **project root** (`/Users/mrrobot/Desktop/Projects/cricpulse`):

   **Lint & Format Gate (run for any code change):**
   ```bash
   source .venv/bin/activate && ruff check --fix src tests scripts && ruff format src tests scripts
   ```
   - `ruff check --fix` — auto-fixes linting errors (import ordering, dead code, etc.)
   - `ruff format` — enforces consistent formatting

   **Test Suite Gate (run for any code change):**
   ```bash
   source .venv/bin/activate && pytest
   ```
   - Full 36+ test suite verifying parsers, builder, marts, semantic catalog, AST guardrails, and agent swarm.

   **Automated UAT Gate (run for API, agent, or pipeline changes):**
   ```bash
   source .venv/bin/activate && python scripts/run_uat.py
   ```
   - 8-scenario end-to-end harness testing live DuckDB queries, Text-to-SQL AST security, Tactical Scout, Storyteller, Supervisor router, and Sync webhook.

   **Architectural Invariant Check:**
   - [ ] AST security guardrails enforced (read-only `SELECT`/CTE, `gold.*` schema allowlist, no DDL/DML).
   - [ ] Bowling economy strictly excludes byes and leg-byes.
   - [ ] No heavy always-on Spark/Airflow compute introduced.

3. **Reflect**:
   - If tests or UAT **FAIL**: Do not give up. Read the traceback/error log, form a hypothesis, fix surgically, and return to Step 2.
   - If `ruff` auto-fixed files: Briefly summarize changes before proceeding.
   - If quality gates **PASS 100%**: Proceed to Step 4.

4. **Context Cleanup**: Summarize the changes made so far to consolidate memory.

5. **Pause and Prompt**:
   Output the following to the user and WAIT for their response:
   > "Build and quality gates passed 100%. Options:
   > [1] Approve (Proceed to Commit)
   > [2] Refactor Code
   > [3] Add more tests"

## ⚠️ Working Directory Discipline
Always run commands from the project root (`/Users/mrrobot/Desktop/Projects/cricpulse`). Ensure virtual environment `.venv` is activated.

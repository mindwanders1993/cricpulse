---
name: batch_add_sql_questions
description: An autonomous factory loop that processes, rewrites, and tests 10 SQL questions at a time with self-correction, culminating in a single user review.
---

# KaizenCodes Batch SQL Question Factory (`batch_add_sql_questions`)

## 🎯 Purpose
The `batch_add_sql_questions` skill automates the creation of KaizenCodes challenges at scale. It utilizes **Goal-Driven Loop Engineering** and **Context Engineering** to autonomously process a batch of 5–10 questions from the Knowledge Base archive, generate unique Parquet datasets with edge cases, self-correct errors, and produce a unified review report with zero conversational interruptions.

---

## 🚦 Operational Workflow (Strict Protocol)

### Phase 1: Autonomous Intake & Deduplication
1. When invoked (e.g., *"Create a batch of 10 Window Functions questions"* or *"Process 5 from raw KB"*), scan `docs/knowledge_base/raw_questions/`.
2. Cross-reference existing manifests in `backend/questions/` to guarantee no logic or title duplication.
3. Autonomously select the requested number of unique candidate problems matching the category/difficulty constraints.

---

### Phase 2: The Autonomous Kaizen Loop (Background Execution)
For each selected question, execute the following enclosed Build ➔ Test ➔ Reflect loop entirely in the background:

#### A. Build (Drafting & Synthesis)
1. **Anti-Plagiarism Rewriting**: Rewrite problem narrative, change names, customize domain semantics. Consult `docs/knowledge_base/duckdb_gotchas.md` to validate the ground truth SQL dialect before finalizing.
2. **Schema & Ground Truth**: Formulate the schema and canonical DuckDB SQL solution.
3. **Generator Script Pattern**: Write a standalone Python generator script at `scripts/generators/batchN.py` that creates ALL Parquet files for this batch. Run it as a background command — do NOT embed raw Parquet data in the chat context.
   ```bash
   python scripts/generators/batchN.py
   ```
   This generates:
   - `backend/questions/<slug>/sample.parquet` (or table-specific files like `sample_orders.parquet`)
   - `backend/questions/<slug>/hidden_test.parquet` (50+ rows containing edge cases, nulls, boundary values)
4. **Manifest Creation**: Write `backend/questions/<slug>/question.json` with `table_mappings` for multi-table questions.

#### B. Test (Deterministic Verification)
1. Run the question service tests:
   ```bash
   cd backend && source .venv/bin/activate && \
     PYTHONPATH=backend pytest backend/tests/test_question_service.py -v
   ```
2. **Serialization Gate**: Verify all output data is JSON-safe using `df_to_json_rows()`. Never use raw `df.values.tolist()` for data assertions — it will break with `pd.Timestamp`, `np.int64`, or `NaT` values.

#### C. Reflect & Self-Correct
1. If any test fails (e.g., syntax discrepancy, null ordering, or data type mismatch), analyze the traceback.
2. Modify the Ground Truth SQL or the synthetic Parquet generation script autonomously.
3. Re-run the test suite until achieving a **100% PASS** rate.
4. Create an individual conventional commit: `git add backend/questions/<slug> && git commit -m "feat(questions): add <slug> challenge"`

---

### Phase 3: Final Batch Review & Full Stack Gate
1. Run full-stack test verification:
   - `cd backend && source .venv/bin/activate && ruff check --fix . && ruff format . && pytest`
   - `cd frontend && npm run test` (component tests)
   - If the question catalog count has changed, update Playwright snapshots:
     ```bash
     cd frontend && npx playwright test --update-snapshots
     ```
   - Then run E2E tests clean: `cd frontend && npm run test:e2e`
2. **Batch Report**: Present a unified Markdown summary table to the user displaying:
   - Question ID & Slug
   - Title & Category
   - Core Concepts & Paradigms
   - Commit Hashes
   - Full Test Results
3. **Prompt User**: *"Batch of N challenges successfully generated and verified. [1] Approve & Push/PR, [2] Author Another Batch, [3] Done for now."*

---

## 🧠 Context Engineering Guidelines
- **Zero Chat Interruption**: Never pause for user confirmation in Phase 1 or Phase 2. Run the inner loop autonomously.
- **Generator Script is Mandatory for batches of 3+**: This keeps Parquet creation isolated, reproducible, and out of the conversation context window.
- **Ephemeral State**: Keep scratchpad scripts and verbose Parquet data dumps out of the user chat context. Only surface the concise final report and milestone summaries.
- **Self-Correction Budget**: Allow up to 3 autonomous retry loops per question before flagging an edge case for user feedback.
- **DuckDB Dialect Reference**: Before writing any ground truth SQL, always consult `docs/knowledge_base/duckdb_gotchas.md`.

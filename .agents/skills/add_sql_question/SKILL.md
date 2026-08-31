---
name: add_sql_question
description: An interactive and batch-capable skill that transforms raw SQL problems from the Knowledge Base into unique, verified KaizenCodes DuckDB challenges with Loop and Context Engineering principles.
---

# KaizenCodes SQL Question Authoring Skill (`add_sql_question`)

## 🎯 Purpose
The `add_sql_question` skill converts raw SQL problems from the Knowledge Base (`docs/knowledge_base/raw_questions/`) into unique, production-ready KaizenCodes challenges.

It strictly adheres to **Anti-Plagiarism** (rewriting narrative, changing entity names, synthesizing unique Parquet datasets with edge cases) and **Kaizen Loop Engineering** (deterministic verification, autonomous self-correction).

---

## 🚦 Operational Workflow & Dual Execution Modes

### Gate 1: Candidate Pool Presentation & Intake
1. Scan the raw archive in `docs/knowledge_base/raw_questions/`.
2. Cross-reference existing questions in `backend/questions/` to avoid duplicate logical patterns.
3. Present **3–5 unique candidate challenges** with domain, source platform, difficulty, and core concepts.
4. **Prompt User**: *"Please select which question you would like to author [1-5], type [R] to see more options, or type 'proceed 1-5' (or select a range) to build all in batch."*

---

### Execution Branching: Single vs. Batch

#### 🎨 Mode A: Single Artisanal Co-Design (User selects 1 question)
If the user selects a single question to design interactively:
1. **Gate 2 (Plan)**: Propose the anti-plagiarized problem narrative, schema, and canonical DuckDB SQL. Wait for user approval (`[1] Approve, [2] Request Changes`).
2. **Gate 3 (Build)**: Generate `backend/questions/<slug>/question.json` and synthesize `sample.parquet` + `hidden_test.parquet`. Present sample preview table. Wait for user approval (`[1] Approve & Test, [2] Modify Data`).
3. **Gate 4 (Test & Commit)**: Run the full verification pipeline (see below). Commit to git upon 100% pass rate.

---

#### ⚡ Mode B: Autonomous Batch Factory (User selects multiple e.g. `proceed 1-5` or `batch N`)
If the user approves multiple items or a range:
1. **Generator Script Pattern**: For batches of 3+ questions, always write a standalone Python generator script (e.g., `scripts/generators/batchN.py`) that creates all Parquet data files. Run the script in the background. Do NOT write Parquet data inline in the chat — this bloats context.
   ```bash
   python scripts/generators/batchN.py
   ```
2. **Zero Chat Interruption (Inner Loop)**: Do NOT stop to ask permission for each question's individual gates.
3. **Autonomous Background Kaizen Execution**:
   For each question in the batch:
   - **Rewrite**: Create distinct, anti-plagiarized problem statement and schema.
   - **Synthesize Data**: Run the generator script to create `sample.parquet` + `hidden_test.parquet` inside `backend/questions/<slug>/`.
   - **Write Manifest**: Save `backend/questions/<slug>/question.json` with ground truth SQL.
   - **Validate & Self-Correct**: Execute DuckDB verification and `test_question_service.py`. If a query or null-handling error occurs, self-correct the SQL or Parquet dataset automatically until 100% PASS.
   - **Commit Individually**: Create a clean conventional commit for each verified challenge (`feat(questions): add <slug> challenge`).
4. **Single Macro Batch Review Gate**:
   - Once all questions are verified and committed, run the full verification suite (`pytest`).
   - Present a single, comprehensive **Batch Review Summary Table** containing all question IDs, titles, difficulty, concepts, and commit hashes.
   - Prompt the user with **[1] Approve Batch & Continue, [2] Create PR, [3] Done for now**.

---

## 🔬 Verification Pipeline (Mandatory for ALL questions)
Run these commands from the **project root** in order:

```bash
# 1. Run the generator script (if using Mode B)
python scripts/generators/batchN.py

# 2. Verify the question service loads the new question correctly
cd backend && source .venv/bin/activate && \
  PYTHONPATH=backend pytest backend/tests/test_question_service.py -v

# 3. Serialization Gate — verify output is JSON-safe
# All data assertions must use df_to_json_rows() not df.values.tolist()
# Example in your test or generator:
#   from app.engine.serializer import df_to_json_rows
#   assert all(isinstance(v, (str, int, float, bool, type(None))) for row in df_to_json_rows(df) for v in row)

# 4. Ruff lint check (no auto-fix needed for generator scripts, but must pass clean)
cd backend && source .venv/bin/activate && ruff check .
```

---

## 🗄️ Multi-Table Standards
For questions requiring JOINs across multiple tables:
- Generate **separate Parquet files** per table: `sample_orders.parquet`, `sample_customers.parquet`, etc.
- Define `table_mappings` in `question.json`:
  ```json
  "table_mappings": [
    {"table_name": "orders", "parquet_file": "sample_orders.parquet"},
    {"table_name": "customers", "parquet_file": "sample_customers.parquet"}
  ]
  ```
- Test both sample and hidden parquet for each table independently.

---

## ⚠️ Anti-Plagiarism & Quality Guidelines
- **Anti-Plagiarism**: Never copy verbatim problem descriptions. Rephrase completely, rename entities (e.g., users → members, products → listings), and change numeric constants.
- **DuckDB Compatibility**: Before writing the ground truth SQL, consult `docs/knowledge_base/duckdb_gotchas.md` for known dialect differences vs. PostgreSQL/Spark SQL.
- **Parquet Quality**: Every challenge must have a sample Parquet dataset (3–10 rows) and a hidden test Parquet dataset (50+ rows) containing edge cases (nulls, boundary values, multi-condition ties).
- **Serialization Safety**: All ground truth results must be serializable via `df_to_json_rows()`. No raw `pd.Timestamp`, `np.int64`, or `NaT` values in returned data.

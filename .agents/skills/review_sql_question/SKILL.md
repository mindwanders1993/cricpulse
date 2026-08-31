---
name: review_sql_question
description: Autonomous AI Agent skill that reviews all live SQL questions in backend/questions/ using DuckDB execution, metadata validation, and AI quality scoring. Produces a unified Markdown audit report with pass/fail results and a prioritized fix list.
---

# KaizenCodes SQL Question Review Skill (`review_sql_question`)

## 🎯 Purpose
The `review_sql_question` skill audits existing KaizenCodes SQL challenges at scale. It runs a **DuckDB-powered execution loop** across all (or a filtered subset of) questions in `backend/questions/`, validates each across 5 quality dimensions, and surfaces a single unified report — following the same **Kaizen Loop Engineering** patterns as `add_sql_question` and `batch_add_sql_questions`.

---

## 🚦 Invocation Patterns

The skill accepts flexible natural-language scoping:

| User Command | Scope |
|---|---|
| `"review all questions"` | All questions in `backend/questions/` |
| `"review category: Window Functions"` | Only questions where `category == "Window Functions"` |
| `"review difficulty: Hard"` | Only Hard questions |
| `"review question: <slug>"` | Single question deep-dive |
| `"review top 20 failing"` | Re-runs only previously flagged failures |

**On activation:**
1. Parse the user's scope request.
2. State: *"Reviewing N questions. Running autonomous audit loop — I'll report back when complete."*
3. Immediately enter **Phase 2** with zero further interruptions.

---

## 🔬 Phase 2: Autonomous Kaizen Audit Loop (Background, Zero Interruptions)

Invoke the audit script:
```bash
cd backend && source .venv/bin/activate && python scripts/audit_questions.py [--category "..."] [--difficulty "..."] [--slug "..."]
```

The script iterates every matching question folder and runs these 5 checks in sequence:

### Check ① — Metadata Integrity
Validate `question.json` has all required fields:
- `id`, `slug`, `title`, `difficulty`, `category`
- `company_tags` (list, can be empty)
- `table_name` or `tables` (at least one defined)
- `problem_statement` (non-empty string)
- `schema_info` (non-empty string)
- `ground_truth.solution_sql` (non-empty string)
- `ground_truth.check_row_order`, `ground_truth.check_column_order` (booleans)
- `dataset_paths.sample_parquet`, `dataset_paths.hidden_test_parquet` (paths defined)
- `ai_context.core_concepts` (non-empty list)
- `ai_context.common_pitfalls` (non-empty list)
- `expected_output_preview.columns`, `expected_output_preview.rows` (non-empty)
- Slug–ID consistency: `slug == id.replace("_", "-")`

### Check ② — Parquet File Health
- `sample.parquet` exists and is readable (`pd.read_parquet()` succeeds)
- `hidden_test.parquet` exists and is readable
- `hidden_test.parquet` has >= 10 rows (sufficient test coverage)
- For multi-table questions: all files listed in `table_mappings` exist

### Check ③ — DuckDB SQL Correctness
- Execute `ground_truth.solution_sql` against `sample.parquet` (or all mapped parquets for multi-table)
- Catch and log any DuckDB errors (syntax errors, missing columns, type mismatches)
- Measure query execution time (warn if > 500ms on sample data)

### Check ④ — Output Schema Match
After successful execution, compare result DataFrame to `expected_output_preview`:
- Column names match (exact, case-sensitive)
- Row count of sample result matches `expected_output_preview.rows` length
- Data types are compatible with `expected_output_preview.dtypes`

### Check ⑤ — AI Quality Score (0–10)
Score these fields using heuristic analysis (deterministic, no LLM call needed):

| Sub-check | Points |
|---|---|
| `problem_statement` >= 50 words | +2 |
| `problem_statement` references domain context (not generic) | +1 |
| `ai_context.core_concepts` has >= 2 items | +2 |
| `ai_context.common_pitfalls` has >= 1 item | +2 |
| `company_tags` non-empty | +1 |
| `expected_output_preview` has column dtypes defined | +2 |

**Score < 6 = WARN (quality gap), Score >= 6 = PASS**

---

## 🔁 Self-Correction Rules

| Failure Type | Action |
|---|---|
| SQL syntax error (DuckDB) | Log error trace; flag for human review |
| Missing parquet file | Flag as FAIL; note path in report |
| Missing metadata field | Flag as WARN with exact missing key |
| Schema mismatch | Log expected vs actual columns/dtypes |
| Timeout (>5s) | Flag as WARN with execution time |

**Self-Correction Budget**: 0 retries — audit is read-only. All failures are logged, not auto-fixed, unless the user selects `[1] Auto-Fix` in Phase 3.

---

## 📊 Phase 3: Unified Review Report Gate

After the full loop completes, the report is saved at `docs/question_review_report.md`.

### Summary Header
```
KaizenCodes SQL Question Audit Report
Generated: <timestamp>
Scope: All questions (285 total)

PASS: 241   WARN: 28   FAIL: 16
Pass Rate: 84.9%
```

### Full Results Table
One row per question: Slug | Difficulty | Category | Metadata | Parquet | SQL Exec | Schema | Quality | Status | Issues

### Category Health Summary
Breakdown of pass rates by category and difficulty.

### Prioritized Fix List
Sorted by severity:
1. FAIL items (SQL broken or parquet missing)
2. WARN items (quality gaps or schema mismatches)

### Final Prompt to User
```
Audit complete. Options:
[1] Auto-Fix — apply safe fixes (missing fields, slug normalization)
[2] Export Report Only — report saved to docs/question_review_report.md
[3] Drill Into a Question — "review question: <slug>" for deep dive
[4] Done
```

---

## 🧠 Context Engineering Guidelines

- **Zero Chat Interruptions** during Phase 2. Run the audit script as a background command — never print 285 rows inline in chat.
- **Surface only the summary** and flagged failures to the user; full details live in the markdown report.
- **Scratchpad isolation**: The audit script lives in `backend/scripts/audit_questions.py` — never embed raw data in the conversation context.
- **Read-Only by Default**: The skill never modifies `question.json` or parquet files unless the user explicitly approves `[1] Auto-Fix`.

---

## 📁 Related Files

| File | Role |
|---|---|
| `backend/scripts/audit_questions.py` | The execution engine invoked by this skill |
| `docs/question_review_report.md` | Auto-generated output report |
| `backend/questions/<slug>/question.json` | Each question's manifest (read-only) |
| `backend/app/engine/query_runner.py` | DuckDB query runner (referenced for context) |
| `backend/app/engine/serializer.py` | `df_to_json_rows()` serialization helper |
| `docs/knowledge_base/duckdb_gotchas.md` | DuckDB dialect reference |

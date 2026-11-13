# CricPulse — Low-Level Design

**Status:** Draft v0.1 · **Date:** 26 Oct 2026
**Input:** `02_HIGH_LEVEL_DESIGN.md` (ADRs as proposed)
**Next:** `04_IMPLEMENTATION_PLAN.md` — each section below is tagged with the module that builds it, e.g. **[M2]**.

This is the component-level design. The module dossier (`features/M<n>-*.md`) goes one level
deeper again, into task cards, when that module is planned.

---

## 1. Target Repository Layout

Surgical: keep today's packages, add what is missing, retire the old agents.

```
src/
  config.py                    # + storage, model, limits settings            [M0a, M0b, M5]
  storage.py                   # NEW: LocalStorage | GCSStorage (same API)    [M0b]
  downloaders/                 # unchanged; writes to bronze/ via storage    [M0b]
  parsers/
    match_parser.py            # + super over, event, retirement kinds        [M1]
    edge_cases.py              # compute_phase aware of super overs           [M1]
    register_parser.py
  builder/
    schema.py                  # Gold DDL + marts + snapshot_info             [M1]
    loader.py                  # builds Gold from Silver (full rebuild)       [M0b]
  publisher/
    main.py                    # job entry: run_pipeline()                   [M0b]
    silver.py                  # NEW: merge changed matches into Silver      [M0b]
    manifest.py                # NEW: replaces src/ledger.py                 [M0b]
    quality_gates.py           # + never-shrinks, schema checks              [M0b]
    publisher.py               # versioned upload + LATEST.json              [M0b]
  semantic/                    # catalog, resolver, models — kept            [M1, M2]
  ai/
    llm.py                     # NEW: model gateway (replaces gemini_client) [M2]
    orchestrator.py            # NEW: replaces supervisor.py                 [M2]
    tools/                     # NEW: one file per tool family               [M2+]
      registry.py  stats.py  matchups.py  venues.py  matches.py  sql.py  clarify.py
    guardrails.py              # hardened                                    [M0a, M1]
    checker.py                 # NEW                                         [M3]
    composer.py                # NEW: answer anatomy                         [M3]
    chart_spec.py              # kept (used by composer)
    prompts/                   # NEW: system.md, composer.md                 [M2]
    # retired after M2: supervisor.py, text_to_sql.py, tactical_scout.py,
    #                   narrative_storyteller.py, clarifier.py (logic moves into tools)
  api/
    app.py                     # lifespan: refuse to start without snapshot  [M0a]
    limits.py                  # NEW: rate limit + spend cap                 [M5]
    routes/chat.py             # NEW: /chat and /chat/stream                 [M2, M4]
    routes/meta.py             # NEW: snapshot info + attribution            [M3]
    routes/health.py           # honest readiness                           [M0a]
    routes/analytics.py        # sort_by fixed                              [M0a]
    # removed: routes/internal.py (sync moves to the job)                   [M0b]
    static/index.html          # streaming answer card                     [M4]
evals/
  questions.yaml               # NEW: evaluation set                        [M2]
  run_evals.py                 # NEW                                        [M2]
```

---

## 2. Ingestion Job **[M0b, M1]**

### 2.1 Entry point
`python -m src.publisher.main run [--full-archive]` — runs locally against `data/`, or as the
Cloud Run Job `cricpulse-ingest` against the GCS bucket. The storage backend comes from config.

### 2.2 Steps

| # | Step | Function | Output |
|---|---|---|---|
| 1 | Download registers + match archive | `RegisterDownloader`, `MatchDownloader` | `bronze/…` |
| 2 | Diff files against the manifest | `manifest.changed(files) -> list[Path]` | changed list |
| 3 | Parse each changed file; bad file → quarantine | `MatchParser.parse_file` in try/except | per-table DataFrames + quarantine list |
| 4 | Merge into Silver | `silver.merge(tables, changed_ids)` | `silver/<table>.parquet` |
| 5 | Write manifest | `manifest.write(rows)` | `silver/manifest.parquet` |
| 6 | Build Gold from **all** Silver | `DuckDBLoader.build_from_silver(silver_dir)` | `temp.duckdb` |
| 7 | Marts + `snapshot_info` | `DuckDBLoader.build_marts()` | marts |
| 8 | Quality gates | `run_quality_gates(con, previous=LATEST)` | pass / fail |
| 9 | Publish | `SnapshotPublisher.publish(temp, version)` | `snapshots/cricket_v….duckdb` |
| 10 | Point to it | `SnapshotPublisher.write_latest(info)` | `snapshots/LATEST.json` |
| 11 | Roll out | ADR-4: build the API image with the snapshot and deploy | new revision |

**Re-parse rule:** a file is re-parsed when its `sha256` changed **or** the manifest's
`parser_version` is older than the code's `PARSER_VERSION`. Bumping `PARSER_VERSION` forces a full re-parse.

### 2.3 Silver merge
```python
def merge(table: str, new_rows: pl.DataFrame, changed_ids: set[str]) -> None:
    old = pl.read_parquet(storage.path(f"silver/{table}.parquet"))  # empty on first run
    kept = old.filter(~pl.col("match_id").is_in(changed_ids))
    storage.write_parquet(pl.concat([kept, new_rows]), f"silver/{table}.parquet")
```
Writes go to a temp key, then move into place, so a crash never leaves half a file.

### 2.4 Manifest (`silver/manifest.parquet`)

| Column | Type | Note |
|---|---|---|
| `match_id` | VARCHAR | Cricsheet id |
| `file_sha256` | VARCHAR | of the JSON file |
| `revision` | INTEGER | Cricsheet `meta.revision` |
| `parser_version` | INTEGER | code constant at parse time |
| `run_id` | VARCHAR | job run that parsed it |

### 2.5 Quality gates
Existing checks stay. New ones:

| Gate | Rule |
|---|---|
| Never shrinks | `match_count ≥ previous`; `delivery_count ≥ 0.999 × previous` |
| Keys unique | no duplicate `delivery_id`, `match_id`, `player_id`, `venue_id` |
| Super overs isolated | no super-over ball in `mart_*` career totals |
| Snapshot info present | `gold.snapshot_info` has exactly one row |
| Quarantine bounded | quarantined files ≤ 1% of the run |

### 2.6 Parser changes **[M1]**

| Change | Detail |
|---|---|
| Super overs | Innings with `super_over: true` → rows get `is_super_over = TRUE`; `compute_phase` returns `super_over` |
| Retirements | `dismissal_kind` kept; a `counts_as_dismissal` list in the catalog excludes `retired hurt`, `retired not out` |
| Events | `dim_match.event_name`, `event_stage`, `event_match_number` from `info.event` |
| Venues | Raw venue name → `venue_aliases` → stable `venue_id`; unknown names get a provisional id and a log line |

---

## 3. Gold Data Model **[M1, M6, M7]**

Only the changes are listed. Today's DDL lives in `src/builder/schema.py`.

| Table | Change | Module |
|---|---|---|
| `dim_match` | + `event_name`, `event_stage`, `event_match_number`, `venue_id` | M1 |
| `fact_delivery` | + `is_super_over` | M1 |
| `dim_venue` | `venue_id` from the curated sheet, not `md5(venue_name)`; + `latitude`, `longitude` | M1 (ids), M7 (geo) |
| `venue_aliases` | NEW: `raw_name → venue_id` | M1 |
| `snapshot_info` | NEW: `version`, `data_cutoff`, `match_count`, `delivery_count`, `built_at`, `parser_version` | M1 |
| `dim_player` | + `batting_hand`, `bowling_style`, `bowling_type`, `born`, `country` | M6 |
| `mart_player_batting_career`, `mart_player_matchup_matrix` | Dismissals use `counts_as_dismissal`; exclude super overs | M1 |
| `mart_player_phase_splits`, `mart_venue_baselines` | NEW, if the tools are too slow on raw facts (decide in M7 by timing) | M7 |
| `mart_style_matchups` | NEW | M6 |

**Rule:** no derived metric is stored as a column. `is_legal_ball`, economy and strike rate are
catalog expressions.

---

## 4. Semantic Layer **[M1, M2]**

- `conf/semantic_catalog.yaml` keeps three sections: `metrics` (SQL expression + denominator
  rules), `dimensions` (phase, dismissal kinds, formats), `semantic_tools` (tool descriptions).
- **[M1]** add `dimensions.dismissal_kind.counts_as_dismissal: [...]`.
- **[M2]** tools build SQL from catalog expressions; no formula is written twice.
- **Entity resolution** stays as built in #10: exact → alias → fuzzy (RapidFuzz Jaro-Winkler),
  with token candidates. The interface the tools use:

```python
resolver.resolve_player(name) -> ResolvedPlayer | None
resolver.candidates(name, limit=5) -> list[ResolvedPlayer]   # NEW [M2] — feeds ask_user
resolver.resolve_team(name) -> ResolvedTeam | None
resolver.resolve_venue(name) -> ResolvedVenue | None
```

---

## 5. AI Service **[M2, M3]**

### 5.1 Orchestrator
Pseudocode — the exact PydanticAI calls are fixed in the M2 dossier.
```python
async def answer(message: str, history: list[Turn], ctx: Context) -> AsyncIterator[Event]:
    agent = Agent(model=settings.orchestrator_model, tools=registry.tools(), output_type=Draft)
    result = await agent.run(message, message_history=history, usage_limits=UsageLimits(tool_calls=8))
    draft = result.output                    # Draft: headline, tiles[], chart_hint, follow_ups[], used_results[]
    verdict = checker.check(draft, result.tool_results)
    if not verdict.ok:
        draft = await agent.regenerate(draft, verdict.bad_numbers)   # once
        verdict = checker.check(draft, result.tool_results)
    yield composer.compose(draft if verdict.ok else None, result.tool_results, snapshot_info)
```
- At most **4 tool rounds / 8 tool calls**. Parallel calls allowed.
- `Context` carries `subjects` and resolved ids sent back by the UI (FR-4).
- Off-topic or betting questions: a short system-prompt rule plus a keyword pre-check → polite redirect.

### 5.2 Tool contract
Every tool takes a Pydantic input and returns a `ToolResult`:

```python
class ToolResult(BaseModel):
    rows: list[dict[str, Any]]      # what the model may quote
    sql: str                        # the query that produced the rows (receipt)
    row_count: int
    sources: list[str]              # e.g. ["Cricsheet"], ["Wikidata"]
    note: str | None = None         # e.g. "min 20 overs applied"
```

### 5.3 Tool catalogue

| Tool | Inputs | Built from | Module |
|---|---|---|---|
| `get_player_stats` | player, format, role, filters¹ | `tactical_scout.batting_career/bowling_career` + marts | M2 |
| `compare_players` | players (2–4), format, role, filters | `get_player_stats` × n | M2 |
| `get_leaderboard` | metric, format, role, filters, min qualifier, top_n | `routes/analytics.py` leaderboards (validated `sort_by`) | M2 |
| `get_matchup` | batter, bowler, format, phase? | `golden_queries.get_head_to_head_matchup` | M2 |
| `get_phase_splits` | player, format, phase? | `golden_queries.get_player_phase_splits` | M2 |
| `get_venue_profile` | venue, format | `golden_queries.get_venue_phase_and_toss_profile` | M2 |
| `get_team_head_to_head` | team_a, team_b, format, filters | new SQL | M2 |
| `get_match_summary` | match ref (teams + date, or id) | `narrative_storyteller` queries | M2 |
| `run_sql` | sql | `text_to_sql` + guard; one repair | M2 |
| `ask_user` | question, options[] | `clarifier.py` rules | M2 |
| `get_player_profile` | player | `dim_player` + Wikidata | M6 |
| `get_style_matchup` | batter, bowling_type, format, phase? | `mart_style_matchups` | M6 |
| `search_knowledge`, `explain_rule` | query | knowledge corpus | M8 |
| `web_search` | query | provider API, domain allowlist, no storage | M10 |

¹ filters: `since`, `until`, `event`, `opposition`, `venue`, `innings` (batting first / chasing), `phase`.

### 5.4 `run_sql` guard **[M0a, M1]**
1. Parse with `sqlglot` (DuckDB dialect). Exactly one `SELECT`/`WITH`/`UNION`.
2. **Tables:** allowlist read from `information_schema.tables WHERE table_schema = 'gold'` at startup **[M1]**.
3. **Functions:** an **allowlist** (aggregates, math, string, date, window), not a denylist — this blocks
   `read_csv`, `read_parquet`, `glob`, `query_table`, `getenv`, etc. **[M0a]**
4. Inject `LIMIT 500` if missing.
5. Run on a **cursor** with a 5 s timer that calls `con.interrupt()`.
6. Connection settings (set once at startup):
   `read_only=True`, `enable_external_access=false`, `lock_configuration=true`, `memory_limit`, `threads`.

### 5.5 Checker **[M3]**
```
numbers_in(draft)   = all numeric tokens in headline + tiles + follow-ups
allowed             = numbers in tool rows  ∪ their roundings (0, 1, 2 dp)
                      ∪ numbers in the user's question ∪ years/dates used as filters
normalise           = strip commas and %, Devanagari digits → ASCII, "1.2k" → 1200
fail if any number ∉ allowed
```
On failure: regenerate once, naming the bad numbers. If it fails again, return the
**numbers-only answer**: tiles and table straight from tool rows, with a one-line neutral headline.

### 5.6 Composer **[M3]**
Builds the response (§6.2): `reply` (headline), `key_points` (tiles, reusing today's field),
`chart_specs` (via `ChartSpecGenerator.generate_spec(rows)`), `table` (rows),
`receipt` (`sql[]`, `row_count`, `data_cutoff`, `sources[]`), `follow_ups`, `subjects`.

### 5.7 Model gateway **[M2]**
- `llm.py` builds PydanticAI models on the OpenRouter provider from config:
  `ORCHESTRATOR_MODEL`, `FALLBACK_MODEL`, `LLM_TIMEOUT_S=30`, one retry.
- The static system prompt + tool schemas go first (cacheable). Volatile text goes last.
- Every call logs tokens and cost into the trace (§8.3).
- Test mode: PydanticAI's `TestModel` / `FunctionModel` replace today's mock branch.

---

## 6. API **[M0a, M2, M3, M4, M5]**

### 6.1 Endpoints

| Method | Path | Purpose | Module |
|---|---|---|---|
| GET | `/health` | Liveness | today |
| GET | `/ready` | 200 only when a snapshot is loaded; returns its version | M0a |
| POST | `/api/v1/chat` | JSON answer | M2 |
| POST | `/api/v1/chat/stream` | SSE answer | M4 |
| GET | `/api/v1/meta` | Snapshot info, attribution, limits | M3 |
| GET | `/api/v1/analytics/leaderboards/*` | Kept; `sort_by` validated | M0a |
| POST | `/api/v1/ai/{query,scout,story,chat}` | Deprecated; removed when the UI moves to `/chat` | M4 |
| POST | `/api/v1/internal/sync-daily` | **Removed** — the job does this | M0b |

### 6.2 Chat request and response
```python
class ChatRequest(BaseModel):
    message: str = Field(max_length=500)
    history: list[Turn] = Field(default_factory=list, max_length=6)   # last 3 exchanges
    subjects: list[str] = Field(default_factory=list)                 # from the previous reply

class Receipt(BaseModel):
    sql: list[str]; row_count: int; data_cutoff: date; sources: list[str]; snapshot_version: str

class ChatResponse(BaseModel):
    reply: str
    key_points: list[dict[str, str]]
    chart_specs: list[dict[str, Any]]
    table: list[dict[str, Any]]
    receipt: Receipt | None          # None only for clarifying questions and refusals
    follow_ups: list[str]
    clarification: bool
    subjects: list[str]
    verified: bool                   # checker result
```

### 6.3 Stream events (SSE)
`status` ("Looking up Kohli's ODI chases…") → `token` (headline text) → `answer` (the full
`ChatResponse`) → end. On error: `error` with a user-safe message and the request id.

### 6.4 Middleware **[M5]**

| Limit | Default (proposed) |
|---|---|
| Per IP | 10 questions / minute, 60 / day |
| Global daily spend | `DAILY_SPEND_USD` (cap ÷ 30); over it → friendly 429 |
| Provider key | Monthly limit set on the OpenRouter key (hard stop) |
| Body size | 8 KB |
| CORS | The app's own origin only |

Rate state is in memory; `max-instances=2` keeps it close enough at beta scale.

### 6.5 Database access **[M0a]**
- `lifespan` opens one read-only base connection with §5.4 settings. **No snapshot → the process exits**
  (no `:memory:` fallback).
- Each request uses `app.state.db.cursor()`. The base connection is never closed or replaced while serving.

---

## 7. Chat UI **[M4]**

Single file `src/api/static/index.html`, plain JS (as today).

| Part | Behaviour |
|---|---|
| Message list | User bubbles; answer cards |
| Answer card | Headline → tiles → chart (Vega-Lite, as today) → table (collapsed) → **"How we got this"** receipt (collapsed) → chips |
| Streaming | `EventSource`-style reader on `/chat/stream`; shows `status`, then text, then the card |
| History | Last 3 exchanges + `subjects` kept in `sessionStorage`; sent with each request |
| States | Loading, clarifying question (option buttons), refusal, limit reached, error with request id |
| Footer | Data: Cricsheet (ODC-By) · cutoff date from `/meta` |

---

## 8. Ops **[M0a, M0b, M5]**

### 8.1 Configuration

| Variable | Used by | Example |
|---|---|---|
| `APP_ENV` | all | `production` |
| `STORAGE_BACKEND` / `GCS_BUCKET` | job | `gcs` / `cricpulse-data` |
| `SNAPSHOT_PATH` | API | `/app/snapshot/cricket.duckdb` |
| `OPENROUTER_API_KEY` | API | Secret Manager |
| `ORCHESTRATOR_MODEL`, `FALLBACK_MODEL` | API | chosen by evals |
| `DAILY_SPEND_USD`, `RATE_PER_MIN`, `RATE_PER_DAY` | API | `0.35`, `10`, `60` |
| `ALLOWED_ORIGINS` | API | the service URL |

### 8.2 Build and deploy
- **ADR-11:** Python 3.12 + `uv.lock`; the Dockerfile runs `uv sync --frozen`; CI does the same. **[M0a]**
- CI: `ruff` → `pytest` → `evals --mock`. Deploy on merge to `main` (owner-run).
- Job image = API image with another entry point. Scheduler → job at 02:00 IST. **[M0b]**
- Keep the last 3 images and 7 snapshots (lifecycle rules). **[M0b]**

### 8.3 Trace record (one JSON log line per answer) **[M5]**
`request_id, ts, snapshot_version, model, tools[{name, ms, row_count}], sql_count, tokens_in, tokens_out, cost_usd, latency_ms, verified, clarification, error`

### 8.4 Evaluation set **[M2]**
```yaml
- id: kohli-odi-chases-2015
  question: "How many ODI runs has Virat Kohli scored in chases since 2015?"
  expect:
    tool: get_player_stats
    numbers: { runs: "SELECT … independent SQL …" }   # computed on the snapshot, not hand-typed
  release: R1
```
Runner: `python -m evals.run_evals [--mock|--live] [--release R1]` → score, failures, cost.
Gate: live score ≥ 90% before a release.

---

## 9. Testing Strategy

| Level | What | Where |
|---|---|---|
| Unit | Parsers (super over, retirements, events), catalog, guard allowlists, checker normalisation | `tests/` |
| Integration | Build a fixture snapshot from `tests/fixtures`; every tool against it | `tests/test_tools.py` [M2] |
| Pipeline | Two runs, second with one changed file → counts never shrink | `tests/test_pipeline.py` [M0b] |
| Contract | `ChatResponse` shape; SSE event order | `tests/test_api_*.py` |
| Evaluation | Question set, mock in CI, live before release | `evals/` [M2] |
| UAT | Scripted chat journeys on the running app | `scripts/run_uat.py` (updated per module) |

---

## 10. Section → Module Map

| Module | LLD sections |
|---|---|
| M0a | §5.4 (functions, settings), §6.1 `/ready` + analytics, §6.5, §8.2 |
| M0b | §2.1–2.5, §6.1 sync removal, §8.2 job |
| M1 | §2.6, §3 (M1 rows), §4 (M1), §5.4 table allowlist |
| M2 | §1 ai/, §4 (M2), §5.1–5.3, §5.7, §6.1–6.2 chat, §8.4 |
| M3 | §5.5, §5.6, §6.1 meta |
| M4 | §6.3, §7 |
| M5 | §6.4, §8.3 |
| M6–M12 | Tool rows and table rows tagged with those modules; detailed in their dossiers |

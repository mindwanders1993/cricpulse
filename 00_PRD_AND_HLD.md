# CricPulse — Product Requirements & High-Level Design

**Status:** Draft v1 · **Scope:** Non-commercial · **Date:** 2026-10-26

This is the master blueprint. The numbered docs `01`–`07` hold subsystem detail; where they disagree with this file, this file wins until they are updated.

---

## 1. Product

### 1.1 One-line vision

A cricket intelligence engine where every number comes from verified ball-by-ball data, and an AI model only explains, never invents.

### 1.2 The problem

- Ball-tracking analytics (Hawk-Eye via CricViz) is locked to broadcasters and franchises.
- Fans get scorecards. Club coaches and academies get nothing.
- Nobody serves deep stats in plain words, in Indian languages, for free.

### 1.3 Users

| Persona | What they need | How they use it |
|---|---|---|
| Fan / writer | "Explain this stat to me" with proof | Chat UI, regional language |
| Coach / analyst | Pre-match matchup breakdowns | Auto-generated Matchup Card |
| Club cricketer | "Who do I play like?" | Pro Twin (later) |

### 1.4 Features by phase

| Phase | Feature | Depends on |
|---|---|---|
| **P0 (now)** | Ask screen: question → insight + chart + "show the query" | Existing repo, bug fixes |
| **P0** | Handedness and bowling-style enrichment | Free `cricketdata` export |
| **P0** | Super-over, DLS, retired-hurt normalisation | Parser work |
| **P1** | Matchup Card, auto-built 2h before each match | Brave Search for XI + toss |
| **P1** | Regional-language answers (Hindi, Tamil, Bengali, Marathi) | Model prompt only |
| **P1** | Venue profiles: par score, chase record, phase baselines | Marts |
| **P2** | What-If Simulator (Monte Carlo on real scoring patterns) | Win-probability model |
| **P2** | Nightly audio recap per match | Batch job + TTS |
| **P3** | Pro Twin via player similarity | Partnership for grassroots data |

### 1.5 Non-negotiables

- Every stat shown is computed by DuckDB, never by the model.
- Every AI answer carries the executed SQL, row count, and data cutoff date.
- Web search is a sensor for live context (XI, toss, pitch); its text is data, never instructions.
- Read-only database with external file access disabled.
- Monthly running cost under ₹1,000.

### 1.6 Explicitly out of scope

Real-money fantasy, phone-camera coaching, ball-tracking data, a separate Next.js frontend.

---

## 2. High-Level Design

### 2.1 Two planes

```
┌──────────────────────── INGESTION PLANE (batch, nightly) ────────────────────────┐
│ Cricsheet ZIP ─┐                                                                 │
│ Register CSVs ─┼─▶ Downloaders ─▶ Ledger (SHA-256) ─▶ Polars parsers ─▶ DuckDB   │
│ Player meta ───┤                                        builder ─▶ Quality gates │
│ Open-Meteo ────┘                                        ─▶ Publish snapshot ─▶ GCS│
└──────────────────────────────────────────────────────────────────────────────────┘
                                          │ cricket_latest.duckdb (immutable)
                                          ▼
┌──────────────────────── SERVING PLANE (Cloud Run, scale-to-zero) ────────────────┐
│ FastAPI ─▶ Entity resolver ─▶ Supervisor ─▶ { Golden tools | Guarded Text-to-SQL │
│                                              | Tactical Scout (+Brave Search)    │
│                                              | Storyteller }                     │
│          ─▶ read-only DuckDB in /tmp  ─▶  insight + chart + provenance ─▶ /ui    │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data warehouse (Medallion in DuckDB)

| Layer | Contents | Storage |
|---|---|---|
| **Bronze** | Raw Cricsheet JSON, register CSVs, player-meta CSV, weather pulls. Tracked by SHA-256 in `ledger.db`. | `data/raw/` → GCS |
| **Silver** | Flattened Polars DataFrames with edge cases normalised (super over flag, DLS, retired hurt vs out). Not persisted long-term. | In-memory |
| **Gold** | Star schema below, plus marts. One immutable `.duckdb` file per publish. Parquet export optional. | `data/published/` → GCS |

**Gold tables (keep existing names, extend columns):**

- `dim_player` + new `batting_hand`, `bowling_style`, `bowling_type`
- `dim_match` + new `event_name`, `match_stage`, `is_super_over_match`
- `dim_venue` + new `latitude`, `longitude`, `pitch_type` (curated)
- `dim_team`, `player_aliases`, `player_identifiers`
- `fact_delivery` + new `is_super_over`, `is_legal_ball`, `bowler_runs_conceded`, `is_bowler_wicket`, `score_before_ball`, `wickets_before_ball`
- `fact_innings`, `fact_wicket_detail`, `fact_player_match`
- `fact_venue_weather` (new: match_id, temp, humidity, dew point)

**Marts (rebuilt every publish):**

- `mart_player_batting_career`, `mart_player_bowling_career` (exist)
- `mart_player_matchup_matrix` (exists) + bowling-style dimension
- `mart_player_phase_splits` (new)
- `mart_venue_phase_baselines` (new: par score, run rate, wicket rate by phase and format)
- `mart_win_probability_inputs` (new, P2)

**Rule:** every publish rebuilds Gold from all Bronze files. The ledger only skips re-parsing unchanged files. This fixes the current delta-overwrites-snapshot bug.

### 2.3 Data engineering pipelines

| # | Pipeline | Trigger | Source → Sink |
|---|---|---|---|
| DE-1 | Match ingestion | Nightly, `all_json` | Cricsheet → Bronze → Gold facts |
| DE-2 | Register ingestion | Nightly | people.csv, names.csv → dim_player, aliases |
| DE-3 | Player enrichment | Monthly | cricketdata export → dim_player style columns |
| DE-4 | Venue curation | Manual | Spreadsheet → dim_venue |
| DE-5 | Weather backfill | One-time, then nightly for new matches | Open-Meteo → fact_venue_weather |
| DE-6 | Mart build + quality gates + publish | End of DE-1 | Gold → snapshot → GCS |
| DE-7 | Pre-match context | 2h before fixtures | Brave Search → cached XI/toss JSON |
| DE-8 | Nightly precompute | After DE-6 | Matchup Cards, recaps → cache |

### 2.4 AI request flow

1. Regex router classifies intent; cheap model only as fallback.
2. Entity resolver maps mentions to IDs (exact → alias → fuzzy, on pre-extracted candidates, not n-grams).
3. Golden tool if the question matches a template; else guarded Text-to-SQL with one retry.
4. DuckDB executes; deterministic stat tiles and chart spec built from rows.
5. Strong model writes the insight from the rows only.
6. Response carries insight, rows, chart, follow-ups, provenance.

---

## 3. Tech stack

| Layer | Choice | Cost |
|---|---|---|
| Language | Python 3.12, `uv` lockfile | Free |
| Transform | Polars, PyArrow | Free |
| Warehouse | DuckDB (pin `<3`), Parquet | Free |
| Semantic layer | YAML catalog + Pydantic v2 | Free |
| Entity resolution | DuckDB + RapidFuzz | Free |
| API | FastAPI + Uvicorn | Free |
| Cheap model | Claude Haiku 5.5 or Gemini 2.5 Flash | ~₹0 at hobby volume |
| Strong model | Claude Sonnet 5.5 (batch API for nightly jobs) | < ₹500 / month |
| Live context | Brave Search API, free plan, domain allowlist, daily cache | Free |
| Weather | Open-Meteo free tier (non-commercial) | Free |
| Hosting | Cloud Run scale-to-zero + GCS | Free tier |
| CI/CD | GitHub Actions, Ruff, Pytest | Free |
| UI | Existing static chat UI at `/ui` | Free |

---

## 4. Tasks (high level, in order)

### Milestone 0 — Make it correct (1 week)

- [ ] Fix snapshot delta bug: rebuild Gold from all Bronze every publish
- [ ] Validate `sort_by` in leaderboard endpoints
- [ ] Open DuckDB with `enable_external_access=false`; add scalar-position function check to guardrail
- [ ] Reduce reflection loop to one retry; drop LLM intent fallback
- [ ] Pin dependencies with a lockfile

### Milestone 1 — Richer data (2 weeks)

- [ ] DE-3 player enrichment (handedness, bowling style)
- [ ] Super-over, DLS, retired-hurt flags in parser and facts
- [ ] `mart_player_phase_splits`, `mart_venue_phase_baselines`
- [ ] DE-4 venue curation sheet, DE-5 weather backfill
- [ ] Wire GCS as the artifact store; API pulls snapshot at startup

### Milestone 2 — Cheaper, better AI (2 weeks)

- [ ] Per-call model selection in the LLM client (cheap vs strong)
- [ ] Prompt caching on the static context blocks
- [ ] Entity resolver: candidate extraction before matching, RapidFuzz
- [ ] Golden tools as parameterised Python functions, not only few-shot text
- [ ] Regional-language output option

### Milestone 3 — Matchup Card (2 weeks)

- [ ] DE-7 Brave Search context fetch with allowlist and cache
- [ ] Tactical scout binds live XI to historical matchups
- [ ] DE-8 nightly precompute and cache
- [ ] Card view in the UI

### Milestone 4 — Simulator and recaps (later)

- [ ] Win-probability model (gradient boosting on match state)
- [ ] What-If Simulator endpoint
- [ ] Nightly audio recap job

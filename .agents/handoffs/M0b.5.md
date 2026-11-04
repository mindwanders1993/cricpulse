# Handoff: M0b.5 (A)
- Branch / worktree: `feat/M0b-trustworthy-data-pipeline` · main checkout `/Users/mrrobot/Desktop/Projects/cricpulse` (M0b.4 landed as `21cc15d`)
- State: done
- What changed:
  - `src/builder/schema.py`, fact-table DDL only (D-10). Removed `PRIMARY KEY` from `fact_delivery` (`delivery_id` is now `VARCHAR NOT NULL`, so the NOT NULL the key implied stays), from `fact_innings` and from `fact_player_match`. `fact_wicket_detail` never had one. The dimension keys are unchanged. A one-line D-10 citation is in the FACTS header.
  - `src/builder/loader.py`:
    - `_MATCH_INSERTS` holds the parsed table → Gold `INSERT … SELECT … FROM {source}` mapping, one entry per match table. It is today's mapping, moved, not changed. `load_matches` fills `{source}` with a registered DataFrame. `build_from_silver` fills it with `read_parquet('<silver_dir>/<table>.parquet')`. The SQL is shared, not copied.
    - Every match-table and derived-dimension insert is now a plain `INSERT` (D-9). That covers `dim_match`, the four facts, `dim_venue` and `dim_team`. `INSERT OR REPLACE` is gone from both `load_matches` and `build_from_silver`.
    - `_derive_venue_and_team()` is today's derivation SQL, moved out so both paths call it.
    - `build_from_silver(silver_dir, register_dfs=None, settings=None)` sets `memory_limit = '2GB'` (`MEMORY_LIMIT`, spike §4) and `temp_directory = settings.tmp_dir` (dossier §5.2: local disk, never the mount). Then it loads the registers if given, inserts the five match tables from Silver and derives the venue and team dimensions.
    - `load_registers` is unchanged (`INSERT OR REPLACE`): dossier §5.5 says "Registers loaded as today".
  - `tests/test_loader_and_schema.py`: the existing test is untouched; 6 new tests. Silver is built the way the pipeline builds it: fixture zip → `archive.iter_changed` → `parse_to_staging` → `silver.merge`, all in `tmp_path`. The zip members keep the fixture file names, so the match ids (file stems, D-9) equal those from `parse_batch`.
- Verification run (after the last file change, see the session):
  - `python -m pytest tests/test_loader_and_schema.py -q` → **7 passed**, exit 0
  - `python -m pytest -q` → **89 passed, 2 skipped** (83 + 6 new), 2 warnings, exit 0. Both warnings were already there (Starlette `httpx`, unregistered `live` marker).
  - `ruff check src tests && ruff format --check src tests` → clean, exit 0
- Done-when lines met (subtasks):
  1. `build_from_silver` fills `dim_match` and the four facts with `INSERT … SELECT … FROM read_parquet(…)` using `load_matches`' mapping, then derives `dim_venue`/`dim_team` as today. The SQL is shared. → `src/builder/loader.py` (`_MATCH_INSERTS`, `_derive_venue_and_team`); `::test_build_from_silver_matches_load_matches`; `::test_build_from_silver_loads_registers_and_builds_marts` (registers, marts and the existing quality gates all pass on a Silver-built DB)
  2. D-10, no fact primary keys; plain `INSERT` in both paths; `load_matches` stays → `src/builder/schema.py`; `::test_fact_tables_have_no_primary_keys_and_dimensions_keep_theirs`; `::test_load_matches_twice_fails_loudly`; the existing `::test_duckdb_loader_and_marts` and all other `load_matches` users in the suite still pass
  2a. `memory_limit` and the spill `temp_directory` are set on the build connection → `::test_build_from_silver_sets_memory_limit_and_spill_dir`
  3. Tests the card names:
     - identical row counts and per-table checksums for the fixtures (7 tables, order-independent md5 of every row) → `::test_build_from_silver_matches_load_matches`. I checked by hand that the checksum changes when one value changes.
     - a duplicated match in Silver fails the build → `::test_duplicated_match_in_silver_fails_the_build` (`duckdb.ConstraintException` from the `dim_match` key)
- Open issues / decisions needed:
  - **Signature.** The card says `build_from_silver(silver_dir)`; dossier §5.5 says `build_from_silver(silver_dir, register_dfs)`. I made `register_dfs` optional, so both calls work, and added an optional `settings` (default `get_settings()`, same as the rest of the codebase) for `tmp_dir`. I read this as compatible, not a conflict. The governor may want to align the card text.
  - **`build_marts()` is not called inside `build_from_silver`.** It is listed in §5.5 "as today", and today the caller runs it after `load_matches`. M0b.8 must call `loader.build_marts()` after `build_from_silver`.
  - **`memory_limit` is a constant, not a setting.** `Settings` has no memory field and `src/config.py` is outside Owns. It is the same `2GB` as `silver.MEMORY_LIMIT`, defined again here rather than imported, so `builder` does not depend on `publisher`. If the owner wants it configurable, that is a `config.py` change.
  - **Risk for M0b.8 on full data: `dim_venue` under plain `INSERT`.** The derivation is today's `SELECT DISTINCT md5(venue_name), venue_name, city`. If one venue name appears with two different `city` values, it yields two rows with the same `venue_id`, and the build now fails loudly. Under `INSERT OR REPLACE` that would also have been a same-statement conflict, but I did not verify DuckDB's behaviour for that here. Tests may not read `data/`. Watch the first full-data build. A fix would change the derivation (M1 changes venue ids anyway) and needs a ruling.
  - Duplicate fact rows (same `delivery_id` twice) no longer fail on insert; D-10 moves that check to the quality gates (`delivery_grain_uniqueness`, plus M0b.6's new grain gates in lane B). A duplicated **match** still fails at `dim_match`.
  - `src/publisher/main.py` and `src/api/routes/internal.py` still call `load_matches` once per fresh DB, so plain `INSERT` does not affect them. Lane B deletes `internal.py` (M0b.9), and M0b.8 replaces the `main.py` flow.
  - `08_AGENTIC_GENAI_REBUILD_BRAINSTORM.md` was already untracked before this session. Not part of this task.
- Next step for whoever picks this up: land with `kura` (`land M0b.5`). Lane A then waits for lane B (M0b.7) to merge before M0b.8.
- Proposed commit: `feat(M0b): Gold from Silver — shared mapping, plain INSERT, no fact keys [M0b.5]` — trailer `Module: M0b.5`
  - Files: `src/builder/loader.py`, `src/builder/schema.py`, `tests/test_loader_and_schema.py`, `.agents/handoffs/M0b.5.md`

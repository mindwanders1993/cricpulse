# Handoff: M0b.9 (B)
- Branch / worktree: `feat/M0b-lane-b` · `/Users/mrrobot/Desktop/Projects/cricpulse-M0b-b`
- State: done
- What changed:
  - `src/snapshot.py`: adds `resolve_snapshot_path(settings) -> Path | None`. The order is: the `snapshot_path` setting if it is non-empty (`""` means unset); otherwise `data_dir / LatestInfo.path` from `LATEST.json`; otherwise `None`. It imports `Settings` from `src.config`. No import cycle, since `config` does not import `snapshot`.
  - `src/api/app.py`: lifespan target = the explicit `db_path` arg, else `resolve_snapshot_path(settings)`, else today's `published/cricket_latest.duckdb` fallback. The fallback stays until M0a. The `internal_router` import and include are removed.
  - `src/api/routes/internal.py` and `src/api/auth.py`: deleted.
  - `src/api/routes/__init__.py`: `internal_router` export removed.
  - `src/api/schemas.py`: `SyncDailyResponse` removed. Nothing else changed.
  - `tests/test_api_and_agents.py`: `test_api_internal_sync_endpoint` removed. The `get_settings` import was used only by that test, so it went too. No other test changed.
  - `tests/test_snapshot.py`: 4 tests added. The existing 6 are unchanged.
- Verification run (after the last file change):
  - `python -m pytest tests/test_snapshot.py tests/test_api_and_agents.py -q` gave **25 passed**, exit 0.
  - `grep -rn "sync-daily\|verify_sync_token" src tests` found nothing (grep exit 1).
  - `python -m pytest -q` gave **64 passed** (61 before, minus the 1 removed sync test, plus 4 new), exit 0. The 1 warning (Starlette `httpx` deprecation) was there before this change.
  - `ruff check src tests && ruff format --check src tests` is clean, exit 0.
- Done-when lines met (subtasks):
  1. Resolver: `src/snapshot.py::resolve_snapshot_path`. Covered by `test_snapshot.py::test_resolve_prefers_snapshot_path_setting`, `::test_resolve_uses_latest_json_when_setting_empty` and `::test_resolve_none_without_setting_or_latest`.
  2. Lifespan uses the resolver, and the fallback is kept: `src/api/app.py`. Covered by `test_snapshot.py::test_app_starts_on_snapshot_named_by_latest_json`. Every `api_client` test still passes, so the explicit `db_path` path still works.
  3. Internal route, auth helper, schema and test deleted: the files above. The Verify grep returns nothing.
  4. Tests:
     - Resolver precedence (env, then `LATEST.json`, then `None`): the three resolver tests above.
     - App starts on a `LATEST.json`-named fixture DB: `test_app_starts_on_snapshot_named_by_latest_json`. It builds `snapshots/cricket_v20261103T0230Z.duckdb` holding a marker table, writes `LATEST.json`, and asserts that `app.state.db` reads the marker.
- Open issues / decisions needed:
  - **`scripts/run_uat.py` scenario 8 still POSTs `/api/v1/internal/sync-daily` and asserts `200` or `401`.** The route is now gone, so that call returns 404 and the UAT harness will report scenario 8 as FAIL. The script is outside this card's Owns and outside the Verify grep (`src tests`), so I did not touch it. Correct a card before M0b.11 (UAT) runs: remove scenario 8, or replace it with a check that the route is gone (404).
  - The dossier §5.8 signature says `-> Path`. The card says `-> Path | None`. I followed the card, because `None` is what lets the "current fallback stays" rule in the same section work until M0a. Worth aligning the dossier text.
  - The `sync_secret_token` setting is still in `src/config.py:22`. Dossier §5.8 lists it as removed. It is not in this card's Owns, and §5.9 and M0b.2's card both put setting removal in M0b.8. Nothing reads it now.
  - `create_app()` reads the `lru_cache`d `get_settings()` once, at factory time. The app-start test monkeypatches `data_dir` and `snapshot_path` on that cached object, and monkeypatch restores them.
- Next step for whoever picks this up: land with `kura` (`land M0b.9`), then M0b.6 on lane B.
- Proposed commit: `feat(M0b): API reads LATEST.json; sync endpoint and hot swap removed [M0b.9]`, trailer `Module: M0b.9`
  - Files: `src/snapshot.py`, `src/api/app.py`, `src/api/routes/__init__.py`, `src/api/schemas.py`, `src/api/routes/internal.py` (deleted), `src/api/auth.py` (deleted), `tests/test_snapshot.py`, `tests/test_api_and_agents.py`, `.agents/handoffs/M0b.9.md`

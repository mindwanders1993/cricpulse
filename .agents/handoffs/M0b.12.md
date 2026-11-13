# Handoff: M0b.12 (A)
- Branch / checkout: `feat/M0b-trustworthy-data-pipeline`, main checkout `/Users/mrrobot/Desktop/Projects/cricpulse`
- State: done
- Colour: 🟡
- What changed:
  - `src/parsers/match_parser.py`: if a player id turns up under both teams in `info.players`, the parse raises `ValueError("player listed for both teams: <name>")`, and the archive reader quarantines the match (D-16(c), D-5)
  - `tests/test_match_parser.py`: two regression tests. The parse raises with the exact message, and `parse_to_staging` quarantines the match while the other match parses
  - `tests/fixtures/both_teams_1229824.json` (new): the real Cricsheet match 1229824 with its meta and info unchanged and each innings cut to its first over
- Verification run: `source .venv/bin/activate && ruff check src tests && ruff format --check src tests && python -m pytest tests/test_match_parser.py -q && python -m pytest -q`. Results: ruff "All checks passed!", "59 files already formatted", match parser 6 passed, full suite 146 passed and 2 skipped (the network tests, which already skipped before), exit code 0
- Done-when lines met:
  - Both pairs named with their cause: met. Both pairs are cause **(c)**:
    1. Match **1130677**, Syed Mushtaq Ali Trophy, Central Zone, 9 Jan 2018. **KV Sharma** (id `119678fd`) is listed for **Vidarbha** and for **Railways**. The registry has 21 names for 22 player slots, so one name maps to one id. He bats in both innings and bowls for Railways.
    2. Match **1229824**, Isle of Man tour of Guernsey, 21 Aug 2020. **J Butler** (id `efcb778e`) is listed for **Isle of Man** and for **Guernsey**. The registry has one id for that name. He bats and bowls for Guernsey.
    - Why this is not (a): the id comes straight from Cricsheet's own `info.registry.people`, which is keyed by name. Our name fallback is not involved.
    - Why this is not (b): the name appears once on each of two teams, not twice on one team.
    - In memory, with nothing written, both real files now raise "player listed for both teams: KV Sharma" and "player listed for both teams: J Butler".
  - Each cause has a test: met. Cause (c) is covered by `test_player_listed_for_both_teams_raises` and `test_player_listed_for_both_teams_is_quarantined_others_parsed`.
  - The full suite passes: met (146 passed, 2 skipped).
- Proof: output only (the Kaizen card's Proof is "none, output only"; no screen changed)
  - A match that lists one player for both teams is now set aside with the reason "player listed for both teams: <name>", so no player shows up twice in one match.
  - Works: yes. Both real matches (1130677 KV Sharma, 1229824 J Butler) are set aside in the parse, and every test passes.
  - Next: M0b.11 runs the full build again (U-1). It must start from an empty Silver. See open issue 1.
- Followed the code, not the card: none
- Open issues / decisions needed:
  1. **The rebuild has to start from an empty Silver, or U-1 stops at the same gate again.** M0b.11's failed run had already merged Silver and saved the manifest (steps 6–7 come before the gates). That left `data/silver/match_players.parquet` holding the two bad pairs, and `data/silver/manifest.parquet` marking 1130677 and 1229824 current at `PARSER_VERSION = 1`. A plain `run --archive all_json` skips both matches, so the old rows stay. `--reparse-all` doesn't help either: a quarantined match is never staged, and `silver.merge` only drops rows for staged ids. Bumping `PARSER_VERSION` has the same problem, so I left it at 1 (its comment says M1 bumps it). Nothing was ever published, so the owner or governor can clear `data/silver/` (the tables and `manifest.parquet`) before U-1. That is a `data/` write, so this card did not do it.
  2. **This is a gap in the pipeline (🔴 `src/publisher/`, not this card's file).** If a match already in Silver later fails to parse, its old rows stay in Silver and reach Gold. Today this only matters for the case above, but the governor may want a D-row: either a quarantined id drops its Silver rows, or it stays as it is.
  3. These are most likely two different people who share a short name. Cricsheet's registry keys ids by name, so it cannot tell them apart. D-16 rules out picking a team, so both matches are out of every figure until Cricsheet fixes the files. The run report lists them under `quarantined`, and 2 out of about 23k is well inside `quarantine_bounded`.
  4. The tree also holds files this card does not own: M0b.11's unlanded `scripts/run_uat.py`, `docs/uat/M0B-UAT.md`, `README.md`, and an untracked `08_AGENTIC_GENAI_REBUILD_BRAINSTORM.md` that was already there. I left all of them alone.
- Proposed commit: `fix(M0b): quarantine a match that lists one player for both teams (D-16c) [M0b.12]`. Trailer `Module: M0b.12`

# R — Local, fully open-source CricPulse

**What it does:** CricPulse becomes a personal app for the owner alone, on the owner's Mac. The chat now runs on
the local model behind the Moonhopper gateway, instead of OpenRouter and Gemini. There is no paid service and no
Google Cloud. The design documents now describe this.

**PR title:** `feat(R): CricPulse goes local and fully open source — chat on the Moonhopper model, documents rewritten`
**Target:** `dev` · **Branch:** `feat/R-local-oss` · **Colour:** 🔴 (`src/config.py`)

## What changed, in the app's words

- **The chat talks to your own model.** Requests go to Moonhopper's LiteLLM gateway at `127.0.0.1:4000/v1`, model
  `cricpulse-local` (Qwen3.5-9B 8-bit on MLX). That model has no cloud fallback. The key is `LLM_API_KEY` in `.env`.
- **Honest when the model is off.** If the gateway or the model behind it is down, the chat says "Local model not
  running — run `make start` in Moonhopper". Before, it gave canned mock text. The mock now runs in tests only.
- **Only this Mac can reach the app.** uvicorn binds `127.0.0.1` instead of `0.0.0.0`.
- **Cloud scripts gone.** `scripts/deploy.sh` and `scripts/infra_m0b.sh` are deleted; git history keeps them.
- **Documents say what we build now.** The PRD, HLD, LLD, implementation plan and AGENTS.md describe a personal,
  local, open-source tool. D-1 to D-5, ADR-2, ADR-4 and ADR-7 keep dated "superseded 17 Nov 2026" notes.
  - M5 becomes "Eval gate and daily use".
  - M7 drops the public launch.
- **The review and the plan are included:** `docs/reviews/PRODUCT-REVIEW-2026-11-16.md` (live test: 5 of 26 right,
  seven causes) and `docs/reviews/PLAN-LOCAL-OSS-REVAMP-2026-11-17.md`.

## Gate

- `ruff check .`, `ruff format --check .`: clean.
- `python -m pytest -q`: 203 passed, 2 skipped (194 before; 9 new tests in `tests/test_llm_client.py`).
- R.2's red-zone diff was read by the governor for security. The key is never logged. Old `GEMINI_API_KEY` lines are
  ignored (`extra="ignore"`).

## Tasks

| Task | What | Colour |
|---|---|---|
| R.1 | Documents rewritten for personal, local use | 🟢 |
| M.1 | Moonhopper: `cricpulse-local` with no cloud fallback; damaged gateway DB backed up and reset (Moonhopper repo, not in this PR) | 🟡 |
| R.2 | App on the local gateway, honest "not running" reply, localhost bind | 🔴 |

## Still the owner's

- Commit Moonhopper's `config/litellm-config.yaml` change in that repo.
- Put `LLM_API_KEY=<gateway key>` in `.env`.
- Merge this PR in GitHub.

## Not in this PR

- The wrong answers from the review. Their fixes are M0a, M1 and M2.
- Mentions of the deleted scripts in `README.md`, the dojo skill and a comment in `.github/workflows/deploy.yml`.
- `.env.example` still lacks `LLM_API_KEY`.
- The 30 s call timeout.

# Plan: CricPulse goes local and fully open source

**Date:** 17 Nov 2026 · **Status:** waiting for the owner's yes · **Follows:** `PRODUCT-REVIEW-2026-11-16.md` §12

## Your answers (17 Nov 2026)

| # | Question | Your answer | What it changes |
|---|---|---|---|
| 1 | Weekly slices or one module at a time? | One module at a time | The ladder M0a → M12 stays. From M2, each module still ends with the eval score (DoD row 4). |
| 2 | Free-form SQL on the public path? | Building for me | No public path. `run_sql` stays available to you. Typed tools still come first, because small local models write worse SQL than Gemini. |
| 3 | Ambiguous question: ask or assume? | Ask | FR-3 holds as written: the bot asks before it answers. |
| 4 | First audience? | Me | One user, on this laptop. D-1 becomes "the owner". |
| 5 | ₹1,000 a month cap? | Personal, local LLMs | No paid service anywhere. A latency target replaces the cost cap. |

---

## The one page

**What you get, in the order it lands**

1. You start Moonhopper (`make start`) and the app, and chat with no internet and no bill. CricPulse uses your
   existing Moonhopper gateway instead of a new model server.
2. The documents say what we now build: a personal tool on your Mac, not a public site.
3. Every answer still shows its receipt and its numbers still come from the database. The model only changes
   where it runs.
4. The 26 questions from the review pick the model: the one that answers the most right, fast enough, wins.

**What we are not doing**

- No Google Cloud: no Cloud Run, Cloud Storage, Secret Manager or Scheduler.
- No rate limits, spend cap or public launch work. M5 becomes "eval gate and daily use".
- No new data sources in this plan. No new tracing server: Moonhopper's gateway already logs every model call
  (tokens, latency, full prompt) to its Postgres.
- This plan does not fix the wrong answers. The seven causes in the review stand. Those fixes are M0a, M1 and
  M2, in order.

**What could go wrong**

- Qwen3.5-9B is a small model. In the 17 Nov test it called the tools correctly, but it guessed "Test" for
  "Smith's average" instead of asking. So "ask when ambiguous" must be enforced by the tools (a missing format
  returns "ask the user"), not left to the model.
- Moonhopper's fallback chain sends a request to cloud models (Experiential Labs, OpenRouter) when the local model
  is busy or down. CricPulse must use a local-only model name, or it is not fully local.
- Moonhopper's gateway does not start today: its Postgres data is damaged (details below).
- Memory is tight on 32 GB. The model, the DuckDB snapshot, Docker and a browser all share it. The 8-bit model
  takes about 10 GB.
- Answers are slower: each model step took 4–8 seconds in the test, so a 3–4 step answer takes 15–30 seconds.
- Local model names move monthly. The eval set decides, not a blog post.
- Riskiest part: 🔴. The model settings live in `src/config.py`, a red zone.

**Your decisions**

1. **Which model to start with:** Moonhopper's Qwen3.5-9B 8-bit, which is already downloaded and passed the
   tool-call test. A bigger MLX model, such as a 30B-class mixture of experts at 4-bit (about 20 GB), is the
   challenger in M2. The eval picks. *Recommended.*
2. **The two Google Cloud scripts** (`scripts/deploy.sh`, `scripts/infra_m0b.sh`): delete them. Git history keeps
   them if you ever go public. *Recommended.*
3. **Moonhopper's damaged gateway database:** reset it. This loses the call logs from before 5 Oct 2026, and
   gives CricPulse a local-only model name with no cloud fallback. This is work in the Moonhopper repo, not
   CricPulse. *Recommended.*

---

## The new stack: all open source, all local

| Layer | Before | After | Instead of X, because Y |
|---|---|---|---|
| Data | Cricsheet → Polars → DuckDB | **Same** | Already open source and local |
| Data refresh | Cloud Run Job, nightly | `cricpulse` CLI, run by hand (or a macOS launchd job later) | Instead of a cloud job, because there is one machine |
| Snapshot delivery | Baked into a container image (ADR-4) | Read from `data/` through `LATEST.json` | Instead of an image, because no deploy step exists |
| Model runtime | OpenRouter (paid gateway) | **Moonhopper**: LiteLLM gateway (`:4000`, MIT) → `mlx_vlm.server` 0.7.3 (`:8080`, MIT) on Metal | Instead of a new llama.cpp server, because Moonhopper is already set up, speaks the same OpenAI-style API and logs every call |
| Model | Gemini 2.5 Flash | Qwen3.5-9B (Apache 2.0), 8-bit MLX, about 10 GB; a bigger MLX model as challenger | The eval set picks (HLD §6.2 rule kept) |
| Agent | Regex supervisor (today); PydanticAI planned (ADR-6) | **PydanticAI** (MIT) pointed at the gateway, `http://127.0.0.1:4000/v1` | ADR-6 stands; it was chosen as provider-neutral |
| Evals | Planned | **pydantic-evals** (MIT), seeded with the review's 26 questions | Same family as the agent; runs offline |
| Traces | Cloud Logging | Moonhopper's LiteLLM logs in Postgres 16 (dashboard at `:4000/ui`), plus CricPulse's own tool-call log | Instead of self-hosted Langfuse, because Moonhopper already logs every call |
| UI | FastAPI + static chat page | **Same**, bound to `127.0.0.1` only | Nothing outside the laptop can reach it |
| Secrets | Secret Manager, `.env` | Only the gateway's local key, which you copy into CricPulse's `.env` | Nothing paid, and nothing leaves the laptop |

Hardware checked on 17 Nov 2026: Apple M5, 32 GB memory, 10 cores, 100 GB free disk.

### Moonhopper check, 17 Nov 2026

| Check | Result |
|---|---|
| Local model server | ✅ `mlx_vlm.server` loaded Qwen3.5-9B 8-bit on `:8080`. |
| Tool calls, CricPulse-shaped (`resolve_entity` → `query_metric`) | ✅ "How many ODI runs has Virat Kohli scored?" became `resolve_entity("Virat Kohli", player)`, then `query_metric(id, runs, ODI, male)`. Clean JSON; 7.7 s and 6.7 s. |
| Asks when ambiguous | ❌ "What is Smith's average?" assumed Test format and did not ask, even though the prompt told it to ask. The tools must enforce this. |
| Gateway (`make start`) | ❌ Postgres will not start: *"could not locate a valid checkpoint record"*. Its data was interrupted on 5 Oct 2026, so LiteLLM never starts. The volume was left untouched, and the stack was stopped after the test. |
| Cloud fallback | ⚠️ Both local model names fall back to Experiential Labs and OpenRouter models (`config/litellm-config.yaml`, `router_settings.fallbacks`). |
| Network exposure | ⚠️ `mlx_vlm.server` listens on `0.0.0.0:8080`, so other devices on your Wi-Fi can reach it. |

---

## What changes in each document (applied on your yes)

- **PRD** `docs/01`:
  - §0.3 principle 4 becomes "Runs on my laptop. No paid service."
  - Principle 5 becomes "Licence settled before anything is shared".
  - §0.4 D-1 to D-5 take the answers above. D-4: the `cricketdata` CSV is fine for personal use; the licence is
    parked until anything is shared.
  - §1.4: the cost row becomes "no paid API calls", and latency becomes ≤ 30 s for a full answer.
  - §7: rewrite the cost, privacy, attribution and availability rows.
  - §9: R1 becomes "daily use by the owner". R2's public launch is parked.
- **HLD** `docs/02`:
  - The diagram in §1 changes: OpenRouter becomes the local model server.
  - §6.2 covers the model runtime and candidates.
  - §7 becomes a local topology instead of GCP.
  - §8 security shrinks to the localhost bind, the guard and the read-only DB.
  - §9 cost becomes a memory and latency budget.
  - §10 traces go to a local file.
  - ADR-2, ADR-4 and ADR-7 are superseded, with dated notes.
- **Plan** `docs/04` §2:
  - M5 becomes "Eval gate and daily use": traces, eval gate and model choice.
  - M7 drops "public launch".
  - M0a keeps the guard fix (invariant: one door) and adds the localhost bind.
- **AGENTS.md** Kaizen card:
  - "What this is" becomes a personal, local cricket assistant.
  - *Run it* gains the model start command.
  - The `gcloud` line goes.
- **Memory:** the direction note moves from "public" to "personal, local".

## Cards (after M0b is sealed, before M0a; M.1 before R.2)

| Card | Lane · colour | Owns | Done when | Verify |
|---|---|---|---|---|
| **R.1 Documents** | docs · 🟢 · `sonnet`/`medium` | `docs/01…`, `docs/02…`, `docs/03…` (storage, `llm.py`, limits and config rows), `docs/04…` §2 and §3, `AGENTS.md` Kaizen card | Every edit listed above is made. In `docs/03`, `llm.py` builds PydanticAI on the Moonhopper gateway, and GCS and OpenRouter config rows are marked superseded. OpenRouter, Cloud Run and GCS appear only on lines that also say "Superseded". AGENTS.md invariant 2 ("No GCS SDK calls") stays as it is, because it is still a live rule | `git grep -n -i -e openrouter -e "cloud run" -e gcs -- docs/0*.md AGENTS.md \| grep -v -i -e superseded -e "No GCS SDK calls"` prints nothing |
| **M.1 Moonhopper** *(Moonhopper repo)* | gateway · 🟡 · `opus`/`high` | `config/litellm-config.yaml` (Moonhopper), the Docker volume `litellm_postgres_data` | First, back up the damaged volume to `~/Backups/moonhopper/litellm_postgres_data-20261117.tar.gz`, so it can be restored. Then reset it, so Postgres starts clean. A new `cricpulse-local` model maps to `mlx-community/Qwen3.5-9B-MLX-8bit` on the MLX server and has **no** entry in `router_settings.fallbacks`. The existing models and fallbacks are unchanged. Moonhopper's `.env` and `.env.example` files are not read or touched. Nothing is committed (the owner commits in Moonhopper) | `make check` passes. After `make start`, `make status` shows LiteLLM up and a `cricpulse-local` call returns text. With MLX stopped, a `cricpulse-local` call fails instead of reaching a cloud model. Finally `make stop` |
| **R.2 Local model** | app · 🔴 · `opus`/`xhigh` | `src/config.py`, `src/ai/gemini_client.py`, `scripts/run_local.sh`, `tests/test_api_and_agents.py` (or a new `tests/test_llm_client.py`), deletes `scripts/deploy.sh` and `scripts/infra_m0b.sh` (decision 2) | Settings gain `llm_base_url` (default `http://127.0.0.1:4000/v1`), `llm_model` (default `cricpulse-local`) and `llm_api_key` (default empty, read from `.env`). The class keeps the name `GeminiClient`, instead of a rename, because six files outside Owns import it. The mock runs only when `app_env == test`. If the gateway cannot be reached, the reply says "Local model not running — run `make start` in Moonhopper" instead of canned text. uvicorn binds `127.0.0.1` instead of `0.0.0.0` (`run_local.sh:14`). Tests cover the request URL, model and auth header with httpx mocked at the transport, and the "not running" message | `python -m pytest -q` and the card's Checks pass. The live call is the owner's hand check: Moonhopper's `make start`, put the gateway key in CricPulse's `.env`, `bash scripts/run_local.sh`, ask one question in the chat |

Left as they are, out of scope: `.github/workflows/deploy.yml`, `Dockerfile` and `src/publisher/rollout.py` (it already does nothing when `rollout_service` is empty). They retire with the HLD's ADR-2 and ADR-4 notes later.

R.2 does not wire in PydanticAI; that is M2. It only makes today's app run on a local model, so you can use it
while M0a and M1 fix the numbers.

Sources for the model picks (checked 17 Nov 2026; names change fast):
- [Best local LLM for 32 GB RAM](https://openclawdc.com/blog/best-local-llms-32gb-ram/)
- [Best local LLM for agents and tool calling](https://vdf.ai/blog/best-local-llm-for-agents-tool-calling/)
- [Ollama vs llama.cpp vs MLX on Apple Silicon](https://antekapetanovic.com/blog/qwen3.5-apple-silicon-benchmark/)

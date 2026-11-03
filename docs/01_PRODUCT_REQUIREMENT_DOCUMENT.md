# CricPulse — Product Requirement Document

**Status:** Draft v0.1 · **Date:** 26 Oct 2026 · **Scope:** Non-commercial, public
**Next documents:** `02_HIGH_LEVEL_DESIGN.md` → `03_LLD_*.md` → `04_IMPLEMENTATION_PLAN.md` → `features/M<n>-*.md`

---

## 0. About This Document

### 0.1 Purpose
This document says **what** CricPulse is and **why**. It does not say how it is built.
The HLD covers the architecture. The LLDs cover each module.

### 0.2 The document ladder (same approach as HoppingCars)

```
PRD (what & why) ─▶ HLD (architecture + diagram) ─▶ LLD (per module)
      ─▶ Implementation plan (modules M0, M1 …) ─▶ Module dossier ─▶ Task cards (M1.1, M1.2 …)
      ─▶ Build ─▶ Review ─▶ UAT ─▶ Sealed
```

- One module at a time. A module is a vertical slice: data, tools, API, chat UI, tests.
- Each module splits into tasks. Each task splits into subtasks with a "Verify" step.
- Inputs used for this draft: `08_AGENTIC_GENAI_REBUILD_BRAINSTORM.md`, the branch draft
  `00_PRD_AND_HLD.md` (`claude/practical-albattani-scr0e1`), and its review.
- When this PRD is approved, it replaces the product parts of the root docs `01`–`07`.

### 0.3 Product principles (they settle arguments)
1. **Numbers come from the database, never from the model.**
2. **Every answer shows its receipt** — the query, row count, data cutoff and sources.
3. **Chat is the only surface.** Features are things you ask for, not pages.
4. **Cheap to run.** A hard monthly cost cap, enforced in code.
5. **Licensed data only at public launch.** Every source has a known licence and attribution.

### 0.4 Decisions

**Status (26 Oct 2026):** the owner asked to proceed, so D-1 … D-5 are taken at the recommended
values below. Any of them can still be changed.

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D-1 | Who is v1 for? | Fans & writers · Coaches & analysts · Both | **Fans & writers** |
| D-2 | How do people get in? | Open + rate limits · Login required | **Open, with per-user limits and a daily spend cap** |
| D-3 | Languages at launch | English only · English + Hindi · Four Indian languages | **English at launch, Hindi next** |
| D-4 | Playing-style data (batting hand, bowling style) | `cricketdata` CSV · Paid API · Curate our own · Skip at launch | **CSV while building; settle the licence before public launch** |
| D-5 | Monthly running-cost cap | ₹1,000 · Other | **₹1,000** |

Architecture choices (DuckDB vs Postgres, agent framework, UI tech) are **HLD decisions**, not PRD ones.

---

## 1. Product Overview

### 1.1 Vision
A cricket chat app where every number comes from verified ball-by-ball data,
and the AI only explains — it never invents.

### 1.2 The problem
- Fans get scorecards. Deep stats sit behind tools that need SQL or a subscription.
- Stat sites show numbers without explaining them.
- AI chatbots explain fluently but invent numbers. Nobody shows proof.

### 1.3 What we build
- One screen, one chat box.
- Ask in plain words. Get a short insight, key numbers, a chart, a table and the receipt.
- Follow-up suggestions keep the conversation going.

### 1.4 Success measures (first 90 days after public launch — proposed)

| Measure | Target |
|---|---|
| Answers whose numbers all appear in tool output (checker pass rate) | 100% shipped; regenerations logged |
| Correct answers on the evaluation set | ≥ 90% |
| Answers carrying a full receipt | 100% |
| Time to first token / full answer (p95) | ≤ 2 s / ≤ 10 s |
| Monthly running cost | ≤ cap (D-5) |

---

## 2. Users

### 2.1 Personas

| Persona | Needs | Example question |
|---|---|---|
| **Fan** | Settle debates with proof | "Kohli vs Smith in ODI chases since 2015?" |
| **Writer / creator** | Quotable stats with sources | "Best death-over economy in IPL 2024, min 20 overs?" |
| **Coach / analyst** *(later, D-1)* | Matchups and phase splits | "How does Buttler score against left-arm spin in the powerplay?" |

### 2.2 Top jobs to be done
1. Look up a player's numbers in a format, period or tournament.
2. Compare two players or teams.
3. Find records and leaderboards.
4. Break down matchups — batter vs bowler, vs bowling style, by phase.
5. Understand a venue — par score, chase record, toss effect.
6. Understand a rule or a piece of cricket history.

---

## 3. Data Domains — What the Bot Knows

| Domain | Source | Licence | Release |
|---|---|---|---|
| Ball-by-ball stats (22,817 matches) | Cricsheet | ODC-By (attribution) | R1 — have |
| Tournaments, stages, events | Cricsheet raw JSON (on disk, not parsed yet) | ODC-By | R1 |
| Player profiles (born, country, role) | Wikidata | CC0 | R2 |
| Playing styles (hand, bowling type) | D-4 | ⚑ unclear for `cricketdata` | R2 |
| Venues (location, curated facts) | Curated sheet | Ours | R2 |
| Weather at venue | Open-Meteo | CC BY, non-commercial | R4 |
| Rules & cricket knowledge | Our own explainers + Wikipedia | Ours / CC BY-SA | R3 |
| News & live context | Web search | Provider terms (no storage on basic plans) | R3, optional |

**Rule:** a domain goes public only when its licence and attribution are settled.

---

## 4. Features (Functional Requirements)

| ID | Feature | What the user gets | Release |
|---|---|---|---|
| FR-1 | **Ask the stats** | Question → insight + stat tiles + chart + table | R1 |
| FR-2 | **Receipts** | Query, row count, data cutoff, sources under every answer | R1 |
| FR-3 | **Clarify, don't guess** | Bot asks when a name, format or period is ambiguous | R1 |
| FR-4 | **Conversation memory** | Follow-ups like "and in Tests?" work | R1 |
| FR-5 | **Follow-up chips** | 3 suggested next questions | R1 (exists) |
| FR-6 | **Streaming answers** | Words appear as they are written | R1 |
| FR-7 | **Records & leaderboards** | Top-N with filters and minimum qualifiers | R1 |
| FR-8 | **Matchups** | Batter vs bowler; vs bowling style | R1 / R2 (style) |
| FR-9 | **Phase splits & venue profiles** | Powerplay/middle/death; par score, chase record | R2 |
| FR-10 | **Player profiles** | Who they are, plus their headline stats | R2 |
| FR-11 | **Rules & knowledge answers** | Cited explanations | R3 |
| FR-12 | **Hindi answers** | Same answer, in Hindi | R3 (D-3) |
| FR-13 | **Match preview card** | Head-to-head, venue, key matchups — in chat | R4 |
| FR-14 | **Win probability & what-if** | "What if they need 40 off 18?" | R4 |

---

## 5. How the Bot Answers

### 5.1 Answer anatomy
1. One-line headline insight.
2. Two to four stat tiles.
3. A chart when it helps; a table always.
4. The receipt (FR-2).
5. Follow-up chips (FR-5).

### 5.2 When the bot cannot answer
- Data not in scope → say so, and say what data exists.
- Query fails after one retry → say so plainly. Never guess a number.

### 5.3 Topic guard
- No betting, odds or real-money fantasy advice. (India's 2025 Online Gaming Act bans these.)
- Off-topic questions get a short, polite redirect.

### 5.4 Tone
Plain, short sentences. Numbers first, adjectives last.

---

## 6. Trust & Cricket-Correctness Requirements

| ID | Requirement |
|---|---|
| TR-1 | Every number in an answer must appear in a tool's output. A checker enforces it; failures regenerate. |
| TR-2 | The database is read-only to the chat. SQL cannot read files or reach the network. |
| TR-3 | Text from the web is data, never instructions. |
| TR-4 | Bowling economy excludes byes and leg-byes. |
| TR-5 | "Retired hurt" is not a dismissal. |
| TR-6 | Super overs are kept apart from the main innings stats. |
| TR-7 | DLS-affected matches are flagged. |
| TR-8 | Every answer shows the data cutoff date. |
| TR-9 | A data update never shrinks or corrupts the live data (fixes the known delta bug). |

---

## 7. Non-Functional Requirements

| Area | Requirement |
|---|---|
| Cost | Monthly cap (D-5) enforced by a daily spend limit; per-user and per-IP rate limits |
| Latency | See §1.4 |
| Availability | Best effort; a cold start must not serve an empty database |
| Security | Read-only data path; hardened SQL guard; secrets outside the image; CORS locked down |
| Privacy | No accounts in v1 (D-2); chat logs kept 30 days for evaluation, no personal data |
| Attribution | Cricsheet, Open-Meteo, Wikipedia credited in the UI |
| Quality | An evaluation set of real questions runs before each release |
| Observability | Per-answer trace: tools called, tokens, cost, latency, checker result |

---

## 8. Out of Scope
- Betting, odds, real-money fantasy.
- Ball-tracking (Hawk-Eye-style) data.
- Phone-camera coaching.
- Dashboard pages outside the chat.
- Live ball-by-ball scores (revisit after R4).

---

## 9. Release Cut

| Release | Name | What ships | Who sees it |
|---|---|---|---|
| **R0** | Make it correct | The three blocking bugs (08 §9): delta rebuild, atomic publish, empty/open deploy. Plus `sort_by` injection, SQL file/network access off, a lockfile. | Internal |
| **R1** | Ask the stats | FR-1 to FR-8 (no style matchups), TR-1 to TR-9, rate limits + spend cap, evaluation set | Private beta |
| **R2** | Public launch | Tournaments, player profiles, playing styles (licence settled), phase/venue splits, attribution | Public |
| **R3** | Knows cricket | Rules & knowledge, Hindi, optional news search | Public |
| **R4** | Predicts | Match preview card, win probability, what-if | Public |

The implementation plan turns each release into modules (M0, M1 …).

---

## 10. Risks & Assumptions

| Risk | Mitigation |
|---|---|
| Playing-style data licence | D-4; skip styles at launch if unresolved |
| LLM cost on a public endpoint | Rate limits, spend cap, cheapest model that passes the evaluation set |
| Model invents or mistranslates numbers | TR-1 checker, including Hindi answers |
| Web search terms (storage limits, no free tier) | Optional feature; cache only derived facts |
| Single developer time | One module at a time; seal before starting the next |

---

## 11. Glossary
- **Receipt** — the proof shown under an answer: query, row count, cutoff, sources.
- **Checker** — a step that rejects an answer whose numbers are not in the tool output.
- **Phase** — powerplay, middle overs, death overs.
- **Sealed** — a module that passed every gate in the implementation plan.

---

## Appendix A — Evaluation Seed Questions *(to grow into the evaluation set)*
1. Most ODI runs by Virat Kohli in chases since 2015?
2. Best IPL death-over economy in 2024, minimum 20 overs?
3. Jasprit Bumrah vs Steve Smith in Tests — balls, runs, dismissals?
4. Highest successful T20I chase at the Wankhede?
5. Who has the most Test five-wicket hauls in Asia?
6. What is the follow-on rule? *(R3)*

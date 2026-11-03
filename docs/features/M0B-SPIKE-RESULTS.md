# M0b.1 — Spike Results: Full Build and Query Speed

**Run:** 26 Oct 2026 · MacBook, 10 CPUs, 32 GB RAM · DuckDB 1.5.5, Polars 1.44.1
**Data:** all 22,818 Cricsheet JSON files in `data/raw/match_json` (downloaded early Sep 2026)
**Scripts:** `docs/features/m0b_spike/spike.py`, `nopk_build.py` · raw numbers: `m0b_spike/results_full.json`
**Code changed:** none

---

## 1. Headline

| Question | Answer |
|---|---|
| How long is a full build? | **65 s** end to end (parse 39 s, Gold 18 s) |
| How much memory? | **5.5 GB peak** today → **~2 GB** without the fact-table keys |
| How big is the snapshot? | **1.1 GB** today → **~0.4 GB** without the fact-table keys |
| How big is Silver? | **69 MB** (Parquet, ZSTD) — tiny |
| How fast are typical questions? | **1–120 ms p95** on local disk |
| Any data problems? | **Yes — one match silently lost** (§3) |

---

## 2. Measurements

### 2.1 Build (batches of 1,000 files)

| Step | Time | Peak memory |
|---|---|---|
| Parse first 1,000 files (`parse_batch`) | 1.8 s | 475 MB |
| Parse all 22,818 → Parquet parts | 38.5 s | 662 MB |
| Compact parts → one Silver file per table | 1.4 s | 3.1 GB* |
| Gold: `fact_delivery` (`INSERT OR REPLACE`, with primary key) | 15.6 s | **5.5 GB** |
| Gold: everything else + marts + gates | 2.7 s | 5.5 GB |
| **Whole run** | **64.7 s** | **5.5 GB** |

\* DuckDB uses free RAM as cache; it stays lower when `memory_limit` is set.

### 2.2 Sizes and counts

| Table | Silver rows | Silver size | Gold rows |
|---|---|---|---|
| matches → `dim_match` | 22,818 | 0.4 MB | **22,817** |
| deliveries → `fact_delivery` | 11,539,809 | 61.5 MB | **11,539,581** |
| innings → `fact_innings` | 50,501 | 0.2 MB | **50,499** |
| wickets → `fact_wicket_detail` | 352,343 | 5.0 MB | 352,343 |
| match players → `fact_player_match` | 503,375 | 2.0 MB | 503,373 |

Snapshot: **1,089.5 MB**. Data cutoff: 2026-09-02. Parse failures: **0**.

### 2.3 Without primary keys on the fact tables

| | With keys (today) | Without keys |
|---|---|---|
| Snapshot size | 1,089.5 MB | **392–415 MB** |
| Build time (facts) | 15.6 s | **4.6 s** (all facts, `memory_limit=2GB`) |
| Peak memory | 5.5 GB | **2.1 GB** |
| Matchup p50 / p95 | 72 / 76 ms | 74 / 84 ms |
| Phase splits p50 / p95 | 84 / 106 ms | 85 / 105 ms |
| Venue profile p50 / p95 | 22 / 28 ms | 22 / 25 ms |

Same query speed. The keys only cost space, time and memory. The quality gates already check
uniqueness (`delivery_grain_uniqueness`, `dim_match_uniqueness`).

### 2.4 Query speed on the full snapshot (local disk, 20 warm runs)

| Question type | Cold | p50 | p95 |
|---|---|---|---|
| One player's batting career (mart) | 1.3 ms | 1.2 ms | 1.8 ms |
| Leaderboard, top 20 ODI run-scorers (mart) | 3.5 ms | 3.2 ms | 4.3 ms |
| Venue profile (`get_venue_phase_and_toss_profile`) | 29 ms | 27 ms | 38 ms |
| Batter vs bowler, Smith v Bumrah Tests (`get_head_to_head_matchup`) | 88 ms | 76 ms | 97 ms |
| Phase splits, Kohli T20 (`get_player_phase_splits`) | 96 ms | 100 ms | 119 ms |

---

## 3. Finding: one match is silently lost today

`211824.json` (men's ODI, Bangladesh v Australia, 2005-06-25) and `wi_211824.json`
(women's domestic, Leeward Islands v Windward Islands, 2022-06-07) **both become match id `211824`**,
because the parser strips the `wi_` prefix (`match_parser.py`, `parse_file`).
`INSERT OR REPLACE` then keeps one and drops the other: **1 match, 228 deliveries, 2 innings** gone,
with no error. Which one survives depends on file order.

25 files carry the `wi_` prefix today; only this one collides, but any new one could.

**Fix (proposed D-9):** the match id is the file name without `.json` — keep the prefix. The Silver → Gold
build uses plain `INSERT`, so a duplicate fails loudly instead of overwriting.

---

## 4. Recommendations

| # | Recommendation | Changes |
|---|---|---|
| 1 | **D-9 (new):** match id = file stem, `wi_` kept; plain `INSERT` from Silver | Dossier §5.3; cards M0b.3, M0b.5 |
| 2 | **D-10 (new):** no primary keys on Gold **fact** tables; uniqueness stays a quality gate. Dimension keys stay. | Dossier §5.5; card M0b.5 (owns `schema.py` fact DDL) |
| 3 | **Job memory 4 GiB**, DuckDB `memory_limit=2GB` + a spill directory. (8 GiB if D-10 is rejected.) | Dossier §5.10; card M0b.10 |
| 4 | **Staging batch = 1,000 files** (parse peak 662 MB) | as designed |
| 5 | **D-3 lean:** the snapshot is ~0.4 GB and local p95 ≤ 120 ms. Try read-only on the mount first; if p95 > 300 ms, bake the snapshot into the image (a 0.4 GB layer is fine). | Measured in M0b.10 |

---

## 5. Reproduce

```bash
# from the repo root, with the project venv
python docs/features/m0b_spike/spike.py "$PWD" /tmp/m0b-spike          # full run (~65 s)
python docs/features/m0b_spike/spike.py "$PWD" /tmp/m0b-spike-dry 1200 # quick check (~7 s)
/usr/bin/time -l python docs/features/m0b_spike/nopk_build.py /tmp/m0b-spike   # keyless facts
```

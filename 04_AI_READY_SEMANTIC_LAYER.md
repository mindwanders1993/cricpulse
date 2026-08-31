# 04 — AI-Ready Semantic Layer & Metric Store

> **Purpose**: Convert raw relational tables into structured, deterministic context for LLM agents, eliminating hallucinations in mathematical formulas and domain rules.

---

## 1. Why an AI-Ready Semantic Layer?

LLMs fail at SQL generation when they are forced to invent business definitions (e.g. calculating Strike Rate with or without wides, or determining which dismissals count against a bowler). 

The **AI-Ready Semantic Layer** provides:
1. **Machine-Readable YAML Metric Definitions**: Mathematical formulas locked as code.
2. **Entity Resolution & Crosswalk**: Maps informal names and abbreviations (`V Kohli`, `King Kohli`) to canonical IDs (`cricsheet_key = "483b8b64"`).
3. **Annotated DDL Catalog**: Detailed column descriptions with allowable enum values.
4. **Golden Query Store**: Verified few-shot SQL patterns for in-context learning.

---

## 2. Canonical YAML Metrics Store (`conf/semantic_catalog.yaml`)

```yaml
version: 1.0.0
domain: cricket_intelligence

metrics:
  batting_strike_rate:
    name: Batting Strike Rate
    description: Number of runs scored per 100 legal balls faced (excludes wides).
    formula: "(SUM(runs_batter) / NULLIF(COUNT(CASE WHEN is_wide = FALSE THEN 1 END), 0)) * 100"
    unit: percentage
    required_grain: [batter_id]

  bowling_economy_rate:
    name: Bowling Economy Rate
    description: Number of runs conceded per 6 legal balls bowled.
    formula: "SUM(total_runs) / NULLIF(COUNT(CASE WHEN is_wide = FALSE AND is_no_ball = FALSE THEN 1 END) / 6.0, 0)"
    unit: rate
    required_grain: [bowler_id]

  dot_ball_percentage:
    name: Dot Ball Percentage
    description: Percentage of legal deliveries that yield zero runs.
    formula: "(COUNT(CASE WHEN total_runs = 0 AND is_wide = FALSE THEN 1 END) / NULLIF(COUNT(CASE WHEN is_wide = FALSE THEN 1 END), 0)) * 100"
    unit: percentage

  boundary_percentage:
    name: Boundary Run Percentage
    description: Percentage of total runs scored solely via 4s and 6s.
    formula: "(SUM(CASE WHEN is_boundary_four THEN 4 WHEN is_boundary_six THEN 6 ELSE 0 END) / NULLIF(SUM(runs_batter), 0)) * 100"
    unit: percentage

  clutch_index:
    name: Death Over Clutch Index
    description: Batting strike rate in death overs (overs 16-20) when chasing a required run rate > 10.
    formula: "(SUM(CASE WHEN phase = 'death' THEN runs_batter ELSE 0 END) / NULLIF(COUNT(CASE WHEN phase = 'death' AND is_wide = FALSE THEN 1 END), 0)) * 100"
    unit: index

dimensions:
  phase_of_play:
    name: Match Phase
    column: phase
    allowed_values:
      - powerplay: "Overs 1 to 6 in T20 (Overs 1 to 10 in ODI)"
      - middle: "Overs 7 to 15 in T20 (Overs 11 to 40 in ODI)"
      - death: "Overs 16 to 20 in T20 (Overs 41 to 50 in ODI)"

  dismissal_kind:
    name: Dismissal Type
    column: dismissal_kind
    bowler_credited_values: ['bowled', 'caught', 'lbw', 'stumped', 'caught and bowled', 'hit wicket']
    non_bowler_values: ['run out', 'retired hurt', 'obstructing the field', 'timed out']
```

---

## 3. Entity Resolution & Crosswalk Engine

Cricsheet source files frequently use abbreviated names (`V Kohli`, `RG Sharma`, `SA Yadav`).

The Entity Resolution service automatically resolves user inputs:

```
[ User Input: "King Kohli" or "V Kohli" ]
                     │
                     ▼
  [ Entity Resolution / String Distance Matcher ]
                     │
     ┌───────────────┴───────────────┐
     ▼                               ▼
`silver.persons`             `silver.name_variations`
(full_name: 'Virat Kohli')   (alias: 'V Kohli', 'Virat Kohli')
                     │
                     ▼
   [ Canonical Identifier: cricsheet_key = '483b8b64' ]
```

### Python Entity Resolver:
```python
import duckdb


def resolve_player_identity(con: duckdb.DuckDBPyConnection, search_name: str) -> dict:
    query = """
    SELECT player_id, full_name, batting_style, bowling_style, country
    FROM gold.dim_player
    WHERE LOWER(full_name) = LOWER(?)
       OR LOWER(unique_name) = LOWER(?)
       OR player_id IN (
           SELECT player_id FROM silver.name_variations WHERE LOWER(name) = LOWER(?)
       )
    LIMIT 1;
    """
    row = con.execute(query, [search_name, search_name, search_name]).fetchone()
    if row:
        return {
            "player_id": row[0],
            "full_name": row[1],
            "batting_style": row[2],
            "bowling_style": row[3],
            "country": row[4],
        }
    return None
```

---

## 4. Few-Shot Golden Query Store (In-Context Learning)

We inject vetted Golden SQL examples into LLM prompts so the agent learns proper joins, CTEs, and filters:

### Example 1: Best Death Over Batters in T20
```sql
-- Golden Query: Top 5 Death Over Batsmen in T20 History (Min 200 balls)
SELECT 
    p.full_name,
    SUM(fd.runs_batter) AS death_runs,
    COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS death_balls,
    ROUND((SUM(fd.runs_batter)::DOUBLE / COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END)) * 100, 2) AS death_strike_rate,
    SUM(CASE WHEN fd.is_boundary_six THEN 1 ELSE 0 END) AS death_sixes
FROM gold.fact_delivery fd
JOIN gold.dim_player p ON fd.batter_id = p.player_id
JOIN gold.dim_match m ON fd.match_id = m.match_id
WHERE fd.phase = 'death'
  AND m.match_type IN ('T20', 'IT20')
GROUP BY p.full_name
HAVING COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) >= 200
ORDER BY death_strike_rate DESC
LIMIT 5;
```

### Example 2: Batter vs Left-Arm Pace Matchup Breakdown
```sql
-- Golden Query: Virat Kohli vs Left-Arm Fast Bowlers
SELECT 
    p_bowl.bowling_style,
    COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced,
    SUM(fd.runs_batter) AS runs_scored,
    COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = p_bat.player_id THEN 1 END) AS dismissals,
    ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS strike_rate
FROM gold.fact_delivery fd
JOIN gold.dim_player p_bat ON fd.batter_id = p_bat.player_id
JOIN gold.dim_player p_bowl ON fd.bowler_id = p_bowl.player_id
WHERE LOWER(p_bat.full_name) = 'virat kohli'
  AND LOWER(p_bowl.bowling_style) LIKE '%left%fast%'
GROUP BY p_bowl.bowling_style;
```

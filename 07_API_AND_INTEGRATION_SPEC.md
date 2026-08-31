# 07 — API & Frontend Integration Specification

> **Protocols**: RESTful HTTPS + WebSocket Streaming  
> **Client**: KaizenCodes Next.js Web App / Any External Client

---

## 1. REST API Endpoints Overview

Base URL: `https://cricket-api-xxxx-uc.a.run.app/api/v1`

### 1.1 Generative AI & Multi-Agent Endpoints

#### `POST /ai/query` — Natural Language to SQL & Insights
Executes an AI-driven analytical query over the cricket lakehouse with AST guardrails.

- **Request Body**:
```json
{
  "query": "Who has the highest strike rate in T20 death overs with min 100 balls in 2024?",
  "session_id": "sess_abc123",
  "include_chart": true
}
```

- **Response Body (200 OK)**:
```json
{
  "status": "success",
  "data": {
    "insight": "Heinrich Klaasen leads with an astonishing strike rate of 215.42 in death overs during 2024.",
    "sql_executed": "SELECT p.full_name, ROUND(SUM(fd.runs_batter) * 100.0 / COUNT(CASE WHEN is_wide = FALSE THEN 1 END), 2) as strike_rate FROM gold.fact_delivery fd JOIN gold.dim_player p ON fd.batter_id = p.player_id WHERE fd.phase = 'death' GROUP BY p.full_name HAVING COUNT(CASE WHEN is_wide = FALSE THEN 1 END) >= 100 ORDER BY strike_rate DESC LIMIT 5;",
    "rows": [
      {"full_name": "Heinrich Klaasen", "strike_rate": 215.42, "balls_faced": 118, "runs": 254},
      {"full_name": "Nicholas Pooran", "strike_rate": 198.65, "balls_faced": 148, "runs": 294},
      {"full_name": "Dinesh Karthik", "strike_rate": 192.11, "balls_faced": 114, "runs": 219}
    ],
    "chart_spec": {
      "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
      "mark": "bar",
      "encoding": {
        "x": {"field": "full_name", "type": "nominal", "sort": "-y", "title": "Batter"},
        "y": {"field": "strike_rate", "type": "quantitative", "title": "Strike Rate (Death Overs)"},
        "color": {"value": "#10B981"}
      }
    }
  }
}
```

---

#### `POST /ai/scout` — Tactical Matchup & Weakness Simulation
- **Request Body**:
```json
{
  "batter_name": "Virat Kohli",
  "bowler_type": "Left-arm fast",
  "phase": "powerplay"
}
```

- **Response Body (200 OK)**:
```json
{
  "status": "success",
  "scouting_report": {
    "summary": "Against Left-arm fast bowlers in the Powerplay, Virat Kohli exhibits a conservative approach with a 38.5% dot ball rate and a strike rate of 114.2.",
    "key_metrics": {
      "balls_faced": 284,
      "runs_scored": 324,
      "strike_rate": 114.08,
      "dismissals": 7,
      "dot_ball_pct": 38.38
    },
    "tactical_recommendation": "Deploy a left-arm pacer over the wicket angling across outside off-stump with a third man and deep point to induce outside edges."
  }
}
```

---

### 1.2 REST Analytical & Leaderboard Endpoints

#### `GET /analytics/leaderboards/batting`
- **Query Params**: `tournament=IPL&season=2024&metric=strike_rate&limit=10`
- **Response Body**:
```json
{
  "tournament": "IPL",
  "season": "2024",
  "metric": "strike_rate",
  "leaderboard": [
    {"rank": 1, "player_id": "483b8b64", "player_name": "Virat Kohli", "runs": 741, "strike_rate": 154.69, "fours": 62, "sixes": 38}
  ]
}
```

---

### 1.3 Internal Ingestion Webhook

#### `POST /internal/sync-daily`
- **Header Required**: `X-Sync-Token: <SECRET_CRON_TOKEN>`
- **Response Body**:
```json
{
  "status": "success",
  "matches_downloaded": 28,
  "matches_ingested": 28,
  "snapshot_published": "gs://kaizencodes-cricket-data/published/cricket_2026_08_30.duckdb",
  "duration_seconds": 12.4
}
```

---

## 2. KaizenCodes Frontend React Integration (Next.js)

### Custom React Hook: `useCricketAI.ts`
```typescript
import { useState } from 'react';

interface AIQueryResponse {
  insight: string;
  sql_executed: string;
  rows: Record<string, any>[];
  chart_spec?: any;
}

export function useCricketAI() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AIQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const askCricketAI = async (query: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_CRICKET_API_URL}/api/v1/ai/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, include_chart: true })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to query Cricket AI');
      setResult(data.data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return { askCricketAI, result, loading, error };
}
```

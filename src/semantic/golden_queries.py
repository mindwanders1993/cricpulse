from src.semantic.models import GoldenQuery

GOLDEN_QUERIES: list[GoldenQuery] = [
    # 1. Death Overs Batting
    GoldenQuery(
        title="Top Death Overs Batsmen in T20s",
        category="batting",
        question="Who has the highest death overs strike rate in T20 matches with a minimum of 100 balls?",
        sql="""
SELECT 
    p.full_name,
    SUM(fd.runs_batter) AS death_runs,
    COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS death_balls_faced,
    ROUND((SUM(fd.runs_batter)::DOUBLE / COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END)) * 100, 2) AS death_strike_rate,
    SUM(CASE WHEN fd.is_boundary_six THEN 1 ELSE 0 END) AS death_sixes
FROM gold.fact_delivery fd
JOIN gold.dim_player p ON fd.batter_id = p.player_id
JOIN gold.dim_match dm ON fd.match_id = dm.match_id
WHERE fd.phase = 'death'
  AND dm.match_type IN ('T20', 'IT20')
GROUP BY p.full_name
HAVING COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) >= 100
ORDER BY death_strike_rate DESC
LIMIT 5;
        """.strip(),
        keywords=["death", "strike rate", "t20", "sixes", "finisher"],
    ),
    # 2. Powerplay Bowling Economy
    GoldenQuery(
        title="Best Powerplay Economy Bowlers in T20s",
        category="bowling",
        question="Which bowlers have the lowest economy rate in the Powerplay (overs 1-6) in T20s with at least 150 balls bowled?",
        sql="""
SELECT 
    p.full_name,
    COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) AS pp_legal_balls,
    ROUND(COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) / 6.0, 1) AS pp_overs,
    SUM(fd.runs_batter + CASE WHEN fd.is_wide OR fd.is_no_ball THEN fd.runs_extras ELSE 0 END) AS pp_runs_conceded,
    COUNT(CASE WHEN fd.is_wicket AND fd.dismissal_kind IN ('bowled', 'caught', 'lbw', 'stumped', 'caught and bowled', 'hit wicket') THEN 1 END) AS pp_wickets,
    ROUND((SUM(fd.runs_batter + CASE WHEN fd.is_wide OR fd.is_no_ball THEN fd.runs_extras ELSE 0 END)::DOUBLE / (COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) / 6.0)), 2) AS pp_economy
FROM gold.fact_delivery fd
JOIN gold.dim_player p ON fd.bowler_id = p.player_id
JOIN gold.dim_match dm ON fd.match_id = dm.match_id
WHERE fd.phase = 'powerplay'
  AND dm.match_type IN ('T20', 'IT20')
GROUP BY p.full_name
HAVING COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) >= 150
ORDER BY pp_economy ASC
LIMIT 5;
        """.strip(),
        keywords=["powerplay", "economy", "bowling", "t20", "dot balls"],
    ),
    # 3. Head-to-Head Batter vs Bowler Matchup
    GoldenQuery(
        title="Head to Head Batter vs Bowler Record",
        category="matchup",
        question="What is Virat Kohli's record against Adam Zampa in all formats?",
        sql="""
SELECT 
    fd.batter_name,
    fd.bowler_name,
    COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced,
    SUM(fd.runs_batter) AS runs_scored,
    COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END) AS times_dismissed,
    ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS strike_rate,
    ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END), 0)), 2) AS batting_average,
    COUNT(CASE WHEN fd.is_dot_ball THEN 1 END) AS dot_balls
FROM gold.fact_delivery fd
WHERE LOWER(fd.batter_name) LIKE '%kohli%'
  AND LOWER(fd.bowler_name) LIKE '%zampa%'
GROUP BY fd.batter_name, fd.bowler_name;
        """.strip(),
        keywords=["matchup", "versus", "vs", "head to head", "record", "dismissed"],
    ),
    # 4. Dot Ball Percentage in ODI
    GoldenQuery(
        title="Most Economical Dot Ball Bowlers in ODI",
        category="bowling",
        question="Which bowlers have the highest dot ball percentage in ODI cricket (min 300 balls)?",
        sql="""
SELECT 
    p.full_name,
    COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) AS legal_balls,
    COUNT(CASE WHEN fd.is_dot_ball THEN 1 END) AS dot_balls,
    ROUND((COUNT(CASE WHEN fd.is_dot_ball THEN 1 END)::DOUBLE / COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END)) * 100, 2) AS dot_ball_pct,
    COUNT(CASE WHEN fd.is_wicket AND fd.dismissal_kind IN ('bowled', 'caught', 'lbw', 'stumped', 'caught and bowled', 'hit wicket') THEN 1 END) AS wickets
FROM gold.fact_delivery fd
JOIN gold.dim_player p ON fd.bowler_id = p.player_id
JOIN gold.dim_match dm ON fd.match_id = dm.match_id
WHERE dm.match_type IN ('ODI', 'ODM')
GROUP BY p.full_name
HAVING COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) >= 300
ORDER BY dot_ball_pct DESC
LIMIT 5;
        """.strip(),
        keywords=["dot ball", "percentage", "odi", "maidens", "pressure"],
    ),
    # 5. Career Batting Leaders by Season
    GoldenQuery(
        title="Top Run Scorers in a Specific Season",
        category="batting",
        question="Who scored the most runs in the 2023 season across all T20 matches?",
        sql="""
SELECT 
    p.full_name,
    COUNT(DISTINCT fd.match_id) AS matches,
    SUM(fd.runs_batter) AS total_runs,
    COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced,
    ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END), 0)), 2) AS batting_average,
    ROUND((SUM(fd.runs_batter)::DOUBLE / COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END)) * 100, 2) AS strike_rate,
    SUM(CASE WHEN fd.is_boundary_four THEN 1 ELSE 0 END) AS fours,
    SUM(CASE WHEN fd.is_boundary_six THEN 1 ELSE 0 END) AS sixes
FROM gold.fact_delivery fd
JOIN gold.dim_player p ON fd.batter_id = p.player_id
JOIN gold.dim_match dm ON fd.match_id = dm.match_id
WHERE dm.season = '2023'
  AND dm.match_type IN ('T20', 'IT20')
GROUP BY p.full_name
ORDER BY total_runs DESC
LIMIT 10;
        """.strip(),
        keywords=["season", "top runs", "most runs", "orange cap", "leaderboard"],
    ),
]


class GoldenQueryRegistry:
    """Manages few-shot SQL examples and provides intent-based query selection."""

    def __init__(self, queries: list[GoldenQuery] | None = None):
        self.queries = queries or GOLDEN_QUERIES

    def select_few_shot_examples(self, user_query: str, limit: int = 2) -> list[GoldenQuery]:
        """Rank and return the top `limit` most relevant golden queries matching user keywords."""
        query_lower = user_query.lower()
        scored_queries: list[tuple[float, GoldenQuery]] = []

        for gq in self.queries:
            score = 0.0
            for kw in gq.keywords:
                if kw in query_lower:
                    score += 1.0
            if gq.category in query_lower:
                score += 1.5

            scored_queries.append((score, gq))

        # Sort by relevance score descending
        scored_queries.sort(key=lambda x: x[0], reverse=True)
        return [q for _, q in scored_queries[:limit]]

    def get_few_shot_prompt_context(self, user_query: str, limit: int = 2) -> str:
        """Format selected few-shot queries into a prompt block for LLMs."""
        selected = self.select_few_shot_examples(user_query, limit=limit)
        if not selected:
            return ""

        lines = [
            "### FEW-SHOT VETTED SQL EXAMPLES",
            "Learn from these verified DuckDB queries for join patterns, CTE structures, and filtering:",
            "",
        ]

        for i, q in enumerate(selected, start=1):
            lines.append(f"#### Example {i}: {q.title}")
            lines.append(f"- **User Question**: {q.question}")
            lines.append(f"```sql\n{q.sql}\n```\n")

        return "\n".join(lines)

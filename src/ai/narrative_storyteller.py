import re
from typing import Any

import duckdb

from src.ai.gemini_client import GeminiClient
from src.utils import setup_logging

logger = setup_logging()


class NarrativeStorytellerAgent:
    """Agent 3: Synthesizes editorial match recaps, turning points, and match momentum charts."""

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        gemini_client: GeminiClient | None = None,
    ):
        self.con = con
        self.gemini = gemini_client or GeminiClient()

    def get_match_summary(self, match_id: str) -> dict[str, Any] | None:
        """Fetch high-level match metadata, teams, and result from DuckDB."""
        query = """
        SELECT 
            match_id,
            match_date,
            match_type,
            season,
            team1,
            team2,
            venue_name,
            city,
            winner AS winner_name,
            result_type,
            COALESCE(win_by_runs, win_by_wickets, 0) AS win_margin,
            player_of_match
        FROM gold.dim_match
        WHERE match_id = ?
        LIMIT 1;
        """
        try:
            rel = self.con.execute(query, [match_id])
            row = rel.fetchone()
            if not row:
                return None
            cols = [d[0] for d in rel.description]
            return dict(zip(cols, row, strict=False))
        except Exception as e:
            logger.warn("match_summary_query_failed", match_id=match_id, error=str(e))
            return None

    def get_over_by_over_progression(self, match_id: str) -> list[dict[str, Any]]:
        """Compute over-by-over progression and identify momentum swings."""
        query = """
        SELECT 
            innings_number,
            over_number,
            SUM(total_runs) AS runs_in_over,
            COUNT(CASE WHEN is_wicket THEN 1 END) AS wickets_in_over,
            COUNT(CASE WHEN is_boundary_four THEN 1 END) AS fours,
            COUNT(CASE WHEN is_boundary_six THEN 1 END) AS sixes,
            COUNT(CASE WHEN is_dot_ball THEN 1 END) AS dot_balls
        FROM gold.fact_delivery
        WHERE match_id = ?
        GROUP BY innings_number, over_number
        ORDER BY innings_number ASC, over_number ASC;
        """
        try:
            rel = self.con.execute(query, [match_id])
            cols = [d[0] for d in rel.description]
            return [dict(zip(cols, r, strict=False)) for r in rel.fetchall()]
        except Exception as e:
            logger.warn("over_progression_failed", match_id=match_id, error=str(e))
            return []

    def get_top_performers(self, match_id: str) -> list[dict[str, Any]]:
        """Identify top batters and bowlers in the match."""
        bat_query = """
        SELECT 
            p.full_name AS player_name,
            'batting' AS role,
            SUM(fd.runs_batter) AS stat_primary,
            COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS stat_secondary
        FROM gold.fact_delivery fd
        JOIN gold.dim_player p ON fd.batter_id = p.player_id
        WHERE fd.match_id = ?
        GROUP BY p.full_name
        ORDER BY stat_primary DESC
        LIMIT 3;
        """
        bowl_query = """
        SELECT 
            p.full_name AS player_name,
            'bowling' AS role,
            COUNT(CASE WHEN fd.is_wicket AND fd.dismissal_kind IN ('bowled', 'caught', 'lbw', 'stumped', 'caught and bowled') THEN 1 END) AS stat_primary,
            SUM(fd.runs_batter + CASE WHEN fd.is_wide OR fd.is_no_ball THEN fd.runs_extras ELSE 0 END) AS stat_secondary
        FROM gold.fact_delivery fd
        JOIN gold.dim_player p ON fd.bowler_id = p.player_id
        WHERE fd.match_id = ?
        GROUP BY p.full_name
        ORDER BY stat_primary DESC, stat_secondary ASC
        LIMIT 3;
        """
        performers = []
        try:
            bat_rows = self.con.execute(bat_query, [match_id]).fetchall()
            for r in bat_rows:
                performers.append(
                    {
                        "player_name": r[0],
                        "role": "batting",
                        "runs": r[2],
                        "balls": r[3],
                        "summary": f"{r[0]} ({r[2]} runs off {r[3]} balls)",
                    }
                )
            bowl_rows = self.con.execute(bowl_query, [match_id]).fetchall()
            for r in bowl_rows:
                performers.append(
                    {
                        "player_name": r[0],
                        "role": "bowling",
                        "wickets": r[2],
                        "runs_conceded": r[3],
                        "summary": f"{r[0]} ({r[2]} wkts for {r[3]} runs)",
                    }
                )
        except Exception as e:
            logger.warn("top_performers_failed", match_id=match_id, error=str(e))
        return performers

    def detect_turning_points(self, progression: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Identify turning point overs based on high run volume or multiple wickets."""
        turning_points = []
        for over in progression:
            runs = over.get("runs_in_over", 0)
            wkts = over.get("wickets_in_over", 0)
            inn = over.get("innings_number", 1)
            over_num = over.get("over_number", 0)

            reasons = []
            if wkts >= 2:
                reasons.append(f"{wkts} wickets taken")
            if runs >= 18:
                reasons.append(f"{runs} runs plundered")
            elif runs >= 14 and over_num >= 16:
                reasons.append(f"Crucial death over explosion ({runs} runs)")

            if reasons:
                turning_points.append(
                    {
                        "innings": inn,
                        "over": over_num,
                        "runs": runs,
                        "wickets": wkts,
                        "description": f"Innings {inn}, Over {over_num}: {', '.join(reasons)}",
                    }
                )
        return turning_points[:5]

    def build_momentum_chart_spec(
        self, progression: list[dict[str, Any]], match_title: str
    ) -> dict[str, Any] | None:
        """Construct a Vega-Lite progression line/area chart spec."""
        if not progression:
            return None

        # Build cumulative totals per innings
        cumulative_data = []
        cum_runs = {1: 0, 2: 0, 3: 0, 4: 0}
        cum_wkts = {1: 0, 2: 0, 3: 0, 4: 0}

        for p in progression:
            inn = p.get("innings_number", 1)
            cum_runs[inn] = cum_runs.get(inn, 0) + p.get("runs_in_over", 0)
            cum_wkts[inn] = cum_wkts.get(inn, 0) + p.get("wickets_in_over", 0)
            cumulative_data.append(
                {
                    "innings": f"Innings {inn}",
                    "over": p.get("over_number", 0),
                    "over_runs": p.get("runs_in_over", 0),
                    "cumulative_runs": cum_runs[inn],
                    "cumulative_wickets": cum_wkts[inn],
                }
            )

        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": f"Match Momentum Flow: {match_title}",
            "data": {"values": cumulative_data},
            "mark": {"type": "line", "point": True, "interpolate": "monotone"},
            "encoding": {
                "x": {"field": "over", "type": "quantitative", "title": "Over Number"},
                "y": {
                    "field": "cumulative_runs",
                    "type": "quantitative",
                    "title": "Cumulative Runs",
                },
                "color": {
                    "field": "innings",
                    "type": "nominal",
                    "scale": {"range": ["#3B82F6", "#EF4444", "#10B981", "#F59E0B"]},
                },
                "tooltip": [
                    {"field": "innings", "type": "nominal"},
                    {"field": "over", "type": "quantitative"},
                    {"field": "over_runs", "type": "quantitative", "title": "Runs in Over"},
                    {"field": "cumulative_runs", "type": "quantitative"},
                    {"field": "cumulative_wickets", "type": "quantitative", "title": "Wickets"},
                ],
            },
        }

    def generate_story(
        self, match_id: str, focus: str | None = None, include_chart: bool = True
    ) -> dict[str, Any]:
        """Synthesize a complete journalistic match recap with turning points and visualization."""
        summary = self.get_match_summary(match_id)
        progression = self.get_over_by_over_progression(match_id)
        performers = self.get_top_performers(match_id)
        turning_points = self.detect_turning_points(progression)

        teams_desc = (
            f"{summary.get('team1', 'Team 1')} vs {summary.get('team2', 'Team 2')}"
            if summary
            else f"Match {match_id}"
        )
        match_title = (
            f"{teams_desc} ({summary.get('match_type', 'Cricket')})" if summary else teams_desc
        )

        chart_spec = (
            self.build_momentum_chart_spec(progression, match_title) if include_chart else None
        )

        system_instruction = """
You are a world-class cricket journalist and editorial storyteller for CricPulse.
Write engaging, vivid, narrative match recaps highlighting key turning points, individual heroics, and tactical swings.
Always maintain an energetic, authentic cricket journalism tone.
Format the output clearly:
HEADLINE: <Gripping Headline>
RECAP: <2-3 paragraph editorial recap>
        """.strip()

        context_prompt = f"""
MATCH CONTEXT:
- Match ID: {match_id}
- Teams: {teams_desc}
- Date: {summary.get("match_date", "N/A") if summary else "N/A"}
- Venue: {summary.get("venue_name", "N/A") if summary else "N/A"}
- Winner: {summary.get("winner_name", "N/A") if summary else "N/A"} ({summary.get("result_type", "")} by {summary.get("win_margin", "")})
- Player of the Match: {summary.get("player_of_match", "N/A") if summary else "N/A"}
- Editorial Focus Angle: {focus or "General match momentum and turning points"}

TOP PERFORMERS:
{[p.get("summary") for p in performers]}

KEY TURNING POINT OVERS:
{[tp.get("description") for tp in turning_points]}

Write a captivating match story with a HEADLINE and RECAP.
        """.strip()

        raw_story = self.gemini.generate_text(system_instruction, context_prompt).strip()

        # Parse headline and recap
        headline_match = re.search(r"HEADLINE:\s*(.*?)(?:\n|$)", raw_story, re.IGNORECASE)
        recap_match = re.search(r"RECAP:\s*(.*)", raw_story, re.DOTALL | re.IGNORECASE)

        headline = (
            headline_match.group(1).strip()
            if headline_match
            else f"Thrilling Encounter: {teams_desc}"
        )
        recap = recap_match.group(1).strip() if recap_match else raw_story

        return {
            "match_id": match_id,
            "headline": headline,
            "editorial_recap": recap,
            "turning_points": turning_points,
            "key_performers": performers,
            "chart_spec": chart_spec,
        }

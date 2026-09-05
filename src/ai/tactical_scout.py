from typing import Any

import duckdb

from src.ai.gemini_client import GeminiClient
from src.semantic.resolver import EntityResolver
from src.utils import setup_logging

logger = setup_logging()


class TacticalScoutAgent:
    """Tactical Matchup and Scouting Agent analyzing player head-to-head records and weaknesses."""

    def __init__(self, con: duckdb.DuckDBPyConnection, gemini_client: GeminiClient | None = None):
        self.con = con
        self.gemini = gemini_client or GeminiClient()
        self.resolver = EntityResolver(self.con)

    def scout_matchup(
        self,
        batter_name: str,
        bowler_name: str | None = None,
        bowling_style: str | None = None,
        phase: str | None = None,
        match_type: str = "T20",
    ) -> dict[str, Any]:
        """Generate an analytical scouting report for a batter against a specific bowler or bowling style."""
        resolved_batter = self.resolver.resolve_player(batter_name)
        batter_id = resolved_batter.player_id if resolved_batter else batter_name
        display_batter = resolved_batter.full_name if resolved_batter else batter_name

        resolved_bowler = self.resolver.resolve_player(bowler_name) if bowler_name else None
        bowler_id = resolved_bowler.player_id if resolved_bowler else None
        display_bowler = (
            resolved_bowler.full_name
            if resolved_bowler
            else (bowler_name or bowling_style or "All Bowlers")
        )

        # Query head to head matchup matrix
        query = """
            SELECT 
                COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced,
                SUM(fd.runs_batter) AS runs_scored,
                COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END) AS dismissals,
                ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS strike_rate,
                ROUND((COUNT(CASE WHEN fd.is_dot_ball THEN 1 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS dot_ball_pct,
                SUM(CASE WHEN fd.is_boundary_four THEN 1 ELSE 0 END) AS fours,
                SUM(CASE WHEN fd.is_boundary_six THEN 1 ELSE 0 END) AS sixes
            FROM gold.fact_delivery fd
            JOIN gold.dim_match dm ON fd.match_id = dm.match_id
            WHERE (fd.batter_id = ? OR LOWER(fd.batter_name) LIKE '%' || LOWER(?) || '%')
        """
        params: list[Any] = [batter_id, batter_name]

        if bowler_id:
            query += " AND (fd.bowler_id = ? OR LOWER(fd.bowler_name) LIKE '%' || LOWER(?) || '%')"
            params.extend([bowler_id, bowler_name])

        if phase:
            query += " AND fd.phase = ?"
            params.append(phase.lower())

        if match_type:
            query += " AND dm.match_type = ?"
            params.append(match_type.upper())

        row = self.con.execute(query, params).fetchone()
        metrics = {
            "balls_faced": row[0] or 0,
            "runs_scored": row[1] or 0,
            "dismissals": row[2] or 0,
            "strike_rate": row[3] or 0.0,
            "dot_ball_pct": row[4] or 0.0,
            "fours": row[5] or 0,
            "sixes": row[6] or 0,
        }

        # Generate tactical recommendation via Gemini
        system_instruction = "You are a professional Cricket Tactical Analyst & Coach. Provide sharp, data-driven tactical instructions."
        prompt = f"""
TACTICAL SCOUTING REQUEST:
- Batter: {display_batter}
- Opponent / Bowling Profile: {display_bowler}
- Match Phase: {phase or "All Phases"}
- Format: {match_type}
- Historical Matchup Stats: {metrics}

Provide:
1. A concise summary of the batter's performance against this bowler profile.
2. An actionable tactical recommendation for fielding captain and bowler (lines, lengths, field placements).
        """.strip()

        raw_analysis = self.gemini.generate_text(system_instruction, prompt)

        return {
            "batter": display_batter,
            "bowler": display_bowler,
            "phase": phase or "all",
            "match_type": match_type,
            "metrics": metrics,
            "tactical_report": raw_analysis,
        }

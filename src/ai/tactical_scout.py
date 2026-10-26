from typing import Any

import duckdb

from src.ai.gemini_client import GeminiClient
from src.semantic.golden_queries import get_head_to_head_matchup
from src.semantic.resolver import EntityResolver
from src.utils import setup_logging

logger = setup_logging()

# Casing as stored in gold.dim_match — "Test", not "TEST", so a plain .upper() finds nothing.
MATCH_TYPES = ("T20", "ODI", "Test", "IT20", "MDM", "ODM")


def canonical_match_type(value: str) -> str:
    """Normalize a caller-supplied format to the casing used in the gold tables."""
    cleaned = (value or "").strip()
    return {m.upper(): m for m in MATCH_TYPES}.get(cleaned.upper(), cleaned)


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

        resolved_type = canonical_match_type(match_type)

        if bowler_id and not phase:
            h2h = get_head_to_head_matchup(self.con, batter_id, bowler_id, resolved_type)
            metrics = {
                "balls_faced": h2h["balls_faced"],
                "runs_scored": h2h["runs_scored"],
                "dismissals": h2h["dismissals"],
                "strike_rate": h2h["strike_rate"],
                "dot_ball_pct": h2h["dot_ball_pct"],
                "fours": h2h["fours"],
                "sixes": h2h["sixes"],
            }
        else:
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
                query += (
                    " AND (fd.bowler_id = ? OR LOWER(fd.bowler_name) LIKE '%' || LOWER(?) || '%')"
                )
                params.extend([bowler_id, bowler_name])

            if phase:
                query += " AND fd.phase = ?"
                params.append(phase.lower())

            if resolved_type:
                query += " AND dm.match_type = ?"
                params.append(resolved_type)

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

        batter_career = self.batting_career(batter_id, resolved_type)
        bowler_career = self.bowling_career(bowler_id, resolved_type) if bowler_id else None

        system_instruction = (
            "You are CricPulse's cricket analyst. You write for fans watching the game: "
            "lead with the verdict, stay short and scannable, and never invent a number."
        )
        prompt = self._build_prompt(
            display_batter=display_batter,
            display_bowler=display_bowler,
            phase=phase,
            match_type=resolved_type,
            metrics=metrics,
            batter_career=batter_career,
            bowler_career=bowler_career,
        )
        raw_analysis = self.gemini.generate_text(system_instruction, prompt)

        return {
            "batter": display_batter,
            "bowler": display_bowler,
            "phase": phase or "all",
            "match_type": resolved_type,
            "metrics": metrics,
            "batter_career": batter_career,
            "bowler_career": bowler_career,
            "key_points": self._build_key_points(metrics),
            "tactical_report": raw_analysis,
        }

    def batting_career(self, player_id: str, match_type: str) -> dict[str, Any] | None:
        """Career batting baseline for the given format, used as context for the matchup."""
        row = self.con.execute(
            """
            SELECT matches_played, total_runs, batting_average, strike_rate
            FROM gold.mart_player_batting_career
            WHERE player_id = ? AND match_type = ?;
            """,
            [player_id, match_type],
        ).fetchone()
        if not row:
            return None
        return {
            "matches": row[0],
            "runs": row[1],
            "average": round(row[2], 2) if row[2] is not None else None,
            "strike_rate": round(row[3], 2) if row[3] is not None else None,
        }

    def bowling_career(self, player_id: str, match_type: str) -> dict[str, Any] | None:
        """Career bowling baseline for the given format, used as context for the matchup."""
        row = self.con.execute(
            """
            SELECT matches_played, wickets, bowling_average, economy_rate
            FROM gold.mart_player_bowling_career
            WHERE player_id = ? AND match_type = ?;
            """,
            [player_id, match_type],
        ).fetchone()
        if not row:
            return None
        return {
            "matches": row[0],
            "wickets": row[1],
            "average": round(row[2], 2) if row[2] is not None else None,
            "economy": round(row[3], 2) if row[3] is not None else None,
        }

    @staticmethod
    def _build_key_points(metrics: dict[str, Any]) -> list[dict[str, str]]:
        """Headline tiles computed here in Python — the most prominent numbers on screen are
        never LLM-authored, so they cannot be hallucinated."""
        if not metrics.get("balls_faced"):
            return []
        return [
            {"label": "Strike Rate", "value": f"{metrics['strike_rate']:,.2f}"},
            {"label": "Runs Scored", "value": f"{metrics['runs_scored']:,}"},
            {"label": "Dismissals", "value": f"{metrics['dismissals']:,}"},
            {"label": "Dot Ball %", "value": f"{metrics['dot_ball_pct']:,.1f}%"},
        ]

    @staticmethod
    def _build_prompt(
        display_batter: str,
        display_bowler: str,
        phase: str | None,
        match_type: str,
        metrics: dict[str, Any],
        batter_career: dict[str, Any] | None,
        bowler_career: dict[str, Any] | None,
    ) -> str:
        """Ask for a short, verdict-first answer that interprets the tiles instead of restating them."""
        if metrics["balls_faced"]:
            head_to_head = (
                f"- {metrics['runs_scored']} runs off {metrics['balls_faced']} balls "
                f"(strike rate {metrics['strike_rate']})\n"
                f"- Dismissed {metrics['dismissals']} time(s)\n"
                f"- {metrics['dot_ball_pct']}% dot balls, {metrics['fours']} fours, {metrics['sixes']} sixes"
            )
        else:
            head_to_head = "- No recorded deliveries between these two in this format/phase."

        career_lines = []
        if batter_career:
            career_lines.append(
                f"- {display_batter}: {batter_career['runs']} runs in {batter_career['matches']} matches, "
                f"average {batter_career['average']}, strike rate {batter_career['strike_rate']}"
            )
        if bowler_career:
            career_lines.append(
                f"- {display_bowler}: {bowler_career['wickets']} wickets in {bowler_career['matches']} matches, "
                f"average {bowler_career['average']}, economy {bowler_career['economy']}"
            )
        career_block = "\n".join(career_lines) or "- No career baseline available."

        return f"""
MATCHUP: {display_batter} (batter) vs {display_bowler} (bowler)
FORMAT: {match_type} · {phase or "all phases"}

HEAD-TO-HEAD (from ball-by-ball data):
{head_to_head}

CAREER BASELINE ({match_type}):
{career_block}

Write the answer in exactly this shape:
1. One or two sentences giving the verdict — who holds the edge here, and why.
2. "## What the numbers say" — at most 4 short bullets. Compare the matchup against each
   player's career baseline (is he scoring faster or slower here than he usually does?).
3. "## How to bowl at him" — at most 2 short bullets of practical tactics.

Rules:
- The headline numbers are already shown as tiles next to your answer. Interpret them; do not
  simply restate them, and never lay stats out as a table.
- Use ONLY the numbers above. Never introduce a statistic that is not listed here.
- Markdown allowed: "## " headings, "- " bullets, **bold**. Nothing else.
- Keep the entire answer under 180 words.
""".strip()

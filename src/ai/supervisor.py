import re
from typing import Any

import duckdb

from src.ai.gemini_client import GeminiClient
from src.ai.narrative_storyteller import NarrativeStorytellerAgent
from src.ai.tactical_scout import TacticalScoutAgent
from src.ai.text_to_sql import TextToSQLAgent
from src.semantic.resolver import EntityResolver
from src.utils import setup_logging

logger = setup_logging()


class SupervisorAgent:
    """Orchestrator that classifies user intent and routes to specialized cricket agents."""

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        gemini_client: GeminiClient | None = None,
    ):
        self.con = con
        self.gemini = gemini_client or GeminiClient()
        self.sql_agent = TextToSQLAgent(con=self.con, gemini_client=self.gemini)
        self.scout_agent = TacticalScoutAgent(con=self.con, gemini_client=self.gemini)
        self.story_agent = NarrativeStorytellerAgent(con=self.con, gemini_client=self.gemini)
        self.resolver = EntityResolver(con=self.con)

    def classify_intent(self, user_message: str) -> str:
        """Classify user intent into ANALYTICAL_SQL, TACTICAL_SCOUT, NARRATIVE_STORY, or GENERAL."""
        msg_lower = user_message.lower()

        # Direct heuristics
        if re.search(r"\b(recap|story|summary|turning point|narrative)\b", msg_lower) or re.search(
            r"\bmatch\s+\d+\b", msg_lower
        ):
            return "NARRATIVE_STORY"

        if re.search(r"\b(vs|against|matchup|scout|weakness|tactic)\b", msg_lower):
            return "TACTICAL_SCOUT"

        if re.search(
            r"\b(highest|most|lowest|average|strike rate|economy|runs|wickets|boundary|sixes|fours|who scored|who took|leaderboard)\b",
            msg_lower,
        ):
            return "ANALYTICAL_SQL"

        # LLM fallback classification
        system_instruction = (
            "You are an intent classifier for a Cricket Multi-Agent Platform. "
            "Classify the user prompt into exactly ONE of the following: "
            "ANALYTICAL_SQL, TACTICAL_SCOUT, NARRATIVE_STORY, GENERAL. "
            "Output ONLY the category name."
        )
        try:
            category = self.gemini.generate_text(system_instruction, user_message).strip().upper()
            if category in ("ANALYTICAL_SQL", "TACTICAL_SCOUT", "NARRATIVE_STORY", "GENERAL"):
                return category
        except Exception as e:
            logger.warn("llm_intent_classification_failed", error=str(e))

        return "ANALYTICAL_SQL"

    def chat(
        self,
        message: str,
        include_chart: bool = True,
    ) -> dict[str, Any]:
        """Dispatch message to the specialized agent and unify response."""
        intent = self.classify_intent(message)
        logger.info("supervisor_routed_message", intent=intent, message=message)

        if intent == "TACTICAL_SCOUT":
            resolved = self.resolver.resolve_all_from_query(message)
            batter_name = resolved.players[0].full_name if resolved.players else "Virat Kohli"
            bowler_name = (
                resolved.players[1].full_name if len(resolved.players) > 1 else "Jasprit Bumrah"
            )

            phase = None
            if "powerplay" in message.lower():
                phase = "powerplay"
            elif "middle" in message.lower():
                phase = "middle"
            elif "death" in message.lower():
                phase = "death"

            report = self.scout_agent.scout_matchup(
                batter_name=batter_name,
                bowler_name=bowler_name,
                phase=phase,
            )
            return {
                "status": "success",
                "intent": "tactical_scout",
                "routed_agent": "TacticalScoutAgent",
                "reply": report["tactical_report"],
                "data": report["metrics"],
                "sql_executed": None,
                "chart_spec": None,
            }

        elif intent == "NARRATIVE_STORY":
            # Extract match_id or pick first available match from DB
            match_id_match = re.search(r"\b(\d{6,8})\b", message)
            if match_id_match:
                target_match_id = match_id_match.group(1)
            else:
                row = self.con.execute(
                    "SELECT match_id FROM gold.dim_match ORDER BY match_date DESC LIMIT 1;"
                ).fetchone()
                target_match_id = str(row[0]) if row else "sample_match"

            story = self.story_agent.generate_story(
                match_id=target_match_id,
                include_chart=include_chart,
            )
            return {
                "status": "success",
                "intent": "narrative_story",
                "routed_agent": "NarrativeStorytellerAgent",
                "reply": f"**{story['headline']}**\n\n{story['editorial_recap']}",
                "data": {
                    "match_id": story["match_id"],
                    "turning_points": story["turning_points"],
                    "key_performers": story["key_performers"],
                },
                "sql_executed": None,
                "chart_spec": story["chart_spec"],
            }

        elif intent == "ANALYTICAL_SQL":
            result = self.sql_agent.query(message)
            return {
                "status": "success",
                "intent": "analytical_sql",
                "routed_agent": "TextToSQLAgent",
                "reply": result["insight"],
                "data": result["rows"],
                "sql_executed": result["sql_executed"],
                "chart_spec": result["chart_spec"] if include_chart else None,
            }

        else:
            # GENERAL conversational reply
            reply = self.gemini.generate_text(
                "You are CricPulse Assistant. Greet the cricket fan and explain you can answer SQL stats, tactical matchups, and match stories.",
                message,
            )
            return {
                "status": "success",
                "intent": "general",
                "routed_agent": "SupervisorAgent",
                "reply": reply
                or "Hello! I am CricPulse Assistant. How can I help you explore cricket data?",
                "data": None,
                "sql_executed": None,
                "chart_spec": None,
            }

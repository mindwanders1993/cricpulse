from fastapi import APIRouter, HTTPException, Request

from src.ai.guardrails import SQLSecurityViolation
from src.ai.narrative_storyteller import NarrativeStorytellerAgent
from src.ai.supervisor import SupervisorAgent
from src.ai.tactical_scout import TacticalScoutAgent
from src.ai.text_to_sql import TextToSQLAgent
from src.api.schemas import (
    AIChatRequest,
    AIChatResponse,
    AIQueryRequest,
    AIQueryResponse,
    AIScoutRequest,
    AIScoutResponse,
    AIStoryRequest,
    AIStoryResponse,
)
from src.utils import setup_logging

logger = setup_logging()
router = APIRouter(prefix="/ai", tags=["Generative AI & Multi-Agent Swarm"])


@router.post("/query", response_model=AIQueryResponse)
def execute_ai_query(body: AIQueryRequest, request: Request) -> AIQueryResponse:
    """Execute natural language to SQL analytics with AST guardrails and automated chart generation."""
    con = request.app.state.db
    gemini = getattr(request.app.state, "gemini", None)
    agent = TextToSQLAgent(con=con, gemini_client=gemini)

    try:
        result = agent.query(body.query)
        return AIQueryResponse(
            status="success",
            query=result["query"],
            insight=result["insight"],
            sql_executed=result["sql_executed"],
            rows=result["rows"],
            chart_spec=result["chart_spec"] if body.include_chart else None,
        )
    except SQLSecurityViolation as sec_err:
        raise HTTPException(
            status_code=400, detail=f"Security Guardrail Violation: {sec_err}"
        ) from sec_err
    except Exception as e:
        logger.error("ai_query_endpoint_failed", error=str(e), query=body.query)
        raise HTTPException(status_code=500, detail=f"Failed to process query: {e}") from e


@router.post("/scout", response_model=AIScoutResponse)
def generate_scouting_report(body: AIScoutRequest, request: Request) -> AIScoutResponse:
    """Generate tactical head-to-head matchup simulation and recommendations."""
    con = request.app.state.db
    gemini = getattr(request.app.state, "gemini", None)
    scout_agent = TacticalScoutAgent(con=con, gemini_client=gemini)

    try:
        report = scout_agent.scout_matchup(
            batter_name=body.batter_name,
            bowler_name=body.bowler_name,
            bowling_style=body.bowling_style,
            phase=body.phase,
            match_type=body.match_type,
        )
        return AIScoutResponse(
            status="success",
            batter=report["batter"],
            bowler=report["bowler"],
            phase=report["phase"],
            match_type=report["match_type"],
            metrics=report["metrics"],
            tactical_report=report["tactical_report"],
        )
    except Exception as e:
        logger.error("scout_endpoint_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to generate scouting report: {e}"
        ) from e


@router.post("/story", response_model=AIStoryResponse)
def generate_match_story(body: AIStoryRequest, request: Request) -> AIStoryResponse:
    """Generate narrative match recap, turning points, and momentum progression."""
    con = request.app.state.db
    gemini = getattr(request.app.state, "gemini", None)
    agent = NarrativeStorytellerAgent(con=con, gemini_client=gemini)

    try:
        story = agent.generate_story(
            match_id=body.match_id,
            focus=body.focus,
            include_chart=body.include_chart,
        )
        return AIStoryResponse(
            status="success",
            match_id=story["match_id"],
            headline=story["headline"],
            editorial_recap=story["editorial_recap"],
            turning_points=story["turning_points"],
            key_performers=story["key_performers"],
            chart_spec=story["chart_spec"],
        )
    except Exception as e:
        logger.error("ai_story_endpoint_failed", error=str(e), match_id=body.match_id)
        raise HTTPException(status_code=500, detail=f"Failed to generate story: {e}") from e


@router.post("/chat", response_model=AIChatResponse)
def execute_ai_chat(body: AIChatRequest, request: Request) -> AIChatResponse:
    """Unified conversational assistant routing across Text-to-SQL, Tactical Scout, and Storyteller."""
    con = request.app.state.db
    gemini = getattr(request.app.state, "gemini", None)
    supervisor = SupervisorAgent(con=con, gemini_client=gemini)

    try:
        result = supervisor.chat(
            message=body.message,
            include_chart=body.include_chart,
        )
        return AIChatResponse(
            status="success",
            intent=result["intent"],
            routed_agent=result["routed_agent"],
            reply=result["reply"],
            data=result["data"],
            sql_executed=result["sql_executed"],
            chart_spec=result["chart_spec"],
        )
    except SQLSecurityViolation as sec_err:
        raise HTTPException(
            status_code=400, detail=f"Security Guardrail Violation: {sec_err}"
        ) from sec_err
    except Exception as e:
        logger.error("ai_chat_endpoint_failed", error=str(e), message=body.message)
        raise HTTPException(status_code=500, detail=f"Failed to process chat: {e}") from e

from fastapi import APIRouter, HTTPException, Request

from src.ai.guardrails import SQLSecurityViolation
from src.ai.tactical_scout import TacticalScoutAgent
from src.ai.text_to_sql import TextToSQLAgent
from src.api.schemas import (
    AIQueryRequest,
    AIQueryResponse,
    AIScoutRequest,
    AIScoutResponse,
)
from src.utils import setup_logging

logger = setup_logging()
router = APIRouter(prefix="/ai", tags=["Generative AI & Scouting"])


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

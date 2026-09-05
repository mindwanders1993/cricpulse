from fastapi import APIRouter, Request

from src.api.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check(request: Request) -> HealthResponse:
    """Liveness probe for Cloud Run."""
    return HealthResponse(status="healthy", database_connected=True)


@router.get("/ready", response_model=HealthResponse)
def readiness_check(request: Request) -> HealthResponse:
    """Readiness probe checking DuckDB table availability."""
    con = getattr(request.app.state, "db", None)
    if not con:
        return HealthResponse(status="degraded", database_connected=False, tables_count=0)

    try:
        tables = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'gold';"
        ).fetchone()[0]
        return HealthResponse(status="ready", database_connected=True, tables_count=tables)
    except Exception:
        return HealthResponse(status="unready", database_connected=False, tables_count=0)

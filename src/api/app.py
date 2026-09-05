from contextlib import asynccontextmanager
from pathlib import Path

import duckdb
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.ai.gemini_client import GeminiClient
from src.api.routes import ai_router, analytics_router, health_router, internal_router
from src.builder.schema import INIT_SCHEMA_SQL
from src.config import get_settings
from src.utils import setup_logging

logger = setup_logging()


def create_app(
    db_path: Path | str | None = None,
    gemini_client: GeminiClient | None = None,
) -> FastAPI:
    """Application factory creating the CricPulse FastAPI microservice."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 1. Initialize DuckDB connection
        target_db = Path(db_path) if db_path else settings.published_dir / "cricket_latest.duckdb"

        if target_db.exists():
            logger.info("mounting_published_duckdb_snapshot", path=str(target_db))
            app.state.db = duckdb.connect(str(target_db), read_only=True)
        else:
            logger.warn("no_published_snapshot_found_using_in_memory", path=str(target_db))
            app.state.db = duckdb.connect(":memory:")
            app.state.db.execute(INIT_SCHEMA_SQL)

        # 2. Initialize Gemini Client
        app.state.gemini = gemini_client or GeminiClient(settings=settings)
        logger.info("cricpulse_api_gateway_started", env=settings.app_env)

        yield

        # Shutdown: close DB connection
        if hasattr(app.state, "db") and app.state.db:
            app.state.db.close()
            logger.info("duckdb_connection_closed")

    app = FastAPI(
        title="CricPulse API Gateway",
        description="Serverless Cricket Lakehouse & Generative AI Multi-Agent Service",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict via env in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routes
    app.include_router(health_router)
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(internal_router, prefix="/api/v1")

    # Chat UI (served same-origin so it can call the API routes above directly)
    static_dir = Path(__file__).parent / "static"
    app.mount("/ui", StaticFiles(directory=static_dir, html=True), name="ui")

    return app


app = create_app()

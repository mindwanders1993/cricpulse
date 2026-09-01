"""CricPulse API Routers."""

from src.api.routes.ai import router as ai_router
from src.api.routes.analytics import router as analytics_router
from src.api.routes.health import router as health_router

__all__ = ["ai_router", "analytics_router", "health_router"]

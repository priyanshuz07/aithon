from app.api.routes.behavior import router as behavior_router
from app.api.routes.adaptive import router as adaptive_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.demo import router as demo_router
from app.api.routes.health import router as health_router
from app.api.routes.sessions import router as sessions_router

__all__ = ["adaptive_router", "behavior_router", "dashboard_router", "demo_router", "health_router", "sessions_router"]

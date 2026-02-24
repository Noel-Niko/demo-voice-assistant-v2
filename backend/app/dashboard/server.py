"""Standalone dashboard server on port 8766.

Completely independent of the main app — reads only from exported JSON
files in /tmp. No database connection or AWS credentials required.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.dashboard.schemas import DashboardSettings
from app.dashboard.service import DashboardService
from app.dashboard.template import DASHBOARD_HTML

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

dashboard_settings = DashboardSettings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Dashboard lifespan: initialize service."""
    app.state.dashboard_service = DashboardService(
        data_dir=dashboard_settings.DASHBOARD_DATA_DIR,
        file_pattern=dashboard_settings.DASHBOARD_FILE_PATTERN,
    )
    logger.info(
        "dashboard_started",
        data_dir=dashboard_settings.DASHBOARD_DATA_DIR,
        port=dashboard_settings.DASHBOARD_PORT,
    )
    yield
    logger.info("dashboard_shutdown")


dashboard_app = FastAPI(
    title="Conversation Intelligence Metrics Dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

dashboard_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@dashboard_app.get("/api/dashboard/data")
async def get_dashboard_data():
    """Return all dashboard data as JSON."""
    service: DashboardService = dashboard_app.state.dashboard_service
    data = service.get_dashboard_data()
    data.main_app_url = dashboard_settings.DASHBOARD_MAIN_APP_URL
    return data.model_dump()


@dashboard_app.get("/api/dashboard/health")
async def dashboard_health():
    """Dashboard health check."""
    return {"status": "healthy", "service": "metrics-dashboard"}


@dashboard_app.get("/", response_class=HTMLResponse)
async def dashboard_page():
    """Serve self-contained HTML dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.dashboard.server:dashboard_app",
        host=dashboard_settings.DASHBOARD_HOST,
        port=dashboard_settings.DASHBOARD_PORT,
        reload=True,
        log_level=dashboard_settings.DASHBOARD_LOG_LEVEL.lower(),
    )

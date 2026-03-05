"""Tellaro PM Backend - FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tellaro_pm.admin.router import router as admin_router
from tellaro_pm.agents.provisioning_router import router as provisioning_router
from tellaro_pm.agents.router import router as agents_router
from tellaro_pm.auth.router import router as auth_router
from tellaro_pm.auth.service import auth_service
from tellaro_pm.chat.router import router as chat_router
from tellaro_pm.core.opensearch import ensure_indices
from tellaro_pm.core.settings import settings
from tellaro_pm.core.tql_router import router as tql_router
from tellaro_pm.github_integration.router import router as github_router
from tellaro_pm.projects.router import router as projects_router
from tellaro_pm.tasks.router import router as tasks_router
from tellaro_pm.users.router import router as users_router
from tellaro_pm.websocket.router import router as websocket_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    logger.info("Starting Tellaro PM backend...")
    try:
        ensure_indices()
        logger.info("OpenSearch indices ready")
    except Exception:
        logger.warning("OpenSearch not available — indices will be created on first connection")

    try:
        auth_service.bootstrap_admin()
        logger.info("Admin bootstrap complete")
    except Exception:
        logger.warning("Admin bootstrap skipped — OpenSearch not available")

    yield
    # Shutdown
    logger.info("Tellaro PM backend shutting down")


app = FastAPI(
    title="Tellaro PM",
    description="AI-orchestration-first project management API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=f"/api/{settings.API_VERSION_STR}/docs",
    openapi_url=f"/api/{settings.API_VERSION_STR}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.API_BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(projects_router)
app.include_router(tasks_router)
app.include_router(chat_router)
app.include_router(agents_router)
app.include_router(provisioning_router)
app.include_router(github_router)
app.include_router(websocket_router)
app.include_router(tql_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(f"/api/{settings.API_VERSION_STR}/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok", "version": settings.API_VERSION_STR}


def main() -> None:
    uvicorn.run(
        "tellaro_pm.main:app",
        host=settings.API_SERVER_HOST,
        port=settings.API_SERVER_PORT,
        reload=settings.API_SERVER_RELOAD,
        workers=settings.API_SERVER_WORKERS if not settings.API_SERVER_RELOAD else 1,
    )


if __name__ == "__main__":
    main()

"""
FastAPI Application Entry Point
"""
from __future__ import annotations
import structlog
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes_v2 import router as router_v2
from config import settings

# ── Structured logging setup ──────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app.startup", host=settings.api_host, port=settings.api_port)
    
    # Register tools on startup
    from tools import get_tool_registry
    registry = get_tool_registry()
    logger.info("app.tools_loaded", count=len(registry.list_tools()))
    
    yield
    logger.info("app.shutdown")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Agent Generation Engine v5",
    description="ReAct-based autonomous code generator",
    version="5.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router_v2, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level="info",
    )

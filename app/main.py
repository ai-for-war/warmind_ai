"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import router as v1_router
from app.common.exceptions import AppException
from app.config.mcp import MCP_SERVERS
from app.config.settings import get_settings
from app.infrastructure.database.mongodb import MongoDB
from app.infrastructure.mcp.manager import get_mcp_tools_manager
from app.infrastructure.redis.client import RedisClient
from app.socket_gateway import sio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    await MongoDB.connect(settings.MONGODB_URI, settings.MONGODB_DB_NAME)
    await MongoDB.create_indexes()
    await RedisClient.connect(settings.REDIS_URL)

    # Initialize MCP Tools Manager
    await _initialize_mcp_tools()

    yield
    # Shutdown
    await RedisClient.disconnect()
    await MongoDB.disconnect()


async def _initialize_mcp_tools() -> None:
    """Initialize MCP Tools Manager with configured servers.

    Handles initialization errors gracefully - if MCP fails to initialize,
    the application continues without MCP tools.
    """
    try:
        mcp_manager = get_mcp_tools_manager()
        await mcp_manager.initialize(MCP_SERVERS)

        if mcp_manager.is_initialized:
            logger.info(
                "MCP Tools Manager initialized successfully with %d tools",
                mcp_manager.tool_count,
            )
        else:
            logger.warning(
                "MCP Tools Manager initialization incomplete. "
                "Agents will work without MCP tools."
            )
    except Exception as e:  # noqa: BLE001
        logger.error(
            "Failed to initialize MCP Tools Manager: %s. "
            "Application will continue without MCP tools.",
            e,
        )


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Global handler for all AppException and subclasses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )

# CORS middleware - allow frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix=settings.API_V1_PREFIX)

# Combine FastAPI with Socket.IO for real-time messaging
# Socket.IO handles WebSocket connections at root path
# FastAPI handles REST API endpoints
combined_app = socketio.ASGIApp(sio, other_asgi_app=app)

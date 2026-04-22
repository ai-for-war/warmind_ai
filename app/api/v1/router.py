"""Aggregate all v1 API routers."""

from fastapi import APIRouter

from app.api.v1.analytics.router import router as analytics_router
from app.api.v1.ai.chat import router as chat_router
from app.api.v1.ai.lead_agent import router as lead_agent_router
from app.api.v1.auth.routes import router as auth_router
from app.api.v1.backtests.router import router as backtests_router
from app.api.v1.health import router as health_router
from app.api.v1.image_generations.router import router as image_generations_router
from app.api.v1.images.router import router as images_router
from app.api.v1.internal.router import router as internal_router
from app.api.v1.meetings.router import router as meetings_router
from app.api.v1.organizations.routes import router as organizations_router
from app.api.v1.sheet_crawler.router import router as sheet_crawler_router
from app.api.v1.stock_research.router import router as stock_research_router
from app.api.v1.stocks.router import router as stocks_router
from app.api.v1.stocks.watchlists import router as stock_watchlists_router
from app.api.v1.tts.router import router as tts_router
from app.api.v1.users.routes import router as users_router
from app.api.v1.voices.router import router as voices_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(organizations_router)
router.include_router(images_router)
router.include_router(image_generations_router)
router.include_router(internal_router)
router.include_router(meetings_router)
router.include_router(sheet_crawler_router)
router.include_router(stock_research_router)
router.include_router(stock_watchlists_router)
router.include_router(stocks_router)
router.include_router(backtests_router)
router.include_router(analytics_router)
router.include_router(chat_router)
router.include_router(lead_agent_router)
router.include_router(voices_router)
router.include_router(tts_router)

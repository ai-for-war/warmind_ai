"""Aggregate all v1 API routers."""

from fastapi import APIRouter

from app.api.v1.analytics.router import router as analytics_router
from app.api.v1.ai.chat import router as chat_router
from app.api.v1.auth.routes import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.internal.router import router as internal_router
from app.api.v1.organizations.routes import router as organizations_router
from app.api.v1.sheet_crawler.router import router as sheet_crawler_router
from app.api.v1.users.routes import router as users_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(organizations_router)
router.include_router(internal_router)
router.include_router(sheet_crawler_router)
router.include_router(analytics_router)
router.include_router(chat_router)

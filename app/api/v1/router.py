"""Public API router composition."""

from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, health, metrics, tickets

router = APIRouter()
router.include_router(health.router)
router.include_router(metrics.router)
router.include_router(tickets.router)
router.include_router(auth.router)
router.include_router(admin.router)

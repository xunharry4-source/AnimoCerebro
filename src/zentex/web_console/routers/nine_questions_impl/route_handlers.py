from __future__ import annotations

from fastapi import APIRouter

from . import route_handlers_control, route_handlers_query

__all__ = ["router"]

router = APIRouter()
router.include_router(route_handlers_query.router)
router.include_router(route_handlers_control.router)

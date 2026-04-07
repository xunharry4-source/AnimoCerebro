from __future__ import annotations

from fastapi import APIRouter

from zentex.web_console.routers.agents import router as agents_router
from zentex.web_console.routers.audit import router as audit_router
from zentex.web_console.routers.cli import router as cli_router
from zentex.web_console.routers.cognition import router as cognition_router
from zentex.web_console.routers.events import router as events_router
from zentex.web_console.routers.interventions import router as interventions_router
from zentex.web_console.routers.memory import router as memory_router
from zentex.web_console.routers.learning import router as learning_router
from zentex.web_console.routers.mcp import router as mcp_router
from zentex.web_console.routers.model_feature_tests import router as model_feature_tests_router
from zentex.web_console.routers.nine_questions import router as nine_questions_router
from zentex.web_console.routers.overview import router as overview_router
from zentex.web_console.routers.plugins import router as plugins_router
from zentex.web_console.routers.replay import router as replay_router
from zentex.web_console.routers.tasks import router as tasks_router
from zentex.web_console.routers.upgrades import router as upgrades_router


api_router = APIRouter(prefix="/api/web", tags=["web-console"])
api_router.include_router(tasks_router)
api_router.include_router(upgrades_router)
api_router.include_router(memory_router)
api_router.include_router(cli_router)
api_router.include_router(agents_router)
api_router.include_router(mcp_router)
api_router.include_router(nine_questions_router)
api_router.include_router(replay_router)
api_router.include_router(plugins_router)
api_router.include_router(overview_router)
api_router.include_router(cognition_router)
api_router.include_router(audit_router)
api_router.include_router(model_feature_tests_router)
api_router.include_router(interventions_router)
api_router.include_router(events_router)
api_router.include_router(learning_router)

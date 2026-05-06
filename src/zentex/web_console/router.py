from __future__ import annotations

from fastapi import APIRouter

from zentex.web_console.routers.agents import router as agents_router
from zentex.web_console.routers.architecture_redlines import router as architecture_redlines_router
from zentex.web_console.routers.audit import router as audit_router
from zentex.web_console.routers.brain_transcript_chain import router as brain_transcript_chain_router
from zentex.web_console.routers.cli import router as cli_router
from zentex.web_console.routers.cognition import router as cognition_router
from zentex.web_console.routers.collaboration import router as collaboration_router
from zentex.web_console.routers.collaboration_security import router as collaboration_security_router
from zentex.web_console.routers.collaboration_social import router as collaboration_social_router
from zentex.web_console.routers.cloud_sanity_auditor import router as cloud_sanity_auditor_router
from zentex.web_console.routers.curiosity import router as curiosity_router
from zentex.web_console.routers.deployment_mode import router as deployment_mode_router
from zentex.web_console.routers.evolution import router as evolution_router
from zentex.web_console.routers.events import router as events_router
from zentex.web_console.routers.execution import router as execution_router
from zentex.web_console.routers.external_connectors import router as external_connectors_router
from zentex.web_console.routers.external_brain import router as external_brain_router
from zentex.web_console.routers.subject_evolution import router as subject_evolution_router
from zentex.web_console.routers.system_identity import router as system_identity_router
from zentex.web_console.routers.interventions import router as interventions_router
from zentex.web_console.routers.memory import router as memory_router
from zentex.web_console.routers.memory_governance import router as memory_governance_router
from zentex.web_console.routers.memory_lifecycle import router as memory_lifecycle_router
from zentex.web_console.routers.memory_self_maintenance import router as memory_self_maintenance_router
from zentex.web_console.routers.memory_repair import router as memory_repair_router
from zentex.web_console.routers.learning import router as learning_router
from zentex.web_console.routers.mcp import router as mcp_router
from zentex.web_console.routers.model_feature_tests import router as model_feature_tests_router
from zentex.web_console.routers.nine_question_reflections import router as nine_question_reflections_router
from zentex.web_console.routers.nine_questions_impl.route_handlers_control import (
    router as nine_questions_control_router,
)
from zentex.web_console.routers.nine_questions_impl.route_handlers_query import (
    router as nine_questions_query_router,
)
from zentex.web_console.routers.observability import router as observability_router
from zentex.web_console.routers.openclaw import router as openclaw_router
from zentex.web_console.routers.overview import router as overview_router
from zentex.web_console.routers.plugins import router as plugins_router
from zentex.web_console.routers.plugin_bus import router as plugin_bus_router
from zentex.web_console.routers.replay import router as replay_router
from zentex.web_console.routers.role_agent_governance import router as role_agent_governance_router
from zentex.web_console.routers.runtime_core import router as runtime_core_router
from zentex.web_console.routers.sanity_auditor import router as sanity_auditor_router
from zentex.web_console.routers.simulator import router as simulator_router
from zentex.web_console.routers.soul_migration import router as soul_migration_router
from zentex.web_console.routers.supervision_hub import router as supervision_hub_router
from zentex.web_console.routers.tasks import router as tasks_router
from zentex.web_console.routers.theory_of_mind import router as theory_of_mind_router
from zentex.web_console.routers.trace_observability import router as trace_observability_router
from zentex.web_console.routers.trace_replay import router as trace_replay_router
from zentex.web_console.routers.unified_errors import router as unified_errors_router
from zentex.web_console.routers.upgrades import router as upgrades_router
from zentex.web_console.routers.governance import router as governance_router
from zentex.web_console.routers.health import router as health_router
from zentex.web_console.routers.i18n import router as i18n_router
from zentex.web_console.routers.managed_memory import router as managed_memory_router
from zentex.web_console.routers.management_acceptance import router as management_acceptance_router
from zentex.web_console.routers.model_provider_runtime import router as model_provider_runtime_router
from zentex.web_console.routers.module_logs import router as module_logs_router
from zentex.web_console.routers.autonomous_loop import router as autonomous_loop_router
from zentex.web_console.routers.notifications import router as notifications_router
from zentex.web_console.routers.observability_acceptance import router as observability_acceptance_router
from zentex.web_console.routers.workspaces import router as workspaces_router


api_router = APIRouter(prefix="/api/web", tags=["web-console"])
api_router.include_router(tasks_router)
api_router.include_router(architecture_redlines_router)
api_router.include_router(brain_transcript_chain_router)
api_router.include_router(upgrades_router)
api_router.include_router(memory_router)
api_router.include_router(memory_governance_router)
api_router.include_router(memory_lifecycle_router)
api_router.include_router(memory_self_maintenance_router)
api_router.include_router(memory_repair_router)
api_router.include_router(cli_router)
api_router.include_router(agents_router)
api_router.include_router(mcp_router)
api_router.include_router(nine_questions_query_router)
api_router.include_router(nine_questions_control_router)
api_router.include_router(replay_router)
api_router.include_router(role_agent_governance_router)
api_router.include_router(runtime_core_router)
api_router.include_router(plugins_router)
api_router.include_router(plugin_bus_router)
api_router.include_router(overview_router)
api_router.include_router(cognition_router)
api_router.include_router(collaboration_router)
api_router.include_router(collaboration_security_router)
api_router.include_router(collaboration_social_router)
api_router.include_router(cloud_sanity_auditor_router)
api_router.include_router(curiosity_router)
api_router.include_router(execution_router)
api_router.include_router(audit_router)
api_router.include_router(model_feature_tests_router)
api_router.include_router(deployment_mode_router)
api_router.include_router(interventions_router)
api_router.include_router(events_router)
api_router.include_router(external_brain_router)
api_router.include_router(subject_evolution_router)
api_router.include_router(learning_router)
api_router.include_router(governance_router)
api_router.include_router(health_router)
api_router.include_router(i18n_router)
api_router.include_router(model_provider_runtime_router)
api_router.include_router(managed_memory_router)
api_router.include_router(management_acceptance_router)
api_router.include_router(module_logs_router)
api_router.include_router(trace_observability_router)
api_router.include_router(trace_replay_router)
api_router.include_router(unified_errors_router)
api_router.include_router(autonomous_loop_router)
api_router.include_router(notifications_router)
api_router.include_router(observability_acceptance_router)
api_router.include_router(workspaces_router)
api_router.include_router(system_identity_router)
api_router.include_router(external_connectors_router)
api_router.include_router(evolution_router)
api_router.include_router(observability_router)
api_router.include_router(openclaw_router)
api_router.include_router(nine_question_reflections_router)
api_router.include_router(sanity_auditor_router)
api_router.include_router(simulator_router)
api_router.include_router(soul_migration_router)
api_router.include_router(supervision_hub_router)
api_router.include_router(theory_of_mind_router)

from __future__ import annotations

"""
Internal factory/export catalog for SystemPluginService bootstrap.

This module is the only sanctioned place inside `zentex.plugins` that imports
plugin implementation factories directly from `src/plugins`.
External callers must use `zentex.plugins.service` instead.
"""

from plugins.execution.cloud_browser.cloud_browser_plugin import (
    build_default_cloud_browser_executor,
)
from plugins.execution.local_system.local_system_plugin import (
    build_default_local_system_executor,
)
from plugins.cognitive.budget_conflict.budget_conflict_plugin import (
    build_budget_conflict_plugin,
)
from plugins.cognitive.semantic_conflict.semantic_conflict_plugin import (
    build_semantic_conflict_plugin,
)
from plugins.cognitive.expired_assumption.expired_assumption_plugin import (
    build_expired_assumption_cleaner_plugin,
)
from plugins.cognitive.failure_cluster.failure_mode_cluster_plugin import (
    build_failure_mode_cluster_plugin,
)
from plugins.memory.memory_extractor.memory_extractor_plugin import build_memory_extractor_plugin
from plugins.nine_questions.q1_where_am_i import build_q1_where_am_i_plugin
from plugins.nine_questions.q2_who_am_i import build_q2_who_am_i_plugin
from plugins.nine_questions.q3_what_do_i_have import build_q3_what_do_i_have_plugin
from plugins.nine_questions.q4_what_can_i_do import build_q4_what_can_i_do_plugin
from plugins.nine_questions.q5_what_am_i_allowed_to_do import build_q5_what_am_i_allowed_to_do_plugin
from plugins.nine_questions.q6_what_should_i_not_do import build_q6_what_should_i_not_do_plugin
from plugins.nine_questions.q7_what_else_can_i_do import build_q7_what_else_can_i_do_plugin
from plugins.nine_questions.q8_what_should_i_do_now import build_q8_what_should_i_do_now_plugin
from plugins.nine_questions.q9_how_should_i_act import build_q9_how_should_i_act_plugin
from plugins.oracle.alternative.alternative_oracle_plugin import (
    build_default_alternative_oracle,
)
from plugins.oracle.objective.objective_oracle_plugin import (
    build_default_objective_oracle,
)
from plugins.oracle.posture.posture_oracle_plugin import (
    build_default_posture_oracle,
)
from plugins.oracle.redline.redline_oracle_plugin import (
    build_default_redline_oracle,
)
from plugins.reflection.reflection_generator.reflection_generator_plugin import (
    build_reflection_generator_plugin,
)
from plugins.model_providers.model_provider_tools.provider_tools_plugin import (
    build_default_provider_tools_model_provider,
)
from plugins.sensory.environment_interpreter.environment_interpreter_plugin import (
    build_default_environment_interpreter_plugin,
)
from plugins.sensory.prompt_injection_sanitizer.prompt_injection_sanitizer_plugin import (
    build_default_prompt_injection_sanitizer_plugin,
)
from plugins.sensory.webhook_ingest.webhook_ingest_plugin import (
    build_default_webhook_ingest_plugin,
)
from plugins.sensory.host_telemetry.host_telemetry_plugin import (
    build_default_host_telemetry_plugin,
)
from plugins.simulation.market.market_simulator_plugin import (
    build_default_market_simulator,
)
from plugins.simulation.thought.thought_sandbox_plugin import (
    build_default_thought_sandbox,
)
from plugins.tasks.capability_matcher.task_capability_matcher_plugin import (
    build_task_capability_matcher_plugin,
)
from plugins.tasks.compensation_workspace_cleanup.task_compensation_workspace_cleanup_plugin import (
    build_task_compensation_workspace_cleanup_plugin,
)
from plugins.tasks.constraint_checker.task_constraint_checker_plugin import (
    build_task_constraint_checker_plugin,
)
from plugins.tasks.document_router.document_router_plugin import (
    build_document_router_plugin,
)
from plugins.tasks.evidence_extractor.task_evidence_extractor_plugin import (
    build_task_evidence_extractor_plugin,
)
from plugins.tasks.project_plan_document.project_plan_document_plugin import (
    build_project_plan_document_plugin,
)
from plugins.tasks.result_normalizer.task_result_normalizer_plugin import (
    build_task_result_normalizer_plugin,
)
from plugins.tasks.verification_rule_based.task_verification_rule_based_plugin import (
    build_task_rule_based_verification_plugin,
)
from plugins.weights.assembler.weight_assembler_plugin import (
    RationalAuditRejectError,
    SubjectiveWeightPlugin,
    WeightPluginAssembler,
    build_cost_guard_weight,
    build_creative_exploration_weight,
    build_default_conservative_weight,
    build_risk_balanced_weight,
)

__all__ = [
    "RationalAuditRejectError",
    "SubjectiveWeightPlugin",
    "WeightPluginAssembler",
    "build_budget_conflict_plugin",
    "build_cost_guard_weight",
    "build_creative_exploration_weight",
    "build_default_alternative_oracle",
    "build_default_cloud_browser_executor",
    "build_default_conservative_weight",
    "build_default_environment_interpreter_plugin",
    "build_default_host_telemetry_plugin",
    "build_default_local_system_executor",
    "build_default_market_simulator",
    "build_default_objective_oracle",
    "build_default_posture_oracle",
    "build_default_prompt_injection_sanitizer_plugin",
    "build_default_provider_tools_model_provider",
    "build_default_redline_oracle",
    "build_default_thought_sandbox",
    "build_default_webhook_ingest_plugin",
    "build_document_router_plugin",
    "build_expired_assumption_cleaner_plugin",
    "build_failure_mode_cluster_plugin",
    "build_memory_extractor_plugin",
    "build_project_plan_document_plugin",
    "build_q1_where_am_i_plugin",
    "build_q2_who_am_i_plugin",
    "build_q3_what_do_i_have_plugin",
    "build_q4_what_can_i_do_plugin",
    "build_q5_what_am_i_allowed_to_do_plugin",
    "build_q6_what_should_i_not_do_plugin",
    "build_q7_what_else_can_i_do_plugin",
    "build_q8_what_should_i_do_now_plugin",
    "build_q9_how_should_i_act_plugin",
    "build_reflection_generator_plugin",
    "build_risk_balanced_weight",
    "build_semantic_conflict_plugin",
    "build_task_capability_matcher_plugin",
    "build_task_compensation_workspace_cleanup_plugin",
    "build_task_constraint_checker_plugin",
    "build_task_evidence_extractor_plugin",
    "build_task_result_normalizer_plugin",
    "build_task_rule_based_verification_plugin",
]

from __future__ import annotations
from typing import List, Optional, Tuple


from concurrent.futures import ThreadPoolExecutor
import asyncio
from datetime import datetime, timedelta, timezone
import functools
import logging
import os
from pathlib import Path
import platform
import sys
from threading import Thread
from unittest.mock import Mock
from uuid import uuid4
from zentex.web_console.errors import ConfigError, InitializationError

try:
    from zentex.cli.adapter import CliAdapterPlugin, SubprocessCliTransport
    from zentex.core.cli import CliToolRegistrationConfig
    from plugins.execution.base_executor_chain import (
        build_default_cloud_browser_executor,
        build_default_local_system_executor,
    )
    from plugins.cognitive import (
        build_budget_conflict_plugin,
        build_expired_assumption_cleaner_plugin,
        build_failure_mode_cluster_plugin,
        build_semantic_conflict_plugin,
    )
    from plugins.memory import build_memory_extractor_plugin
    from plugins.nine_questions import (
        build_q1_where_am_i_plugin,
        build_q2_who_am_i_plugin,
        build_q3_what_do_i_have_plugin,
        build_q4_what_can_i_do_plugin,
        build_q5_what_am_i_allowed_to_do_plugin,
        build_q6_what_should_i_not_do_plugin,
        build_q7_what_else_can_i_do_plugin,
        build_q8_what_should_i_do_now_plugin,
        build_q9_how_should_i_act_plugin,
    )
    from plugins.nine_questions.q2_who_am_i.identity_core_plugin import (
        ConstraintPackPlugin,
        RolePackPlugin,
    )
    from plugins.nine_questions.runtime_functional_oracles import (
        build_default_alternative_oracle,
        build_default_objective_oracle,
        build_default_posture_oracle,
        build_default_redline_oracle,
    )
    from plugins.reflection import build_reflection_generator_plugin
    from plugins.model_providers.provider_tools_provider import (
        build_default_provider_tools_model_provider,
    )
    from plugins.sensory.base_sensory_chain import (
        BasicEnvironmentInterpreter,
        BasicPromptInjectionSanitizer,
        BasicWebhookIngestPlugin,
    )
    from plugins.sensory.host_telemetry_plugin import build_default_host_telemetry_plugin
    from plugins.simulation.base_simulation_bus import (
        build_default_market_simulator,
        build_default_thought_sandbox,
    )
    from plugins.weights.subjective_weight_plugin import (
        RationalAuditRejectError,
        SubjectiveWeightPlugin,
        WeightPluginAssembler,
        build_cost_guard_weight,
        build_creative_exploration_weight,
        build_default_conservative_weight,
        build_risk_balanced_weight,
    )
    from zentex.common.plugin_registry import AbstractPluginRegistry
    from zentex.core.cognitive_tools_spec import CognitiveToolSpec
    from zentex.core.execution_registry import ExecutionDomainRegistry
    from zentex.core.mcp import McpServerConfig, McpToolBindingConfig, McpToolDescriptor
    from zentex.core.plugin_base import (
        BasePluginSpec,
        PluginHealthStatus,
        PluginLifecycleStatus,
    )
    from zentex.mcp.adapter import FakeMcpTransportClient, McpAdapterPlugin
    from zentex.runtime.runtime import BrainRuntime
    from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry, InMemoryAuditSink
    from zentex.runtime.nine_questions.executor import NineQuestionExecutor
    from zentex.runtime.nine_questions.router import build_event
    from zentex.runtime.nine_questions.startup_snapshot import build_runtime_workspace_snapshot
    from zentex.runtime.think_loop import ThinkLoop
    from zentex.safety.conflict_engine import CognitiveConflictEngine, CognitiveConflictReport
    from zentex.cognition.social_mind import (
        CommunicationFitProfile,
        InteractionMindEngine,
        InteractionMindModel,
        InteractionMindState,
        KnowledgeGapEstimate,
        MisunderstandingSignal,
    )
    from zentex.cognition.simulation import (
        CounterfactualSimulationEngine,
        SimulationBundle,
        OutcomeComparison,
        ScenarioBranch,
    )
    from zentex.memory import (
        ConsolidationCycle,
        ConsolidationEngine,
        ForgettableNoiseRule,
        MemoryPromotionCandidate,
        PatternStabilityScore,
    )
    from zentex.memory import EnhancedMemoryService, EpisodeGraphMemoryAdapter
    from zentex.memory import KuzuGraphMemoryClient
    from zentex.runtime.working_memory import WorkingMemoryController, FocusBudget
    from zentex.runtime.self_model import LivingSelfModelEngine
    from zentex.runtime.metacognition import MetaCognitionController
    from zentex.runtime.temporal import CognitiveTemporalEngine
    from zentex.runtime.transcript import (
        BrainTranscriptEntry,
        BrainTranscriptEntryType,
        BrainTranscriptStore,
    )
    from zentex.web_console.api import (
        PluginFeatureCatalogItem,
        build_managed_plugin_record,
        create_web_console_app,
    )
    from zentex.agents.manager import AgentManager, AgentAsset, AgentStatus, AgentTrustLevel
    from zentex.agents.service import AgentCoordinationService
    from zentex.tasks.registry import TaskRegistry
    from zentex.tasks.service import TaskManagementService
    from zentex.upgrade.management import (
        UpgradeLifecycleStatus,
        UpgradeManagementRecord,
        UpgradeManagementStore,
        UpgradeTargetKind,
        utc_now,
    )
    from zentex.tasks.models import TaskStatus, TaskType, ZentexTask
    from zentex.core.model_provider_spec import ModelProviderSpec
    from zentex.tasks.llm_decomposer import LLMTaskDecomposerPlugin
except ModuleNotFoundError as exc:
    missing_name = exc.name or (str(exc).split("'")[1] if "'" in str(exc) else "unknown dependency")
    raise InitializationError(
        f"Web 控制台启动失败：缺少依赖模块 `{missing_name}`。请先安装启动依赖后再重试。"
    ) from exc


logger = logging.getLogger(__name__)


class DevelopmentPluginRegistry(AbstractPluginRegistry[BasePluginSpec]):
    def __init__(self) -> None:
        super().__init__(BasePluginSpec)

    def register(self, plugin: BasePluginSpec) -> BasePluginSpec | None:
        try:
            normalized = plugin.__class__.model_validate(
                {
                    **plugin.model_dump(),
                    "status": PluginLifecycleStatus.CANDIDATE,
                }
            )
        except Exception:
            normalized = super().register(plugin)
            if normalized is None:
                return None
        self._plugins[normalized.plugin_id] = normalized
        return normalized


def _run_startup_coro(coro) -> None:  # type: ignore[no-untyped-def]
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    def _runner() -> None:
        try:
            asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover
            logger.exception("Background startup task failed: %s", exc)

    thread = Thread(target=_runner, name="zentex-dev-startup", daemon=True)
    thread.start()
    # No join() here to avoid blocking startup


def _build_cognitive_tool_spec(
    *,
    plugin_id: str,
    version: str = "1.0.0",
    behavior_key: Optional[str] = None,
    status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY,
    trigger_conditions: List[str] | None = None,
    is_default_version: bool = False,
    is_official_release: bool = True,
    supports_multiple_plugins: bool = False,
    feature_code: Optional[str] = None,
) -> CognitiveToolSpec:
    return CognitiveToolSpec(
        plugin_id=plugin_id,
        version=version,
        feature_code=feature_code or behavior_key or plugin_id,
        is_concurrency_safe=True,
        status=status,
        health_status=health_status,
        rollback_conditions=["runtime_regression_detected"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="analysis",
        purpose=f"{plugin_id} for web console inspection",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        required_context=["context_snapshot"],
        trigger_conditions=trigger_conditions or ["metacognition"],
        behavior_key=behavior_key or plugin_id,
        supports_multiple_plugins=supports_multiple_plugins,
        is_default_version=is_default_version,
        is_official_release=is_official_release,
        do_not_use_when=["unsafe_external_action"],
    )


def _seed_cognitive_registry(transcript_store: BrainTranscriptStore) -> CognitiveToolRegistry:
    startup_audit_sink = InMemoryAuditSink()
    registry = CognitiveToolRegistry(
        transcript_store=startup_audit_sink,
        protected_plugin_ids={
            "risk-comparator",
            "evidence-ranker",
            "decision-summarizer",
        },
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-comparator",
            behavior_key="risk_assessment",
            is_default_version=True,
        ),
        source_kind="builtin",
        description="Default risk assessment tool (builtin)",
    )
    registry.promote_plugin(
        "risk-comparator",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox checks passed",
    )
    registry.promote_plugin(
        "risk-comparator",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="health checks passed",
    )
    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="evidence-ranker",
            behavior_key="evidence_ranking",
            is_default_version=True,
        ),
        source_kind="builtin",
        description="Default evidence ranking tool (builtin)",
    )
    registry.promote_plugin(
        "evidence-ranker",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="sandbox checks passed",
    )
    registry.promote_plugin(
        "evidence-ranker",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="staged for runtime failure drill",
    )
    degraded_ranker = registry.get_registration("evidence-ranker")
    degraded_timestamp = datetime.now(timezone.utc)
    degraded_ranker_spec = degraded_ranker.spec.transition_to(
        PluginLifecycleStatus.DEGRADED,
        revocation_reasons=["seeded_degraded_for_web_console_demo"],
    )
    registry._plugins["evidence-ranker"] = degraded_ranker_spec
    registry._registrations["evidence-ranker"] = degraded_ranker.model_copy(
        update={
            "spec": degraded_ranker_spec,
            "failure_count": 3,
            "updated_at": degraded_timestamp,
            "started_at": degraded_ranker.started_at or degraded_timestamp,
        }
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="decision-summarizer",
            behavior_key="decision_summary",
            health_status=PluginHealthStatus.DEGRADED,
            is_default_version=True,
        ),
        source_kind="builtin",
        description="Default decision summarizer tool (builtin)",
    )
    registry.revoke_plugin("decision-summarizer", "manual audit revocation")

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="idea-scout",
            behavior_key="risk_assessment",
            trigger_conditions=["inspection"],
            is_official_release=True,
        )
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-lab-preview",
            version="1.3.0-preview",
            behavior_key="risk_assessment",
            trigger_conditions=["inspection"],
            is_official_release=False,
        )
    )

    registry.register(
        _build_cognitive_tool_spec(
            plugin_id="risk-comparator-legacy",
            version="0.9.0",
            behavior_key="risk_assessment",
            is_official_release=True,
        ),
        source_kind="builtin",
        description="Legacy risk comparator (builtin rollback candidate)",
    )

    # Core cognitive operators (LLM MANDATORY): nine questions + memory + reflection.
    # These are registered as real executable CognitiveToolSpec subclasses so they can
    # be invoked from the web-console test panel and audited via transcript replay.
    core_plugins = [
        build_q1_where_am_i_plugin(),
        build_q2_who_am_i_plugin(),
        build_q3_what_do_i_have_plugin(),
        build_q4_what_can_i_do_plugin(),
        build_q5_what_am_i_allowed_to_do_plugin(),
        build_q6_what_should_i_not_do_plugin(),
        build_q7_what_else_can_i_do_plugin(),
        build_q8_what_should_i_do_now_plugin(),
        build_q9_how_should_i_act_plugin(),
        build_memory_extractor_plugin(),
        build_reflection_generator_plugin(),
    ]
    for plugin in core_plugins:
        registration = registry.register(
            plugin,
            source_kind="builtin",
            description=f"Core cognitive operator: {plugin.plugin_id}",
        )
        if registration is None:
            continue
        registry.promote_plugin(
            plugin.plugin_id,
            PluginLifecycleStatus.SANDBOX_VERIFIED,
            audit_reason="web console sandbox verified",
        )
        registry.promote_plugin(
            plugin.plugin_id,
            PluginLifecycleStatus.ACTIVE,
            audit_reason="web console active for inspection/testing",
        )

    risk_comparator = registry.get_registration("risk-comparator")
    usage_timestamp = datetime.now(timezone.utc)
    registry._registrations["risk-comparator"] = risk_comparator.model_copy(
        update={
            "usage_count": max(1, risk_comparator.usage_count),
            "updated_at": usage_timestamp,
            "last_used_at": usage_timestamp,
            "started_at": risk_comparator.started_at or usage_timestamp,
        }
    )
    return registry


def _seed_plugin_registry() -> DevelopmentPluginRegistry:
    registry = DevelopmentPluginRegistry()
    plugins: list[BasePluginSpec] = [
        RolePackPlugin(),
        ConstraintPackPlugin(),
        build_default_conservative_weight(),
        build_default_redline_oracle(),
        build_default_alternative_oracle(),
        build_default_objective_oracle(),
        build_default_posture_oracle(),
    ]
    for plugin in plugins:
        registration = registry.register(plugin)
        if registration is None:
            continue
        registry.promote_plugin(
            plugin.plugin_id,
            PluginLifecycleStatus.SANDBOX_VERIFIED,
            audit_reason="sandbox checks passed",
        )
        registry.promote_plugin(
            plugin.plugin_id,
            PluginLifecycleStatus.ACTIVE,
            audit_reason="dev runtime functional plugin activated",
        )
    return registry


def _seed_runtime(
    *,
    interaction_mind_engine: InteractionMindEngine,
    consolidation_engine: ConsolidationEngine,
    transcript_store: BrainTranscriptStore,
) -> Tuple[BrainRuntime, object]:
    temporal_engine = CognitiveTemporalEngine(
        initial_items=[
            {
                "item_id": "agenda-refresh-plugin-panel",
                "title": "刷新插件状态面板",
                "status": "watching",
                "priority": 60,
                "next_review_condition": "wait_for_next_registry_snapshot",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "last_reviewed_at": datetime.now(timezone.utc),
                "watching": True,
                "reminder_rule": {
                    "review_interval_seconds": 600,
                    "cooldown_seconds": 300,
                    "grace_period_seconds": 60,
                    "expire_after_seconds": 7200,
                    "staleness_scale_seconds": 600,
                },
            },
            {
                "item_id": "agenda-check-degraded-tools",
                "title": "核查 degraded 工具",
                "status": "open",
                "priority": 80,
                "next_review_condition": "degraded_tools_present",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "last_reviewed_at": datetime.now(timezone.utc).replace(microsecond=0),
                "impact_score": 0.9,
                "uncertainty_score": 0.75,
                "reminder_rule": {
                    "review_interval_seconds": 60,
                    "cooldown_seconds": 30,
                    "grace_period_seconds": 10,
                    "expire_after_seconds": 7200,
                    "staleness_scale_seconds": 60,
                },
            },
            {
                "item_id": "agenda-ui-acceptance",
                "title": "补全 UI 验收流程",
                "status": "blocked",
                "priority": 70,
                "next_review_condition": "waiting_for_ui_acceptance_checklist",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "last_reviewed_at": datetime.now(timezone.utc).replace(microsecond=0),
                "impact_score": 0.95,
                "uncertainty_score": 0.8,
                "reminder_rule": {
                    "review_interval_seconds": 30,
                    "cooldown_seconds": 5,
                    "grace_period_seconds": 5,
                    "expire_after_seconds": 7200,
                    "staleness_scale_seconds": 30,
                },
            },
        ]
    )
    temporal_state = temporal_engine.evaluate(datetime.now(timezone.utc) + timedelta(minutes=3))
    conflict_engine = CognitiveConflictEngine(brain_scope="web-console")
    conflict_engine.ingest_reports(
        [
            CognitiveConflictReport(
                conflict_type="semantic_identity_conflict",
                severity="critical",
                suggested_resolution="pause_expansion_reasoning_and_review_identity_constraints",
                source_plugin_id="semantic-conflict",
                details={
                    "goal": "Aggressively expand autonomous action plan",
                    "identity_constraints": ["preserve continuity", "avoid unsafe escalation"],
                },
            ),
            CognitiveConflictReport(
                conflict_type="budget_conflict",
                severity="high",
                suggested_resolution="reduce_reasoning_branch_count_or_pause_expansion",
                source_plugin_id="budget-conflict",
                details={
                    "requested_tokens": 12000,
                    "token_budget": 4000,
                },
            ),
        ]
    )
    simulation_engine = CounterfactualSimulationEngine(
        model_provider=Mock(name="simulation_summary_provider"),
        simulation_plugins=[],
    )
    simulation_engine.seed_bundle(
        SimulationBundle(
            goal_id="goal-runtime-stability",
            idempotency_key="seed-runtime-stability",
            snapshot_version=0,
            status="completed",
            branches=[
                ScenarioBranch(
                    branch_id="branch-conservative",
                    branch_label="保守修复路径",
                    target_domain="general",
                    predicted_impacts=["优先稳定 replay 链路", "算力消耗可控"],
                    risk_score=0.2,
                    failure_cascade=False,
                    simulated_by=["simulation-thought-sandbox"],
                ),
                ScenarioBranch(
                    branch_id="branch-aggressive",
                    branch_label="激进扩展路径",
                    target_domain="market",
                    predicted_impacts=["推理分支显著增加", "存在灾难性失败级联风险"],
                    risk_score=0.92,
                    failure_cascade=True,
                    veto_reason="Projected failure cascade under degraded runtime",
                    simulated_by=["simulation-market-impact"],
                ),
            ],
            outcome_comparison=OutcomeComparison(
                summary="保守修复路径风险最低，建议优先收敛运行态。",
                risk_ranking=[
                    {"branch_id": "branch-conservative", "risk_score": 0.2, "rank": 1},
                    {"branch_id": "branch-aggressive", "risk_score": 0.92, "rank": 2},
                ],
                recommended_branch_id="branch-conservative",
            ),
            completed_at=datetime.now(timezone.utc),
        )
    )
    kuzu_adapter = None
    cluster_mode = os.environ.get("ZENTEX_CLUSTER_MODE", "false").lower() == "true"
    if not cluster_mode:
        try:
            kuzu_client = KuzuGraphMemoryClient(db_path=".zentex/kuzu_db")
            kuzu_adapter = EpisodeGraphMemoryAdapter(graph_client=kuzu_client)
        except Exception as e:
            logger.warning(f"Failed to initialize KuzuDB graph client: {e}")
            kuzu_adapter = None


    enhanced_memory_service = EnhancedMemoryService(
        semantic_store_path=Path(".zentex/runtime/enhanced_semantic.jsonl"),
        procedural_store_path=Path(".zentex/runtime/enhanced_procedural.jsonl"),
        episodic_store_path=Path(".zentex/runtime/enhanced_episodic.jsonl"),
        management_store_path=Path(".zentex/runtime/enhanced_management.json"),
        audit_store_path=Path(".zentex/runtime/enhanced_memory_audit.jsonl"),
        episodic_sink=kuzu_adapter,
        episodic_recall_client=kuzu_adapter,
    )
    runtime = BrainRuntime(
        default_workspace=".",
        transcript_store=transcript_store,
        runtime_memory_store=enhanced_memory_service,
        working_memory_controller=WorkingMemoryController(
            budget=FocusBudget(
                max_active_focus=3,
                max_suspended_focus=5,
                overflow_policy="drop_oldest"
            )
        ),
        living_self_model_engine=LivingSelfModelEngine(),
        metacognition_controller=MetaCognitionController(),
        temporal_engine=temporal_engine,
        conflict_engine=conflict_engine,
        simulation_engine=simulation_engine,
        interaction_mind_engine=interaction_mind_engine,
        consolidation_engine=consolidation_engine,
    )
    # Defer potentially heavy backfill to background to avoid blocking startup
    def _backfill_bg():
        try:
            enhanced_memory_service.backfill_transcript_entries(
                transcript_store.get_entries_snapshot()
            )
        except Exception:
            logger.exception("Deferred memory backfill failed")

    Thread(target=_backfill_bg, name="memory-backfill-bg", daemon=True).start()

    session = runtime.create_session("web-console")
    # Force transcript store to refresh from disk on startup to avoid stale cache
    transcript_store.get_entries_snapshot()
    existing_entries = transcript_store.read_by_session_id("web-console")
    
    if existing_entries:
        logger.info(f"[Startup] Found {len(existing_entries)} transcript entries for web-console. Restoring session...")
        session.restore_from_transcript()
        runtime.nine_question_state = session.current_nine_question_state
        runtime.active_session = session
        
        snapshot_count = len(runtime.nine_question_state.question_snapshots)
        logger.info(f"[Startup] Session restored. Recovered {snapshot_count}/9 cognitive snapshots.")
        
        if snapshot_count > 0:
            runtime.set_nine_question_bootstrap_status("ready")
        else:
            runtime.set_nine_question_bootstrap_status("initializing", trace_id="startup-cold-start")
        return runtime, session

    logger.info("[Startup] No existing transcript found for web-console. Entering initializing state.")
    runtime.set_nine_question_bootstrap_status("initializing", trace_id="startup-cold-start")
    return runtime, session


def _seed_interaction_mind_engine(*, model_provider: ModelProviderSpec) -> InteractionMindEngine:
    """构造开发态社会心智模型引擎，并注入一条可视化样本状态。"""
    engine = InteractionMindEngine(
        model_provider=model_provider,
        brain_scope="web-console",
    )
    engine.seed_state(
        InteractionMindState(
            entity_id="web-console",
            brain_scope="web-console",
            snapshot_version=1,
            clarification_mode=False,
            model=InteractionMindModel(
                entity_id="web-console",
                role_hint="人工验收操作者",
                current_goal_hypothesis="希望快速核对系统状态并定位风险点",
                knowledge_depth="high",
                tolerance_for_detail="medium",
                current_engagement_state="high",
                trust_estimate=0.78,
            ),
            knowledge_gap=KnowledgeGapEstimate(
                entity_id="web-console",
                known_topics=["插件状态", "事件流观测"],
                uncertain_topics=["多分支推演内部细节"],
                likely_missing_topics=["最新的误解风险来源"],
                confidence=0.72,
            ),
            communication_fit=CommunicationFitProfile(
                entity_id="web-console",
                preferred_style="evidence_first",
                detail_level="medium",
                clarification_bias=0.65,
                risk_of_misunderstanding=0.82,
            ),
            misunderstanding_signals=[
                MisunderstandingSignal(
                    entity_id="web-console",
                    signal_type="correction",
                    severity="high",
                )
            ],
        )
    )
    return engine


def _seed_weight_assembler() -> WeightPluginAssembler:
    audit_client = Mock()
    audit_client.evaluate.side_effect = RationalAuditRejectError(
        "G25 rejected the candidate weight plugin due to unsafe creative drift."
    )
    assembler = WeightPluginAssembler(audit_client=audit_client)
    assembler.mount_plugin(build_creative_exploration_weight())
    return assembler


def _seed_consolidation_engine(
    *,
    model_provider: ModelProviderSpec,
    transcript_store: BrainTranscriptStore,
) -> ConsolidationEngine:
    """构造开发态巩固引擎，并注入一条完成周期样本供前端回放。"""
    engine = ConsolidationEngine(
        model_provider=model_provider,
        analysis_plugins=[
            build_failure_mode_cluster_plugin(),
            build_expired_assumption_cleaner_plugin(),
        ],
        transcript_store=transcript_store,
        brain_scope="web-console",
    )
    engine.seed_memory_snapshot(
        ref_versions={
            "reflection:timeout-incident-1": 1,
            "reflection:timeout-incident-2": 1,
            "assumption:expired-budget-guess": 1,
            "identity_role_pack:core-role": 1,
        },
        tombstone_state={"identity_role_pack:core-role": False},
        snapshot_version=2,
    )
    engine.seed_cycle(
        ConsolidationCycle(
            cycle_id="cycle-memory-bootstrap",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=15),
            ended_at=datetime.now(timezone.utc) - timedelta(minutes=14),
            input_refs=[
                "reflection:timeout-incident-1",
                "reflection:timeout-incident-2",
                "assumption:expired-budget-guess",
                "identity_role_pack:core-role",
            ],
            promoted_refs=[
                "reflection:timeout-incident-1",
                "reflection:timeout-incident-2",
            ],
            pruned_refs=["assumption:expired-budget-guess"],
            compressed_refs=[
                "reflection:timeout-incident-1",
                "reflection:timeout-incident-2",
            ],
            summary="系统在离线巩固中识别出重复超时事故模式，并保留核心身份包不被遗忘。",
            trigger_stage="sleep_phase",
            brain_scope="web-console",
            lease_id="lease-memory-bootstrap",
            idempotency_key="bootstrap-memory-cycle",
            snapshot_version=3,
            status="completed",
            promotion_candidates=[
                MemoryPromotionCandidate(
                    candidate_id="candidate-timeout-lesson",
                    source_ref="reflection:timeout-incident-1",
                    candidate_type="lesson",
                    stability_score=0.95,
                    reuse_value=0.91,
                    promotion_reason="Repeated timeout incidents produced a stable reusable lesson.",
                )
            ],
            pattern_scores=[
                PatternStabilityScore(
                    pattern_id="pattern:timeout-escalation",
                    frequency=2,
                    time_span_seconds=1800,
                    cross_context_reuse=0.84,
                    conflict_count=0,
                    stability_score=0.95,
                )
            ],
        )
    )
    return engine


def _seed_managed_plugins() -> List[object]:
    # Set feature codes for each plugin domain
    semantic_conflict = build_semantic_conflict_plugin()
    # Pydantic is frozen=True, need to model_copy if we want to change it, 
    # but build_* should probably handle it. For now let's just use defaults or override.
    # Actually build_* might not have feature_code yet. 
    # I'll update the plugins to HAVE feature_code.
    semantic_conflict = build_semantic_conflict_plugin()
    budget_conflict = build_budget_conflict_plugin()
    failure_cluster = build_failure_mode_cluster_plugin()
    assumption_cleaner = build_expired_assumption_cleaner_plugin()
    sensory_ingest = BasicWebhookIngestPlugin(
        payload="web console seeded sensory payload",
        plugin_id="sensory-ingest-webhook",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["webhook_parse_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )
    sensory_sanitize = BasicPromptInjectionSanitizer(
        plugin_id="sensory-sanitize-basic",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["sanitize_false_negative_spike"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )
    sensory_interpret = BasicEnvironmentInterpreter(
        plugin_id="sensory-interpret-generic",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["interpretation_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )
    host_telemetry = build_default_host_telemetry_plugin()

    # Dev-server should follow the operator's actual runtime configuration.
    # Prefer direct OpenAI when OPENAI_API_KEY is present; otherwise keep
    from plugins.provider_tools import get_default_provider_key

    provider_name = get_default_provider_key()
    model_provider = build_default_provider_tools_model_provider(
        provider_name=provider_name,
        plugin_id=f"model-provider-{provider_name.replace('_', '-')}",
        version="1.0.0",
    )

    execution_system = build_default_local_system_executor().model_copy(
        update={"status": PluginLifecycleStatus.ACTIVE}
    )
    execution_browser = build_default_cloud_browser_executor().model_copy(
        update={"status": PluginLifecycleStatus.SANDBOX_VERIFIED}
    )
    simulation_sandbox = build_default_thought_sandbox().model_copy(
        update={"status": PluginLifecycleStatus.ACTIVE}
    )
    simulation_market = build_default_market_simulator().model_copy(
        update={"status": PluginLifecycleStatus.SANDBOX_VERIFIED}
    )
    weight_plugins: List[SubjectiveWeightPlugin] = [
        build_default_conservative_weight(),
        build_risk_balanced_weight(),
        build_cost_guard_weight().model_copy(
            update={"status": PluginLifecycleStatus.SANDBOX_VERIFIED}
        ),
    ]
    identity_role_pack = RolePackPlugin()
    identity_constraint_pack = ConstraintPackPlugin()
    redline_oracle = build_default_redline_oracle()
    alternative_oracle = build_default_alternative_oracle()
    objective_oracle = build_default_objective_oracle()
    posture_oracle = build_default_posture_oracle()

    return [
        build_managed_plugin_record(
            semantic_conflict,
            feature_code="cognitive_conflict_detection",
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            budget_conflict,
            feature_code="cognitive_conflict_detection",
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            failure_cluster,
            feature_code="memory_consolidation",
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            assumption_cleaner,
            feature_code="memory_consolidation",
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            model_provider,
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            sensory_ingest,
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            sensory_sanitize,
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            sensory_interpret,
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            host_telemetry,
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            execution_system,
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            execution_browser,
            is_default=False,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            simulation_sandbox,
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            simulation_market,
            is_default=False,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            weight_plugins[0],
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            weight_plugins[1],
            is_default=False,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            weight_plugins[2],
            is_default=False,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            identity_role_pack,
            feature_code="identity.role",
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            identity_constraint_pack,
            feature_code="identity.constraint",
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            redline_oracle,
            feature_code="redline.core",
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            alternative_oracle,
            feature_code="alternative.core",
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            objective_oracle,
            feature_code="objective.core",
            is_default=True,
            is_official_release=True,
        ),
        build_managed_plugin_record(
            posture_oracle,
            feature_code="posture.core",
            is_default=True,
            is_official_release=True,
        ),
    ]


def _seed_plugin_feature_catalog() -> List[PluginFeatureCatalogItem]:
    return [
        PluginFeatureCatalogItem(
            feature_code="risk_assessment",
            display_name="风险评估",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="evidence_ranking",
            display_name="证据排序",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="decision_summary",
            display_name="决策摘要",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="cognitive_conflict_detection",
            display_name="认知冲突监控",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="memory_consolidation",
            display_name="离线记忆巩固",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="core.model_provider",
            display_name="大模型推理底座",
            plugin_kind="model_provider",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="sensory.ingest",
            display_name="信号摄取",
            plugin_kind="signal_ingest",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="sensory.sanitize",
            display_name="信号净化",
            plugin_kind="signal_sanitize",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="sensory.interpret",
            display_name="信号解释",
            plugin_kind="signal_interpret",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="host.telemetry",
            display_name="宿主机健康度采集",
            plugin_kind="host_telemetry",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="execution.system",
            display_name="系统执行域",
            plugin_kind="execution_domain",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="execution.browser",
            display_name="浏览器执行域",
            plugin_kind="execution_domain",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="simulation.bundle",
            display_name="通用推演沙箱",
            plugin_kind="simulation_domain",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="simulation.market",
            display_name="市场推演沙箱",
            plugin_kind="simulation_domain",
            supports_multiple_plugins=False,
        ),
        PluginFeatureCatalogItem(
            feature_code="weights:subjective_preferences",
            display_name="主观权重偏好",
            plugin_kind="subjective_weight",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="identity:package_loader",
            display_name="身份与经验包",
            plugin_kind="identity_package",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="redline.core",
            display_name="红线禁区基座",
            plugin_kind="redline",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="alternative.core",
            display_name="备选策略基座",
            plugin_kind="alternative",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="objective.core",
            display_name="主目标编排基座",
            plugin_kind="objective",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="posture.core",
            display_name="行动姿态基座",
            plugin_kind="posture",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="nine_questions.q1",
            display_name="九问 Q1（LLM 强制）",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="nine_questions.q2",
            display_name="九问 Q2（LLM 强制）",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="nine_questions.q3",
            display_name="九问 Q3（LLM 强制）",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="nine_questions.q4",
            display_name="九问 Q4（LLM 强制）",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="nine_questions.q5",
            display_name="九问 Q5（LLM 强制）",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="nine_questions.q6",
            display_name="九问 Q6（LLM 强制）",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="nine_questions.q7",
            display_name="九问 Q7（LLM 强制）",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="nine_questions.q8",
            display_name="九问 Q8（LLM 强制）",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="nine_questions.q9",
            display_name="九问 Q9（LLM 强制）",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="memory.extract",
            display_name="记忆提取（LLM 强制）",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
        PluginFeatureCatalogItem(
            feature_code="reflection.generate",
            display_name="反思生成（LLM 强制）",
            plugin_kind="cognitive_tool",
            supports_multiple_plugins=True,
        ),
    ]


def _seed_agent_coordination(transcript_store: BrainTranscriptStore) -> Tuple[AgentManager, AgentCoordinationService]:
    manager = AgentManager()
    service = AgentCoordinationService(manager, transcript_store)
    return manager, service


def _seed_mcp_adapter(
    transcript_store: BrainTranscriptStore,
    cognitive_registry: CognitiveToolRegistry,
    *,
    defer_sync: bool = False,
) -> Tuple[McpAdapterPlugin, ExecutionDomainRegistry]:
    execution_registry = ExecutionDomainRegistry()
    server_configs = [
        McpServerConfig(
            server_id="knowledge-hub",
            transport_type="stdio",
            command="uvx",
            args=["knowledge-hub-mcp"],
            env={"KNOWLEDGE_ENV": "dev"},
            tool_bindings=[
                McpToolBindingConfig(
                    tool_name="search_documents",
                    domain="cognitive",
                    read_only=True,
                    side_effect_free=True,
                    mutates_state=False,
                )
            ],
        ),
        McpServerConfig(
            server_id="ops-bridge",
            transport_type="sse",
            command="https://ops.example.invalid/mcp",
            args=[],
            env={},
        ),
    ]

    transports = {
        "knowledge-hub": FakeMcpTransportClient(
            tools=[
                McpToolDescriptor(
                    tool_name="search_documents",
                    description="Search indexed runbooks and incident notes",
                    input_schema={"type": "object"},
                    mutates_state=False,
                    read_only_hint=True,
                )
            ],
            invocations={
                "search_documents": {
                    "summary": "knowledge search completed",
                    "context_updates": {"knowledge_hits": ["runbook-42"]},
                }
            },
            healthy=True,
        ),
        "ops-bridge": FakeMcpTransportClient(
            tools=[
                McpToolDescriptor(
                    tool_name="update_ticket",
                    description="Update incident ticket in external system",
                    input_schema={"type": "object"},
                    mutates_state=True,
                    read_only_hint=False,
                )
            ],
            invocations={"update_ticket": {"summary": "ticket updated", "receipt_id": "ops-991"}},
            healthy=True,
        ),
    }

    adapter = McpAdapterPlugin(
        plugin_id="mcp-adapter-core",
        version="1.0.0",
        feature_code="external.mcp",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["mcp_adapter_regression"],
        revocation_reasons=["mcp_adapter_disabled"],
        health_probe_endpoint="mcp://health",
        server_configs=server_configs,
    )
    adapter.attach_runtime(
        client_factory=lambda config: transports[config.server_id],
        transcript_store=transcript_store,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
    )
    if defer_sync:

        def _sync_bg():
            try:
                adapter.sync_servers()
            except Exception:
                logger.exception("Deferred MCP sync failed")

        Thread(target=_sync_bg, name="mcp-bg-sync", daemon=True).start()
    else:
        adapter.sync_servers()
    return adapter, execution_registry


def _seed_cli_adapter(
    transcript_store: BrainTranscriptStore,
    cognitive_registry: CognitiveToolRegistry,
    execution_registry: ExecutionDomainRegistry,
) -> CliAdapterPlugin:
    adapter = CliAdapterPlugin(
        plugin_id="cli-adapter-dev",
        version="1.0.0",
        feature_code="external.cli",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["cli_adapter_regression"],
        revocation_reasons=["cli_adapter_disabled"],
    )
    adapter.attach_runtime(
        transport=SubprocessCliTransport(),
        transcript_store=transcript_store,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
    )
    adapter.register_tool(
        CliToolRegistrationConfig(
            tool_name="repo_echo_probe",
            command_executable="/bin/echo",
            description="Read-only shell probe for CLI integration smoke tests.",
            read_only_flag=True,
            project_path=".",
            project_name="AnimoCerebro",
            project_description="Zentex workspace shell probe",
        )
    )
    return adapter


def _seed_task_management(
    transcript_store: BrainTranscriptStore,
    *,
    managed_plugins: List[object],
) -> TaskManagementService:
    registry = TaskRegistry()
    # Prefer LLM-backed mission decomposition for task splitting.
    model_provider = next(
        record.plugin
        for record in managed_plugins
        if getattr(record.plugin, "plugin_kind", lambda: "")() == "model_provider"
    )
    service = TaskManagementService(
        registry,
        transcript_store,
        decomposer=LLMTaskDecomposerPlugin(
            model_provider=model_provider,
            transcript_store=transcript_store,
        ),
    )
    return service


def _seed_nine_question_runtime_state(runtime: BrainRuntime, session: object) -> None:
    state = getattr(session, "current_nine_question_state", None)
    if state is None:
        return

    question_specs = {
        "q1": {
            "title": "当前运行域是本地 Web Console 验收环境，重点检查真实 API 绑定。",
            "tool_id": "nine_questions.q1",
            "context_updates": {
                "primary_domain": "web_console",
                "environment_description": "本地开发运行态，正在核对九问、任务、Agent 三条控制面链路。",
            },
            "phase": "nine_question_q1_where_am_i",
        },
        "q2": {
            "title": "当前主体是 Zentex Web Console 操作代理，职责是展示运行态与审计结果。",
            "tool_id": "nine_questions.q2",
            "context_updates": {
                "active_role": "web_console_operator",
                "role_summary": "负责读取运行态状态机并向前端呈现。",
            },
            "phase": "nine_question_q2_who_am_i",
        },
        "q3": {
            "title": "当前可用资源包括任务状态机、Agent 协调服务、transcript 与九问缓存。",
            "tool_id": "nine_questions.q3",
            "context_updates": {
                "resource_status": "ready",
                "resource_inventory": ["task_service", "agent_coordination_service", "transcript_store"],
            },
            "phase": "nine_question_q3_what_do_i_have",
        },
        "q4": {
            "title": "当前可以读取控制面 API、查看审计回放、执行受控人工干预。",
            "tool_id": "nine_questions.q4",
            "context_updates": {
                "capabilities": ["read_api_state", "inspect_replay", "intervene_tasks"],
            },
            "phase": "nine_question_q4_what_can_i_do",
        },
        "q5": {
            "title": "允许动作限定为受审计的只读检查与显式人工干预。",
            "tool_id": "nine_questions.q5",
            "context_updates": {
                "permission_boundary": {
                    "execution_tier": "guarded_write",
                    "interaction_scope": "web_console_control_plane",
                },
                "compliance_checklist": {
                    "explicitly_forbidden_actions": ["skip_audit", "fake_runtime_state"],
                },
            },
            "phase": "nine_question_q5_authorization",
        },
        "q6": {
            "title": "即使具备权限，也不能伪造运行态、跳过审计或隐藏失败。",
            "tool_id": "nine_questions.q6",
            "context_updates": {
                "forbidden_zone_profile": {
                    "absolute_red_lines": ["NO_FAKE_RUNTIME_STATE", "NO_FAKE_TEST_RESULT"],
                    "performance_tradeoff_bans": ["NO_SPEED_OVER_AUDIT"],
                },
            },
            "phase": "nine_question_q6_redline",
        },
        "q7": {
            "title": "可选路径包括重跑状态机、追踪 transcript、检查 Agent/任务聚合视图。",
            "tool_id": "nine_questions.q7",
            "context_updates": {
                "alternatives": ["replay_trace", "refresh_task_queue", "inspect_agent_receipts"],
            },
            "phase": "nine_question_q7_alternatives",
        },
        "q8": {
            "title": "当前优先动作是验证前后端是否真实连到了状态对象。",
            "tool_id": "nine_questions.q8",
            "context_updates": {
                "current_priority": "verify_real_bindings",
                "recommended_next_step": "inspect_web_console_panels",
            },
            "phase": "nine_question_q8_decision",
        },
        "q9": {
            "title": "行动姿态应保持保守、可审计、先证据后结论。",
            "tool_id": "nine_questions.q9",
            "context_updates": {
                "action_posture": "audit_first",
                "style": "conservative_and_traceable",
            },
            "phase": "nine_question_q9_posture",
        },
    }

    entries_to_write: List[BrainTranscriptEntry] = []
    for index, (question_id, spec) in enumerate(question_specs.items(), start=1):
        trace_id = f"seed-nine-{question_id}"
        state.apply_question_result(
            question_id=question_id,  # type: ignore[arg-type]
            tool_id=spec["tool_id"],
            summary=spec["title"],
            confidence=0.91,
            context_updates=spec["context_updates"],
            trace_id=trace_id,
            refresh_reason="dev_server_seed",
            driver_refs=["seed:web-console", f"seed:{question_id}"],
        )
        timestamp = datetime.now(timezone.utc) + timedelta(seconds=index)
        entries_to_write.append(
            BrainTranscriptEntry(
                entry_id=str(uuid4()),
                session_id="web-console",
                turn_id=f"seed-turn-{question_id}",
                entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
                timestamp=timestamp,
                source="dev_server.seed",
                trace_id=trace_id,
                payload={
                    "request_id": f"seed-request-{question_id}",
                    "decision_id": f"seed-decision-{question_id}",
                    "provider_plugin_id": "model-provider-openai-compat",
                    "prompt": spec["title"],
                    "context": spec["context_updates"],
                    "caller_context": {
                        "source_module": "dev_server.seed",
                        "invocation_phase": spec["phase"],
                        "question_driver_refs": ["seed:web-console", f"seed:{question_id}"],
                    },
                },
            )
        )
        entries_to_write.append(
            BrainTranscriptEntry(
                entry_id=str(uuid4()),
                session_id="web-console",
                turn_id=f"seed-turn-{question_id}",
                entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
                timestamp=timestamp + timedelta(milliseconds=250),
                source="dev_server.seed",
                trace_id=trace_id,
                payload={
                    "result": spec["context_updates"],
                    "caller_context": {
                        "source_module": "dev_server.seed",
                        "invocation_phase": spec["phase"],
                        "question_driver_refs": ["seed:web-console", f"seed:{question_id}"],
                    },
                },
            )
        )
    runtime.transcript_store.append_entries(entries_to_write)


async def _seed_task_and_agent_runtime_state(
    task_service: TaskManagementService,
    agent_service: AgentCoordinationService,
) -> None:
    agents = [
        AgentAsset(
            agent_id="agent-build",
            name="agent-build",
            agent_name="Build Bot",
            version="1.2.3",
            function_description="负责构建、测试与交付前的运行态检查。",
            endpoint="http://127.0.0.1:9101",
            role_tag="worker",
            trust_level=AgentTrustLevel.TRUSTED,
            status=AgentStatus.ACTIVE,
            scope=["build", "ci"],
            capabilities=[{"capability": "build", "version": "1.0"}],
            latency_ms=32.5,
            success_rate=0.98,
        ),
        AgentAsset(
            agent_id="agent-audit",
            name="agent-audit",
            agent_name="Audit Bot",
            version="2.0.1",
            function_description="负责 transcript 审计与运行态回放核对。",
            endpoint="http://127.0.0.1:9102",
            role_tag="auditor",
            trust_level=AgentTrustLevel.TRUSTED,
            status=AgentStatus.IDLE,
            scope=["audit", "replay"],
            capabilities=[{"capability": "audit", "version": "2.0"}],
            latency_ms=41.0,
            success_rate=0.995,
        ),
        AgentAsset(
            agent_id="agent-memory",
            name="agent-memory",
            agent_name="Memory Bot",
            version="1.5.0",
            function_description="负责记忆整理与任务回执归档。",
            endpoint="http://127.0.0.1:9103",
            role_tag="support",
            trust_level=AgentTrustLevel.RESTRICTED,
            status=AgentStatus.BUSY,
            scope=["memory"],
            capabilities=[{"capability": "memory", "version": "1.5"}],
            latency_ms=58.0,
            success_rate=0.97,
        ),
    ]
    for agent in agents:
        agent_service.manager.add_asset(agent)

    seed_tasks = [
        {
            "idempotency_key": "seed-task-001",
            "title": "校验九问真实状态绑定",
            "task_type": TaskType.SYSTEM_ACTION,
            "status": TaskStatus.IN_PROGRESS,
            "progress": 0.55,
            "originator_id": "web-console",
            "target_id": "agent-build",
            "remarks": "正在核对 NineQuestionState 与前端卡片绑定。",
        },
        {
            "idempotency_key": "seed-task-002",
            "title": "审计 Agent 收件箱聚合",
            "task_type": TaskType.COGNITIVE_STEP,
            "status": TaskStatus.TODO,
            "progress": 0.0,
            "originator_id": "web-console",
            "target_id": "agent-audit",
            "remarks": "等待检查 receipts 与 inbox 视图。",
        },
        {
            "idempotency_key": "seed-task-003",
            "title": "归档任务执行回执",
            "task_type": TaskType.INTERVENTION,
            "status": TaskStatus.DONE,
            "progress": 1.0,
            "originator_id": "web-console",
            "target_id": "agent-memory",
            "remarks": "历史回执已归档。",
        },
    ]
    for payload in seed_tasks:
        key = str(payload["idempotency_key"])
        # Use the shared idempotency store instead of direct attribute access
        existing_id = task_service._shared_idempotency.get(key)
        if existing_id:
            continue
        now = datetime.now(timezone.utc)
        task_id = str(uuid4())[:8]
        started_at = None
        completed_at = None
        if payload["status"] == TaskStatus.IN_PROGRESS:
            started_at = now
        elif payload["status"] == TaskStatus.DONE:
            started_at = now - timedelta(minutes=8)
            completed_at = now - timedelta(minutes=2)

        task = ZentexTask(
            task_id=task_id,
            idempotency_key=key,
            title=str(payload["title"]),
            task_type=payload["task_type"],
            status=payload["status"],
            progress=float(payload["progress"]),
            originator_id=str(payload["originator_id"]),
            target_id=str(payload["target_id"]),
            remarks=str(payload["remarks"]),
            started_at=started_at,
            completed_at=completed_at,
            created_at=now,
            last_updated_at=now,
        )
        # Use shared state stores
        task_service._shared_tasks.set(task_id, task)
        task_service._shared_idempotency.set(key, task_id)
        # Also update local cache for backward compatibility
        task_service._tasks[task_id] = task
        task_service._idempotency_log[key] = task_id


def _should_autorun_real_startup_nine_questions() -> bool:
    flag = str(os.getenv("ZENTEX_AUTORUN_STARTUP_NINE_QUESTIONS", "")).strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _should_seed_fake_startup_nine_questions() -> bool:
    flag = str(os.getenv("ZENTEX_SEED_STARTUP_NINE_QUESTIONS", "")).strip().lower()
    return flag in {"1", "true", "yes", "on"} or "pytest" in sys.modules


def _build_startup_workspace_snapshot(
    *,
    workspace_root: str,
    cognitive_registry: CognitiveToolRegistry,
    execution_registry: ExecutionDomainRegistry | None,
    task_service: TaskManagementService | None,
    host_telemetry_plugin: object | None = None,
    mcp_service: object | None = None,
    cli_service: object | None = None,
) -> dict[str, object]:
    return build_runtime_workspace_snapshot(
        workspace_root=workspace_root,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
        task_service=task_service,
        environment_summary="web console startup auto-ran nine questions",
        host_telemetry_plugin=host_telemetry_plugin,
        mcp_service=mcp_service,
        cli_service=cli_service,
    )


def _auto_run_startup_nine_questions(
    *,
    runtime: BrainRuntime,
    session: object,
    cognitive_registry: CognitiveToolRegistry,
    execution_registry: ExecutionDomainRegistry | None,
    task_service: TaskManagementService | None,
    mcp_adapter: object | None = None,
    cli_adapter: object | None = None,
) -> None:
    state = getattr(session, "current_nine_question_state", None)
    if state is None:
        return

    # Create MCP and CLI integration services from adapters (via service facade)
    mcp_service = None
    cli_service = None
    try:
        from zentex.mcp.service import McpIntegrationService
        from zentex.cli.service import CliIntegrationService
        
        if mcp_adapter is not None:
            mcp_service = McpIntegrationService(adapter=mcp_adapter)
            # Log MCP server count for debugging
            mcp_servers = mcp_service.list_servers()
            logger.info(f"[Nine Questions Q3] MCP servers count: {len(mcp_servers)}")
            if len(mcp_servers) > 0:
                for srv in mcp_servers:
                    logger.info(f"  - MCP Server: {srv.get('server_id')} ({srv.get('tool_count')} tools)")
            else:
                logger.warning("[Nine Questions Q3] No MCP servers registered. Q3 data may be incomplete.")
        
        if cli_adapter is not None:
            cli_service = CliIntegrationService(adapter=cli_adapter)
            # Log CLI tools count for debugging
            cli_tools = cli_service.list_tools()
            logger.info(f"[Nine Questions Q3] CLI tools count: {len(cli_tools)}")
            if len(cli_tools) > 0:
                for tool in cli_tools:
                    logger.info(f"  - CLI Tool: {tool.get('command_name')} -> {tool.get('plugin_id')}")
    except Exception as exc:
        logger.warning(f"Failed to create MCP/CLI integration services: {exc}")

    # Log execution registry status
    if execution_registry is not None and hasattr(execution_registry, "list_registrations"):
        exec_domains = list(execution_registry.list_registrations())
        logger.info(f"[Nine Questions Q3] Execution domains count: {len(exec_domains)}")
        for domain in exec_domains:
            logger.info(f"  - Execution Domain: {domain.plugin_id}")
    else:
        logger.warning("[Nine Questions Q3] Execution registry is None or invalid")

    workspace_root = str(getattr(runtime, "default_workspace", ".") or ".")
    startup_context = _build_startup_workspace_snapshot(
        workspace_root=workspace_root,
        cognitive_registry=cognitive_registry,
        execution_registry=execution_registry,
        task_service=task_service,
        host_telemetry_plugin=next(
            (
                record.plugin
                for record in getattr(runtime, "managed_plugin_records", {}).values()
                if getattr(record, "feature_code", None) == "host.telemetry"
                and getattr(getattr(record, "plugin", None), "status", None) == PluginLifecycleStatus.ACTIVE
            ),
            None,
        ),
        mcp_service=mcp_service,
        cli_service=cli_service,
    )
    session.last_context_snapshot = dict(startup_context)

    event = build_event(
        event_type="cold_start",
        reason="dev_server_startup_autorun",
        trace_id="startup-nine-questions",
        dirty_questions=runtime.nine_question_router.derive_dirty_questions_for_event("cold_start"),
        payload={"workspace_root": workspace_root},
    )
    runtime.nine_question_router.publish(state, event)
    runtime.refresh_nine_question_state(
        question_driver_refs=["startup:web-console", "cold_start"],
        refresh_reason="dev_server_startup_autorun",
        context_snapshot=startup_context,
        active_constraints=[],
    )
    executor = NineQuestionExecutor(
        registry=cognitive_registry,
        transcript_store=runtime.transcript_store,
    )
    for queued_event in runtime.nine_question_router.drain():
        executor.run_questions(
            runtime=runtime,
            session=session,
            state=state,
            question_ids=queued_event.dirty_questions,
            trace_id=queued_event.trace_id,
            refresh_reason=queued_event.reason,
            driver_refs=["startup:web-console", queued_event.event_type],
            turn_id="turn-startup-nine-questions",
        )


def _start_cold_start_onboarding_background(
    *,
    runtime: BrainRuntime,
    session: object,
) -> None:
    def _runner() -> None:
        think_loop = ThinkLoop()
        try:
            result = think_loop.run(session)
            session.advance_turn(result)
            runtime.set_nine_question_bootstrap_status("ready", trace_id=result.turn_id)
        except Exception as exc:
            logger.exception("cold-start onboarding failed")
            runtime.set_nine_question_bootstrap_status(
                "failed",
                trace_id="startup-cold-start",
                error=str(exc),
            )

    Thread(target=_runner, name="zentex-cold-start-nine-questions", daemon=True).start()


def build_dev_server_app():
    try:
        # Step 1: Parallelize plugin builds which are CPU-bound / non-dependent
        with ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 1) * 4)) as executor:
            plugin_records_future = executor.submit(_seed_managed_plugins)
            feature_catalog_future = executor.submit(_seed_plugin_feature_catalog)
            
            managed_plugins = plugin_records_future.result()
            plugin_feature_catalog = feature_catalog_future.result()

        transcript_store = BrainTranscriptStore(".zentex/runtime/web_console_transcript.jsonl")
        cognitive_registry = _seed_cognitive_registry(transcript_store)
        
        # Step 2: Defer MCP sync
        mcp_adapter, execution_registry = _seed_mcp_adapter(
            transcript_store, cognitive_registry, defer_sync=True
        )
        cli_adapter = _seed_cli_adapter(transcript_store, cognitive_registry, execution_registry)
        cognitive_registry.set_audit_sink(transcript_store=transcript_store)
        plugin_registry = _seed_plugin_registry()
        weight_assembler = _seed_weight_assembler()
        model_provider = next(
            (
                record.plugin
                for record in managed_plugins
                if getattr(record.plugin, "plugin_kind", lambda: "")() == "model_provider"
            ),
            None,
        )
        if model_provider is None:
            raise ConfigError("Web 控制台启动失败：未找到可用的 model_provider 插件。")
        interaction_mind_engine = _seed_interaction_mind_engine(model_provider=model_provider)
        consolidation_engine = _seed_consolidation_engine(
            model_provider=model_provider,
            transcript_store=transcript_store,
        )
        task_service = _seed_task_management(transcript_store, managed_plugins=managed_plugins)
        upgrade_management_store = UpgradeManagementStore(
            records=[
                UpgradeManagementRecord(
                    record_id="llm-upgrade-q1-001",
                    target_kind=UpgradeTargetKind.LLM,
                    action="upgrade",
                    target_id="nine_questions.q1.where_am_i",
                    title="Q1 reasoning accuracy optimization",
                    reason="Q1 domain classification drift detected in mixed workspaces.",
                    trace_id="upgrade-trace-q1-001",
                    request_id="upgrade-request-q1-001",
                    source_event_id="signal:q1-drift-001",
                    parent_record_id=None,
                    evidence_refs=["metrics/q1_drift_report.json"],
                    change_summary="Re-optimize prompt bundle and scorer thresholds.",
                    function_summary="Improve Q1 environment inference stability.",
                    previous_version="1.0.0",
                    current_version="1.0.0",
                    candidate_version="1.1.0-candidate",
                    current_status=UpgradeLifecycleStatus.VALIDATING,
                    current_progress=72,
                    audit_status="running",
                    memory_status="queued",
                    started_at=utc_now(),
                ),
                UpgradeManagementRecord(
                    record_id="llm-upgrade-q4-queue-001",
                    target_kind=UpgradeTargetKind.LLM,
                    action="upgrade",
                    target_id="nine_questions.q4.what_can_i_do",
                    title="Q4 capability reasoning upgrade queue",
                    reason="Queued behind the active Q1 optimization batch.",
                    trace_id="upgrade-trace-q4-queue-001",
                    request_id="upgrade-request-q4-queue-001",
                    source_event_id="queue:q4-batch-001",
                    parent_record_id="llm-upgrade-q1-001",
                    evidence_refs=["queue/q4_upgrade_batch.json"],
                    change_summary="Prepare DSPy optimization assets for Q4 capability reasoning.",
                    function_summary="Improve Q4 actionable-space ranking consistency.",
                    previous_version="1.2.0",
                    current_version="1.2.0",
                    candidate_version="1.3.0-candidate",
                    current_status=UpgradeLifecycleStatus.QUEUED,
                    current_progress=0,
                    audit_status="queued",
                    memory_status="queued",
                ),
                UpgradeManagementRecord(
                    record_id="plugin-upgrade-router-001",
                    target_kind=UpgradeTargetKind.PLUGIN,
                    action="upgrade",
                    target_id="cognitive-tool-router",
                    title="Cognitive router publication hook upgrade",
                    reason="Need structured publication hooks for candidate promotion.",
                    trace_id="upgrade-trace-plugin-router-001",
                    request_id="upgrade-request-plugin-router-001",
                    source_event_id="signal:router-hook-gap-001",
                    parent_record_id=None,
                    evidence_refs=["audits/router_publication_gap.md"],
                    change_summary="Add publication hook output and validation gate.",
                    function_summary="Upgrade existing plugin behavior without mutating the source plugin.",
                    previous_version="0.4.0",
                    current_version="0.4.0",
                    candidate_version="0.5.0-candidate",
                    current_status=UpgradeLifecycleStatus.COMPLETED,
                    current_progress=100,
                    source_path="src/zentex/runtime/cognitive_tools",
                    candidate_path="src/zentex/runtime/cognitive_tools_candidate_0_5_0_candidate",
                    audit_status="completed",
                    memory_status="persisted",
                    started_at=utc_now(),
                    finished_at=utc_now(),
                ),
                UpgradeManagementRecord(
                    record_id="plugin-create-anomaly-001",
                    target_kind=UpgradeTargetKind.PLUGIN,
                    action="create",
                    target_id="workspace-anomaly-cluster",
                    title="Workspace anomaly cluster plugin scaffold",
                    reason="A new plugin is required for workspace anomaly clustering.",
                    trace_id="upgrade-trace-plugin-create-001",
                    request_id="upgrade-request-plugin-create-001",
                    source_event_id="gap:workspace-anomaly-cluster-001",
                    parent_record_id=None,
                    evidence_refs=["reports/workspace_anomaly_gap.json"],
                    change_summary="Create isolated candidate scaffold and startup contract.",
                    function_summary="Create a new plugin candidate before registration.",
                    previous_version=None,
                    current_version="0.1.0",
                    candidate_version="0.1.1-candidate",
                    current_status=UpgradeLifecycleStatus.FAILED,
                    current_progress=41,
                    failure_reason="Validation command failed because startup schema was incomplete.",
                    source_path=None,
                    candidate_path="src/plugins/workspace_anomaly_cluster_candidate_0_1_1_candidate",
                    audit_status="failed",
                    memory_status="persisted",
                    started_at=utc_now(),
                    finished_at=utc_now(),
                ),
            ]
        )
        agent_manager, agent_coordination_service = _seed_agent_coordination(transcript_store)
        runtime, session = _seed_runtime(
            interaction_mind_engine=interaction_mind_engine,
            consolidation_engine=consolidation_engine,
            transcript_store=transcript_store,
        )
        runtime.cognitive_tool_registry = cognitive_registry
        runtime.execution_registry = execution_registry
        runtime.task_service = task_service
        runtime.plugin_registry = plugin_registry
        runtime.managed_plugin_records = {
            record.plugin.plugin_id: record
            for record in managed_plugins
            if getattr(record, "plugin", None) is not None
        }
        # Log nine questions state for debugging
        snapshot_count = len(session.current_nine_question_state.question_snapshots)
        if snapshot_count == 0:
            logger.info(
                f"[Nine Questions] No existing snapshots found. Starting cold start onboarding..."
            )
            _start_cold_start_onboarding_background(
                runtime=runtime,
                session=session,
            )
        else:
            snapshot_ids = sorted(session.current_nine_question_state.question_snapshots.keys())
            logger.info(
                f"[Nine Questions] Found {snapshot_count}/9 existing snapshots: {snapshot_ids}"
            )
            if snapshot_count < 9:
                missing = [f"q{i}" for i in range(1, 10) if f"q{i}" not in snapshot_ids]
                logger.warning(
                    f"[Nine Questions] INCOMPLETE STATE: Missing {len(missing)} questions: {missing}. "
                    f"This indicates a previous cold start failure. "
                    f"User should click '强制运行一次 9 问' to re-execute."
                )
        
        if _should_autorun_real_startup_nine_questions():
            # Defer nine questions execution to background after MCP sync completes
            def _run_nine_q_bg():
                try:
                    # Wait for MCP async sync to complete
                    import time
                    logger.info("[Nine Questions] Waiting 5 seconds for MCP/CLI async initialization...")
                    time.sleep(5)  # Wait 5 seconds for async operations
                    
                    logger.info("[Nine Questions] Starting deferred cold start...")
                    _auto_run_startup_nine_questions(
                        runtime=runtime,
                        session=session,
                        cognitive_registry=cognitive_registry,
                        execution_registry=execution_registry,
                        task_service=task_service,
                        mcp_adapter=mcp_adapter,
                        cli_adapter=cli_adapter,
                    )
                    logger.info("[Nine Questions] Deferred cold start completed successfully")
                except Exception:
                    logger.exception("Deferred nine questions execution failed")

            Thread(target=_run_nine_q_bg, name="nine-q-deferred", daemon=True).start()
            logger.info("[Nine Questions] Cold start deferred to background thread (will execute in 5s)")
        elif _should_seed_fake_startup_nine_questions():
            # Defer fake seeding to background
            def _seed_bg():
                try:
                    _seed_nine_question_runtime_state(runtime, session)
                except Exception:
                    logger.exception("Deferred nine-question seeding failed")

            Thread(target=_seed_bg, name="nine-q-seed-bg", daemon=True).start()
        _run_startup_coro(_seed_task_and_agent_runtime_state(task_service, agent_coordination_service))

        return create_web_console_app(
            cognitive_tool_registry=cognitive_registry,
            plugin_registry=plugin_registry,
            weight_assembler=weight_assembler,
            managed_plugins=managed_plugins,
            plugin_feature_catalog=plugin_feature_catalog,
            runtime=runtime,
            session=session,
            transcript_store=transcript_store,
            agent_manager=agent_manager,
            agent_coordination_service=agent_coordination_service,
            task_service=task_service,
            upgrade_management_store=upgrade_management_store,
            cli_adapter=cli_adapter,
            mcp_adapter=mcp_adapter,
            execution_registry=execution_registry,
        )
    except ConfigError:
        raise
    except ModuleNotFoundError as exc:
        missing_name = exc.name or (str(exc).split("'")[1] if "'" in str(exc) else "unknown dependency")
        raise InitializationError(
            f"Web 控制台启动失败：缺少依赖模块 `{missing_name}`。请先安装启动依赖后再重试。"
        ) from exc
    except (TimeoutError, ConnectionError, OSError) as exc:
        raise InitializationError(
            f"Web 控制台启动失败：运行时装配未就绪，原因：{exc}"
        ) from exc
    except Exception as exc:
        raise InitializationError(
            f"Web 控制台启动失败：初始化过程中出现未处理异常：{exc}"
        ) from exc


# NOTE (anti-fallback):
# Do NOT seed fake MODEL_PROVIDER_* transcript entries in dev_server.
# Why:
# - It makes the UI look like the model already ran even when the real provider
#   is unavailable or credentials are missing.
# - It hides configuration problems and violates the audit requirement (replay
#   must reflect real remote calls).

# Lazy initialization to avoid blocking module import
_app_instance = None
_app_initializing = False

def __getattr__(name: str):
    """Lazy load the app instance on first access."""
    global _app_instance, _app_initializing
    
    if name == "app":
        if _app_instance is not None:
            return _app_instance
        
        if _app_initializing:
            # Prevent recursive initialization
            raise InitializationError("App initialization loop detected")
        
        _app_initializing = True
        try:
            _app_instance = build_dev_server_app()
            return _app_instance
        finally:
            _app_initializing = False
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

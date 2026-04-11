"""Web console development server bootstrapper.

⚠️ ARCHITECTURAL CONSTRAINT - MAX 800 LINES (HARD LIMIT)
═════════════════════════════════════════════════════════════════════════════
This module **MUST NOT** exceed 800 lines. All new startup logic MUST be
extracted into bootstrap modules: _bootstrap_runtime.py, _bootstrap_adapters.py,
_bootstrap_integrations.py. Do NOT add business logic to this file.

🚫 VIOLATION PREVENTION RULES (ENFORCED):
- NEVER import from zentex.{tasks,agents,mcp,cli,memory,upgrade,plugins,learning,reflection,safety,supervision}.* directly
- ALWAYS use service APIs or bootstrap modules for cross-module calls
- Maximum file size: 800 lines (hard limit - will fail CI if exceeded)
- If you need functionality from another module, use its service.py or create a bootstrap helper
- This file is ONLY for orchestration, not implementation

✅ CORRECT PATTERNS:
- Use setup_*() functions from _bootstrap_*.py modules
- Import only from zentex.boot._bootstrap_* and zentex.web_console.*
- Keep all business logic in dedicated bootstrap modules

❌ WRONG PATTERNS (VIOLATIONS):
- from zentex.tasks.service import TaskManagementService  # WRONG! Use bootstrap
- from zentex.upgrade.management import ...  # WRONG! Use upgrade.service
- from zentex.memory.storage.asset_store import ...  # WRONG! Use memory.service
- Direct instantiation of service classes in this file  # WRONG!
═════════════════════════════════════════════════════════════════════════════
"""

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
from zentex.common.plugin_registry import AbstractPluginRegistry
from zentex.core.plugin_base import BasePluginSpec, PluginHealthStatus, PluginLifecycleStatus
from zentex.web_console.errors import ConfigError, InitializationError


def _configure_dspy_cache_dir() -> None:
    """Force DSPy disk cache into the project workspace."""
    project_root = Path(__file__).resolve().parents[3]
    cache_dir = project_root / "app_data" / "cache" / "dspy"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DSPY_CACHEDIR", str(cache_dir))


_configure_dspy_cache_dir()

try:
    # Core imports - models, services and public APIs only
    from zentex.web_console.api import (
        PluginFeatureCatalogItem,
        build_managed_plugin_record,
        create_web_console_app,
    )
    from zentex.runtime.transcript import (
        BrainTranscriptEntry,
        BrainTranscriptEntryType,
        BrainTranscriptStore,
    )
    from zentex.runtime.runtime import BrainRuntime
    from zentex.core.model_provider_spec import ModelProviderSpec
    
    # ✅ CORRECT: Import service types via bootstrap modules
    # These are type hints only - actual instantiation happens in bootstrap functions
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from zentex.tasks.service import TaskManagementService
        from zentex.agents.service import AgentCoordinationService
        from zentex.plugins.service import SystemPluginService
        from zentex.upgrade.service import UpgradeManagementStore
    
    # Import new bootstrap modules to replace internal direct imports
    from zentex.boot._bootstrap_runtime import (
        setup_brain_runtime,
        setup_interaction_mind_engine,
        setup_consolidation_engine,
    )
    from zentex.boot._bootstrap_adapters import (
        setup_agent_coordination,
    )
    from zentex.boot._bootstrap_integrations import (
        setup_cognitive_registry,
        setup_mcp_adapter,
        setup_cli_adapter,
        setup_weight_assembler,
        setup_task_management,
    )
    from zentex.boot._bootstrap_plugins import (
        seed_plugin_service,
        seed_managed_plugins,
        seed_plugin_feature_catalog,
    )
    from zentex.boot._bootstrap_nine_questions import (
        seed_nine_question_runtime_state,
        seed_task_and_agent_runtime_state,
        should_autorun_real_startup_nine_questions,
        should_seed_fake_startup_nine_questions,
        build_startup_workspace_snapshot,
        auto_run_startup_nine_questions,
        start_cold_start_onboarding_background,
    )
    
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


# Plugin seeding functions have been moved to _bootstrap_plugins.py
# Import them from there instead of defining them here


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


def _seed_consolidation_engine(
    *,
    model_provider: ModelProviderSpec,
    transcript_store: BrainTranscriptStore,
    plugin_service: Any,
) -> ConsolidationEngine:
    """构造开发态巩固引擎，并注入一条完成周期样本供前端回放。"""
    plugin_map = {
        plugin.plugin_id: plugin
        for plugin in plugin_service.list_plugin_instances()
        if getattr(plugin, "plugin_id", None)
    }
    engine = ConsolidationEngine(
        model_provider=model_provider,
        analysis_plugins=[
            plugin_map["cognitive_failure_cluster"],
            plugin_map["cognitive_expired_assumption"],
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


# Plugin seeding functions moved to _bootstrap_plugins.py


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
    await seed_task_and_agent_runtime_state(
        task_service=task_service,
        agent_service=agent_service,
    )


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

    # ✅ CORRECT: Use bootstrap module to create MCP and CLI services
    from zentex.boot._bootstrap_integrations import create_mcp_and_cli_services
    mcp_service, cli_service = create_mcp_and_cli_services(
        mcp_adapter=mcp_adapter,
        cli_adapter=cli_adapter,
    )

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
        plugin_service=runtime.plugin_service,
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
    """
    Build and configure the development server FastAPI application.
    
    This function initializes all core components including:
    - Unified database connection
    - DAO registry for data access
    - Plugin system
    - Runtime environment
    - Web console routers
    
    Returns:
        FastAPI: Configured FastAPI application instance
    """
    try:
        # Step 0: Initialize unified database connection and DAO registry
        from zentex.common.dao_registry import get_dao_registry
        
        logger.info("[Database] Initializing unified database connection...")
        db_path = os.path.join(os.getcwd(), "runtime", "data", "zentex_core.db")
        
        registry = get_dao_registry()
        registry.initialize(db_path, cache_max_size=1000, cache_ttl=300)
        
        logger.info(f"[Database] Database initialized at: {db_path}")
        logger.info("[Database] DAO registry ready")
        
        # Step 1: Parallelize plugin builds which are CPU-bound / non-dependent
        with ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 1) * 4)) as executor:
            plugin_records_future = executor.submit(seed_managed_plugins)
            feature_catalog_future = executor.submit(seed_plugin_feature_catalog)
            
            managed_plugins = plugin_records_future.result()
            plugin_feature_catalog = feature_catalog_future.result()

        transcript_store = BrainTranscriptStore(".zentex/runtime/web_console_transcript.jsonl")
        
        # 0. Initialize Central Asset Store
        # ✅ CORRECT: Use memory.service instead of direct import
        from zentex.memory.service import get_memory_service
        asset_store = get_memory_service().get_asset_store("runtime/data/zentex_assets.sqlite")

        plugin_service = seed_plugin_service(".zentex/plugins.db")
        cognitive_registry = setup_cognitive_registry(
            transcript_store,
            plugin_service,
            asset_store=asset_store,
        )
        
        # Step 2: Defer MCP sync
        mcp_adapter, execution_registry = setup_mcp_adapter(
            transcript_store, cognitive_registry, asset_store=asset_store, defer_sync=True
        )
        cli_adapter = setup_cli_adapter(transcript_store, cognitive_registry, execution_registry, asset_store=asset_store)
        cognitive_registry.set_audit_sink(transcript_store=transcript_store)
        weight_assembler = setup_weight_assembler(plugin_service)
        model_provider = next(
            (
                plugin
                for plugin in managed_plugins
                if getattr(plugin, "plugin_kind", lambda: "")() == "model_provider"
            ),
            None,
        )
        if model_provider is None:
            raise ConfigError("Web 控制台启动失败：未找到可用的 model_provider 插件。")
        interaction_mind_engine = setup_interaction_mind_engine(model_provider=model_provider)
        consolidation_engine = setup_consolidation_engine(
            model_provider=model_provider,
            transcript_store=transcript_store,
        )
        task_service = setup_task_management(transcript_store, managed_plugins=managed_plugins, asset_store=asset_store)
        
        # ✅ CORRECT: Use upgrade.service instead of direct import
        from zentex.upgrade.service import UpgradeFacade
        upgrade_facade = UpgradeFacade()
        upgrade_management_store = upgrade_facade.execution_service.management_store
        agent_manager, agent_coordination_service = setup_agent_coordination(
            asset_store=asset_store,
            task_service=task_service,  # ⭐ Pass task_service for automatic status updates
            transcript_store=transcript_store,
        )
        runtime, session = setup_brain_runtime(
            interaction_mind_engine=interaction_mind_engine,
            consolidation_engine=consolidation_engine,
            transcript_store=transcript_store,
        )
        runtime.plugin_service = plugin_service  # Use SystemPluginService instance
        runtime.cognitive_tool_registry = cognitive_registry
        runtime.tool_registry = cognitive_registry
        runtime.task_service = task_service
        runtime.agent_service = agent_coordination_service
        runtime.mcp_service = mcp_adapter
        runtime.cli_service = cli_adapter
        runtime.managed_plugin_records = {} # Moved to DB
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

        # Create the FastAPI app
        app = create_web_console_app(
            cognitive_tool_registry=cognitive_registry,
            plugin_service=plugin_service,
            managed_plugins=managed_plugins,
            weight_assembler=weight_assembler,
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
        
        # Add shutdown handler to cleanup database connection
        @app.on_event("shutdown")
        def shutdown_database():
            """Cleanup database connection on application shutdown."""
            try:
                logger.info("[Database] Shutting down unified database connection...")
                registry.shutdown()
                logger.info("[Database] Database connection shutdown complete")
            except Exception as e:
                logger.error(f"[Database] Error during shutdown: {e}", exc_info=True)
        
        return app
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

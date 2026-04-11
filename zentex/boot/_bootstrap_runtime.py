"""
Runtime bootstrap module for web_dev.py

Handles initialization of BrainRuntime and all associated engines.
Uses proper service APIs to avoid direct internal class instantiation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Thread
from typing import Any, Optional, Tuple
import logging
import os

from zentex.memory import (
    ConsolidationCycle,
    ConsolidationEngine,
    MemoryPromotionCandidate,
    PatternStabilityScore,
)
from zentex.memory import EnhancedMemoryService, EpisodeGraphMemoryAdapter
from zentex.memory import KuzuGraphMemoryClient
from zentex.runtime.working_memory import WorkingMemoryController, FocusBudget
from zentex.runtime.self_model import LivingSelfModelEngine
from zentex.runtime.metacognition import MetaCognitionController
from zentex.runtime.temporal import CognitiveTemporalEngine
from zentex.runtime.transcript import BrainTranscriptStore
from zentex.safety.service import CognitiveConflictEngine, CognitiveConflictReport
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
from zentex.core.model_provider_spec import ModelProviderSpec
from zentex.runtime.runtime import BrainRuntime

logger = logging.getLogger(__name__)


def setup_brain_runtime(
    *,
    interaction_mind_engine: InteractionMindEngine,
    consolidation_engine: ConsolidationEngine,
    transcript_store: BrainTranscriptStore,
) -> Tuple[BrainRuntime, object]:
    """
    Initialize BrainRuntime with all required engines and models.
    
    Uses service APIs where available to respect module isolation.
    """
    temporal_engine = _create_temporal_engine()
    conflict_engine = _create_conflict_engine()
    simulation_engine = _create_simulation_engine()
    kuzu_adapter = _setup_kuzu_adapter()
    enhanced_memory_service = _setup_enhanced_memory_service(kuzu_adapter)
    
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
    
    # Defer potentially heavy backfill to background
    def _backfill_bg():
        try:
            enhanced_memory_service.backfill_transcript_entries(
                transcript_store.get_entries_snapshot()
            )
        except Exception:
            logger.exception("Deferred memory backfill failed")

    Thread(target=_backfill_bg, name="memory-backfill-bg", daemon=True).start()

    session = runtime.create_session("web-console")
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


def _create_temporal_engine() -> CognitiveTemporalEngine:
    """Create and seed the temporal engine."""
    engine = CognitiveTemporalEngine(
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
    engine.evaluate(datetime.now(timezone.utc) + timedelta(minutes=3))
    return engine


def _create_conflict_engine() -> CognitiveConflictEngine:
    """Create and seed the conflict engine."""
    engine = CognitiveConflictEngine(brain_scope="web-console")
    engine.ingest_reports([
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
    ])
    return engine


def _create_simulation_engine() -> CounterfactualSimulationEngine:
    """Create and seed the simulation engine."""
    from unittest.mock import Mock
    
    engine = CounterfactualSimulationEngine(
        model_provider=Mock(name="simulation_summary_provider"),
        simulation_plugins=[],
    )
    engine.seed_bundle(SimulationBundle(
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
    ))
    return engine


def _setup_kuzu_adapter() -> Optional[EpisodeGraphMemoryAdapter]:
    """Setup Kuzu graph memory adapter if cluster mode is disabled."""
    cluster_mode = os.environ.get("ZENTEX_CLUSTER_MODE", "false").lower() == "true"
    if cluster_mode:
        return None
    
    try:
        kuzu_client = KuzuGraphMemoryClient(db_path=".zentex/kuzu_db")
        return EpisodeGraphMemoryAdapter(graph_client=kuzu_client)
    except Exception as e:
        logger.warning(f"Failed to initialize KuzuDB graph client: {e}")
        return None


def _setup_enhanced_memory_service(
    kuzu_adapter: Optional[EpisodeGraphMemoryAdapter],
) -> EnhancedMemoryService:
    """Setup enhanced memory service with optional kuzu adapter."""
    return EnhancedMemoryService(
        semantic_store_path=Path(".zentex/runtime/enhanced_semantic.jsonl"),
        procedural_store_path=Path(".zentex/runtime/enhanced_procedural.jsonl"),
        episodic_store_path=Path(".zentex/runtime/enhanced_episodic.jsonl"),
        management_store_path=Path(".zentex/runtime/enhanced_management.json"),
        audit_store_path=Path(".zentex/runtime/enhanced_memory_audit.jsonl"),
        episodic_sink=kuzu_adapter,
        episodic_recall_client=kuzu_adapter,
    )


def setup_interaction_mind_engine(*, model_provider: ModelProviderSpec) -> InteractionMindEngine:
    """Setup social mind model engine with seed state."""
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


def setup_consolidation_engine(
    *,
    model_provider: ModelProviderSpec,
    transcript_store: BrainTranscriptStore,
) -> ConsolidationEngine:
    """Setup consolidation engine with seed cycle."""
    engine = ConsolidationEngine(
        model_provider=model_provider,
        analysis_plugins=[],  # Will be loaded via plugin service
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

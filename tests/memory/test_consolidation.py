from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import time
from unittest import mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.core.model_provider_spec import ModelProviderRateLimitError  # noqa: E402
from zentex.core.plugin_base import PluginLifecycleStatus  # noqa: E402
from zentex.memory.consolidation import (  # noqa: E402
    ConsolidationEngine,
    ConsolidationPluginOutput,
    ForgettableNoiseRule,
    MemoryPromotionCandidate,
    PatternStabilityScore,
    StaleWriteError,
)
from zentex.runtime.transcript import BrainTranscriptStore  # noqa: E402


class SlowFailureClusterPlugin:
    """Slow plugin used to create a stale-write race in tests."""

    plugin_id = "slow-failure-cluster"
    status = PluginLifecycleStatus.ACTIVE
    behavior_key = "memory_consolidation"
    supports_multi_active = True

    def analyze_memory(
        self,
        *,
        context: dict[str, object],
        noise_rules: list[ForgettableNoiseRule],
    ) -> ConsolidationPluginOutput:
        del context, noise_rules
        time.sleep(0.15)
        return ConsolidationPluginOutput(plugin_id=self.plugin_id)


class CandidatePlugin:
    """Plugin that proposes reusable lessons for consolidation promotion."""

    plugin_id = "candidate-plugin"
    status = PluginLifecycleStatus.ACTIVE
    behavior_key = "memory_consolidation"
    supports_multi_active = True

    def analyze_memory(
        self,
        *,
        context: dict[str, object],
        noise_rules: list[ForgettableNoiseRule],
    ) -> ConsolidationPluginOutput:
        del noise_rules
        refs = list(context.get("input_memory_refs") or [])
        return ConsolidationPluginOutput(
            plugin_id=self.plugin_id,
            promotion_candidates=[
                MemoryPromotionCandidate(
                    source_ref=str(refs[0]["ref_id"]),
                    candidate_type="lesson",
                    stability_score=0.83,
                    reuse_value=0.87,
                    promotion_reason="Repeated timeout mitigation pattern is reusable.",
                )
            ],
            compressed_refs=[str(refs[0]["ref_id"])],
            pattern_scores=[
                PatternStabilityScore(
                    pattern_id="pattern:timeout-recovery",
                    frequency=2,
                    time_span_seconds=3600,
                    cross_context_reuse=0.8,
                    conflict_count=0,
                    stability_score=0.88,
                )
            ],
        )


class CleanerPlugin:
    """Plugin that proposes forgettable low-value assumptions, including a protected ref."""

    plugin_id = "cleaner-plugin"
    status = PluginLifecycleStatus.ACTIVE
    behavior_key = "memory_consolidation"
    supports_multi_active = True

    def analyze_memory(
        self,
        *,
        context: dict[str, object],
        noise_rules: list[ForgettableNoiseRule],
    ) -> ConsolidationPluginOutput:
        del noise_rules
        refs = list(context.get("input_memory_refs") or [])
        return ConsolidationPluginOutput(
            plugin_id=self.plugin_id,
            pruned_refs=[
                str(refs[1]["ref_id"]),
                "identity_role_pack:core-role",
            ],
        )


def _build_engine(
    tmp_path: Path,
    *,
    model_provider: mock.Mock,
    plugins: list[object],
) -> ConsolidationEngine:
    transcript_store = BrainTranscriptStore(tmp_path / "consolidation_transcript.jsonl")
    engine = ConsolidationEngine(
        model_provider=model_provider,
        analysis_plugins=plugins,
        transcript_store=transcript_store,
        brain_scope="brain-a",
    )
    return engine


def test_consolidation_engine_rejects_stale_worker_write(tmp_path: Path) -> None:
    model_provider = mock.Mock()
    model_provider.generate_json.return_value = {
        "summary": "stale result should not commit",
        "promotion_candidates": [],
        "compressed_refs": [],
    }
    engine = _build_engine(
        tmp_path,
        model_provider=model_provider,
        plugins=[SlowFailureClusterPlugin()],
    )
    engine.seed_memory_snapshot(
        ref_versions={"reflection:timeout-1": 1},
        snapshot_version=0,
    )

    _, future = engine.submit_cycle(
        trigger_stage="sleep_phase",
        input_memory_refs=[
            {
                "ref_id": "reflection:timeout-1",
                "kind": "reflection",
                "summary": "failure timeout incident",
            }
        ],
        noise_rules=[],
        context={},
        idempotency_key="idem-stale-cycle",
        snapshot_version=0,
    )
    engine.mark_memory_ref_updated("reflection:timeout-1")

    with pytest.raises(StaleWriteError, match="Stale consolidation write"):
        future.result(timeout=2)


def test_consolidation_engine_enters_backoff_when_llm_is_rate_limited(tmp_path: Path) -> None:
    model_provider = mock.Mock()
    model_provider.generate_json.side_effect = ModelProviderRateLimitError("429")
    engine = _build_engine(
        tmp_path,
        model_provider=model_provider,
        plugins=[CandidatePlugin()],
    )
    engine.seed_memory_snapshot(
        ref_versions={"reflection:timeout-1": 1},
        snapshot_version=0,
    )

    _, future = engine.submit_cycle(
        trigger_stage="reflection_postprocess",
        input_memory_refs=[
            {
                "ref_id": "reflection:timeout-1",
                "kind": "reflection",
                "summary": "failure timeout incident",
            }
        ],
        noise_rules=[],
        context={},
        idempotency_key="idem-rate-limit",
        snapshot_version=0,
    )

    with pytest.raises(ModelProviderRateLimitError, match="429"):
        future.result(timeout=2)

    failed_cycle = engine.list_cycles(cycle_id=engine.list_cycles()[0].cycle_id)[0]
    assert failed_cycle.status == "failed"
    assert failed_cycle.backoff_seconds == 30
    assert failed_cycle.promoted_refs == []
    assert failed_cycle.pruned_refs == []
    assert failed_cycle.compressed_refs == []


def test_consolidation_engine_merges_parallel_plugin_outputs_and_protects_identity_refs(
    tmp_path: Path,
) -> None:
    model_provider = mock.Mock()
    model_provider.generate_json.return_value = {
        "summary": "Timeout failures are reusable; expired assumption can be safely forgotten.",
        "promotion_candidates": [
            {
                "source_ref": "reflection:timeout-1",
                "candidate_type": "pattern",
                "stability_score": 0.95,
                "reuse_value": 0.92,
                "promotion_reason": "This timeout recovery pattern repeats across incidents.",
            }
        ],
        "compressed_refs": ["reflection:timeout-2"],
    }
    engine = _build_engine(
        tmp_path,
        model_provider=model_provider,
        plugins=[CandidatePlugin(), CleanerPlugin()],
    )
    engine.seed_memory_snapshot(
        ref_versions={
            "reflection:timeout-1": 1,
            "assumption:expired-budget": 1,
            "identity_role_pack:core-role": 1,
            "reflection:timeout-2": 1,
        },
        tombstone_state={"identity_role_pack:core-role": False},
        snapshot_version=0,
    )

    _, future = engine.submit_cycle(
        trigger_stage="memory_governance_review",
        input_memory_refs=[
            {
                "ref_id": "reflection:timeout-1",
                "kind": "reflection",
                "summary": "failure timeout incident",
                "created_at": datetime.now(timezone.utc) - timedelta(hours=2),
            },
            {
                "ref_id": "assumption:expired-budget",
                "kind": "assumption",
                "summary": "expired assumption about available budget",
                "created_at": datetime.now(timezone.utc) - timedelta(hours=3),
                "noise_kind": "expired_assumption",
                "reuse_value": 0.1,
                "confidence": 0.2,
            },
            {
                "ref_id": "identity_role_pack:core-role",
                "kind": "identity pack",
                "summary": "core role continuity anchor",
                "created_at": datetime.now(timezone.utc) - timedelta(hours=5),
                "noise_kind": "expired_assumption",
                "reuse_value": 0.0,
                "confidence": 0.0,
            },
            {
                "ref_id": "reflection:timeout-2",
                "kind": "reflection",
                "summary": "failure timeout incident repeated",
                "created_at": datetime.now(timezone.utc) - timedelta(hours=1),
            },
        ],
        noise_rules=[
            ForgettableNoiseRule(
                rule_id="rule-expired-assumption",
                noise_kind="expired_assumption",
                age_threshold_seconds=60,
                reuse_threshold=0.2,
                confidence_threshold=0.3,
            )
        ],
        context={},
        idempotency_key="idem-merge",
        snapshot_version=0,
    )

    cycle = future.result(timeout=2)

    assert cycle.status == "completed"
    assert "assumption:expired-budget" in cycle.pruned_refs
    assert "identity_role_pack:core-role" not in cycle.pruned_refs
    assert "reflection:timeout-1" in cycle.promoted_refs
    assert "reflection:timeout-2" in cycle.compressed_refs
    assert cycle.promotion_candidates
    assert cycle.pattern_scores

from __future__ import annotations

from unittest.mock import Mock

from zentex.runtime.cognitive_tools import CognitiveToolOrchestrator
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.transcript import BrainTranscriptStore
from zentex.core.plugin_base import PluginLifecycleStatus

from plugins.nine_questions.q1_where_am_i import (
    build_q1_where_am_i_capability_patch_plugin,
    build_q1_where_am_i_plugin,
)


def test_base_and_patch_plugins_run_and_merge_into_nine_question_state(tmp_path):
    # Shared transcript store for the orchestration + LLM calls.
    store = BrainTranscriptStore(tmp_path / "transcript.jsonl")
    runtime = BrainRuntime(transcript_store=store)

    # CognitiveToolRegistry requires either a transcript-style audit sink exposing `append`
    # or an audit_logger. For this runtime test we use an audit_logger to avoid coupling
    # registry audit events to BrainTranscriptStore.
    registry = CognitiveToolRegistry(audit_logger=Mock())
    registry.register(build_q1_where_am_i_plugin())
    registry.promote_plugin("nine-question-q1-where-am-i", PluginLifecycleStatus.SANDBOX_VERIFIED, audit_reason="t")
    registry.promote_plugin("nine-question-q1-where-am-i", PluginLifecycleStatus.ACTIVE, audit_reason="t")

    registry.register(build_q1_where_am_i_capability_patch_plugin())
    registry.promote_plugin(
        "nine-question-q1-where-am-i-capability-patch",
        PluginLifecycleStatus.SANDBOX_VERIFIED,
        audit_reason="t",
    )
    registry.promote_plugin(
        "nine-question-q1-where-am-i-capability-patch",
        PluginLifecycleStatus.ACTIVE,
        audit_reason="t",
    )

    provider = Mock()
    # First call: base Q1 returns WorkspaceDomainInference
    # Second call: Q1 patch returns Q1CapabilityPatchOutput
    provider.generate_json = Mock(
        side_effect=[
            {
                "primary_domain": "Python开发",
                "secondary_domains": ["财务账单"],
                "confidence": 0.7,
                "reasoning_summary": "mixed workspace",
                "uncertainties": ["need more samples"],
                "suggested_first_step": "classify",
            },
            {
                "patch_summary": "add finance tag and risk hints",
                "patch_updates": {"domain_tags": ["finance"], "risk_hints": ["invoice csv present"]},
            },
        ]
    )

    orchestrator = CognitiveToolOrchestrator(
        registry=registry,
        transcript_store=store,
        session_id="s",
        turn_id="t",
    )

    report = orchestrator.run(
        {
            "inspection": True,
            "session_id": "s",
            "turn_id": "t",
            "trace_id": "trace:test",
            "decision_id": "decision:test",
            "model_provider": provider,
            "transcript_store": store,
            "context_snapshot": {
                "workspace_structure_analysis": {"directory_hierarchy_summary": "src/"},
                "workspace_content_samples": {"file_samples": []},
                "environment_event": {"event_type": "manual", "summary": "test", "timestamp": "now"},
                "physical_host_state": {"memory_pressure": "unknown", "network_health": "unknown"},
            },
        }
    )

    merged_updates = report.merged_result.context_updates
    assert "workspace_domain_inference" in merged_updates
    assert "q1_capability_patch" in merged_updates

    # Assemble into runtime NineQuestionState (context snapshot merge).
    runtime.refresh_nine_question_state(
        question_driver_refs=["我在哪"],
        refresh_reason="test:merge_base_and_patch",
        context_snapshot=merged_updates,
        active_constraints=[],
    )
    assert runtime.nine_question_state.current_context.get("workspace_domain_inference")
    assert runtime.nine_question_state.current_context.get("q1_capability_patch")

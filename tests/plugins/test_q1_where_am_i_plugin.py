from __future__ import annotations

from unittest.mock import Mock

import pytest

from zentex.core.model_provider_spec import (
    ModelProviderCallerContext,
    ModelProviderRemoteError,
)
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore
from plugins.nine_questions.q1_where_am_i import build_q1_where_am_i_plugin


def _read_jsonl(path):
    import json

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def test_q1_where_am_i_mixed_scenario_extracts_primary_secondary_and_uncertainties(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(
        return_value={
            "primary_domain": "Python开发",
            "secondary_domains": ["财务账单"],
            "confidence": 0.72,
            "reasoning_summary": "代码目录与 .py 占比高，同时存在 invoice CSV 与账单表头。",
            "uncertainties": ["缺少更完整的 data/ 目录抽样", "invoice 文件命名可能混杂其他用途"],
            "suggested_first_step": "先将 workspace 目录按代码/数据/文档分组并确认账单 CSV 的来源。",
        }
    )

    transcript_path = tmp_path / "transcript.jsonl"
    store = BrainTranscriptStore(transcript_path)
    plugin = build_q1_where_am_i_plugin()

    context = {
        "session_id": "test-session",
        "turn_id": "test-turn",
        "trace_id": "trace:q1",
        "decision_id": "decision:q1",
        "model_provider": provider,
        "transcript_store": store,
        "context_snapshot": {
            "workspace_structure_analysis": {
                "directory_hierarchy_summary": "src/, docs/, data/",
                "file_total_count": 50,
                "suffix_distribution": {".py": 20, ".md": 10, ".csv": 3},
                "high_frequency_filename_keywords": {"invoice": 2, "api": 4},
                "candidate_groups": ["python_code", "docs", "billing_csv"],
                "obvious_risk_files": ["data/invoices_2025.csv"],
            },
            "workspace_content_samples": {
                "file_samples": [
                    {"path": "src/main.py", "title": "entrypoint", "snippet": "def main(...):"},
                    {"path": "data/invoices_2025.csv", "header": "date,amount,vendor", "snippet": "2025-01-..."},
                ],
                "log_anomaly_snippets": ["ERROR billing import mismatch"],
            },
            "environment_event": {"event_type": "manual_test", "summary": "mixed workspace", "timestamp": "now"},
            "physical_host_state": {"memory_pressure": "unknown", "network_health": "unknown"},
        },
    }

    result = plugin.run_tool(context)
    assert "primary_domain=Python开发" in result.summary
    assert result.context_updates["workspace_domain_inference"]["secondary_domains"] == ["财务账单"]
    assert result.context_updates["workspace_domain_inference"]["uncertainties"]
    assert result.context_updates["q1_llm_upgrade"]["planning_status"] == "profile_only"
    assert result.context_updates["q1_llm_upgrade"]["profile"]["baseline_version"] == "1.0.0"
    assert result.context_updates["q1_llm_upgrade"]["profile"]["target_component"] == "workspace_domain_inference"

    # Ensure prompt contains the required 3-layer structure and evidence hinting at mixed domain.
    kwargs = provider.generate_json.call_args.kwargs
    assert isinstance(kwargs["caller_context"], ModelProviderCallerContext)
    assert kwargs["caller_context"].question_driver_refs == ["我在哪"]
    prompt = kwargs["prompt"]
    assert "Evidence Summary:" in prompt
    assert "Local Stats:" in prompt
    assert "Uncertainty Hints:" in prompt
    assert ".csv" in str(kwargs["context"].get("suffix_distribution"))

    rows = _read_jsonl(transcript_path)
    types = [row["entry_type"] for row in rows]
    assert BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED.value in types
    assert BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED.value in types


def test_q1_where_am_i_can_emit_llm_upgrade_candidate_plan(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(
        return_value={
            "primary_domain": "audit_console",
            "secondary_domains": ["runtime_ops"],
            "confidence": 0.61,
            "reasoning_summary": "控制台与运行态信号混合，边界仍有歧义。",
            "uncertainties": ["环境切换过快", "缺少更多日志抽样"],
            "suggested_first_step": "先确认运行态来源和最近一次环境切换。",
        }
    )
    upgrade_service = Mock()
    upgrade_service.plan_candidate = Mock(
        return_value=Mock(
            candidate_version="1.1.0-candidate",
            release_gate=[
                "Optimization metrics must beat or match the active baseline.",
                "Validation commands must pass before candidate promotion.",
            ],
        )
    )

    transcript_path = tmp_path / "transcript.jsonl"
    store = BrainTranscriptStore(transcript_path)
    plugin = build_q1_where_am_i_plugin()

    result = plugin.run_tool(
        {
            "session_id": "test-session",
            "turn_id": "test-turn",
            "trace_id": "trace:q1",
            "decision_id": "decision:q1",
            "model_provider": provider,
            "transcript_store": store,
            "llm_upgrade_service": upgrade_service,
            "enable_llm_upgrade_planning": True,
            "context_snapshot": {
                "workspace_structure_analysis": {
                    "directory_hierarchy_summary": "src/, runtime/, logs/",
                    "file_total_count": 30,
                    "suffix_distribution": {".py": 16, ".log": 4},
                },
                "workspace_content_samples": {"file_samples": []},
                "environment_event": {"event_type": "manual_test", "summary": "audit console", "timestamp": "now"},
                "physical_host_state": {"memory_pressure": "medium", "network_health": "stable"},
            },
        }
    )

    upgrade_payload = result.context_updates["q1_llm_upgrade"]
    assert upgrade_payload["planning_status"] == "candidate_planned"
    assert upgrade_payload["candidate_version"] == "1.1.0-candidate"
    assert upgrade_payload["release_gate"]
    request = upgrade_service.plan_candidate.call_args.args[0]
    assert request.program_id == "nine_questions.q1.where_am_i"
    assert request.target_metric == "q1_domain_accuracy"
    assert request.baseline_version == "1.0.0"


def test_q1_where_am_i_fail_closed_and_provenance_injected(tmp_path):
    provider = Mock()
    provider.generate_json = Mock(side_effect=ModelProviderRemoteError("remote 500"))

    transcript_path = tmp_path / "transcript.jsonl"
    store = BrainTranscriptStore(transcript_path)
    plugin = build_q1_where_am_i_plugin()

    context = {
        "session_id": "test-session",
        "turn_id": "test-turn",
        "trace_id": "trace:q1",
        "decision_id": "decision:q1",
        "model_provider": provider,
        "transcript_store": store,
        "context_snapshot": {
            "workspace_structure_analysis": {
                "directory_hierarchy_summary": "src/, data/",
                "file_total_count": 10,
                "suffix_distribution": {".py": 3, ".csv": 1},
            },
            "workspace_content_samples": {"file_samples": []},
            "environment_event": {"event_type": "manual_test", "summary": "mixed workspace", "timestamp": "now"},
            "physical_host_state": {"memory_pressure": "unknown", "network_health": "unknown"},
        },
    }

    with pytest.raises(ModelProviderRemoteError):
        plugin.run_tool(context)

    kwargs = provider.generate_json.call_args.kwargs
    assert kwargs["caller_context"].question_driver_refs == ["我在哪"]
    assert kwargs["caller_context"].source_module == "q1_where_am_i_plugin"

    rows = _read_jsonl(transcript_path)
    types = [row["entry_type"] for row in rows]
    assert BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED.value in types
    assert BrainTranscriptEntryType.MODEL_PROVIDER_FAILED.value in types

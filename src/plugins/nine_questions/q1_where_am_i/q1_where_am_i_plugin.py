from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from plugins.shared.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q1
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q1_where_am_i.compression_budget import LocalCompressionBudget
from plugins.nine_questions.q1_where_am_i.llm_prompt import build_q1_llm_request
from plugins.nine_questions.q1_where_am_i.llm_upgrade import build_q1_upgrade_payload
from plugins.nine_questions.q1_where_am_i.models import WorkspaceDomainInference
# Decoupled: Inputs come from sensory plugins, not direct snapshot extract
from zentex.plugins.service import (
    query_enabled_cognitive_plugin_functionals,
    unwrap_plugin_feedback_result,
)

QUESTION_REF = "我在哪"


from zentex.common.nine_questions_shared import (
    build_caller_context,
    build_model_context,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)

logger = logging.getLogger(__name__)


def _normalize_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _infer_host_runtime_type(physical_host_state: Dict[str, Any]) -> tuple[str, str]:
    """
    Infer whether current runtime host is likely a server or a regular computer.

    This is a deterministic heuristic to guarantee Q1 can answer the host type even
    when model output is brief or omits this distinction.
    """
    platform_text = str(physical_host_state.get("platform") or "").lower()
    hostname = str(physical_host_state.get("hostname") or "").lower()
    cwd_text = str(physical_host_state.get("cwd") or "").lower()

    server_markers = [
        "linux",
        "ubuntu",
        "debian",
        "centos",
        "red hat",
        "alpine",
        "server",
        "prod",
        "staging",
        "k8s",
        "kubernetes",
        "container",
    ]
    desktop_markers = [
        "darwin",
        "macos",
        "windows",
        "desktop",
        "laptop",
        "notebook",
    ]

    server_hits = sum(1 for token in server_markers if token in platform_text or token in hostname or token in cwd_text)
    desktop_hits = sum(1 for token in desktop_markers if token in platform_text or token in hostname)

    if server_hits >= 2 and server_hits >= desktop_hits:
        return "服务器", "平台/主机名特征更接近服务端运行环境"
    if desktop_hits >= 1 and desktop_hits > server_hits:
        return "普通电脑", "平台特征更接近个人电脑（桌面或笔记本）"
    if "darwin" in platform_text or "macos" in platform_text:
        return "普通电脑", "检测到 macOS 运行环境"
    if "windows" in platform_text:
        return "普通电脑", "检测到 Windows 运行环境"
    if "linux" in platform_text:
        return "服务器", "检测到 Linux 运行环境（默认按服务器场景判定）"
    return "未知", "宿主机特征不足，无法稳定区分服务器或普通电脑"


class Q1WhereAmIPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q1
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q1"
    display_name: str = "Q1: Where am I?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Q1: 我在哪 (workspace domain inference)

    Absolute red lines (enforced here):
    - NEVER read raw file bodies.
    - Only consume pre-processed structured summaries from ContextSnapshot.
    - LLM is mandatory; fail-closed on any provider failure or schema mismatch.

    Plugin bus contract:
    - supports_multiple_plugins = True: 强制声明支持基础插件与能力补丁并发执行
    """

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        
        # 1. G14 Sensory Chain Implementation via Registry
        # This replaces: extract_q1_local_inputs(context)
        local_inputs: Dict[str, Any]
        plugin_service = context.get("plugin_service")
        sensory_chain_ok = False
        if not sensory_chain_ok:
            snapshot = context.get("context_snapshot", {}) or {}
            structure = snapshot.get("workspace_structure_analysis", {}) or {}
            samples_block = snapshot.get("workspace_content_samples", {}) or {}
            local_inputs = {
                "structure": structure,
                "samples": samples_block,
                "environment_event": snapshot.get("environment_event", {}) or {},
                "physical_host_state": snapshot.get("physical_host_state", {}) or {},
                "interpretation_markers": None,
                "risk_markers": None,
            }

        if plugin_service is not None:
            raw_signal: Any = None
            sanitized_signal: Any = None
            try:
                for binding in query_enabled_cognitive_plugin_functionals(plugin_service, self.plugin_id, limit=200):
                    functional_plugin_id = str(binding.get("plugin_id") or "")
                    feature_code = str(binding.get("feature_code") or "")
                    parameters: dict[str, Any]
                    if feature_code == "sensory.ingest":
                        parameters = {}
                    elif feature_code == "sensory.sanitize":
                        parameters = {"raw_signal": raw_signal or ""}
                    elif feature_code == "sensory.interpret":
                        parameters = {"signal": sanitized_signal}
                    else:
                        parameters = {
                            "workspace_root": (
                                (context.get("context_snapshot", {}) or {}).get("workspace_root")
                                or (context.get("context_snapshot", {}) or {}).get("cwd")
                                or context.get("workspace_root")
                            )
                        }
                    feedback = plugin_service.execute_plugin_once_sync(
                        plugin_id=functional_plugin_id,
                        task_id=f"{str(context.get('trace_id') or 'q1')}:{functional_plugin_id}",
                        parameters=parameters,
                        trace_id=str(context.get("trace_id") or "q1"),
                        originator_id=str(context.get("session_id") or "unknown-session"),
                        caller_plugin_id=self.plugin_id,
                    )
                    if getattr(feedback, "status", None) != "done":
                        continue
                    result = unwrap_plugin_feedback_result(getattr(feedback, "result", None))
                    if feature_code == "sensory.ingest" and isinstance(result, str):
                        raw_signal = result
                        continue
                    if feature_code == "sensory.sanitize":
                        sanitized_signal = result
                        local_inputs["risk_markers"] = list(getattr(result, "redaction_evidence", []) or [])
                        continue
                    if feature_code == "sensory.interpret" and result is not None:
                        local_inputs["environment_event"] = {
                            "event_type": getattr(result, "event_type", None),
                            "summary": getattr(result, "summary", None),
                            "structured_payload": getattr(result, "structured_payload", {}),
                            "risk_flags": list(getattr(result, "risk_flags", []) or []),
                            "audit_evidence": list(getattr(result, "audit_evidence", []) or []),
                        }
                        local_inputs["interpretation_markers"] = list(
                            getattr(result, "risk_flags", []) or []
                        )
                        sensory_chain_ok = True
                        continue
                    if isinstance(result, dict):
                        merged_host_state = dict(local_inputs.get("physical_host_state") or {})
                        merged_host_state.update(result)
                        local_inputs["physical_host_state"] = merged_host_state
            except Exception as exc:
                logger.error("Q1 functional plugin execution failed: %s", exc)
                raise RuntimeError(f"Q1 Functional Plugin Chain Failed: {exc}") from exc

        structure_snapshot = _normalize_dict(local_inputs.get("structure"))
        samples_snapshot = _normalize_dict(local_inputs.get("samples"))
        environment_event = _normalize_dict(local_inputs.get("environment_event"))
        physical_host_state = _normalize_dict(local_inputs.get("physical_host_state"))
        sampled_file_summaries = _normalize_list_of_dicts(
            samples_snapshot.get("sampled_file_summaries") or samples_snapshot.get("file_samples")
        )
        log_anomaly_snippets = [
            str(item).strip()
            for item in (samples_snapshot.get("log_anomaly_snippets") or samples_snapshot.get("anomalies") or [])
            if str(item).strip()
        ] if isinstance(samples_snapshot.get("log_anomaly_snippets") or samples_snapshot.get("anomalies") or [], list) else []
        sensory_audit = {
            "sensory_chain_ok": sensory_chain_ok,
            "interpretation_markers": list(local_inputs.get("interpretation_markers") or []),
            "risk_markers": list(local_inputs.get("risk_markers") or []),
            "sampled_file_count": len(sampled_file_summaries),
            "anomaly_count": len(log_anomaly_snippets),
        }

        # 2. Local compression budget + three-layer payload assembly.
        # Note: local_inputs is now the dictionary from workspace_sensor.interpret
        budget = LocalCompressionBudget()
        compressed = budget.compress(
            structure=structure_snapshot,
            samples=samples_snapshot,
            environment_event=environment_event,
            physical_host_state=physical_host_state,
        )

        llm_request = build_q1_llm_request(
            compressed=compressed,
            environment_event=environment_event,
            physical_host_state=physical_host_state,
            interpretation_markers=local_inputs.get("interpretation_markers"),
            risk_markers=local_inputs.get("risk_markers"),
            suffix_distribution=(local_inputs.get("structure") or {}).get("suffix_distribution"),
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        trace_id = str(context.get("trace_id") or f"q1-where-am-i:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q1_where_am_i")

        caller_context = build_caller_context(
            source_module="q1_where_am_i_plugin",
            invocation_phase="nine_question_q1_where_am_i",
            question_ref=QUESTION_REF,
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q1_where_am_i",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "system_prompt": system_prompt,
                "context": model_context,
            },
        )

        started = perf_counter()
        try:
            raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{prompt}",
                context=model_context,
                caller_context=caller_context,
            )
        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q1_where_am_i",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            raise

        inference = WorkspaceDomainInference.model_validate(raw)

        # Hard requirement for Q1: explicitly answer whether current host is a server
        # or a regular computer based on local telemetry.
        host_type, host_reason = _infer_host_runtime_type(physical_host_state)
        host_line = f"当前运行主机类型判断：{host_type}（{host_reason}）。"
        updated_reasoning = f"{inference.reasoning_summary.strip()}\n\n{host_line}".strip()
        updated_uncertainties = list(inference.uncertainties)
        if host_type == "未知":
            updated_uncertainties.append("宿主机类型区分存在不确定性（server vs regular computer）")
        inference = inference.model_copy(
            update={
                "reasoning_summary": updated_reasoning,
                "uncertainties": updated_uncertainties,
                "host_runtime_type": host_type,
                "host_runtime_reason": host_reason,
            }
        )
        upgrade_payload = build_q1_upgrade_payload(
            baseline_version=self.version,
            inference=inference,
            upgrade_service=context.get("llm_upgrade_service"),
            enable_candidate_planning=bool(context.get("enable_llm_upgrade_planning")),
        )

        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q1_where_am_i",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": inference.model_dump(mode="json"),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", {})),
                "model": json_safe_payload(
                    getattr(provider, "last_model_name", None) or getattr(provider, "default_model", None)
                ),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )

        summary = (
            f"primary_domain={inference.primary_domain}; "
            f"secondary={inference.secondary_domains}; "
            f"confidence={inference.confidence:.2f}"
        )
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "workspace_domain_inference",
                    "question_ref": QUESTION_REF,
                    **inference.model_dump(mode="json"),
                }
            ],
            uncertainties=[{"kind": "uncertainties", "items": inference.uncertainties}],
            context_updates={
                "nine_questions": {QUESTION_REF: inference.primary_domain},
                "workspace_domain_inference": inference.model_dump(mode="json"),
                "workspace_structure_analysis": structure_snapshot,
                "workspace_content_samples": {
                    **samples_snapshot,
                    "sampled_file_summaries": sampled_file_summaries,
                    "log_anomaly_snippets": log_anomaly_snippets,
                },
                "environment_event": environment_event,
                "physical_host_state": physical_host_state,
                "q1_sensory_audit": sensory_audit,
                "q1_compression_snapshot": {
                    "analysis_summary": compressed["analysis_summary"],
                    "sample_summary": compressed["sample_summary"],
                    "schema_summary": compressed["schema_summary"],
                    "uncertainty_summary": compressed["uncertainty_summary"],
                },
                "q1_scene_model": {
                    "primary_domain": inference.primary_domain,
                    "secondary_domains": list(inference.secondary_domains),
                    "suggested_first_step": inference.suggested_first_step,
                    "host_runtime_type": host_type,
                },
                "q1_uncertainty_profile": {
                    "risk_sources": list(inference.uncertainties),
                    "risk_summary": inference.reasoning_summary,
                    "uncertainty_intensity": max(0.0, min(1.0, 1.0 - float(inference.confidence))),
                    "sensory_chain_ok": sensory_chain_ok,
                },
                "q1_llm_upgrade": upgrade_payload.model_dump(mode="json"),
            },
            confidence=float(inference.confidence),
        )


def build_q1_where_am_i_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q1,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q1WhereAmIPlugin:
    return Q1WhereAmIPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q1",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )

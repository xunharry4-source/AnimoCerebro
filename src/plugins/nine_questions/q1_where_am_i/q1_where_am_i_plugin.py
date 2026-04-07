from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, List
from uuid import uuid4

from zentex.core.model_provider_spec import ModelProviderCallerContext, ModelProviderSpec
from zentex.core.models import LogicalCognitiveToolSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore

from plugins.nine_questions.q1_where_am_i.compression_budget import LocalCompressionBudget
from plugins.nine_questions.q1_where_am_i.llm_upgrade import build_q1_upgrade_payload
from plugins.nine_questions.q1_where_am_i.models import WorkspaceDomainInference
# Decoupled: Inputs come from sensory plugins, not direct snapshot extract
from zentex.common.plugin_registry import PluginNotBoundError
from zentex.core.plugin_family import HostTelemetryPluginSpec, SensoryPluginSpec
from zentex.common.plugin_registry import PluginNotBoundError
from zentex.core.plugin_family import SensoryPluginSpec

QUESTION_REF = "我在哪"


from plugins.nine_questions._shared import (
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


class Q1WhereAmIPlugin(LogicalCognitiveToolSpec):
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
        registry = context.get("plugin_registry")
        sensory_chain_ok = False
        if registry is not None:
            try:
                workspace_sensor: SensoryPluginSpec = registry.get_bound_plugin(SensoryPluginSpec)
                raw_data = context.get("context_snapshot", {})
                ingested = workspace_sensor.ingest(raw_data)
                sanitized = workspace_sensor.sanitize(ingested)
                local_inputs = workspace_sensor.interpret(sanitized)
                sensory_chain_ok = True
            except PluginNotBoundError:
                # SensoryPluginSpec not bound in this registry (e.g. dev-server uses a
                # CognitiveToolSpec-only registry). Fall through to the direct snapshot path.
                logger.debug("G14 Sensory Chain: SensoryPluginSpec not bound, using context_snapshot fallback")
            except Exception as exc:
                logger.error(f"G14 Sensory Chain Break: {exc}")
                raise RuntimeError(f"Q1 Ingestion Failed: {exc}") from exc
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

        host_telemetry_plugin = context.get("host_telemetry_plugin")
        if host_telemetry_plugin is None and registry is not None:
            try:
                host_telemetry_plugin = registry.get_bound_plugin(HostTelemetryPluginSpec)
            except Exception:
                host_telemetry_plugin = None
        if host_telemetry_plugin is not None and callable(
            getattr(host_telemetry_plugin, "capture_host_state", None)
        ):
            try:
                captured_host_state = host_telemetry_plugin.capture_host_state(
                    {
                        "workspace_root": (
                            (context.get("context_snapshot", {}) or {}).get("workspace_root")
                            or (context.get("context_snapshot", {}) or {}).get("cwd")
                            or context.get("workspace_root")
                        )
                    }
                )
                if isinstance(captured_host_state, dict):
                    merged_host_state = dict(local_inputs.get("physical_host_state") or {})
                    merged_host_state.update(captured_host_state)
                    local_inputs["physical_host_state"] = merged_host_state
            except Exception as exc:
                logger.error("Q1 host telemetry capture failed: %s", exc)
                raise RuntimeError(f"Q1 Host Telemetry Failed: {exc}") from exc

        # 2. Local compression budget + three-layer payload assembly.
        # Note: local_inputs is now the dictionary from workspace_sensor.interpret
        budget = LocalCompressionBudget()
        compressed = budget.compress(
            structure=local_inputs.get("structure", {}),
            samples=local_inputs.get("samples", []),
            environment_event=local_inputs.get("environment_event", {}),
            physical_host_state=local_inputs.get("physical_host_state", {}),
        )

        evidence_summary = "\n".join(
            part
            for part in [compressed["analysis_summary"], compressed["sample_summary"]]
            if part.strip()
        ).strip()
        local_stats = compressed["schema_summary"].strip()
        uncertainty_hints = compressed["uncertainty_summary"].strip()

        system_prompt = (
            "You are Zentex. Infer the current workspace domain (Q1: 我在哪). "
            "Return STRICT JSON that matches the WorkspaceDomainInference schema exactly."
        )
        prompt = (
            "Required keys:\n"
            "- primary_domain (str)\n"
            "- secondary_domains (List[str])\n"
            "- confidence (float 0..1)\n"
            "- reasoning_summary (str)\n"
            "- uncertainties (List[str], must be non-empty)\n"
            "- suggested_first_step (str)\n\n"
            "Evidence Summary:\n"
            f"{evidence_summary or '(empty)'}\n\n"
            "Local Stats:\n"
            f"{local_stats or '(empty)'}\n\n"
            "Uncertainty Hints:\n"
            f"{uncertainty_hints or '(empty)'}\n"
        )

        model_context = {
            "analysis_summary": compressed["analysis_summary"],
            "sample_summary": compressed["sample_summary"],
            "schema_summary": compressed["schema_summary"],
            "uncertainty_summary": compressed["uncertainty_summary"],
            "suffix_distribution": (local_inputs.get("structure") or {}).get("suffix_distribution"),
            "interpretation_markers": local_inputs.get("interpretation_markers"),
            "risk_markers": local_inputs.get("risk_markers"),
            "environment_event": local_inputs.get("environment_event"),
            "physical_host_state": local_inputs.get("physical_host_state"),
        }

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
                "q1_scene_model": {
                    "primary_domain": inference.primary_domain,
                    "secondary_domains": list(inference.secondary_domains),
                    "suggested_first_step": inference.suggested_first_step,
                },
                "q1_uncertainty_profile": {
                    "risk_sources": list(inference.uncertainties),
                    "risk_summary": inference.reasoning_summary,
                    "uncertainty_intensity": max(0.0, min(1.0, 1.0 - float(inference.confidence))),
                },
                "q1_llm_upgrade": upgrade_payload.model_dump(mode="json"),
            },
            confidence=float(inference.confidence),
        )


def build_q1_where_am_i_plugin(
    *,
    plugin_id: str = "nine-question-q1-where-am-i",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q1WhereAmIPlugin:
    return Q1WhereAmIPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q1",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["q1_where_am_i_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="nine_question",
        purpose=(
            "LLM-backed nine-question Q1: 我在哪 (workspace domain inference) with strict local pre-processing."
        ),
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "required": [
                "primary_domain",
                "secondary_domains",
                "confidence",
                "reasoning_summary",
                "uncertainties",
                "suggested_first_step",
            ],
        },
        required_context=["context_snapshot", "model_provider", "transcript_store"],
        trigger_conditions=["inspection"],
        behavior_key="nine_questions",
        supports_multiple_plugins=True,
        is_default_version=True,
        is_official_release=True,
        do_not_use_when=["missing_model_provider", "unsafe_external_action"],
    )

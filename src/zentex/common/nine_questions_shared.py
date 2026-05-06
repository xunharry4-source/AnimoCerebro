from __future__ import annotations

import logging
"""Shared utilities for nine-questions cognitive plugins.

These helpers are used across Q1-Q9 plugin implementations.
Kept in zentex/common to avoid polluting the nine_questions plugin group
directory with non-plugin code.
"""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter, perf_counter_ns
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from zentex.foundation.specs.model_provider import ModelProviderCallerContext, ModelProviderSpec
from zentex.common.flow_audit import FlowAudit
from zentex.kernel import AuditEventStore, AuditEventType
from zentex.kernel.state_domain.transcript import TranscriptStore
from zentex.reflection.models import ReflectionType

logger = logging.getLogger(__name__)
_RUN_PARENT_REGISTRY: dict[int, "PersistentModuleRuns"] = {}
_QUALIFIED_SNAPSHOT_STATUSES = {"completed", "ready"}
_UNQUALIFIED_MODULE_STATUSES = {"failed", "missing", "degraded", "partial", "partial_failed", "abnormal", "stopped"}
_QUESTION_LLM_OUTPUT_KEYS: dict[str, tuple[str, ...]] = {
    "q1": (
        "workspace_domain_inference",
        "q1_scene_model",
        "q1_uncertainty_profile",
        "q1_llm_upgrade",
    ),
    "q2": (
        "identity_kernel_snapshot",
        "identity_kernel",
        "asset_inventory",
        "q2_asset_inventory",
        "q2_internal_tool_asset_inventory",
        "q2_external_tool_asset_inventory",
        "unified_asset_inventory",
        "resource_evaluation",
        "q2_unified_asset_inventory",
        "q2_resource_evaluation",
        "q2_resource_status_humanized",
    ),
    "q3": (
        "identity_kernel_snapshot",
        "identity_kernel",
        "Q3InferenceResult",
        "q3_role_profile",
        "q3_mission_boundary",
        "mission_continuity_projection",
    ),
    "q4": (
        "capability_boundary_profile",
        "permission_profile",
        "q4_capability_boundary_profile",
        "q4_permission_profile",
    ),
    "q5": (
        "authorization_boundary",
        "q5_authorization_boundary",
        "authorization_boundary_profile",
        "q5_authorization_boundary_profile",
        "q5_permission_boundary",
        "q5_objective_convergence_guard",
    ),
    "q6": (
        "forbidden_zone_profile",
        "q6_forbidden_zone_profile",
    ),
    "q7": (
        "red_line_assessment",
        "q7_red_line_assessment",
        "q7_non_bypassable_constraints",
        "q7_current_red_line_hits",
    ),
    "q8": (
        "objective_profile",
        "task_queue",
        "q8_objective_profile",
        "q8_task_queue",
        "q8_external_execution_tasks",
        "q8_internal_cognitive_tasks",
    ),
    "q9": (
        "current_action_plan",
        "method_selection",
        "required_resources",
        "risk_assessment",
        "expected_outcome",
        "alternative_candidates",
        "question_driver_refs",
        "action_plan",
        "q9_action_plan",
        "evaluation_profile",
        "evolution_profile",
        "escalation_profile",
        "q9_evaluation_profile",
        "q9_evolution_profile",
        "q9_escalation_profile",
        "q9_internal_llm_input",
        "q9_internal_llm_output",
        "q9_external_llm_input",
        "q9_external_llm_output",
    ),
}
_PRESERVE_EMPTY_LLM_OUTPUT_KEYS: dict[str, set[str]] = {
    "q8": {"q8_external_execution_tasks", "q8_internal_cognitive_tasks"},
}
_LLM_OUTPUT_METADATA_KEYS = ("summary", "confidence", "trace_id", "tool_id", "timestamp")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_non_empty_str(*values: object) -> Optional[str]:
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _coerce_timeout_seconds(*values: object, default: float = 240.0) -> float:
    for value in values:
        try:
            if value is None:
                continue
            timeout = float(value)
        except (TypeError, ValueError):
            continue
        if timeout > 0:
            return max(5.0, timeout)
    return float(default)


def resolve_model_provider_key(context: Dict[str, Any]) -> Optional[str]:
    explicit_provider = context.get("model_provider")
    if isinstance(explicit_provider, str) and explicit_provider.strip():
        return explicit_provider.strip()
    return _first_non_empty_str(
        context.get("llm_provider_key"),
        context.get("provider_key"),
    )


class LLMServiceModelProviderAdapter:
    """
    Compatibility shim for legacy nine-question plugins.

    Q1-Q9 plugins historically called `ModelProviderSpec.generate_json(...)`
    directly. The real LLM entrypoint must now be `src/zentex/llm`, so this
    adapter preserves the old plugin surface while routing all requests through
    `LLMService -> LLMGateway`.
    """

    def __init__(self, llm_service: Any, root_context: Dict[str, Any]) -> None:
        self._llm_service = llm_service
        self._root_context = root_context
        self.plugin_id = "llm_gateway"
        self.provider_name = "llm_gateway"
        self.default_model = _first_non_empty_str(
            root_context.get("llm_model"),
            root_context.get("model"),
        ) or ""
        self.last_raw_response: Dict[str, Optional[Any]] = None
        self.last_token_usage: Dict[str, Any] = {}
        self.last_model_name: Optional[str] = None

    def generate_json(
        self,
        *,
        prompt: str,
        context: dict[str, Any],
        caller_context: Union[ModelProviderCallerContext, dict[str], Any],
        max_output_tokens: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if isinstance(caller_context, dict):
            normalized_caller_context = ModelProviderCallerContext.model_validate(caller_context)
        else:
            normalized_caller_context = caller_context

        provider_key = resolve_model_provider_key(self._root_context)
        model = _first_non_empty_str(
            self._root_context.get("llm_model"),
            self._root_context.get("model"),
        )
        request_timeout_seconds = _coerce_timeout_seconds(
            context.get("request_timeout_seconds"),
            context.get("llm_request_timeout_seconds"),
            self._root_context.get("request_timeout_seconds"),
            self._root_context.get("llm_request_timeout_seconds"),
            default=240.0,
        )
        caller_metadata = dict(metadata or {})
        max_json_repair_attempts = _first_present(
            caller_metadata,
            "max_json_repair_attempts",
            context,
            "max_json_repair_attempts",
            context,
            "llm_max_json_repair_attempts",
            self._root_context,
            "max_json_repair_attempts",
            self._root_context,
            "llm_max_json_repair_attempts",
        )
        resolved_max_output_tokens = _first_present(
            {"max_output_tokens": max_output_tokens},
            "max_output_tokens",
            context,
            "max_output_tokens",
            context,
            "llm_max_output_tokens",
            self._root_context,
            "max_output_tokens",
            self._root_context,
            "llm_max_output_tokens",
        )
        if resolved_max_output_tokens is not None:
            resolved_max_output_tokens = int(resolved_max_output_tokens)
        temperature = float(
            context.get("temperature")
            or context.get("llm_temperature")
            or self._root_context.get("temperature")
            or self._root_context.get("llm_temperature")
            or 0.2
        )

        call = self._llm_service.generate_json(
            prompt=prompt,
            context=context,
            caller_context=normalized_caller_context,
            source_module=normalized_caller_context.source_module,
            invocation_phase=normalized_caller_context.invocation_phase,
            decision_id=normalized_caller_context.decision_id,
            model_provider=provider_key,
            model=model,
            temperature=temperature,
            max_output_tokens=resolved_max_output_tokens,
            metadata={
                **caller_metadata,
                "trace_id": normalized_caller_context.trace_id,
                "question_driver_refs": list(normalized_caller_context.question_driver_refs),
                # Keep provider-side wall clock below question-level timeout budgets.
                "request_timeout_seconds": request_timeout_seconds,
                "max_json_repair_attempts": max_json_repair_attempts,
            },
        )
        self.plugin_id = call.provider_key
        self.provider_name = call.provider_key
        self.default_model = call.model
        self.last_model_name = call.model
        self.last_raw_response = call.raw_response
        self.last_token_usage = {
            "input_tokens": call.usage.input_tokens,
            "output_tokens": call.usage.output_tokens,
            "total_tokens": call.usage.total_tokens,
        }
        return call.output


def _first_present(*pairs: Any) -> Any:
    for index in range(0, len(pairs), 2):
        source = pairs[index]
        key = pairs[index + 1]
        if isinstance(source, dict) and key in source and source.get(key) is not None:
            return source.get(key)
    return None


def require_model_provider(context: Dict[str, Any]) -> ModelProviderSpec:
    llm_service = context.get("llm_service")
    if llm_service is not None and hasattr(llm_service, "generate_json"):
        return LLMServiceModelProviderAdapter(llm_service, context)

    provider = context.get("model_provider")
    if provider is None or not hasattr(provider, "generate_json"):
        registry = context.get("plugin_registry")
        if registry is not None and callable(getattr(registry, "get_bound_plugin", None)):
            try:
                provider = registry.get_bound_plugin(ModelProviderSpec)
            except Exception as exc:
                raise RuntimeError(
                    "LLM MANDATORY: missing active ModelProvider in context['model_provider'] "
                    "and plugin_registry binding failed"
                ) from exc
        else:
            raise RuntimeError(
                "LLM MANDATORY: missing active llm_service and ModelProvider in execution context"
            )
    return provider


def require_audit_store(context: Dict[str, Any]) -> Union[AuditEventStore, TranscriptStore]:
    store = context.get("audit_store") or context.get("transcript_store")
    if isinstance(store, (AuditEventStore, TranscriptStore)):
        return store
    if store and hasattr(store, "read_entries") and hasattr(store, "write_entry"):
        return store  # type: ignore

    raise RuntimeError(
        f"audit_store is required for auditable replay. Got: {type(store).__name__ if store else 'None'}"
    )


def require_transcript_store(context: Dict[str, Any]) -> Union[AuditEventStore, TranscriptStore]:
    return require_audit_store(context)


def build_caller_context(
    *,
    source_module: str,
    invocation_phase: str,
    question_ref: str,
    question_driver_refs: List[Optional[str]] = None,
    decision_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ModelProviderCallerContext:
    driver_refs: List[str]
    if question_driver_refs and any(str(item).strip() for item in question_driver_refs):
        driver_refs = [str(item) for item in question_driver_refs if str(item).strip()]
        if question_ref not in driver_refs:
            driver_refs.append(question_ref)
    else:
        driver_refs = [question_ref]
    return ModelProviderCallerContext(
        source_module=source_module,
        invocation_phase=invocation_phase,
        question_driver_refs=driver_refs,
        decision_id=decision_id,
        trace_id=trace_id,
    )


def build_model_context(context: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure we never leak non-serializable runtime objects into the model prompt.
    stripped: Dict[str, Any] = {}
    for key, value in context.items():
        if key in {"model_provider", "transcript_store", "audit_store", "nine_question_state", "plugin_registry"}:
            continue
        stripped[key] = value
    return stripped


def get_question_snapshot_map_from_context(context: Dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return authoritative per-question stored snapshots from `nine_question_state`.

    Business rule:
    Q2-Q9 must read upstream results from `nine_question_state.question_snapshots`
    instead of the deprecated shared `context_snapshot`.
    """
    state_payload = _as_dict(context.get("nine_question_state"))
    snapshot_map = state_payload.get("question_snapshots")
    if not isinstance(snapshot_map, dict):
        return {}
    return {str(key): value for key, value in snapshot_map.items() if isinstance(value, dict)}


def _extract_snapshot_diagnosis(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    for payload in (
        snapshot.get("context_updates"),
        ((snapshot.get("result") or {}).get("context_updates") if isinstance(snapshot.get("result"), dict) else None),
        ((snapshot.get("execution_result") or {}).get("context_updates") if isinstance(snapshot.get("execution_result"), dict) else None),
    ):
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if str(key).endswith("_execution_diagnosis") and isinstance(value, dict):
                return deepcopy(value)
    return {}


def _compact_module_run_for_upstream(run: Any) -> dict[str, Any]:
    if not isinstance(run, dict):
        return {}
    return {
        key: deepcopy(run.get(key))
        for key in (
            "module_id",
            "status",
            "error_code",
            "error_message",
            "source",
            "used_fallback",
        )
        if run.get(key) not in (None, "", [], {})
    }


def _compact_snapshot_diagnosis_for_upstream(snapshot: dict[str, Any]) -> dict[str, Any]:
    diagnosis = _extract_snapshot_diagnosis(snapshot)
    if not diagnosis:
        return {}
    compact = {
        key: deepcopy(diagnosis.get(key))
        for key in (
            "authenticity_status",
            "used_fallback",
            "snapshot_fallback_used",
            "upstream_degraded",
        )
        if diagnosis.get(key) not in (None, "", [], {})
    }
    module_runs = diagnosis.get("module_runs")
    if isinstance(module_runs, list):
        compact["module_runs"] = [
            item
            for item in (_compact_module_run_for_upstream(run) for run in module_runs)
            if item
        ]
    return compact


def _iter_snapshot_payloads_for_llm_output(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for key in ("result", "context_updates", "execution_result"):
        payload = snapshot.get(key)
        if isinstance(payload, dict):
            payloads.append(payload)
            nested_context = payload.get("context_updates")
            if isinstance(nested_context, dict):
                payloads.append(nested_context)
            nested_result = payload.get("result")
            if isinstance(nested_result, dict):
                payloads.append(nested_result)
    return payloads


def project_authoritative_question_llm_output(
    question_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Return only the latest LLM-derived business output for one question."""
    qid = str(question_id or snapshot.get("question_id") or "").strip().lower()
    allowed_keys = set(_QUESTION_LLM_OUTPUT_KEYS.get(qid, ()))
    preserve_empty_keys = _PRESERVE_EMPTY_LLM_OUTPUT_KEYS.get(qid, set())
    table_llm_output = snapshot.get("llm_output")
    projected: dict[str, Any] = {}
    if isinstance(table_llm_output, dict):
        projected = {
            key: deepcopy(value)
            for key, value in table_llm_output.items()
            if value not in (None, "", [], {}) or key in preserve_empty_keys
        }
    if qid != "q2":
        for payload in _iter_snapshot_payloads_for_llm_output(snapshot):
            for key in allowed_keys:
                value = payload.get(key)
                if (value not in (None, "", [], {}) or key in preserve_empty_keys) and projected.get(key) in (None, "", [], {}):
                    projected[key] = deepcopy(value)

    # Normalize canonical aliases expected by downstream prompts/modules.
    if qid == "q1":
        domain = projected.get("workspace_domain_inference")
        if isinstance(domain, dict):
            try:
                confidence = float(domain.get("confidence") or 0.5)
            except (TypeError, ValueError):
                confidence = 0.5
            projected.setdefault(
                "q1_scene_model",
                {
                    "primary_domain": domain.get("primary_domain"),
                    "secondary_domains": domain.get("secondary_domains"),
                    "suggested_first_step": domain.get("suggested_first_step"),
                },
            )
            projected.setdefault(
                "q1_uncertainty_profile",
                {
                    "risk_sources": domain.get("uncertainties"),
                    "risk_summary": domain.get("reasoning_summary"),
                    "uncertainty_intensity": max(0.0, min(1.0, 1.0 - confidence)),
                },
            )
    elif qid == "q2":
        if projected.get("q2_asset_inventory") in (None, "", [], {}) and projected.get("asset_inventory") not in (None, "", [], {}):
            projected["q2_asset_inventory"] = projected.get("asset_inventory")
        if projected.get("q2_unified_asset_inventory") in (None, "", [], {}) and projected.get("unified_asset_inventory") not in (None, "", [], {}):
            projected["q2_unified_asset_inventory"] = projected.get("unified_asset_inventory")
        if projected.get("q2_resource_evaluation") in (None, "", [], {}) and projected.get("resource_evaluation") not in (None, "", [], {}):
            projected["q2_resource_evaluation"] = projected.get("resource_evaluation")
    elif qid == "q3":
        q3_result = projected.get("Q3InferenceResult")
        q3_result = q3_result if isinstance(q3_result, dict) else {}
        projected.setdefault("q3_role_profile", q3_result.get("RoleProfile"))
        projected.setdefault("q3_mission_boundary", q3_result.get("MissionContinuityBoundary"))
    elif qid == "q4":
        projected.setdefault("q4_capability_boundary_profile", projected.get("capability_boundary_profile"))
        projected.setdefault("q4_permission_profile", projected.get("permission_profile"))
    elif qid == "q5":
        projected.setdefault("q5_authorization_boundary", projected.get("authorization_boundary"))
        projected.setdefault(
            "q5_authorization_boundary_profile",
            projected.get("authorization_boundary_profile") or projected.get("q5_permission_boundary"),
        )
        projected.setdefault("q5_permission_boundary", projected.get("q5_authorization_boundary_profile"))
    elif qid == "q6":
        projected.setdefault("q6_forbidden_zone_profile", projected.get("forbidden_zone_profile"))
    elif qid == "q7":
        projected.setdefault("q7_red_line_assessment", projected.get("red_line_assessment"))
        assessment = _as_dict(projected.get("q7_red_line_assessment") or projected.get("red_line_assessment"))
        if assessment:
            projected.setdefault("q7_current_red_line_hits", assessment.get("current_red_line_hits"))
            projected.setdefault("q7_rejected_operation_records", assessment.get("rejected_operation_records"))
            projected.setdefault("q7_ban_source_explanations", assessment.get("ban_source_explanations"))
            projected.setdefault("q7_non_bypassable_constraints", assessment.get("non_bypassable_constraints"))
            projected.setdefault("q7_question_driver_refs", assessment.get("question_driver_refs"))
    elif qid == "q8":
        projected.setdefault("q8_objective_profile", projected.get("objective_profile"))
        projected.setdefault("q8_task_queue", projected.get("task_queue"))
    elif qid == "q9":
        if "action_plan" not in projected and "current_action_plan" in projected:
            projected["action_plan"] = {
                key: projected.get(key)
                for key in (
                    "current_action_plan",
                    "method_selection",
                    "required_resources",
                    "risk_assessment",
                    "expected_outcome",
                    "alternative_candidates",
                    "question_driver_refs",
                )
                if key in projected
            }
        projected.setdefault("q9_action_plan", projected.get("action_plan"))
        projected.setdefault("q9_evaluation_profile", projected.get("evaluation_profile"))
        projected.setdefault("q9_evolution_profile", projected.get("evolution_profile"))
        projected.setdefault("q9_escalation_profile", projected.get("escalation_profile"))

    for key in _LLM_OUTPUT_METADATA_KEYS:
        value = snapshot.get(key)
        if value not in (None, "", [], {}):
            projected[key] = deepcopy(value)
    diagnosis = _compact_snapshot_diagnosis_for_upstream(snapshot)
    if diagnosis:
        projected[f"{qid}_execution_diagnosis"] = diagnosis
    return {
        key: value
        for key, value in projected.items()
        if value not in (None, "", [], {}) or key in preserve_empty_keys
    }


def build_authoritative_question_llm_snapshot(
    question_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Build a scoped upstream snapshot: LLM output plus minimal qualification data."""
    qid = str(question_id or snapshot.get("question_id") or "").strip().lower()
    llm_output = project_authoritative_question_llm_output(qid, snapshot)
    diagnosis = _compact_snapshot_diagnosis_for_upstream(snapshot)
    context_updates: dict[str, Any] = {}
    if diagnosis:
        context_updates[f"{qid}_execution_diagnosis"] = diagnosis
    scoped_snapshot = {
        "question_id": qid,
        "summary": str(snapshot.get("summary") or llm_output.get("summary") or ""),
        "confidence": snapshot.get("confidence"),
        "trace_id": snapshot.get("trace_id"),
        "tool_id": snapshot.get("tool_id"),
        "timestamp": snapshot.get("timestamp") or snapshot.get("updated_at") or snapshot.get("generated_at"),
        "result": llm_output,
        "context_updates": context_updates,
    }
    llm_trace_payload = extract_authoritative_question_llm_trace(snapshot)
    if llm_trace_payload:
        scoped_snapshot["llm_trace_payload"] = llm_trace_payload
    return scoped_snapshot


def extract_authoritative_question_llm_trace(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the stored LLM trace payload for one question snapshot."""
    if not isinstance(snapshot, dict):
        return {}
    candidates: list[dict[str, Any]] = []
    direct_trace = snapshot.get("llm_trace_payload")
    if isinstance(direct_trace, dict) and direct_trace:
        candidates.append(direct_trace)
    for key in ("context_updates", "result", "execution_result"):
        payload = snapshot.get(key)
        if not isinstance(payload, dict):
            continue
        nested_trace = payload.get("llm_trace_payload")
        if isinstance(nested_trace, dict) and nested_trace:
            candidates.append(nested_trace)
    for candidate in candidates:
        if isinstance(candidate.get("asset_scopes"), list) and candidate.get("asset_scopes"):
            return deepcopy(candidate)
    if candidates:
        return deepcopy(candidates[0])
    return {}


def require_authoritative_question_llm_trace(
    question_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed unless the upstream question has a real persisted LLM trace."""
    qid = str(question_id or snapshot.get("question_id") or "").strip().lower()
    trace = extract_authoritative_question_llm_trace(snapshot)
    if not trace:
        raise RuntimeError(f"{qid} upstream LLM trace is missing")
    error_type = str(trace.get("error_type") or "").strip()
    error_message = str(trace.get("error_message") or trace.get("error") or "").strip()
    if error_type or error_message:
        raise RuntimeError(f"{qid} upstream LLM trace failed: {error_type or error_message}")

    invocations = trace.get("invocations")
    if not isinstance(invocations, list) or not invocations:
        raise RuntimeError(f"{qid} upstream LLM trace invocations missing")

    material_invocation_found = False
    for index, invocation in enumerate(invocations):
        if not isinstance(invocation, dict):
            raise RuntimeError(f"{qid} upstream LLM trace invocation[{index}] is invalid")
        invocation_error = str(invocation.get("error_type") or invocation.get("error_message") or invocation.get("error") or "").strip()
        if invocation_error:
            continue
        provider_name = str(invocation.get("provider_name") or invocation.get("provider_plugin_id") or "").strip()
        prompt = str(invocation.get("prompt") or "").strip()
        context_payload = invocation.get("context_data") if isinstance(invocation.get("context_data"), dict) else invocation.get("context")
        raw_response = invocation.get("raw_response") if invocation.get("raw_response") not in (None, "", [], {}) else invocation.get("result")
        token_usage = invocation.get("token_usage")
        if (
            provider_name
            and prompt
            and isinstance(context_payload, dict)
            and context_payload
            and raw_response not in (None, "", [], {})
            and isinstance(token_usage, dict)
        ):
            material_invocation_found = True
    if not material_invocation_found:
        raise RuntimeError(f"{qid} upstream LLM trace has no material request/result invocation")

    if not str(trace.get("provider_name") or trace.get("provider_plugin_id") or "").strip():
        raise RuntimeError(f"{qid} upstream LLM trace provider missing")
    if not str(trace.get("prompt") or "").strip():
        raise RuntimeError(f"{qid} upstream LLM trace prompt missing")
    if not isinstance(trace.get("context_data"), dict) and not isinstance(trace.get("context"), dict):
        raise RuntimeError(f"{qid} upstream LLM trace context missing")
    if trace.get("raw_response") in (None, "", [], {}) and trace.get("result") in (None, "", [], {}):
        raise RuntimeError(f"{qid} upstream LLM trace result missing")
    return trace


def _normalize_dirty_questions_from_state(context: Dict[str, Any]) -> set[str]:
    state_payload = _as_dict(context.get("nine_question_state"))
    dirty = state_payload.get("dirty_questions")
    if not isinstance(dirty, list):
        return set()
    return {str(item).strip() for item in dirty if str(item).strip()}


def _assert_snapshot_is_latest_qualified(
    *,
    context: Dict[str, Any],
    question_id: str,
    snapshot: dict[str, Any],
) -> None:
    if not snapshot:
        raise RuntimeError(f"{question_id} upstream snapshot missing from nine_question_state")

    diagnosis = _extract_snapshot_diagnosis(snapshot)
    authenticity = str(diagnosis.get("authenticity_status") or "").strip().lower()
    if authenticity not in _QUALIFIED_SNAPSHOT_STATUSES:
        raise RuntimeError(
            f"{question_id} upstream snapshot is not qualified: authenticity_status={authenticity or 'missing'}"
        )

    if diagnosis.get("snapshot_fallback_used") is True or diagnosis.get("used_fallback") is True:
        raise RuntimeError(f"{question_id} upstream snapshot fallback is not allowed")

    module_runs = diagnosis.get("module_runs")
    if not isinstance(module_runs, list) or not module_runs:
        raise RuntimeError(f"{question_id} upstream snapshot module_runs missing")
    for run in module_runs:
        if not isinstance(run, dict):
            raise RuntimeError(f"{question_id} upstream snapshot has invalid module run payload")
        status = str(run.get("status") or "").strip().lower()
        if status in _UNQUALIFIED_MODULE_STATUSES or status not in _QUALIFIED_SNAPSHOT_STATUSES:
            module_id = str(run.get("module_id") or "unknown")
            raise RuntimeError(
                f"{question_id} upstream snapshot module is not qualified: {module_id} status={status or 'missing'}"
            )

    trace_id = str(snapshot.get("trace_id") or "").strip()
    if not trace_id or trace_id.endswith(":no-trace"):
        raise RuntimeError(f"{question_id} upstream snapshot trace_id is missing or placeholder")

    timestamp = (
        str(snapshot.get("updated_at") or "").strip()
        or str(snapshot.get("generated_at") or "").strip()
        or str(snapshot.get("timestamp") or "").strip()
    )
    if not timestamp:
        raise RuntimeError(f"{question_id} upstream snapshot missing updated_at/generated_at/timestamp")

    dirty_questions = _normalize_dirty_questions_from_state(context)
    if question_id in dirty_questions:
        raise RuntimeError(f"{question_id} upstream snapshot is marked dirty and not latest qualified")


def get_authoritative_question_snapshot(
    context: Dict[str, Any],
    question_id: str,
) -> dict[str, Any]:
    qid = str(question_id or "").strip().lower()
    snapshot = _as_dict(get_question_snapshot_map_from_context(context).get(qid))
    _assert_snapshot_is_latest_qualified(context=context, question_id=qid, snapshot=snapshot)
    return snapshot


def merge_authoritative_question_payload(
    snapshot: dict[str, Any],
    question_id: str = "",
) -> dict[str, Any]:
    """Return one stored question's latest LLM output as the upstream read model."""
    return project_authoritative_question_llm_output(question_id, snapshot)


def build_authoritative_question_context(
    context: Dict[str, Any],
    question_ids: list[str],
) -> dict[str, Any]:
    """Merge multiple upstream question snapshots into a local read context.

    This helper is only for Q2-Q9 upstream reconstruction. It is not a shared
    runtime `context_snapshot`, and it must only be built from stored question
    snapshots for the explicitly requested question ids.
    """
    merged: dict[str, Any] = {}
    snapshot_map = get_question_snapshot_map_from_context(context)
    for question_id in question_ids:
        snapshot = _as_dict(snapshot_map.get(question_id))
        if not snapshot:
            continue
        merged.update(merge_authoritative_question_payload(snapshot, question_id))
    return merged


def build_authoritative_question_bundle(
    context: Dict[str, Any],
    question_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Return per-question merged payloads from authoritative stored snapshots."""
    snapshot_map = get_question_snapshot_map_from_context(context)
    return {
        question_id: merge_authoritative_question_payload(_as_dict(snapshot_map.get(question_id)), question_id)
        for question_id in question_ids
    }


def load_authoritative_question_context_from_storage(
    context: Dict[str, Any],
    question_ids: list[str],
) -> dict[str, Any]:
    """Load upstream question payloads from authoritative question snapshots only."""
    return build_authoritative_question_context(context, question_ids)


def load_authoritative_question_bundle_from_storage(
    context: Dict[str, Any],
    question_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Load per-question upstream payloads from authoritative question snapshots only."""
    return build_authoritative_question_bundle(context, question_ids)


def safe_provider_plugin_id(provider: Any) -> Optional[str]:
    candidate = getattr(provider, "plugin_id", None) or getattr(provider, "provider_name", None)
    if isinstance(candidate, str):
        text = candidate.strip()
        return text or None
    return None


def json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [json_safe_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe_payload(item) for key, item in value.items()}
    return None


def log_payload_dump(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(value)


def _is_real_service(candidate: Any) -> bool:
    return candidate is not None and not bool(getattr(candidate, "_is_stub", False))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PersistentModuleRuns(list):
    """List wrapper that emits module-run patches whenever its contents change."""

    def __init__(
        self,
        iterable: list[dict[str, Optional[Any]]] = None,
        *,
        question_id: str,
        callback: Optional[Any] = None,
    ) -> None:
        super().__init__(iterable or [])
        self.question_id = question_id
        self._callback = callback

    def _notify(self) -> None:
        if not callable(self._callback):
            return
        try:
            payload = [deepcopy(json_safe_payload(item)) for item in self]
            self._callback(self.question_id, payload)
        except Exception:
            logger.exception("Failed to persist module runs for %s", self.question_id)

    def append(self, item) -> None:
        super().append(item)
        self._notify()

    def extend(self, items) -> None:
        super().extend(items)
        self._notify()

    def insert(self, index: int, item) -> None:
        super().insert(index, item)
        self._notify()

    def __setitem__(self, index, value) -> None:
        super().__setitem__(index, value)
        self._notify()


def bind_module_runs(
    context: dict[str, Any],
    question_id: str,
    *,
    initial: list[dict[str, Optional[Any]]] = None,
) -> PersistentModuleRuns:
    callback = context.get("module_run_persistor")
    return PersistentModuleRuns(
        initial,
        question_id=question_id,
        callback=callback if callable(callback) else None,
    )


def persist_question_module_output(
    context: dict[str, Any],
    *,
    question_id: str,
    module_id: str,
    payload: Any,
    status: str = "completed",
    output_kind: str = "evidence",
    rollback_available: bool = True,
    retry_available: bool = True,
    trace_id: Optional[str] = None,
    extra: dict[str, Optional[Any]] = None,
) -> dict[str, Any]:
    committed_payload = {
        "question_id": question_id,
        "module_id": module_id,
        "status": status,
        "output_kind": output_kind,
        "data": json_safe_payload(payload),
        "trace_id": str(trace_id or context.get("trace_id") or f"{question_id}:{module_id}"),
        "committed_at": utc_now_iso(),
        "rollback_available": rollback_available,
        "retry_available": retry_available,
        **(extra or {}),
    }
    callback = context.get("module_output_persistor")
    if callable(callback):
        try:
            callback(question_id, module_id, deepcopy(committed_payload))
        except Exception:
            logger.exception("Failed to persist module output for %s.%s", question_id, module_id)
    return committed_payload


def _notify_module_run_parent(run: dict[str, Any]) -> None:
    parent = _RUN_PARENT_REGISTRY.get(id(run))
    if parent is not None:
        parent._notify()


def _parse_iso_timestamp(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _derive_question_id_from_module(module_id: str) -> str:
    module_text = str(module_id or "").strip().lower()
    if module_text.startswith("q") and len(module_text) > 2 and module_text[1].isdigit() and module_text[2] == "_":
        return module_text.split("_", 1)[0]
    return "unknown"


def _extract_run_trace_id(run: dict[str, Any]) -> str:
    direct_trace = str(run.get("trace_id") or "").strip()
    if direct_trace:
        return direct_trace
    data = run.get("data")
    if isinstance(data, dict):
        nested_trace = str(data.get("trace_id") or "").strip()
        if nested_trace:
            return nested_trace
    return ""


def build_question_dependency(
    dependency_id: str,
    *,
    payload: Any,
    required: bool = True,
    allow_degraded: bool = False,
    message: Optional[str] = None,
) -> dict[str, Any]:
    """Normalize upstream dependency health for Q2-Q9 authenticity checks."""
    status = "missing"
    normalized_message = message
    if isinstance(payload, dict) and payload:
        raw_status = str(
            payload.get("authenticity_status")
            or payload.get("status")
            or payload.get("current_status")
            or ""
        ).strip()
        if raw_status in {"completed", "ready", "success"}:
            status = "completed"
        elif raw_status in {"degraded", "partial_failed", "partial"}:
            status = "degraded"
        elif raw_status in {"failed", "missing"}:
            status = raw_status
        else:
            status = "completed"
    elif payload not in (None, {}, [], ""):
        status = "completed"

    if status == "degraded" and allow_degraded:
        effective_status = "completed"
    else:
        effective_status = status
    if not normalized_message:
        normalized_message = f"{dependency_id} {effective_status}"
    return {
        "dependency_id": dependency_id,
        "required": required,
        "status": effective_status,
        "message": normalized_message,
    }


def validate_question_dependency(
    dependency_id: str,
    payload: Any,
    *,
    required: bool = True,
    allow_degraded: bool = False,
    message: Optional[str] = None,
) -> tuple[bool, dict[str, Any]]:
    dependency = build_question_dependency(
        dependency_id,
        payload=payload,
        required=required,
        allow_degraded=allow_degraded,
        message=message,
    )
    ok = dependency["status"] == "completed" or (not required and dependency["status"] == "missing")
    return ok, dependency


def start_module_run(
    module_runs: list[dict[str, Any]],
    module_id: str,
    *,
    source: str = "nine_questions",
    question_id: str | None = None,
) -> dict[str, Any]:
    normalized_module_id = str(module_id or "").strip()
    normalized_question_id = str(question_id or "").strip().lower()
    run = {
        "module_id": normalized_module_id,
        "question_id": normalized_question_id or _derive_question_id_from_module(normalized_module_id),
        "status": "running",
        "error_code": "",
        "error_message": "",
        "started_at": utc_now_iso(),
        "finished_at": "",
        "duration_ms": 0,
        "used_fallback": False,
        "source": source,
        "_started_perf_ns": perf_counter_ns(),
    }
    module_runs.append(run)
    if isinstance(module_runs, PersistentModuleRuns):
        _RUN_PARENT_REGISTRY[id(run)] = module_runs
    logger.info(
        "[NINE QUESTIONS MODULE] START question=%s module=%s source=%s started_at=%s",
        run["question_id"],
        normalized_module_id,
        source,
        run["started_at"],
    )
    return run


def finish_module_run(
    run: dict[str, Any],
    *,
    status: str = "completed",
    used_fallback: bool = False,
    error_code: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    start_perf_ns = run.pop("_started_perf_ns", None)
    if isinstance(start_perf_ns, int):
        duration_ms = max(0, int((perf_counter_ns() - start_perf_ns) / 1_000_000))
    else:
        started_at = _parse_iso_timestamp(run.get("started_at"))
        finished_probe = datetime.now(timezone.utc)
        if started_at is not None:
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            duration_ms = max(0, int((finished_probe - started_at).total_seconds() * 1000))
        else:
            duration_ms = 0
    run["status"] = status
    run["finished_at"] = utc_now_iso()
    run["duration_ms"] = duration_ms
    run["used_fallback"] = used_fallback
    run["error_code"] = error_code
    run["error_message"] = error_message
    log_fn = logger.info if status in {"completed", "ready", "success"} and not error_code else logger.error
    log_fn(
        "[NINE QUESTIONS MODULE] END question=%s module=%s source=%s status=%s started_at=%s finished_at=%s duration_ms=%s fallback=%s trace_id=%s error_code=%s error_message=%s run=%s",
        str(run.get("question_id") or _derive_question_id_from_module(str(run.get("module_id") or ""))),
        str(run.get("module_id") or ""),
        str(run.get("source") or ""),
        status,
        str(run.get("started_at") or ""),
        str(run.get("finished_at") or ""),
        duration_ms,
        used_fallback,
        _extract_run_trace_id(run),
        error_code,
        error_message,
        log_payload_dump(run),
    )
    _notify_module_run_parent(run)
    return run


def fail_module_run(
    run: dict[str, Any],
    *,
    error_code: str,
    error_message: str,
    status: str = "failed",
    used_fallback: bool = False,
) -> dict[str, Any]:
    logger.error(
        "[NINE QUESTIONS MODULE] FAILED question=%s module=%s source=%s error_code=%s error_message=%s run=%s",
        str(run.get("question_id") or _derive_question_id_from_module(str(run.get("module_id") or ""))),
        str(run.get("module_id") or ""),
        str(run.get("source") or ""),
        error_code,
        error_message,
        log_payload_dump(run),
        stack_info=True,
    )
    return finish_module_run(
        run,
        status=status,
        used_fallback=used_fallback,
        error_code=error_code,
        error_message=error_message,
    )


def append_ordered_module_run(
    module_runs: list[dict[str, Any]],
    run: dict[str, Any],
) -> list[dict[str, Any]]:
    """Append or replace a downstream integration module while preserving phase order."""
    phase_order = {
        "_audit_integration": 0,
        "_memory_integration": 1,
        "_reflection_integration": 2,
        "_learning_integration": 3,
    }

    module_id = str(run.get("module_id") or "")
    retained = [
        item for item in module_runs
        if str(item.get("module_id") or "") != module_id
    ]

    def _phase_rank(value: dict[str, Any]) -> int:
        candidate = str(value.get("module_id") or "")
        for suffix, rank in phase_order.items():
            if candidate.endswith(suffix):
                return rank
        return 999

    insert_at = len(retained)
    run_rank = _phase_rank(run)
    for index, item in enumerate(retained):
        item_rank = _phase_rank(item)
        if item_rank > run_rank:
            insert_at = index
            break
    retained.insert(insert_at, run)
    module_runs[:] = retained
    if isinstance(module_runs, PersistentModuleRuns):
        _RUN_PARENT_REGISTRY[id(run)] = module_runs
    return module_runs


def build_downstream_module_data(
    *,
    question_id: str,
    module_kind: str,
    trace_id: str,
    summary: str,
    payload: Any,
    extra: dict[str, Optional[Any]] = None,
) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "module_kind": module_kind,
        "trace_id": trace_id,
        "summary": summary,
        "payload": json_safe_payload(payload),
        **(extra or {}),
    }


def run_audit_integration(
    context: dict[str, Any],
    *,
    question_id: str,
    module_runs: list[dict[str, Any]],
    summary: str,
    payload: Any,
) -> dict[str, Any]:
    trace_id = str(context.get("trace_id") or f"{question_id}:audit")
    session_id = str(context.get("session_id") or "zentex-default-session")
    turn_id = str(context.get("turn_id") or "nine-question-bootstrap")
    source = f"plugins.nine_questions.{question_id}"
    run = start_module_run(module_runs, f"{question_id}_audit_integration", source=source)
    append_ordered_module_run(module_runs, run)
    run["data"] = build_downstream_module_data(
        question_id=question_id,
        module_kind="audit",
        trace_id=trace_id,
        summary=summary,
        payload=payload,
    )

    audit_service = context.get("audit_service")
    if _is_real_service(audit_service) and callable(getattr(audit_service, "record_nine_question_audit", None)):
        try:
            audit = FlowAudit.new(
                "nine_questions",
                source_module=source,
                question_driver_refs=[question_id],
            )
            result = audit_service.record_nine_question_audit(
                question_id=question_id,
                module_id=run["module_id"],
                summary=summary,
                payload=json_safe_payload(payload),
                trace_id=trace_id,
                session_id=session_id,
                turn_id=turn_id,
                source=source,
                audit=audit,
                status="completed",
            )
            run["data"]["audit_id"] = str((result or {}).get("audit_id") or audit.audit_id)
            finish_module_run(run, status="completed")
        except Exception as exc:
            logger.exception("Audit integration failed for %s", question_id)
            fail_module_run(run, error_code="audit_write_failed", error_message=str(exc))
    elif not run.get("finished_at"):
        finish_module_run(
            run,
            status="missing",
            error_code="audit_service_missing",
            error_message="Audit service is unavailable.",
        )
    persist_question_module_output(
        context,
        question_id=question_id,
        module_id=run["module_id"],
        payload=run.get("data") or {},
        status=str(run.get("status") or "completed"),
        output_kind="integration",
        trace_id=trace_id,
        extra={
            "error_code": str(run.get("error_code") or ""),
            "error_message": str(run.get("error_message") or ""),
        },
    )
    return run


def run_memory_integration(
    context: dict[str, Any],
    *,
    question_id: str,
    module_runs: list[dict[str, Any]],
    title: str,
    summary: str,
    layer: str,
    payload: Any,
    tags: list[Optional[str]] = None,
) -> dict[str, Any]:
    trace_id = str(context.get("trace_id") or f"{question_id}:memory")
    source = f"plugins.nine_questions.{question_id}"
    run = start_module_run(module_runs, f"{question_id}_memory_integration", source=source)
    append_ordered_module_run(module_runs, run)
    run["data"] = build_downstream_module_data(
        question_id=question_id,
        module_kind="memory",
        trace_id=trace_id,
        summary=summary,
        payload=payload,
        extra={"layer": layer},
    )
    memory_service = context.get("memory_service")
    if (not _is_real_service(memory_service)) or not callable(getattr(memory_service, "remember", None)):
        finish_module_run(
            run,
            status="missing",
            error_code="memory_service_missing",
            error_message="Memory service is unavailable.",
        )
    else:
        try:
            memory_content = {
                "trace_id": trace_id,
                "question_id": question_id,
                "module_id": run["module_id"],
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "execution_id": str(uuid4()),
                "payload": json_safe_payload(payload),
            }
            remember_result = memory_service.remember(
                title=title,
                summary=summary,
                content=json.dumps(memory_content, ensure_ascii=False, indent=2),
                layer=layer,
                source=source,
                trace_id=trace_id,
                tags=list(tags or []),
                question_id=question_id,
                module_id=run["module_id"],
            )
            memory_id = str(getattr(remember_result, "memory_id", "") or "")
            if not memory_id:
                raise RuntimeError("Memory service returned no durable memory_id")
            if callable(getattr(memory_service, "get_record", None)):
                written_record = memory_service.get_record(memory_id)
                if written_record is None:
                    raise RuntimeError(f"Memory record not queryable after write: {memory_id}")
                if str(getattr(written_record, "trace_id", "") or "") != trace_id:
                    raise RuntimeError(
                        f"Memory record trace mismatch after write: memory_id={memory_id} "
                        f"expected_trace_id={trace_id} actual_trace_id={getattr(written_record, 'trace_id', '')}"
                    )
            if callable(getattr(memory_service, "query_managed_records", None)):
                trace_rows = memory_service.query_managed_records(trace_id=trace_id, limit=100)
                if not any(str(getattr(item, "memory_id", "") or "") == memory_id for item in trace_rows):
                    raise RuntimeError(
                        f"Memory record not queryable by trace_id after write: memory_id={memory_id} trace_id={trace_id}"
                    )
            run["data"]["memory_id"] = memory_id
            finish_module_run(run, status="completed")
        except Exception as exc:
            logger.exception("Memory integration failed for %s", question_id)
            fail_module_run(run, error_code="memory_write_failed", error_message=str(exc))
    persist_question_module_output(
        context,
        question_id=question_id,
        module_id=run["module_id"],
        payload=run.get("data") or {},
        status=str(run.get("status") or "completed"),
        output_kind="integration",
        trace_id=trace_id,
        extra={
            "error_code": str(run.get("error_code") or ""),
            "error_message": str(run.get("error_message") or ""),
        },
    )
    return run


def run_reflection_integration(
    context: dict[str, Any],
    *,
    question_id: str,
    module_runs: list[dict[str, Any]],
    subject: str,
    summary: str,
    reflection_type: str,
    payload: Any,
) -> dict[str, Any]:
    trace_id = str(context.get("trace_id") or f"{question_id}:reflection")
    source = f"plugins.nine_questions.{question_id}"
    run = start_module_run(module_runs, f"{question_id}_reflection_integration", source=source)
    append_ordered_module_run(module_runs, run)
    run["data"] = build_downstream_module_data(
        question_id=question_id,
        module_kind="reflection",
        trace_id=trace_id,
        summary=summary,
        payload=payload,
        extra={"reflection_type": reflection_type},
    )
    reflection_service = context.get("reflection_service")
    if not _is_real_service(reflection_service):
        finish_module_run(
            run,
            status="missing",
            error_code="reflection_service_missing",
            error_message="Reflection service is unavailable.",
        )
    else:
        try:
            raw_reflection_type = getattr(reflection_type, "value", reflection_type)
            normalized_reflection_type = ReflectionType(str(raw_reflection_type).strip())
        except ValueError:
            fail_module_run(
                run,
                error_code="reflection_type_invalid",
                error_message=f"Invalid reflection type: {reflection_type}",
            )
            persist_question_module_output(
                context,
                question_id=question_id,
                module_id=run["module_id"],
                payload=run.get("data") or {},
                status=str(run.get("status") or "failed"),
                output_kind="integration",
                trace_id=trace_id,
                extra={
                    "error_code": str(run.get("error_code") or ""),
                    "error_message": str(run.get("error_message") or ""),
                },
            )
            return run
        try:
            reflection_context = {
                "question_id": question_id,
                "summary": summary,
                "payload": json_safe_payload(payload),
                "trace_id": trace_id,
                "module_id": run["module_id"],
                "session_id": context.get("session_id"),
            }
            reflection_record = None
            if callable(getattr(reflection_service, "record_nine_question_reflection", None)):
                reflection_record = reflection_service.record_nine_question_reflection(
                    subject=subject,
                    reflection_type=normalized_reflection_type,
                    context=reflection_context,
                    trace_id=trace_id,
                )
            elif callable(getattr(reflection_service, "reflect", None)):
                reflection_record = reflection_service.reflect(
                    subject=subject,
                    context=reflection_context,
                    reflection_type=normalized_reflection_type.value,
                    trace_id=trace_id,
                )
            elif callable(getattr(reflection_service, "generate_reflection", None)):
                reflection_record = reflection_service.generate_reflection(
                    subject=subject,
                    reflection_type=normalized_reflection_type,
                    context=reflection_context,
                    trace_id=trace_id,
                )
            else:
                finish_module_run(
                    run,
                    status="missing",
                    error_code="reflection_entrypoint_missing",
                    error_message="Reflection service has no supported entrypoint.",
                )
                persist_question_module_output(
                    context,
                    question_id=question_id,
                    module_id=run["module_id"],
                    payload=run.get("data") or {},
                    status=str(run.get("status") or "missing"),
                    output_kind="integration",
                    trace_id=trace_id,
                    extra={
                        "error_code": str(run.get("error_code") or ""),
                        "error_message": str(run.get("error_message") or ""),
                    },
                )
                return run
            reflection_id = str(getattr(reflection_record, "reflection_id", "") or "")
            if not reflection_id:
                raise RuntimeError("Reflection service returned no durable reflection_id")
            run["data"]["reflection_id"] = reflection_id
            finish_module_run(run, status="completed")
        except Exception as exc:
            logger.exception("Reflection integration failed for %s", question_id)
            fail_module_run(run, error_code="reflection_write_failed", error_message=str(exc))
    persist_question_module_output(
        context,
        question_id=question_id,
        module_id=run["module_id"],
        payload=run.get("data") or {},
        status=str(run.get("status") or "completed"),
        output_kind="integration",
        trace_id=trace_id,
        extra={
            "error_code": str(run.get("error_code") or ""),
            "error_message": str(run.get("error_message") or ""),
        },
    )
    return run


def run_learning_integration(
    context: dict[str, Any],
    *,
    question_id: str,
    module_runs: list[dict[str, Any]],
    learning_kind: str,
    summary: str,
    payload: Any,
) -> dict[str, Any]:
    trace_id = str(context.get("trace_id") or f"{question_id}:learning")
    source = f"plugins.nine_questions.{question_id}"
    run = start_module_run(module_runs, f"{question_id}_learning_integration", source=source)
    append_ordered_module_run(module_runs, run)
    run["data"] = build_downstream_module_data(
        question_id=question_id,
        module_kind="learning",
        trace_id=trace_id,
        summary=summary,
        payload=payload,
        extra={"learning_kind": learning_kind},
    )
    learning_service = context.get("learning_service")
    if (not _is_real_service(learning_service)) or not callable(getattr(learning_service, "record_nine_question_learning", None)):
        finish_module_run(
            run,
            status="missing",
            error_code="learning_service_missing",
            error_message="Learning service is unavailable.",
        )
    else:
        try:
            audit = FlowAudit.new(
                "learning",
                source_module=source,
                question_driver_refs=[question_id],
            )
            learning_record = learning_service.record_nine_question_learning(
                question_id=question_id,
                learning_kind=learning_kind,
                detail={
                    "summary": summary,
                    "payload": json_safe_payload(payload),
                    "trace_id": trace_id,
                    "module_id": run["module_id"],
                },
                trace_id=trace_id,
                store=None,
                audit=audit,
            )
            learning_trace_id = str(getattr(learning_record, "trace_id", "") or (learning_record or {}).get("trace_id") or "")
            if not learning_trace_id:
                raise RuntimeError("Learning service returned no durable trace_id")
            run["data"]["learning_trace_id"] = learning_trace_id
            finish_module_run(run, status="completed")
        except Exception as exc:
            logger.exception("Learning integration failed for %s", question_id)
            fail_module_run(run, error_code="learning_write_failed", error_message=str(exc))
    persist_question_module_output(
        context,
        question_id=question_id,
        module_id=run["module_id"],
        payload=run.get("data") or {},
        status=str(run.get("status") or "completed"),
        output_kind="integration",
        trace_id=trace_id,
        extra={
            "error_code": str(run.get("error_code") or ""),
            "error_message": str(run.get("error_message") or ""),
        },
    )
    return run


def record_plugin_attempt(
    plugin_runs: list[dict[str, Any]],
    *,
    plugin_id: str,
    feature_code: str,
    expected: bool = True,
    attempted: bool = True,
    input_summary: dict[str, Optional[Any]] = None,
) -> dict[str, Any]:
    run = {
        "plugin_id": plugin_id,
        "feature_code": feature_code,
        "expected": expected,
        "attempted": attempted,
        "status": "running" if attempted else "missing",
        "error_code": "",
        "error_message": "",
        "duration_ms": 0,
        "input_summary": input_summary or {},
        "output_summary": {},
        "_started_perf": perf_counter(),
    }
    plugin_runs.append(run)
    logger.info(
        "[NINE QUESTIONS PLUGIN RUN] START plugin=%s feature=%s expected=%s attempted=%s input=%s",
        plugin_id,
        feature_code,
        expected,
        attempted,
        log_payload_dump(run["input_summary"]),
    )
    return run


def record_plugin_result(
    run: dict[str, Any],
    *,
    status: str,
    error_code: str = "",
    error_message: str = "",
    output_summary: dict[str, Optional[Any]] = None,
) -> dict[str, Any]:
    started = run.pop("_started_perf", None)
    duration_ms = 0
    if isinstance(started, (int, float)):
        duration_ms = int((perf_counter() - started) * 1000)
    run["status"] = status
    run["duration_ms"] = duration_ms
    run["error_code"] = error_code
    run["error_message"] = error_message
    run["output_summary"] = output_summary or {}
    log_fn = logger.info if status in {"completed", "done", "success"} and not error_code else logger.error
    log_fn(
        "[NINE QUESTIONS PLUGIN RUN] END plugin=%s feature=%s status=%s duration_ms=%s error_code=%s error_message=%s input=%s output=%s",
        str(run.get("plugin_id") or ""),
        str(run.get("feature_code") or ""),
        status,
        duration_ms,
        error_code,
        error_message,
        log_payload_dump(run.get("input_summary") or {}),
        log_payload_dump(run.get("output_summary") or {}),
    )
    return run


def question_authenticity_judgment(
    *,
    module_runs: list[dict[str, Any]],
    upstream_dependencies: list[dict[str, Any]],
    used_fallback: bool,
    diagnosis_code: str,
    diagnosis_message: str,
    required_modules: list[Optional[str]] = None,
) -> dict[str, Any]:
    required_module_ids = set(required_modules or [])
    module_by_id = {str(item.get("module_id")): item for item in module_runs}
    module_statuses = [str(item.get("status") or "missing") for item in module_runs]
    dep_statuses = [str(item.get("status") or "missing") for item in upstream_dependencies if item.get("required")]

    if any(status == "failed" for status in dep_statuses):
        authenticity_status = "partial_failed"
    elif any(status == "missing" for status in dep_statuses):
        authenticity_status = "degraded"
    elif required_module_ids and any(
        str(module_by_id.get(module_id, {}).get("status") or "missing") in {"failed", "missing"}
        for module_id in required_module_ids
    ):
        authenticity_status = "degraded"
    elif any(status == "failed" for status in module_statuses):
        authenticity_status = "partial_failed"
    elif used_fallback or any(status in {"degraded", "missing"} for status in module_statuses):
        authenticity_status = "degraded"
    else:
        authenticity_status = "completed"

    upstream_degraded = any(status in {"degraded", "missing", "failed"} for status in dep_statuses)
    return {
        "authenticity_status": authenticity_status,
        "diagnosis_code": diagnosis_code,
        "diagnosis_message": diagnosis_message,
        "used_fallback": used_fallback,
        "upstream_degraded": upstream_degraded,
        "module_runs": module_runs,
        "upstream_dependencies": upstream_dependencies,
    }


def build_recovery_action(
    action_id: str,
    *,
    label: str,
    kind: str,
    executable: bool,
    scope: str,
    target: str,
    reason: str,
    path: Optional[str] = None,
    method: str = "POST",
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "label": label,
        "kind": kind,
        "executable": executable,
        "scope": scope,
        "target": target,
        "reason": reason,
        "path": path or "",
        "method": method,
    }


def build_recovery_plan(
    *,
    question_id: str,
    retriable: bool,
    rollback_available: bool,
    partial_retry_available: bool,
    partial_replace_available: bool,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "retriable": retriable,
        "rollback_available": rollback_available,
        "partial_retry_available": partial_retry_available,
        "partial_replace_available": partial_replace_available,
        "actions": actions,
    }


def humanize_identifier(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "未知项"
    normalized = text.replace("_", " ").replace("-", " ").replace(":", " ").replace(".", " ")
    return " ".join(chunk.capitalize() for chunk in normalized.split())


def _humanize_key(key: object) -> str:
    text = str(key or "").strip()
    if not text:
        return "未命名字段"
    return text.replace("_", " ").replace("-", " ").strip()


def render_human_readable_block(
    value: Any,
    *,
    heading: Optional[str] = None,
    indent: int = 0,
    max_items: int = 12,
) -> str:
    prefix = "  " * indent
    lines: list[str] = []
    if heading:
        lines.append(f"{prefix}{heading}")

    if value is None:
        lines.append(f"{prefix}- 无")
        return "\n".join(lines)

    if isinstance(value, (str, int, float, bool)):
        lines.append(f"{prefix}- {value}")
        return "\n".join(lines)

    if isinstance(value, dict):
        if not value:
            lines.append(f"{prefix}- 无")
            return "\n".join(lines)
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                lines.append(f"{prefix}- 其余字段已省略")
                break
            label = _humanize_key(key)
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}- {label}:")
                lines.append(render_human_readable_block(item, indent=indent + 1, max_items=max_items))
            else:
                lines.append(f"{prefix}- {label}: {item}")
        return "\n".join(lines)

    if isinstance(value, list):
        if not value:
            lines.append(f"{prefix}- 无")
            return "\n".join(lines)
        for index, item in enumerate(value):
            if index >= max_items:
                lines.append(f"{prefix}- 其余条目已省略")
                break
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}- 条目 {index + 1}:")
                lines.append(render_human_readable_block(item, indent=indent + 1, max_items=max_items))
            else:
                lines.append(f"{prefix}- {item}")
        return "\n".join(lines)

    lines.append(f"{prefix}- {str(value)}")
    return "\n".join(lines)


def render_plugin_catalog(plugin_ids: list[str], *, heading: str) -> str:
    rows = [
        {
            "名称": humanize_identifier(item),
            "内部标识": item,
            "功能说明": f"{humanize_identifier(item)} 提供与 {item} 对应的运行能力。",
        }
        for item in plugin_ids
    ]
    return render_human_readable_block(rows, heading=heading)


def render_q2_asset_inventory(context: dict[str, Any]) -> str:
    inventory = context.get("q2_humanized_asset_inventory") or context.get("q2_unified_asset_inventory") or {}
    return render_human_readable_block(inventory, heading="Q2 资产清单")


def render_q4_boundary(context: dict[str, Any]) -> str:
    return render_human_readable_block(
        context.get("q4_capability_boundary_profile") or context.get("q4_inference_result") or {},
        heading="Q4 能力边界",
    )


def render_q5_boundary(context: dict[str, Any]) -> str:
    return render_human_readable_block(
        context.get("q5_permission_boundary")
        or context.get("q5_authorization_boundary_profile")
        or context.get("q5_inference_result")
        or {},
        heading="Q5 授权边界",
    )


def render_q6_redlines(context: dict[str, Any]) -> str:
    return render_human_readable_block(
        context.get("q6_forbidden_zone_profile") or {},
        heading="Q6 红线禁区",
    )


def render_identity_kernel(context: dict[str, Any]) -> str:
    return render_human_readable_block(
        context.get("identity_kernel") or context.get("identity_kernel_snapshot") or {},
        heading="身份内核快照",
    )


def render_nine_questions_snapshot(nine_questions: Any) -> str:
    return render_human_readable_block(nine_questions or {}, heading="Q1-Q8 认知快照")


def render_task_state(task_state: Any) -> str:
    return render_human_readable_block(task_state or [], heading="当前任务状态")


def record_model_invoked(
    store: AuditEventStore,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    source: str,
    payload: Dict[str, Any],
):
    logger.info(
        "[NINE QUESTIONS MODEL INVOKED] source=%s trace=%s session=%s turn=%s payload=%s",
        source,
        trace_id,
        session_id,
        turn_id,
        log_payload_dump(payload),
    )
    store.write_entry(
        session_id=session_id,
        turn_id=turn_id,
        entry_type=AuditEventType.MODEL_PROVIDER_INVOKED,
        timestamp=datetime.now(timezone.utc),
        source=source,
        trace_id=trace_id,
        payload=payload,
    )


def record_model_completed(
    store: AuditEventStore,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    source: str,
    payload: Dict[str, Any],
):
    logger.info(
        "[NINE QUESTIONS MODEL COMPLETED] source=%s trace=%s session=%s turn=%s payload=%s",
        source,
        trace_id,
        session_id,
        turn_id,
        log_payload_dump(payload),
    )
    store.write_entry(
        session_id=session_id,
        turn_id=turn_id,
        entry_type=AuditEventType.MODEL_PROVIDER_COMPLETED,
        timestamp=datetime.now(timezone.utc),
        source=source,
        trace_id=trace_id,
        payload=payload,
    )


def record_model_failed(
    store: AuditEventStore,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    source: str,
    payload: Dict[str, Any],
):
    logger.error(
        "[NINE QUESTIONS MODEL FAILED] source=%s trace=%s session=%s turn=%s payload=%s",
        source,
        trace_id,
        session_id,
        turn_id,
        log_payload_dump(payload),
    )
    store.write_entry(
        session_id=session_id,
        turn_id=turn_id,
        entry_type=AuditEventType.MODEL_PROVIDER_FAILED,
        timestamp=datetime.now(timezone.utc),
        source=source,
        trace_id=trace_id,
        payload=payload,
    )


def build_nine_question_partial_failure(
    *,
    context: dict[str, Any],
    tool_id: str,
    question_id: str,
    question_ref: str,
    error_code: str,
    error_message: str,
    diagnosis_key: str,
    module_runs: List[dict[str, Any]],
    plugin_runs: List[dict[str, Any]] | None = None,
    upstream_dependencies: List[dict[str, Any]] | None = None,
    context_updates: dict[str, Any],
    required_modules: List[str] | None = None,
    partial_replace_available: bool = False,
    extra_actions: List[dict[str, Any]] | None = None,
) -> Any:  # Returns CognitiveToolResult
    """
    Standardized partial failure builder for Q1-Q9 plugins.
    Complies with Pure Plugin Group Container policy by residing in shared location.
    """
    from zentex.common.cognitive_result import CognitiveToolResult
    
    diagnosis = question_authenticity_judgment(
        module_runs=module_runs,
        upstream_dependencies=upstream_dependencies or [],
        used_fallback=True,
        diagnosis_code=error_code,
        diagnosis_message=error_message,
        required_modules=required_modules or [],
    )
    diagnosis["plugin_runs"] = plugin_runs or []
    diagnosis["recovery_plan"] = build_recovery_plan(
        question_id=question_id,
        retriable=True,
        rollback_available=True,
        partial_retry_available=True,
        partial_replace_available=partial_replace_available,
        actions=[
            build_recovery_action(
                f"{question_id}-rerun-question",
                label=f"重跑 {question_id.upper()}",
                kind="retry",
                executable=True,
                scope="question",
                target=question_id,
                reason=f"重新执行 {question_id.upper()} 并保留已完成模块结果。",
                path=f"/api/web/nine-questions/{question_id}/run",
            ),
            build_recovery_action(
                f"{question_id}-rollback-previous-success",
                label="回滚到上一份成功快照",
                kind="rollback",
                executable=True,
                scope="record",
                target=question_id,
                reason="当前失败或降级结果不应破坏上一份正确结果。",
                path=f"/api/web/nine-questions/{question_id}/rollback",
            ),
            *(extra_actions or []),
        ],
    )
    
    safe_context = dict(context)
    run_audit_integration(
        safe_context,
        question_id=question_id,
        module_runs=module_runs,
        summary=f"{question_id.upper()} partial failure audit: {error_message}",
        payload=context_updates,
    )
    run_memory_integration(
        safe_context,
        question_id=question_id,
        module_runs=module_runs,
        title=f"{question_id.upper()} Partial Failure",
        summary=f"{question_id.upper()} encountered a partial failure: {error_message}",
        layer="episodic",
        payload=context_updates,
        tags=["nine-questions", question_id, "partial-failure", "anomaly"],
    )
    run_reflection_integration(
        safe_context,
        question_id=question_id,
        module_runs=module_runs,
        subject=f"{question_id.upper()} partial failure",
        summary=f"{question_id.upper()} failure reflection recorded.",
        reflection_type=ReflectionType.PROCESS_REFLECTION,
        payload=context_updates,
    )
    run_learning_integration(
        safe_context,
        question_id=question_id,
        module_runs=module_runs,
        learning_kind="anomaly_detection",
        summary=f"{question_id.upper()} partial failure learning event.",
        payload=context_updates,
    )

    return CognitiveToolResult(
        tool_id=tool_id,
        summary=f"{question_id.upper()} partial failure: {error_message}",
        context_updates={
            "nine_questions": {question_ref: f"{question_id.upper()} partial failure"},
            diagnosis_key: diagnosis,
            **context_updates,
        },
        confidence=0.0,
        status="partial_failed",
        error=error_message,
        error_code=error_code,
        error_message=error_message,
    )

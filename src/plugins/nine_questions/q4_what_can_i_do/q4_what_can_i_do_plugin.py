from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from plugins.shared.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q4
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q4_what_can_i_do.models import Q4WhatCanIDoInference
from plugins.nine_questions.q4_what_can_i_do.llm_prompt import build_q4_llm_request


QUESTION_REF = "我能做什么"


from zentex.common.nine_questions_shared import (
    build_caller_context,
    build_model_context,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_plugin_catalog,
    render_q3_asset_inventory,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals

logger = logging.getLogger(__name__)


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _derive_permission_profile(snapshot: dict[str, Any], q3_inventory: dict[str, Any]) -> dict[str, Any]:
    permissions = snapshot.get("permissions")
    permissions = permissions if isinstance(permissions, dict) else {}
    workspace_permissions = snapshot.get("workspaces_and_permissions")
    workspace_permissions = workspace_permissions if isinstance(workspace_permissions, dict) else {}
    q3_permissions = q3_inventory.get("permissions")
    q3_permissions = q3_permissions if isinstance(q3_permissions, dict) else {}

    mode = _normalize_text(q3_permissions.get("mode") or permissions.get("mode")) or "unknown"
    tenant_permissions = _coerce_string_list(
        workspace_permissions.get("tenant_permissions") or permissions.get("tenant_scope")
    )
    execution_tokens = _coerce_string_list(
        workspace_permissions.get("execution_tokens")
        or permissions.get("execution_tokens")
        or permissions.get("brain_scope")
    )
    workspace_zones = _coerce_string_list(
        (q3_inventory.get("accessible_workspace_zones") if isinstance(q3_inventory, dict) else None)
        or workspace_permissions.get("available_workspaces")
        or permissions.get("accessible_workspace_zones")
    )
    return {
        "mode": mode,
        "tenant_permissions": tenant_permissions,
        "execution_tokens": execution_tokens,
        "accessible_workspace_zones": workspace_zones,
        "is_read_only": mode == "read_only" or not execution_tokens,
    }


def _normalize_functional_capabilities(functional_capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in functional_capabilities:
        if not isinstance(item, dict) or item.get("status") != "done":
            continue
        normalized.append(
            {
                "plugin_id": _normalize_text(item.get("plugin_id")),
                "status": _normalize_text(item.get("status")) or "done",
                "result": item.get("result") if isinstance(item.get("result"), dict) else {},
            }
        )
    return normalized


def _derive_capability_baseline(
    snapshot: dict[str, Any],
    q3_inventory: dict[str, Any],
    exec_domains: list[str],
    permission_profile: dict[str, Any],
    functional_capabilities: list[dict[str, Any]],
) -> dict[str, list[str]]:
    resource_evaluation = snapshot.get("q3_resource_evaluation")
    resource_evaluation = resource_evaluation if isinstance(resource_evaluation, dict) else {}
    cognitive_tools = _coerce_string_list(q3_inventory.get("available_cognitive_tools"))
    connected_agents = q3_inventory.get("connected_agents")
    connected_agents = connected_agents if isinstance(connected_agents, list) else []
    workspace_zones = _coerce_string_list(permission_profile.get("accessible_workspace_zones"))
    strategy_patches = _coerce_string_list(q3_inventory.get("activated_strategy_patches"))

    capability_upper_limits: list[str] = []
    actionable_space: list[str] = []
    executable_strategies: list[str] = []

    if cognitive_tools:
        capability_upper_limits.append("analyze available workspace and runtime state")
        actionable_space.append("inspect workspace summaries")
        executable_strategies.append("static analysis")

    if workspace_zones:
        capability_upper_limits.append("operate within accessible workspace zones")
        actionable_space.append("inspect accessible workspace zones")

    if exec_domains:
        capability_upper_limits.append("invoke enabled execution domains")
        actionable_space.append("invoke enabled tool endpoints")
        executable_strategies.append("tool-assisted execution")
    else:
        executable_strategies.append("analysis-only planning")

    if connected_agents:
        capability_upper_limits.append("delegate work to connected agents")
        actionable_space.append("coordinate connected agents")
        executable_strategies.append("delegated collaboration")

    if strategy_patches:
        capability_upper_limits.append("apply active strategy patches")
        executable_strategies.append("strategy-patch-guided execution")

    for item in functional_capabilities:
        plugin_id = _normalize_text(item.get("plugin_id"))
        if plugin_id:
            capability_upper_limits.append(f"use functional capability {plugin_id}")

    resource_status = _normalize_text(resource_evaluation.get("resource_status"))
    if resource_status == "critically_lacking":
        executable_strategies.append("resource recovery before execution")
    elif resource_status == "degraded":
        executable_strategies.append("conservative degraded-mode execution")

    if permission_profile.get("is_read_only"):
        capability_upper_limits.append("perform read-only inspection")
        actionable_space = [
            item
            for item in actionable_space
            if not _contains_write_like_action(item)
        ]
        executable_strategies = [
            item
            for item in executable_strategies
            if not _contains_write_like_action(item)
        ]
        actionable_space.append("read logs and inspect snapshots")
        executable_strategies.append("request human confirmation before any write action")

    capability_upper_limits = list(dict.fromkeys(item for item in capability_upper_limits if _normalize_text(item)))
    actionable_space = list(dict.fromkeys(item for item in actionable_space if _normalize_text(item)))
    executable_strategies = list(dict.fromkeys(item for item in executable_strategies if _normalize_text(item)))

    return {
        "capability_upper_limits": capability_upper_limits,
        "actionable_space": actionable_space,
        "executable_strategies": executable_strategies,
    }


def _merge_with_capability_baseline(
    inferred: list[str],
    baseline: list[str],
    *,
    read_only: bool,
) -> list[str]:
    merged = list(dict.fromkeys(_coerce_string_list(inferred) + _coerce_string_list(baseline)))
    if read_only:
        merged = [item for item in merged if not _contains_write_like_action(item)]
    return merged


class Q4WhatCanIDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q4
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q4"
    display_name: str = "Q4: What can I do?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Q4: 我能做什么 (capability boundary profile)

    Anti-hallucination enforcement:
    - LLM must operate strictly within Q3 asset inventory + permissions.
    - Post-validate actionable_space does not claim write actions when the input states read-only / no execution tools.
    - Violations are fail-closed (raise), never silently corrected.
    """

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        snapshot = context.get("context_snapshot", {}) or {}
        q3_inventory = snapshot.get("q3_unified_asset_inventory", {}) or {}
        if not isinstance(q3_inventory, dict):
            q3_inventory = {}
        exec_domains = list(q3_inventory.get("available_execution_tools", []) or [])
        plugin_service = context.get("plugin_service")
        functional_capabilities: list[dict[str, Any]] = []
        if plugin_service is not None:
            functional_capabilities = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters={"context": dict(context)},
                trace_id=str(context.get("trace_id") or "q4"),
                originator_id=str(context.get("session_id") or "unknown-session"),
                caller_plugin_id=self.plugin_id,
            )
            exec_domains.extend(
                str(item.get("plugin_id") or "")
                for item in functional_capabilities
                if item.get("status") == "done"
            )
            exec_domains = list(dict.fromkeys(exec_domains))
        normalized_functional_capabilities = _normalize_functional_capabilities(functional_capabilities)
        permission_profile = _derive_permission_profile(snapshot, q3_inventory)
        capability_baseline = _derive_capability_baseline(
            snapshot,
            q3_inventory,
            exec_domains,
            permission_profile,
            normalized_functional_capabilities,
        )

        execution_domain_catalog = render_plugin_catalog(exec_domains, heading="执行工具目录")
        asset_inventory_summary = render_q3_asset_inventory(snapshot)
        llm_request = build_q4_llm_request(
            capability_baseline=capability_baseline,
            permission_profile=permission_profile,
            execution_domain_catalog=execution_domain_catalog,
            asset_inventory_summary=asset_inventory_summary,
            snapshot_version=snapshot.get("snapshot_version"),
            q1_scene_model=snapshot.get("q1_scene_model"),
            q1_uncertainty_profile=snapshot.get("q1_uncertainty_profile"),
            q2_role_profile=snapshot.get("q2_role_profile"),
            q2_mission_boundary=snapshot.get("q2_mission_boundary"),
            q3_unified_asset_inventory=q3_inventory,
            q3_resource_evaluation=snapshot.get("q3_resource_evaluation"),
            q3_humanized_asset_inventory=snapshot.get("q3_humanized_asset_inventory"),
            q3_workspaces_and_permissions=snapshot.get("workspaces_and_permissions"),
            q3_memory_and_strategy=snapshot.get("memory_and_strategy"),
            active_execution_domains=exec_domains,
            functional_capabilities=normalized_functional_capabilities,
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        trace_id = str(context.get("trace_id") or f"q4-what-can-i-do:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q4_what_can_i_do")

        caller_context = build_caller_context(
            source_module="q4_what_can_i_do_plugin",
            invocation_phase="nine_question_q4_what_can_i_do",
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
            source="plugins.nine_questions.q4_what_can_i_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "context": model_context,
            },
        )

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
                source="plugins.nine_questions.q4_what_can_i_do",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                    "snapshot_version": snapshot.get("snapshot_version"),
                },
            )
            # Fail-Closed: Strictly raise fatal exception.
            raise

        inference = Q4WhatCanIDoInference.model_validate(raw)
        profile = inference.capability_boundary_profile
        read_only = bool(permission_profile.get("is_read_only"))
        profile.capability_upper_limits = _merge_with_capability_baseline(
            profile.capability_upper_limits,
            capability_baseline.get("capability_upper_limits", []),
            read_only=read_only,
        )
        profile.actionable_space = _merge_with_capability_baseline(
            profile.actionable_space,
            capability_baseline.get("actionable_space", []),
            read_only=read_only,
        )
        profile.executable_strategies = _merge_with_capability_baseline(
            profile.executable_strategies,
            capability_baseline.get("executable_strategies", []),
            read_only=read_only,
        )

        # Guardrail validation (anti-hallucination): if there is no execution tool or permissions are read-only,
        # the model must not claim write-like actions.
        execution_tools = q3_inventory.get("available_execution_tools") or []
        if not execution_tools:
            read_only = True
        if read_only:
            offending = [a for a in profile.actionable_space if isinstance(a, str) and _contains_write_like_action(a)]
            if offending:
                raise RuntimeError(
                    "Anti-hallucination violation: actionable_space contains write-like actions while read-only/no execution tools: "
                    + "; ".join(offending[:5])
                )

        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q4_what_can_i_do",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                    "result": inference.model_dump(mode="json"),
                    "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                    "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                    "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                },
            )

        summary = f"actionable={len(profile.actionable_space)}; strategies={len(profile.executable_strategies)}"
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "capability_boundary_profile",
                    **profile.model_dump(mode="json"),
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "q4_capability_boundary_profile": profile.model_dump(mode="json"),
                "q4_snapshot_version": snapshot.get("snapshot_version"),
                "q4_active_execution_domains": exec_domains,
                "q4_permission_profile": permission_profile,
                "q4_capability_baseline": capability_baseline,
                "q4_functional_capabilities": normalized_functional_capabilities,
                "q4_capability_evidence": {
                    "q1_scene_model": snapshot.get("q1_scene_model"),
                    "q2_role_profile": snapshot.get("q2_role_profile"),
                    "q2_mission_boundary": snapshot.get("q2_mission_boundary"),
                    "q3_unified_asset_inventory": q3_inventory,
                    "q3_resource_evaluation": snapshot.get("q3_resource_evaluation"),
                },
            },
            confidence=0.7,
        )


def _contains_write_like_action(action: str) -> bool:
    lowered = action.lower()
    if re.search(r"\brm\b", lowered):
        return True
    write_markers = (
        "write",
        "delete",
        "remove",
        "modify",
        "edit",
        "overwrite",
        "deploy",
        "apply",
        "chmod",
        "chown",
        "kill",
        "shutdown",
        "format",
        "drop",
    )
    return any(re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in write_markers)


def build_q4_what_can_i_do_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q4,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q4WhatCanIDoPlugin:
    return Q4WhatCanIDoPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q4",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )

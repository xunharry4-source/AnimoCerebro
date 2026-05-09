from __future__ import annotations

from typing import Any

from plugins.nine_questions.q2_asset_inventory.service import (
    load_external_public_output as load_q2_external,
)
from plugins.nine_questions.q4_what_can_i_do.service import (
    load_external_public_output as load_q4_external,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.forbidden_items import (
    query_nine_question_forbidden_items,
)
from zentex.safety.cloud_auditor import CloudAuditorConfig, CloudBoundaryDefinition


EXTERNAL_REDLINES = {
    "data_destruction",
    "privilege_escalation",
    "security_downgrade",
    "resource_exhaustion",
    "external_leakage",
}


def query_q5_external_lane_data(context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Collect the External Lane data Q5 needs before auditing external objectives."""
    payload = context if isinstance(context, dict) else {}
    session_id = payload.get("session_id", "nq-baseline")
    db_path = payload.get("nine_question_state_db_path")
    
    # 强制通过上游提供的方法获取，上游会对数据进行脱敏/清洗/格式化处理
    try:
        q2_llm_output = load_q2_external(session_id=session_id, db_path=db_path)
    except Exception:
        q2_llm_output = {}
        
    try:
        q4_llm_output = load_q4_external(session_id=session_id, db_path=db_path)
    except Exception:
        q4_llm_output = {}

    forbidden_items = query_nine_question_forbidden_items(payload)
    execution_rights = _query_execution_rights_matrix(payload, q2_llm_output=q2_llm_output, q4_llm_output=q4_llm_output)
    safety_redlines = _query_safety_gate_external_redlines(forbidden_items)
    cloud_audit = _query_cloud_audit_policies(payload)
    q4_candidates = _query_q4_external_objective_candidates(q4_llm_output=q4_llm_output)
    return {
        "Execution_Rights_Matrix": execution_rights,
        "SafetyGate_Redlines_External": safety_redlines,
        "CloudAudit_Policies": cloud_audit,
        "Q4_ExternalObjectiveCandidates": q4_candidates,
        "consumption_sequence": {
            "blind_boundary_inputs": [
                "Execution_Rights_Matrix",
                "SafetyGate_Redlines_External",
                "CloudAudit_Policies",
            ],
            "collision_test_inputs": ["Q4_ExternalObjectiveCandidates"],
            "release_contract": "allowed_objectives_with_conditions",
        },
    }

def _query_execution_rights_matrix(context: dict[str, Any], *, q2_llm_output: dict[str, Any], q4_llm_output: dict[str, Any]) -> dict[str, Any]:
    q4_permission = _dict(q4_llm_output.get("permission_profile"))
    workspace_permission = _dict(
        context.get("workspaces_and_permissions")
        or context.get("workspace_permission_inventory")
        or context.get("workspace_permission")
    )
    q2_external_inventory = _dict(q2_llm_output)
    return {
        "filesystem": {
            "accessible_workspace_zones": _list(q4_permission.get("accessible_workspace_zones")),
            "workspace_permission": workspace_permission,
            "read_only": bool(q4_permission.get("is_read_only")) if "is_read_only" in q4_permission else None,
        },
        "browser": {
            "browser_permissions": _list(q4_permission.get("browser_permissions")),
            "execution_tokens": _list(q4_permission.get("execution_tokens")),
        },
        "external_api": {
            "tenant_permissions": _list(q4_permission.get("tenant_permissions")),
            "allowed_delegation_targets": _list(context.get("allowed_delegation_targets")),
        },
        "resource_calls": {
            "available_external_assets": q2_external_inventory,
            "permission_boundaries": _list(q2_external_inventory.get("permission_boundaries")),
        },
        "source": [
            "database.q4_snapshots.permission_profile",
            "database.q2_snapshots.external_asset_inventory",
        ],
    }


def _query_safety_gate_external_redlines(forbidden_items: dict[str, Any]) -> dict[str, Any]:
    redlines = [
        item
        for item in forbidden_items.get("system_safety_redline_actions", [])
        if _dict(item).get("category") in EXTERNAL_REDLINES
    ]
    return {
        "redlines": redlines,
        "configured_forbidden_actions": list(forbidden_items.get("user_forbidden_actions") or []),
        "combined_forbidden_actions": list(forbidden_items.get("combined_forbidden_actions") or []),
        "external_redline_categories": sorted(EXTERNAL_REDLINES),
        "source": {
            "system_safety_redlines": forbidden_items.get("sources", {}).get("system_safety_redlines"),
            "configured_forbidden_actions": forbidden_items.get("sources", {}).get("user_settings") or {},
        },
    }


def _query_cloud_audit_policies(context: dict[str, Any]) -> dict[str, Any]:
    raw_config = _dict(context.get("cloud_audit_config"))
    config = CloudAuditorConfig(
        endpoint=str(raw_config.get("endpoint") or CloudAuditorConfig().endpoint),
        api_key=str(raw_config.get("api_key") or ""),
        api_secret=str(raw_config.get("api_secret") or ""),
        timeout_seconds=float(raw_config.get("timeout_seconds") or CloudAuditorConfig().timeout_seconds),
        enable_degradation=bool(raw_config.get("enable_degradation", CloudAuditorConfig().enable_degradation)),
        degraded_policy_version=str(
            raw_config.get("degraded_policy_version") or CloudAuditorConfig().degraded_policy_version
        ),
    )
    boundary = CloudBoundaryDefinition()
    return {
        "high_risk_requires_cloud_audit": boundary.high_risk_requires_cloud_audit,
        "missing_credentials_fail_closed": boundary.missing_credentials_fail_closed,
        "invalid_response_signature_rejected": boundary.invalid_response_signature_rejected,
        "configured": bool(config.api_key and config.api_secret),
        "endpoint": config.endpoint,
        "api_key_configured": bool(config.api_key),
        "api_secret_configured": bool(config.api_secret),
        "timeout_seconds": config.timeout_seconds,
        "enable_degradation": config.enable_degradation,
        "degraded_policy_version": config.degraded_policy_version,
        "sensitive_action_thresholds": [
            "high_or_critical_risk_actions",
            "credential_access",
            "sensitive_data_egress",
            "cross_domain_external_side_effects",
        ],
        "source": "zentex.safety.cloud_auditor.CloudAuditorConfig + CloudBoundaryDefinition",
    }


def _query_q4_external_objective_candidates(*, q4_llm_output: dict[str, Any]) -> dict[str, Any]:
    # 严格遵循架构原则：仅允许从上游 Loader 获取数据，禁止从 context 或 fallback 获取
    # Q4 Loader 返回的是 ExternalObjectiveCandidateSet 模型字典
    if q4_llm_output and q4_llm_output.get("type") == "ExternalObjectiveCandidateSet":
        candidates = q4_llm_output
        source = "database.q4_snapshots.external_objective_candidates"
    else:
        candidates = {"type": "ExternalObjectiveCandidateSet", "objective_candidates": []}
        source = "database.q4_snapshots.missing"
        
    return {"candidate_set": _jsonable(candidates), "source": source}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    if value in (None, ""):
        return []
    return [value]


def _nested_get(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)

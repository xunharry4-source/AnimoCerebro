from __future__ import annotations

import importlib.util
from typing import Any

from plugins.nine_questions.q5_what_am_i_allowed_to_do.forbidden_items import (
    query_nine_question_forbidden_items,
)
from zentex.kernel.self_refactor import PROTECTED_PATH_PARTS


PROTECTED_INTERNAL_MODULES: tuple[tuple[str, str], ...] = (
    ("G12 SafetyGate", "zentex.kernel.safety_gate"),
    ("G21 SupervisionService", "zentex.supervision.service"),
    ("AuditTraceStore", "zentex.audit.trace_store"),
    ("CausalAuditChain", "zentex.audit.causal_chain"),
    ("IdentityKernel", "zentex.kernel.identity_kernel"),
)


def query_q5_internal_lane_data(context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Collect the Internal Lane data Q5 needs before auditing internal objectives."""
    payload = context if isinstance(context, dict) else {}
    forbidden_items = query_nine_question_forbidden_items(payload)
    identity = _query_identity_kernel_constraints(payload, forbidden_items)
    memory_rules = _query_memory_integrity_and_continuity_rules(payload)
    protected_modules = _query_protected_modules_state(payload)
    q4_candidates = _query_q4_internal_objective_candidates(payload)
    return {
        "IdentityKernel_NonBypassableConstraints": identity,
        "MemoryIntegrity_And_ContinuityRules": memory_rules,
        "ProtectedModules_State": protected_modules,
        "Q4_InternalObjectiveCandidates": q4_candidates,
        "consumption_sequence": {
            "blind_boundary_inputs": [
                "IdentityKernel_NonBypassableConstraints",
                "MemoryIntegrity_And_ContinuityRules",
                "ProtectedModules_State",
            ],
            "collision_test_inputs": ["Q4_InternalObjectiveCandidates"],
            "release_contract": "allowed_objectives_with_conditions",
        },
    }


def _query_identity_kernel_constraints(
    context: dict[str, Any],
    forbidden_items: dict[str, Any],
) -> dict[str, Any]:
    snapshot = (
        _dict(context.get("identity_kernel_snapshot"))
        or _dict(context.get("identity_kernel"))
        or _dict(_nested_get(context, "system_identity", "identity_kernel_snapshot"))
        or _dict(context.get("q2_identity_kernel_snapshot"))
    )
    return {
        "non_bypassable_constraints": list(forbidden_items.get("system_identity_constraints") or []),
        "configured_forbidden_actions": list(forbidden_items.get("user_forbidden_actions") or []),
        "combined_forbidden_actions": list(forbidden_items.get("combined_forbidden_actions") or []),
        "role_name": snapshot.get("role_name") or snapshot.get("role") or context.get("identity_role"),
        "mission": snapshot.get("mission") or snapshot.get("meta_motivation"),
        "meta_drives": _list(snapshot.get("meta_drives")),
        "continuity_lock": _dict(snapshot.get("continuity_lock")),
        "self_binding_constraints": _list(snapshot.get("self_binding_constraints")),
        "source": {
            "identity_constraints": forbidden_items.get("sources", {}).get("system_identity_constraints") or [],
            "configured_forbidden_actions": forbidden_items.get("sources", {}).get("user_settings") or {},
        },
    }


def _query_memory_integrity_and_continuity_rules(context: dict[str, Any]) -> dict[str, Any]:
    explicit = (
        context.get("MemoryIntegrity_And_ContinuityRules")
        or context.get("memory_integrity_and_continuity_rules")
        or context.get("memory_integrity_rules")
        or context.get("memory_continuity_rules")
    )
    if isinstance(explicit, dict):
        return {"rules": explicit, "source": "context.memory_integrity_and_continuity_rules"}

    identity = _dict(context.get("identity_kernel_snapshot") or context.get("identity_kernel"))
    rules = {
        "continuity_lock": _dict(identity.get("continuity_lock")),
        "self_binding_constraints": _list(identity.get("self_binding_constraints")),
        "core_memory_anchors": _list(context.get("core_memory_anchors") or context.get("identity_memory_anchors")),
        "unrecoverable_experience_refs": _list(context.get("unrecoverable_experience_refs")),
    }
    memory_service = context.get("memory_service")
    list_main_memory = getattr(memory_service, "list_main_memory", None)
    if callable(list_main_memory):
        records = list_main_memory()
        rules["main_memory_records"] = _jsonable(records)
        return {"rules": rules, "source": "memory_service.list_main_memory"}
    return {"rules": rules, "source": "context.identity_and_memory_anchor_fields", "memory_service_available": False}


def _query_protected_modules_state(context: dict[str, Any]) -> dict[str, Any]:
    explicit = context.get("ProtectedModules_State") or context.get("protected_modules_state")
    if isinstance(explicit, dict):
        return {"modules": explicit, "source": "context.protected_modules_state"}

    modules = []
    for label, module_name in PROTECTED_INTERNAL_MODULES:
        spec = importlib.util.find_spec(module_name)
        modules.append(
            {
                "label": label,
                "module": module_name,
                "importable": spec is not None,
                "origin": getattr(spec, "origin", None) if spec is not None else None,
                "self_modification_protected": True,
            }
        )
    return {
        "modules": modules,
        "protected_path_parts": list(PROTECTED_PATH_PARTS),
        "source": "importlib.util.find_spec + zentex.kernel.self_refactor.PROTECTED_PATH_PARTS",
    }


def _query_q4_internal_objective_candidates(context: dict[str, Any]) -> dict[str, Any]:
    candidates = (
        context.get("Q4_InternalObjectiveCandidates")
        or context.get("q4_internal_objective_candidates")
        or _nested_get(context, "q4", "q4_internal_objective_candidates")
        or _nested_get(context, "q4_internal_llm_output", "InternalObjectiveCandidateSet")
        or context.get("q4_internal_llm_output")
    )
    source = "context.q4_internal_objective_candidates" if candidates is not None else "missing"
    return {"candidate_set": _jsonable(candidates or {}), "source": source}


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

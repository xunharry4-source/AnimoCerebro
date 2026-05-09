from __future__ import annotations

import importlib.util
from typing import Any

from plugins.nine_questions.q2_asset_inventory.service import (
    load_internal_public_output as load_q2_internal,
)
from plugins.nine_questions.q4_what_can_i_do.service import (
    load_internal_public_output as load_q4_internal,
)
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
    session_id = payload.get("session_id", "nq-baseline")
    db_path = payload.get("nine_question_state_db_path")

    # 强制通过上游提供的方法获取
    try:
        q2_internal_output = load_q2_internal(session_id=session_id, db_path=db_path)
    except Exception:
        q2_internal_output = {}

    try:
        q4_internal_output = load_q4_internal(session_id=session_id, db_path=db_path)
    except Exception:
        q4_internal_output = {}

    forbidden_items = query_nine_question_forbidden_items(payload)
    identity_constraints = _query_identity_kernel_constraints(q2_internal_output=q2_internal_output)
    if not identity_constraints.get("configured_forbidden_actions"):
        identity_constraints["configured_forbidden_actions"] = _list(forbidden_items.get("user_forbidden_actions"))
    if not identity_constraints.get("combined_forbidden_actions"):
        identity_constraints["combined_forbidden_actions"] = _list(forbidden_items.get("combined_forbidden_actions"))
    memory_rules = _query_memory_integrity_and_continuity_rules(q2_internal_output=q2_internal_output)
    protected_modules = _query_protected_modules_state(payload)
    q4_candidates = _query_q4_internal_objective_candidates(q4_internal_output=q4_internal_output)

    return {
        "IdentityKernel_NonBypassableConstraints": identity_constraints,
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
            "release_contract": "allowed_internal_objectives_with_conditions",
        },
    }


def _query_identity_kernel_constraints(*, q2_internal_output: dict[str, Any]) -> dict[str, Any]:
    snapshot = _dict(q2_internal_output)
    return {
        "non_bypassable_constraints": _list(snapshot.get("non_bypassable_internal_constraints")),
        "self_binding_constraints": _list(snapshot.get("self_binding_constraints")),
        "role_name": _text(snapshot.get("role_name")),
        "mission": snapshot.get("mission"),
        "meta_drives": _list(snapshot.get("meta_drives")),
        "continuity_lock": _dict(snapshot.get("continuity_lock")),
        "configured_forbidden_actions": _list(snapshot.get("configured_forbidden_actions")),
        "combined_forbidden_actions": _list(snapshot.get("combined_forbidden_actions")),
        "source": snapshot.get("source") or "database.q2_snapshots.internal_asset_inventory",
    }


def _query_memory_integrity_and_continuity_rules(*, q2_internal_output: dict[str, Any]) -> dict[str, Any]:
    rules = {
        "continuity_lock": _dict(q2_internal_output.get("continuity_lock")),
        "self_binding_constraints": _list(q2_internal_output.get("self_binding_constraints")),
        "long_term_memories": _list(q2_internal_output.get("long_term_memories")),
        "reusable_strategy_patches": _list(q2_internal_output.get("reusable_strategy_patches")),
        "unrecoverable_experience_refs": _list(q2_internal_output.get("unrecoverable_experience_refs")),
    }
    return {"rules": rules, "source": "database.q2_snapshots.internal_asset_inventory"}


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


def _query_q4_internal_objective_candidates(*, q4_internal_output: dict[str, Any]) -> dict[str, Any]:
    # 严格遵循架构原则：仅允许从上游 Loader 获取数据，禁止从 context 或 fallback 获取
    # Q4 Loader 返回的是 InternalObjectiveCandidateSet 模型字典
    if q4_internal_output and q4_internal_output.get("type") == "InternalObjectiveCandidateSet":
        candidates = q4_internal_output
        source = "database.q4_snapshots.internal_objective_candidates"
    else:
        candidates = {"type": "InternalObjectiveCandidateSet", "objective_candidates": []}
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

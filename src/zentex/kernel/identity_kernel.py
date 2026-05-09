from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType


UTC = timezone.utc
IDENTITY_TARGET_PREFIX = "g6:identity:"
IDENTITY_ENTRY_MOUNTED = "g6_identity_kernel_mounted"
IDENTITY_ENTRY_ANCHORS_QUERIED = "g6_identity_anchors_queried"
IDENTITY_ENTRY_CHANGE_EVALUATED = "g6_identity_change_evaluated"
IDENTITY_PACKAGE_TYPES = {"identity_role_pack", "identity_constraint_pack", "identity_experience_pack"}


def mount_identity_kernel(
    kernel_service: Any,
    *,
    session_id: str,
    topics: list[str] | None = None,
    risk_level: str = "low",
    identity_package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mount the G6 identity kernel and persist queryable memory anchors."""
    state = _require_session_state(kernel_service, session_id)
    memory_service = _require_memory_service(kernel_service)
    identity_kernel = _identity_kernel_payload(kernel_service)
    normalized_topics = _normalize_list(topics)
    normalized_risk = str(risk_level or "low").strip().lower()
    package_verification = _verify_identity_package(identity_package, identity_kernel) if identity_package else None

    anchor_specs = _anchor_specs(identity_kernel, topics=normalized_topics, risk_level=normalized_risk)
    mounted_anchors = [
        _ensure_anchor(memory_service, spec=spec, trace_prefix=session_id)
        for spec in anchor_specs
    ]
    if not mounted_anchors:
        raise RuntimeError("G6 failed to mount any identity anchors")

    payload = {
        "feature_code": "G6",
        "session_id": session_id,
        "identity_kernel": identity_kernel,
        "mounted_anchor_count": len(mounted_anchors),
        "mounted_anchors": mounted_anchors,
        "package_verification": package_verification,
        "continuity_lock": identity_kernel["continuity_lock"],
        "self_binding_constraints": identity_kernel["self_binding_constraints"],
        "mounted_at": datetime.now(UTC).isoformat(),
    }
    _write_transcript(state, session_id=session_id, event=IDENTITY_ENTRY_MOUNTED, payload=payload)
    return payload


def query_identity_anchors(
    kernel_service: Any,
    *,
    session_id: str,
    role: str | None = None,
    risk_level: str | None = None,
    topics: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Query persisted G6 identity anchors by role, risk, and topic dimensions."""
    state = _require_session_state(kernel_service, session_id)
    memory_service = _require_memory_service(kernel_service)
    if limit <= 0:
        raise ValueError("limit must be > 0")
    identity_kernel = _identity_kernel_payload(kernel_service)
    normalized_role = str(role or identity_kernel["role"]).strip()
    normalized_risk = str(risk_level or "").strip().lower()
    normalized_topics = _normalize_list(topics)
    anchors = _query_anchor_records(
        memory_service,
        role=normalized_role,
        risk_level=normalized_risk,
        topics=normalized_topics,
        limit=limit,
    )
    payload = {
        "feature_code": "G6",
        "session_id": session_id,
        "query": {
            "role": normalized_role,
            "risk_level": normalized_risk,
            "topics": normalized_topics,
            "limit": limit,
        },
        "anchor_count": len(anchors),
        "anchors": anchors,
        "conflict_resolution_order": [
            "non_bypassable_constraints",
            "continuity_lock",
            "self_binding_constraints",
            "identity_role_pack",
            "identity_constraint_pack",
            "identity_experience_pack",
            "runtime_preferences",
        ],
    }
    _write_transcript(
        state,
        session_id=session_id,
        event=IDENTITY_ENTRY_ANCHORS_QUERIED,
        payload={"query": payload["query"], "anchor_count": len(anchors)},
    )
    return payload


def evaluate_identity_change(
    kernel_service: Any,
    *,
    session_id: str,
    proposed_changes: dict[str, Any],
    human_confirmed: bool = False,
    reviewer: str | None = None,
    drift_threshold: float = 0.34,
) -> dict[str, Any]:
    """Evaluate an identity change proposal against G6 continuity locks."""
    state = _require_session_state(kernel_service, session_id)
    if not isinstance(proposed_changes, dict) or not proposed_changes:
        raise ValueError("proposed_changes must be a non-empty object")
    identity_kernel = _identity_kernel_payload(kernel_service)
    locked_fields = set(identity_kernel["continuity_lock"]["locked_fields"])
    proposed_fields = set(proposed_changes)
    protected_aliases = set(locked_fields)
    if "role_name" in locked_fields:
        protected_aliases.add("role")
    locked_change_fields = sorted(proposed_fields & protected_aliases)
    drift_fields = sorted(
        field
        for field in proposed_fields
        if field in {"role_name", "role", "mission", "core_values", "non_bypassable_constraints"}
        and _stringify(proposed_changes.get(field)) != _stringify(_current_identity_value(identity_kernel, field))
    )
    drift_score = len(drift_fields) / 3.0 if drift_fields else 0.0
    violations = []
    if locked_change_fields and not human_confirmed:
        violations.append("locked_identity_field_requires_human_confirmation")
    if drift_score > drift_threshold:
        violations.append("identity_continuity_drift_exceeds_threshold")
    if _violates_self_binding(identity_kernel, proposed_changes):
        violations.append("self_binding_constraint_violation")

    decision = "allowed_for_manual_review" if not violations else "blocked"
    payload = {
        "feature_code": "G6",
        "session_id": session_id,
        "decision": decision,
        "allowed": decision != "blocked",
        "human_confirmed": bool(human_confirmed),
        "reviewer": str(reviewer or ""),
        "proposed_changes": _json_safe(proposed_changes),
        "locked_change_fields": locked_change_fields,
        "drift_fields": drift_fields,
        "drift_score": drift_score,
        "drift_threshold": drift_threshold,
        "violations": violations,
        "rollback_required": bool(violations),
        "manual_review_required": bool(locked_change_fields or drift_fields),
        "identity_kernel_before": identity_kernel,
    }
    _write_transcript(
        state,
        session_id=session_id,
        event=IDENTITY_ENTRY_CHANGE_EVALUATED,
        payload={
            "decision": decision,
            "locked_change_fields": locked_change_fields,
            "drift_fields": drift_fields,
            "violations": violations,
        },
    )
    return payload


def sign_identity_package(package_payload: dict[str, Any], *, secret: str) -> str:
    """Return an HMAC signature for an identity package payload."""
    if not secret:
        raise ValueError("secret is required")
    body = _canonical_json(
        {
            k: v
            for k, v in package_payload.items()
            if k not in {"signature", "verification_secret"}
        }
    )
    return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def _identity_kernel_payload(kernel_service: Any) -> dict[str, Any]:
    foundation_service = getattr(kernel_service, "_foundation_service", None)
    if foundation_service is None:
        raise RuntimeError("G6 identity kernel requires an attached foundation service")
    identity = kernel_service._svc_call(foundation_service, "get_identity_snapshot")
    role = str(getattr(identity, "role_name", "") or "").strip()
    mission = str(getattr(identity, "mission", "") or "").strip()
    core_values = [str(item).strip() for item in list(getattr(identity, "core_values", ()) or ()) if str(item).strip()]
    if not role or not mission or not core_values:
        raise RuntimeError("G6 identity kernel is incomplete; role, mission, and core_values are required")
    lock = getattr(identity, "continuity_lock", None)
    locked_fields = sorted(str(item) for item in getattr(lock, "locked_fields", set()) or [])
    lock_reason = str(getattr(lock, "lock_reason", "") or "")
    return {
        "role": role,
        "role_name": role,
        "mission": mission,
        "meta_motivation": mission,
        "meta_drives": [mission],
        "core_values": core_values,
        "non_bypassable_constraints": core_values,
        "continuity_lock": {
            "locked_fields": locked_fields,
            "lock_reason": lock_reason,
            "enforced": bool(locked_fields),
        },
        "self_binding_constraints": [
            "core identity fields require human confirmation before structural change",
            "dynamic goals cannot override non-bypassable constraints",
            "identity package data cannot cross scopes silently",
        ],
        "identity_package_families": sorted(IDENTITY_PACKAGE_TYPES),
        "version": _model_dump(getattr(identity, "version", None)),
        "loaded_from": "foundation_service.get_identity_snapshot",
    }


def _anchor_specs(identity_kernel: dict[str, Any], *, topics: list[str], risk_level: str) -> list[dict[str, Any]]:
    role = identity_kernel["role"]
    mission = identity_kernel["mission"]
    constraints = identity_kernel["non_bypassable_constraints"]
    topic_text = ", ".join(topics) if topics else "general"
    return [
        {
            "anchor_kind": "role",
            "role": role,
            "title": f"G6 Identity Anchor role {role}",
            "content": f"Role anchor for {role}. Mission: {mission}. Topics: {topic_text}.",
            "topics": topics or ["identity"],
            "risk_level": risk_level,
        },
        {
            "anchor_kind": "constraint",
            "role": role,
            "title": f"G6 Identity Anchor constraints {role}",
            "content": (
                f"Non-bypassable constraints for {role}: {', '.join(constraints)}. "
                f"Risk: {risk_level}. Topics: {topic_text}."
            ),
            "topics": list(set((topics or []) + ["constraints", "safety"])),
            "risk_level": risk_level,
        },
        {
            "anchor_kind": "self_binding",
            "role": role,
            "title": f"G6 Identity Anchor self binding {role}",
            "content": (
                "Self-binding constraints: dynamic goals cannot override identity locks "
                f"or core values. Topics: {topic_text}. Risk: {risk_level}."
            ),
            "topics": list(set((topics or []) + ["self_binding", "continuity"])),
            "risk_level": risk_level,
        },
    ]


def _ensure_anchor(memory_service: Any, *, spec: dict[str, Any], trace_prefix: str) -> dict[str, Any]:
    role = str(spec["role"])
    anchor_key = _anchor_key(spec)
    existing = _find_existing_anchor(memory_service, anchor_key)
    if existing is not None:
        return _anchor_payload(existing, hit_reasons=["existing_anchor_reused"])
    record = memory_service.remember(
        title=str(spec["title"]),
        content=str(spec["content"]),
        summary=str(spec["content"])[:180],
        layer="semantic",
        source="g6_identity_kernel",
        trace_id=f"g6-anchor:{trace_prefix}:{uuid4().hex}",
        target_id=IDENTITY_TARGET_PREFIX + role,
        tags=["G6", "identity_anchor", str(spec["anchor_kind"]), str(spec["risk_level"]), *list(spec["topics"])],
        feature_code="G6",
        anchor_key=anchor_key,
        anchor_kind=spec["anchor_kind"],
        role=role,
        risk_level=spec["risk_level"],
        topics=spec["topics"],
    )
    queried = memory_service.get_record(record.memory_id)
    if queried is None:
        raise RuntimeError(f"G6 identity anchor write was not query-visible: {record.memory_id}")
    return _anchor_payload(queried, hit_reasons=["created_identity_anchor"])


def _query_anchor_records(
    memory_service: Any,
    *,
    role: str,
    risk_level: str,
    topics: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    records = memory_service.query_managed_records(limit=1000)
    anchors = []
    for record in records:
        payload = getattr(record, "payload", {}) or {}
        tags = set(getattr(record, "tags", []) or [])
        if payload.get("feature_code") != "G6" and "G6" not in tags:
            continue
        reasons = []
        record_role = str(payload.get("role") or "")
        role_matches = not role or role == record_role or role in str(getattr(record, "title", ""))
        if role and role_matches:
            reasons.append("role_match")
        record_risk = str(payload.get("risk_level") or "").lower()
        risk_matches = not risk_level or risk_level == record_risk
        if risk_level and risk_matches:
            reasons.append("risk_match")
        record_topics = {str(item) for item in payload.get("topics", []) or []} | tags
        topic_hits = sorted(set(topics) & record_topics)
        topic_matches = not topics or bool(topic_hits)
        if topics and topic_hits:
            reasons.append("topic_match:" + ",".join(topic_hits))
        if not (role_matches and risk_matches and topic_matches):
            continue
        if not reasons:
            reasons.append("identity_anchor_available")
        anchors.append(_anchor_payload(record, hit_reasons=reasons))
    anchors.sort(key=lambda item: (len(item["hit_reasons"]), item["created_at"]), reverse=True)
    return anchors[:limit]


def _find_existing_anchor(memory_service: Any, anchor_key: str) -> Any | None:
    for record in memory_service.query_managed_records(limit=1000):
        payload = getattr(record, "payload", {}) or {}
        if payload.get("anchor_key") == anchor_key:
            return record
    return None


def _anchor_payload(record: Any, *, hit_reasons: list[str]) -> dict[str, Any]:
    payload = getattr(record, "payload", {}) or {}
    return {
        "memory_id": str(getattr(record, "memory_id", "")),
        "title": str(getattr(record, "title", "")),
        "summary": str(getattr(record, "summary", "")),
        "target_id": str(getattr(record, "target_id", "") or ""),
        "tags": list(getattr(record, "tags", []) or []),
        "anchor_kind": str(payload.get("anchor_kind") or ""),
        "role": str(payload.get("role") or ""),
        "risk_level": str(payload.get("risk_level") or ""),
        "topics": list(payload.get("topics") or []),
        "anchor_key": str(payload.get("anchor_key") or ""),
        "hit_reasons": hit_reasons,
        "created_at": str(getattr(record, "created_at", "")),
    }


def _verify_identity_package(package: dict[str, Any], identity_kernel: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(package, dict):
        raise ValueError("identity_package must be an object")
    package_type = str(package.get("package_type") or "").strip()
    if package_type not in IDENTITY_PACKAGE_TYPES:
        raise ValueError(f"Unsupported identity package type: {package_type}")
    package_scope = str(package.get("identity_scope") or "").strip()
    if package_scope and package_scope != identity_kernel["role"]:
        raise ValueError("identity package scope does not match mounted identity role")
    signature = str(package.get("signature") or "").strip()
    if not signature:
        raise ValueError("identity package signature is required")
    package_id = str(package.get("package_id") or "").strip()
    secret = str(package.get("verification_secret") or package_id or "").strip()
    if not secret:
        raise ValueError("identity package requires package_id or verification_secret for signature verification")
    expected = sign_identity_package(package, secret=secret)
    if not hmac.compare_digest(signature, expected):
        raise ValueError("identity package signature verification failed")
    return {
        "verified": True,
        "package_id": package_id,
        "package_type": package_type,
        "identity_scope": package_scope,
        "isolation_enforced": True,
    }


def _current_identity_value(identity_kernel: dict[str, Any], field: str) -> Any:
    if field in {"role_name", "role"}:
        return identity_kernel.get("role")
    return identity_kernel.get(field)


def _violates_self_binding(identity_kernel: dict[str, Any], proposed_changes: dict[str, Any]) -> bool:
    text = _stringify(proposed_changes).lower()
    return any(
        token in text
        for token in (
            "override non-bypassable",
            "disable safety",
            "ignore core values",
            "bypass identity",
        )
    )


def _require_session_state(kernel_service: Any, session_id: str) -> Any:
    state = kernel_service._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for G6 identity kernel: {session_id}")
    return state


def _require_memory_service(kernel_service: Any) -> Any:
    memory_service = getattr(kernel_service, "_memory_service", None)
    if memory_service is None:
        raise RuntimeError("G6 identity kernel requires an attached memory service")
    for method_name in ("remember", "query_managed_records", "get_record"):
        if not callable(getattr(memory_service, method_name, None)):
            raise RuntimeError(f"G6 memory service missing required method: {method_name}")
    return memory_service


def _write_transcript(state: Any, *, session_id: str, event: str, payload: dict[str, Any]) -> None:
    transcript = getattr(state, "transcript", None)
    if transcript is None:
        raise RuntimeError("G6 identity kernel requires a session transcript store")
    trace_id = f"g6-identity-kernel:{uuid4().hex}"
    transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=session_id,
            turn_id=f"g6-{uuid4().hex}",
            trace_id=trace_id,
            source="kernel.identity_kernel",
            payload={
                "feature_code": "G6",
                "entry_type": event,
                "trace_id": trace_id,
                **_json_safe(payload),
            },
        )
    )


def _anchor_key(spec: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(spec).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _model_dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return _json_safe(value)


def _normalize_list(value: list[str] | None) -> list[str]:
    return [str(item).strip() for item in (value or []) if str(item).strip()]


def _stringify(value: Any) -> str:
    return _canonical_json(value) if isinstance(value, (dict, list, tuple, set)) else str(value)

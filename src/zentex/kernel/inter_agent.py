from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import requests

from zentex.agents.manager import AgentStatus, AgentTrustLevel
from zentex.kernel.state_domain.transcript_models import TranscriptEntry, TranscriptEntryType


UTC = timezone.utc
INTER_AGENT_METADATA_KEY = "g7_inter_agent_conflicts"
INTER_AGENT_ENTRY_NEGOTIATED = "g7_inter_agent_negotiated"
INTER_AGENT_ENTRY_REASSIGNED = "g7_inter_agent_reassigned"
UNAVAILABLE_AGENT_STATUSES = {
    AgentStatus.OFFLINE.value,
    AgentStatus.HANDSHAKE_FAILED.value,
    AgentStatus.AUDIT_FAILED.value,
    AgentStatus.INVOCATION_BLOCKED.value,
}


async def create_inter_agent_conflict(
    kernel_service: Any,
    *,
    session_id: str,
    task_id: str,
    task_payload: dict[str, Any],
    required_capabilities: list[str],
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Broadcast a task to real agent HTTP endpoints and adjudicate bids."""
    state = _require_session_state(kernel_service, session_id)
    agent_service = _require_agent_service(kernel_service)
    task_service = _require_task_service(kernel_service)
    task = _require_task(task_service, task_id)
    if not isinstance(task_payload, dict) or not task_payload:
        raise ValueError("task_payload must be a non-empty object")
    required = _normalize_list(required_capabilities)
    if not required:
        raise ValueError("required_capabilities must be non-empty")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be > 0")

    candidates = _candidate_agents(agent_service)
    if not candidates:
        raise RuntimeError("G7 has no connected agents eligible for real bidding")

    conflict_id = f"g7-{uuid4().hex}"
    broadcast_payload = {
        "feature_code": "G7",
        "conflict_id": conflict_id,
        "task_id": task_id,
        "task_payload": _json_safe(task_payload),
        "required_capabilities": required,
        "broadcasted_at": datetime.now(UTC).isoformat(),
    }
    bid_results = [
        _request_bid(
            agent_service,
            agent=agent,
            broadcast_payload=broadcast_payload,
            timeout_seconds=timeout_seconds,
        )
        for agent in candidates
    ]
    accepted_bids = [item for item in bid_results if item["status"] == "accepted"]
    if not accepted_bids:
        raise RuntimeError(
            "G7 task broadcast reached no eligible bids; failures="
            + json.dumps(bid_results, ensure_ascii=False, default=str)
        )

    ranked_bids = sorted(accepted_bids, key=lambda item: item["adjudication_score"], reverse=True)
    winner = ranked_bids[0]
    conflict = {
        "feature_code": "G7",
        "conflict_id": conflict_id,
        "session_id": session_id,
        "task_id": task_id,
        "status": "assigned",
        "transport": "http",
        "required_capabilities": required,
        "task_payload": _json_safe(task_payload),
        "broadcast_count": len(candidates),
        "bid_count": len(accepted_bids),
        "bids": ranked_bids,
        "failed_agents": [item for item in bid_results if item["status"] != "accepted"],
        "selected_agent_id": winner["agent_id"],
        "selected_bid_id": winner["bid_id"],
        "adjudication": {
            "order": [
                "capability_match_score",
                "agent_reported_confidence",
                "trust_level",
                "success_rate",
                "cost",
            ],
            "winning_score": winner["adjudication_score"],
            "reason": winner["adjudication_reason"],
        },
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    await _persist_conflict(task_service, task_id=task_id, conflict=conflict)
    persisted = _get_persisted_conflict(task_service, task_id=task_id, conflict_id=conflict_id)
    if persisted is None:
        raise RuntimeError(f"G7 conflict persistence is not query-visible: {conflict_id}")
    _write_transcript(
        state,
        session_id=session_id,
        event=INTER_AGENT_ENTRY_NEGOTIATED,
        payload={
            "conflict_id": conflict_id,
            "task_id": task_id,
            "selected_agent_id": winner["agent_id"],
            "bid_count": len(accepted_bids),
        },
    )
    queried_task = task_service.get_task(task_id)
    return {
        **persisted,
        "task": _task_payload(queried_task or task),
    }


def query_inter_agent_conflict(
    kernel_service: Any,
    *,
    session_id: str,
    conflict_id: str,
    task_id: str,
) -> dict[str, Any]:
    """Query the persisted G7 conflict record from real task metadata."""
    _require_session_state(kernel_service, session_id)
    task_service = _require_task_service(kernel_service)
    conflict = _get_persisted_conflict(task_service, task_id=task_id, conflict_id=conflict_id)
    if conflict is None:
        raise KeyError(f"G7 conflict {conflict_id} is not persisted on task {task_id}")
    if str(conflict.get("session_id")) != session_id:
        raise ValueError("G7 conflict session_id does not match query")
    task = _require_task(task_service, task_id)
    return {
        **conflict,
        "task": _task_payload(task),
    }


async def reassign_inter_agent_conflict(
    kernel_service: Any,
    *,
    session_id: str,
    conflict_id: str,
    task_id: str,
    failed_agent_id: str,
    failure_reason: str,
) -> dict[str, Any]:
    """Remove a failed winner and reassign to the next persisted real bid."""
    state = _require_session_state(kernel_service, session_id)
    agent_service = _require_agent_service(kernel_service)
    task_service = _require_task_service(kernel_service)
    conflict = _get_persisted_conflict(task_service, task_id=task_id, conflict_id=conflict_id)
    if conflict is None:
        raise KeyError(f"G7 conflict {conflict_id} is not persisted on task {task_id}")
    if str(conflict.get("selected_agent_id")) != str(failed_agent_id):
        raise ValueError("failed_agent_id must match the currently selected agent")
    if not failure_reason:
        raise ValueError("failure_reason is required")

    _mark_agent_offline(agent_service, failed_agent_id, reason=failure_reason)
    failed_agents = list(conflict.get("failed_agents") or [])
    failed_agents.append(
        {
            "agent_id": str(failed_agent_id),
            "status": "execution_failed",
            "reason": str(failure_reason),
            "failed_at": datetime.now(UTC).isoformat(),
        }
    )
    bids = [
        item
        for item in list(conflict.get("bids") or [])
        if str(item.get("agent_id")) != str(failed_agent_id)
        and not _is_agent_unavailable(agent_service, str(item.get("agent_id")))
    ]
    if not bids:
        conflict.update(
            {
                "status": "unassigned",
                "selected_agent_id": "",
                "selected_bid_id": "",
                "failed_agents": failed_agents,
                "updated_at": datetime.now(UTC).isoformat(),
                "reassignment_reason": "no_remaining_live_bid",
            }
        )
    else:
        winner = sorted(bids, key=lambda item: item["adjudication_score"], reverse=True)[0]
        conflict.update(
            {
                "status": "reassigned",
                "selected_agent_id": winner["agent_id"],
                "selected_bid_id": winner["bid_id"],
                "failed_agents": failed_agents,
                "updated_at": datetime.now(UTC).isoformat(),
                "reassignment_reason": str(failure_reason),
            }
        )
    await _persist_conflict(task_service, task_id=task_id, conflict=conflict)
    persisted = _get_persisted_conflict(task_service, task_id=task_id, conflict_id=conflict_id)
    if persisted is None:
        raise RuntimeError(f"G7 reassignment was not query-visible: {conflict_id}")
    _write_transcript(
        state,
        session_id=session_id,
        event=INTER_AGENT_ENTRY_REASSIGNED,
        payload={
            "conflict_id": conflict_id,
            "task_id": task_id,
            "failed_agent_id": failed_agent_id,
            "selected_agent_id": persisted.get("selected_agent_id"),
            "status": persisted.get("status"),
        },
    )
    task = _require_task(task_service, task_id)
    return {
        **persisted,
        "task": _task_payload(task),
    }


def _request_bid(
    agent_service: Any,
    *,
    agent: Any,
    broadcast_payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    agent_id = str(getattr(agent, "agent_id", ""))
    endpoint = str(getattr(agent, "endpoint", "") or "").rstrip("/")
    if not endpoint:
        _mark_agent_offline(agent_service, agent_id, reason="missing endpoint")
        return {"agent_id": agent_id, "status": "transport_failed", "error": "missing endpoint"}
    try:
        response = requests.post(
            endpoint + "/bid",
            json=broadcast_payload,
            timeout=timeout_seconds,
        )
        if response.status_code >= 400:
            _mark_agent_offline(agent_service, agent_id, reason=f"bid http {response.status_code}")
            return {
                "agent_id": agent_id,
                "status": "transport_failed",
                "http_status": response.status_code,
                "error": response.text,
            }
        bid_payload = response.json()
    except requests.RequestException as exc:
        _mark_agent_offline(agent_service, agent_id, reason=str(exc))
        return {"agent_id": agent_id, "status": "transport_failed", "error": str(exc)}
    except ValueError as exc:
        _mark_agent_offline(agent_service, agent_id, reason=f"invalid json: {exc}")
        return {"agent_id": agent_id, "status": "transport_failed", "error": f"invalid json: {exc}"}

    if not bid_payload.get("accept"):
        return {
            "agent_id": agent_id,
            "status": "declined",
            "reason": str(bid_payload.get("reason") or "agent declined"),
        }
    bid = _normalize_bid(agent=agent, bid_payload=bid_payload, broadcast_payload=broadcast_payload)
    return bid


def _normalize_bid(agent: Any, bid_payload: dict[str, Any], broadcast_payload: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(getattr(agent, "agent_id", ""))
    agent_capabilities = _agent_capability_names(agent)
    required = set(broadcast_payload["required_capabilities"])
    capability_hits = sorted(required & set(agent_capabilities))
    capability_score = len(capability_hits) / len(required)
    confidence = _bounded_float(bid_payload.get("confidence", 0.0), default=0.0)
    cost = max(float(bid_payload.get("cost", 0.0) or 0.0), 0.0)
    success_rate = _bounded_float(getattr(agent, "success_rate", 0.0), default=0.0)
    trust_score = _trust_score(getattr(agent, "trust_level", "unknown"))
    adjudication_score = round(
        capability_score * 0.45
        + confidence * 0.25
        + trust_score * 0.15
        + success_rate * 0.10
        - min(cost / 100.0, 1.0) * 0.05,
        6,
    )
    if capability_score <= 0:
        return {
            "agent_id": agent_id,
            "status": "declined",
            "reason": "no_required_capability_match",
        }
    return {
        "agent_id": agent_id,
        "agent_name": str(getattr(agent, "agent_name", "")),
        "status": "accepted",
        "bid_id": str(bid_payload.get("bid_id") or f"bid-{uuid4().hex}"),
        "capability_hits": capability_hits,
        "capability_match_score": capability_score,
        "confidence": confidence,
        "cost": cost,
        "estimated_seconds": float(bid_payload.get("estimated_seconds", 0.0) or 0.0),
        "transport": "http",
        "adjudication_score": adjudication_score,
        "adjudication_reason": (
            f"capability={capability_score:.3f}; confidence={confidence:.3f}; "
            f"trust={trust_score:.3f}; success_rate={success_rate:.3f}; cost={cost:.3f}"
        ),
        "raw_bid": _json_safe(bid_payload),
    }


def _candidate_agents(agent_service: Any) -> list[Any]:
    candidates = []
    for agent in list(agent_service.manager.list_assets()):
        status = _enum_value(getattr(agent, "status", ""))
        if status in UNAVAILABLE_AGENT_STATUSES:
            continue
        if not str(getattr(agent, "endpoint", "") or "").strip():
            continue
        candidates.append(agent)
    return candidates


def _agent_capability_names(agent: Any) -> list[str]:
    values = []
    for item in list(getattr(agent, "capabilities", []) or []):
        if isinstance(item, dict):
            candidate = item.get("name") or item.get("id") or item.get("capability")
        else:
            candidate = item
        text = str(candidate or "").strip()
        if text:
            values.append(text)
    return values


async def _persist_conflict(task_service: Any, *, task_id: str, conflict: dict[str, Any]) -> None:
    task = _require_task(task_service, task_id)
    existing = list((task.metadata or {}).get(INTER_AGENT_METADATA_KEY) or [])
    updated = [item for item in existing if item.get("conflict_id") != conflict["conflict_id"]]
    updated.append(_json_safe(conflict))
    await task_service.update_task_metadata(
        task_id,
        {INTER_AGENT_METADATA_KEY: updated},
        remarks=f"G7 inter-agent conflict {conflict['conflict_id']} updated",
    )


def _get_persisted_conflict(task_service: Any, *, task_id: str, conflict_id: str) -> dict[str, Any] | None:
    task = task_service.get_task(task_id)
    if task is None:
        return None
    for item in list((task.metadata or {}).get(INTER_AGENT_METADATA_KEY) or []):
        if item.get("conflict_id") == conflict_id:
            return _json_safe(item)
    return None


def _mark_agent_offline(agent_service: Any, agent_id: str, *, reason: str) -> None:
    if not agent_id:
        return
    updated = agent_service.manager.update_asset(
        agent_id,
        status=AgentStatus.OFFLINE,
        last_ping_at=datetime.now(UTC),
    )
    if updated is None:
        raise KeyError(f"G7 failed to mark missing agent offline: {agent_id}")
    record_audit = getattr(agent_service, "record_audit", None)
    if callable(record_audit):
        record_audit(agent_id, "G7_AGENT_EJECTED", {"reason": reason})


def _is_agent_unavailable(agent_service: Any, agent_id: str) -> bool:
    asset = agent_service.manager.get_asset(agent_id)
    if asset is None:
        return True
    return _enum_value(getattr(asset, "status", "")) in UNAVAILABLE_AGENT_STATUSES


def _require_session_state(kernel_service: Any, session_id: str) -> Any:
    state = kernel_service._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for G7 inter-agent negotiation: {session_id}")
    return state


def _require_agent_service(kernel_service: Any) -> Any:
    agent_service = getattr(kernel_service, "_agent_service", None)
    if agent_service is None:
        raise RuntimeError("G7 inter-agent negotiation requires an attached agent service")
    for method_name in ("manager",):
        if getattr(agent_service, method_name, None) is None:
            raise RuntimeError(f"G7 agent service missing required attribute: {method_name}")
    return agent_service


def _require_task_service(kernel_service: Any) -> Any:
    task_service = getattr(kernel_service, "_task_service", None)
    if task_service is None:
        raise RuntimeError("G7 inter-agent negotiation requires an attached task service")
    for method_name in ("get_task", "update_task_metadata"):
        if not callable(getattr(task_service, method_name, None)):
            raise RuntimeError(f"G7 task service missing required method: {method_name}")
    return task_service


def _require_task(task_service: Any, task_id: str) -> Any:
    task = task_service.get_task(task_id)
    if task is None:
        raise KeyError(f"Task {task_id} not found for G7 inter-agent negotiation")
    return task


def _write_transcript(state: Any, *, session_id: str, event: str, payload: dict[str, Any]) -> None:
    transcript = getattr(state, "transcript", None)
    if transcript is None:
        raise RuntimeError("G7 inter-agent negotiation requires a session transcript store")
    trace_id = f"g7-inter-agent:{uuid4().hex}"
    transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=session_id,
            turn_id=f"g7-{uuid4().hex}",
            trace_id=trace_id,
            source="kernel.inter_agent",
            payload={
                "feature_code": "G7",
                "entry_type": event,
                "trace_id": trace_id,
                **_json_safe(payload),
            },
        )
    )


def _task_payload(task: Any) -> dict[str, Any]:
    return {
        "task_id": str(getattr(task, "task_id", "")),
        "status": _enum_value(getattr(task, "status", "")),
        "target_id": str(getattr(task, "target_id", "") or ""),
        "metadata": _json_safe(getattr(task, "metadata", {}) or {}),
    }


def _trust_score(value: Any) -> float:
    normalized = _enum_value(value)
    return {
        AgentTrustLevel.TRUSTED.value: 1.0,
        AgentTrustLevel.RESTRICTED.value: 0.6,
        AgentTrustLevel.PENDING.value: 0.4,
        AgentTrustLevel.UNKNOWN.value: 0.2,
        AgentTrustLevel.REVOKED.value: 0.0,
    }.get(normalized, 0.2)


def _bounded_float(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, 0.0), 1.0)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _normalize_list(value: list[str] | None) -> list[str]:
    return [str(item).strip() for item in (value or []) if str(item).strip()]


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))

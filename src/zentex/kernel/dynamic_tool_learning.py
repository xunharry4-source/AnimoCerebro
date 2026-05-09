from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import requests

from zentex.kernel.state_domain import TranscriptEntry, TranscriptEntryType


UTC = timezone.utc
REAL_DOCUMENT = "real_document"
STATIC_SAMPLE = "static_catalog_sample"
ALLOWED_SOURCE_KINDS = {REAL_DOCUMENT, STATIC_SAMPLE}


def learn_dynamic_tool_capability(
    kernel: Any,
    *,
    session_id: str,
    documentation_url: str,
    source_kind: str,
    capability_name: Optional[str] = None,
    verification_endpoint: Optional[str] = None,
    verification_cases: Optional[list[dict[str, Any]]] = None,
    timeout_seconds: float = 3.0,
) -> dict[str, Any]:
    if not session_id:
        raise ValueError("session_id is required")
    if not documentation_url:
        raise ValueError("documentation_url is required")
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise ValueError(f"source_kind must be one of {sorted(ALLOWED_SOURCE_KINDS)}")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")

    document = _fetch_document(documentation_url, timeout_seconds=timeout_seconds)
    extracted = _extract_tool_knowledge(document["text"], capability_name=capability_name)
    endpoint = verification_endpoint or extracted.get("verification_endpoint")
    cases = list(verification_cases or extracted.get("verification_cases") or [])

    sandbox = _run_sandbox_precheck(kernel, session_id=session_id, extracted=extracted)
    if sandbox.get("vetoed"):
        raise RuntimeError(f"G12 sandbox precheck vetoed capability learning: {sandbox.get('veto_reason')}")

    verification = _verify_capability(
        source_kind=source_kind,
        endpoint=endpoint,
        cases=cases,
        timeout_seconds=timeout_seconds,
    )
    knowledge_id = f"g12-knowledge-{uuid4().hex}"
    capability_id = f"g12-capability-{uuid4().hex}" if verification["registered"] else None
    now = datetime.now(UTC).isoformat()
    record = {
        "feature_code": "G12",
        "session_id": session_id,
        "knowledge_id": knowledge_id,
        "capability_id": capability_id,
        "documentation": {
            "url": documentation_url,
            "source_kind": source_kind,
            "content_sha256": document["content_sha256"],
            "content_length": document["content_length"],
        },
        "tool_knowledge_record": {
            "tool_name": extracted["tool_name"],
            "description": extracted["description"],
            "version": extracted["version"],
            "usage_example": extracted["usage_example"],
            "input_schema": extracted["input_schema"],
            "output_schema": extracted["output_schema"],
            "source_ref": documentation_url,
            "verification_status": verification["verification_status"],
        },
        "sandbox_outcome_ref": sandbox.get("outcome_id"),
        "verification": verification,
        "capability_registration": None,
        "registered": verification["registered"],
        "created_at": now,
        "evidence_refs": [],
    }
    if verification["registered"]:
        record["capability_registration"] = {
            "capability_id": capability_id,
            "tool_name": extracted["tool_name"],
            "version": extracted["version"],
            "status": "active",
            "verification_status": "real_verified",
            "documentation_url": documentation_url,
            "registered_at": now,
            "input_schema": extracted["input_schema"],
            "output_schema": extracted["output_schema"],
            "verification_receipts": verification["receipts"],
        }

    memory_id = _persist_memory(kernel, record)
    if memory_id:
        record["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    if sandbox.get("outcome_id"):
        record["evidence_refs"].append({"type": "thought_sandbox", "outcome_id": sandbox["outcome_id"]})
    _cache_record(kernel, "_tool_knowledge_records", knowledge_id, record)
    if record["capability_registration"]:
        _cache_record(kernel, "_capabilities_store", capability_id, record["capability_registration"])
    _append_transcript(state, record, "g12_dynamic_tool_learning_completed")
    return record


def query_tool_knowledge_record(kernel: Any, *, session_id: str, knowledge_id: str) -> dict[str, Any]:
    if not session_id or not knowledge_id:
        raise ValueError("session_id and knowledge_id are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    record = getattr(kernel, "_tool_knowledge_records", {}).get(knowledge_id)
    if not record or record["session_id"] != session_id:
        raise KeyError(f"G12 tool knowledge record not found: {knowledge_id}")
    _append_transcript(state, record, "g12_tool_knowledge_queried")
    return {**record, "query_visible": True}


def query_capability_registration(kernel: Any, *, session_id: str, capability_id: str) -> dict[str, Any]:
    if not session_id or not capability_id:
        raise ValueError("session_id and capability_id are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    capability = getattr(kernel, "_capabilities_store", {}).get(capability_id)
    if not capability:
        raise KeyError(f"G12 capability registration not found: {capability_id}")
    records = getattr(kernel, "_tool_knowledge_records", {}).values()
    source_record = next((item for item in records if item.get("capability_id") == capability_id), None)
    if not source_record or source_record["session_id"] != session_id:
        raise KeyError(f"G12 capability registration not found for session: {capability_id}")
    payload = {"feature_code": "G12", "session_id": session_id, **capability}
    _append_transcript(state, payload, "g12_capability_registration_queried")
    return {**payload, "query_visible": True}


def _fetch_document(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    response = requests.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    text = response.text
    if not text.strip():
        raise ValueError(f"documentation_url returned empty content: {url}")
    import hashlib

    return {
        "text": text,
        "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "content_length": len(text.encode("utf-8")),
    }


def _extract_tool_knowledge(text: str, *, capability_name: Optional[str]) -> dict[str, Any]:
    parsed: dict[str, Any]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = _parse_markdown_key_values(text)
    tool_name = str(capability_name or parsed.get("tool_name") or parsed.get("name") or "").strip()
    description = str(parsed.get("description") or "").strip()
    if not tool_name:
        raise ValueError("documentation did not provide tool_name")
    if not description:
        raise ValueError("documentation did not provide description")
    input_schema = parsed.get("input_schema") or {}
    output_schema = parsed.get("output_schema") or {}
    if not isinstance(input_schema, dict) or not isinstance(output_schema, dict):
        raise ValueError("input_schema and output_schema must be objects")
    return {
        "tool_name": tool_name,
        "description": description,
        "version": str(parsed.get("version") or "0.0.0"),
        "usage_example": str(parsed.get("usage_example") or parsed.get("example") or ""),
        "input_schema": input_schema,
        "output_schema": output_schema,
        "verification_endpoint": parsed.get("verification_endpoint"),
        "verification_cases": parsed.get("verification_cases") if isinstance(parsed.get("verification_cases"), list) else [],
    }


def _parse_markdown_key_values(text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        parsed[key.strip().lower()] = value.strip()
    return parsed


def _run_sandbox_precheck(kernel: Any, *, session_id: str, extracted: dict[str, Any]) -> dict[str, Any]:
    method = getattr(kernel, "run_thought_sandbox_simulation", None)
    if not callable(method):
        raise RuntimeError("G12 requires G9 thought sandbox service")
    return method(
        session_id=session_id,
        action_type="register_capability",
        action_payload={
            "target": "capabilities_store",
            "tool_name": extracted["tool_name"],
            "input_schema": extracted["input_schema"],
            "output_schema": extracted["output_schema"],
        },
        risk_level="medium",
        task_type="tool_learning",
        domain="general",
        catastrophe_threshold=0.85,
    )


def _verify_capability(
    *,
    source_kind: str,
    endpoint: Optional[str],
    cases: list[dict[str, Any]],
    timeout_seconds: float,
) -> dict[str, Any]:
    if source_kind != REAL_DOCUMENT:
        return {
            "verification_status": "simulated_learned",
            "registered": False,
            "reason": "static_catalog_sample_cannot_be_real_verified",
            "receipts": [],
            "failure_samples": [],
        }
    if not endpoint or not cases:
        return {
            "verification_status": "simulated_learned",
            "registered": False,
            "reason": "missing_real_verification_endpoint_or_cases",
            "receipts": [],
            "failure_samples": [],
        }

    receipts: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        case_input = case.get("input")
        expected = case.get("expected_output")
        if not isinstance(case_input, dict) or not isinstance(expected, dict):
            failures.append({"case_index": index, "reason": "invalid_case_schema", "case": case})
            continue
        try:
            response = requests.post(endpoint, json=case_input, timeout=timeout_seconds)
            response.raise_for_status()
            actual = response.json()
        except Exception as exc:
            failures.append({"case_index": index, "reason": exc.__class__.__name__, "message": str(exc)})
            continue
        mismatches = [
            {"field": key, "expected": value, "actual": actual.get(key)}
            for key, value in expected.items()
            if actual.get(key) != value
        ]
        receipt = {
            "case_index": index,
            "endpoint": endpoint,
            "input": case_input,
            "expected_output": expected,
            "actual_output": actual,
            "passed": not mismatches,
            "mismatches": mismatches,
        }
        receipts.append(receipt)
        if mismatches:
            failures.append({"case_index": index, "reason": "output_mismatch", "mismatches": mismatches})

    if failures:
        return {
            "verification_status": "verification_failed",
            "registered": False,
            "reason": "real_verification_failed",
            "receipts": receipts,
            "failure_samples": failures,
        }
    return {
        "verification_status": "real_verified",
        "registered": True,
        "reason": "all_real_verification_cases_passed",
        "receipts": receipts,
        "failure_samples": [],
    }


def _persist_memory(kernel: Any, record: dict[str, Any]) -> str | None:
    memory_service = getattr(kernel, "_memory_service", None)
    if memory_service is None or not callable(getattr(memory_service, "remember", None)):
        return None
    memory = memory_service.remember(
        title=f"G12 tool knowledge {record['tool_knowledge_record']['tool_name']}",
        summary=f"G12 {record['tool_knowledge_record']['verification_status']} {record['tool_knowledge_record']['tool_name']}",
        content=json.dumps(record, ensure_ascii=False, sort_keys=True),
        layer="procedural",
        source="g12_dynamic_tool_learning",
        trace_id=record["knowledge_id"],
        target_id=record["capability_id"] or record["knowledge_id"],
        tags=["G12", "dynamic_tool_learning", record["tool_knowledge_record"]["verification_status"]],
        tool_learning_record=record,
    )
    memory_id = str(getattr(memory, "memory_id", "") or "")
    if memory_id and getattr(memory_service.get_record(memory_id), "memory_id", None) != memory_id:
        raise RuntimeError(f"G12 memory writeback query verification failed: {memory_id}")
    return memory_id or None


def _cache_record(kernel: Any, attr: str, key: str, record: dict[str, Any]) -> None:
    if not hasattr(kernel, attr):
        setattr(kernel, attr, {})
    getattr(kernel, attr)[key] = record


def _append_transcript(state: Any, record: dict[str, Any], entry_type: str) -> None:
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=record["session_id"],
            payload={"feature_code": "G12", "entry_type": entry_type, **record},
        )
    )

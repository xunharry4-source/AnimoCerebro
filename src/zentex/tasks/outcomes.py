from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from zentex.tasks.models import ZentexTask
from zentex.tasks.models.errors import TaskStateError


def record_task_outcome(
    *,
    outcome_dao: Any,
    task: ZentexTask,
    result: Dict[str, Any],
    verification_result: Any,
) -> Dict[str, Any]:
    if not outcome_dao:
        raise TaskStateError("Task outcome DAO is unavailable")

    verification_payload = (
        verification_result.model_dump(mode="json")
        if hasattr(verification_result, "model_dump")
        else dict(verification_result)
    )
    actual_outcome = result.get("actual_outcome") if isinstance(result, dict) else None
    deviation_report = {
        "summary": verification_payload.get("summary", ""),
        "recommendation": verification_payload.get("recommendation", ""),
        "failed_verifiers": [
            item.get("verifier_id")
            for item in verification_payload.get("verifier_results", [])
            if not item.get("passed")
        ],
    }
    outcome_data = {
        "task_id": task.task_id,
        "trace_id": str(task.metadata.get("trace_id") or ""),
        "objective_profile": task.metadata.get("objective_profile"),
        "evaluation_profile": task.metadata.get("evaluation_profile"),
        "expected_outcome": task.contract.expected_outcome,
        "success_criteria": task.contract.success_criteria,
        "acceptance_conditions": task.contract.acceptance_conditions,
        "risk_assessment": task.contract.risk_assessment,
        "actual_outcome": actual_outcome if actual_outcome is not None else result,
        "deviation_report": deviation_report,
        "verification_result": verification_payload,
        "overall_passed": bool(verification_payload.get("overall_passed")),
        "confidence_score": verification_payload.get("confidence_score"),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if not outcome_dao.upsert_outcome(outcome_data):
        raise TaskStateError(f"Failed to persist task outcome for {task.task_id}")
    return outcome_data


def _task_metadata(task: ZentexTask) -> Dict[str, Any]:
    metadata = getattr(task, "metadata", None)
    return dict(metadata) if isinstance(metadata, dict) else {}


def _actual_outcome_dict(outcome: Dict[str, Any]) -> Dict[str, Any]:
    actual = outcome.get("actual_outcome")
    return dict(actual) if isinstance(actual, dict) else {}


def _executor_context(task: ZentexTask, outcome: Dict[str, Any]) -> Dict[str, Any]:
    metadata = _task_metadata(task)
    actual = _actual_outcome_dict(outcome)
    execution_evidence = actual.get("execution_evidence") if isinstance(actual.get("execution_evidence"), dict) else {}
    executor_type = str(
        execution_evidence.get("executor_type")
        or metadata.get("executor_type")
        or metadata.get("external_executor_type")
        or ""
    ).strip()
    return {
        "executor_type": executor_type,
        "tool_name": str(
            execution_evidence.get("tool_name")
            or metadata.get("cli_tool_name")
            or metadata.get("external_connector_capability")
            or metadata.get("tool_name")
            or ""
        ).strip(),
        "connector_id": str(metadata.get("external_connector_id") or "").strip(),
        "execution_evidence": execution_evidence,
    }


def _risk_signal_payload(task: ZentexTask, outcome: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    risk_signal = str(metadata.get("risk_signal") or "").strip()
    if not risk_signal:
        return {}
    dataset_id = str(metadata.get("dataset_id") or "").strip()
    trace_id = str(outcome.get("trace_id") or metadata.get("trace_id") or "")
    return {
        "learning_type": str(metadata.get("learning_type") or "evolution_rule"),
        "source_trace_id": trace_id,
        "dataset_id": dataset_id,
        "risk_signal": risk_signal,
        "best_practice": str(
            metadata.get("best_practice")
            or metadata.get("recommended_best_practice")
            or f"precheck and isolate risk signal before continuing: {risk_signal}"
        ),
        "avoid_pattern": str(
            metadata.get("avoid_pattern")
            or metadata.get("recommended_avoid_pattern")
            or f"do not continue the full workflow while risk signal remains unresolved: {risk_signal}"
        ),
        "trigger_condition": {
            "dataset_fingerprint": str(metadata.get("dataset_fingerprint") or ""),
            "risk_signal": risk_signal,
            "observed_count": int(metadata.get("observed_count") or 1),
            "evidence_ref": str(metadata.get("evidence_ref") or outcome.get("task_id") or task.task_id),
        },
        "recommended_next_action": str(
            metadata.get("recommended_next_action")
            or metadata.get("risk_precheck_action")
            or f"run a focused precheck for risk signal: {risk_signal}"
        ),
    }


def _risk_signal_reflection_payload(task: ZentexTask, outcome: Dict[str, Any], metadata: Dict[str, Any], summary: str) -> Dict[str, Any]:
    risk_signal = str(metadata.get("risk_signal") or "").strip()
    if not risk_signal:
        return {}
    return {
        "reflection_type": str(metadata.get("reflection_type") or "evolution_adjustment"),
        "source_trace_id": str(outcome.get("trace_id") or metadata.get("trace_id") or ""),
        "dataset_id": str(metadata.get("dataset_id") or "").strip(),
        "risk_signal": risk_signal,
        "root_cause": str(
            metadata.get("root_cause")
            or metadata.get("risk_root_cause")
            or f"verification failed with unresolved risk signal: {risk_signal}"
        ),
        "system_limitation": str(
            metadata.get("system_limitation")
            or f"workflow continued to execution without resolving risk signal: {risk_signal}"
        ),
        "actionable_adjustment": {
            "q4_add_action": str(metadata.get("risk_precheck_action") or "precheck_risk_signal"),
            "q9_posture_hint": str(metadata.get("q9_posture_hint") or "cautious_slow"),
            "fallback_path": str(metadata.get("fallback_path") or "q7_risk_recovery_path"),
        },
        "verification_summary": summary,
        "evidence_ref": f"task_outcome:{task.task_id}",
    }


def _derive_learning_fields(task: ZentexTask, outcome: Dict[str, Any]) -> Dict[str, Any]:
    context = _executor_context(task, outcome)
    executor_type = context["executor_type"]
    tool_name = context["tool_name"]
    metadata = _task_metadata(task)
    verification = outcome.get("verification_result") if isinstance(outcome.get("verification_result"), dict) else {}
    actual_outcome = _actual_outcome_dict(outcome)
    if actual_outcome.get("resource_recovery") == "complete":
        return {
            "best_practice": (
                "For future resource recovery tasks, run data path checks and CLI health probe before dispatch, "
                "request missing files or credentials through HITL, re-evaluate Q1/Q3/Q7/Q8/Q9 after the repair, "
                "and preserve physical evidence plus state_transition_history before accepting completion."
            ),
            "avoid_pattern": (
                "Do not resume blocked resource-gap work until the missing file exists, a credential or fallback executor "
                "is approved, and the refreshed context shows the recovery path is clear."
            ),
        }
    if outcome.get("overall_passed") is False and executor_type in {"", "internal"}:
        failed_verifiers = [
            str(item.get("verifier_id") or "")
            for item in verification.get("verifier_results", [])
            if isinstance(item, dict) and item.get("passed") is not True
        ]
        risk_signal_fields = _risk_signal_payload(task, outcome, metadata)
        if risk_signal_fields:
            return risk_signal_fields
        return {
            "best_practice": (
                "For future verification-failed tasks, keep the task out of DONE, preserve the physical evidence path, "
                "contract expectations, verifier_results, failed verifier ids, and remediation guidance before retrying. "
                f"Failed verifiers: {', '.join(item for item in failed_verifiers if item) or 'unknown'}."
            ),
            "avoid_pattern": (
                "Do not write successful Memory or mark the task as passed when verification_result.overall_passed is false, "
                "physical evidence is missing or mismatched, expected contract text is absent, or verifier details cannot be "
                "re-read from the persisted outcome."
            ),
        }
    if executor_type == "cli":
        label = f"CLI tool {tool_name}" if tool_name else "CLI executor"
        return {
            "best_practice": (
                f"For future {label} tasks, run a real health probe first, preserve command arguments, "
                "stdout/stderr summaries, trace_id, and physical evidence paths before accepting the outcome. "
                "When the tool was newly registered, verify the capability propagated from registry to Q3 inventory, "
                "Q4 action mapping, and Q8 selection rationale before dispatch."
            ),
            "avoid_pattern": (
                "Do not mark CLI work as passed when the binary is unavailable, arguments were preflight_blocked, "
                "authentication failed, expected physical evidence cannot be re-read from disk, or Q8 selected the "
                "target without registry-backed Q3/Q4 propagation and non-selected candidate rationale."
            ),
        }
    if executor_type == "mcp":
        label = f"MCP tool {tool_name}" if tool_name else "MCP executor"
        return {
            "best_practice": (
                f"For future {label} tasks, run a real health probe before dispatch, preserve the server id, "
                "tool schema snapshot, permission scope, query assertions, JSON path results, rate limit "
                "observations, response evidence path, and any authorized replacement capability registration."
            ),
            "avoid_pattern": (
                "Do not mark MCP work as passed when the server is unavailable, the tool is missing, schema validation "
                "fails, permission scope is unclear, replacement Q5/Q6 authorization is missing, or JSON path assertions "
                "are not verified against the real payload."
            ),
        }
    if executor_type == "external_connector":
        connector_label = context["connector_id"] or "external connector"
        capability_label = tool_name or "connector capability"
        return {
            "best_practice": (
                f"For future {connector_label}/{capability_label} tasks, require real connector health probing, "
                "unique session_id/trace_id filters, read-after-write or post-query verification, permission-bound "
                "collection scope, and cleanup evidence before accepting remote side effects."
            ),
            "avoid_pattern": (
                "Do not mark MongoDB connector work as passed when create/update/delete only reports counts, "
                "the read-back document is missing or mismatched, the filter lacks traceability, write concern or "
                "permission scope is unclear, or cleanup cannot be verified."
            ),
        }
    if executor_type == "agent":
        return {
            "best_practice": (
                "For future Agent tasks, verify live health first, bind external_task_ref, invocation_id, "
                "zentex_task_id, and trace_id in the invocation ledger, then read the Agent-side task or business "
                "object back by external_task_ref before accepting completion. For callback mode, also verify the "
                "callback token and duplicate callback idempotency."
            ),
            "avoid_pattern": (
                "Do not mark Agent work as passed when dispatch merely returns OK but the Agent-side object cannot "
                "be read back, the trace_id is missing or mismatched, the expected chapter/novel/world object is "
                "absent or content-mismatched, callback status is failed or uncertain, or repeated callbacks create "
                "duplicate outcomes."
            ),
        }
    return {
        "best_practice": (
            "For future task outcomes, preserve executor evidence, verification details, trace_id, and outcome context "
            "before recording completion."
        ),
        "avoid_pattern": (
            "Do not treat a task as learned from if the outcome lacks executor evidence, verification result, or trace linkage."
        ),
    }


def _derive_reflection_fields(task: ZentexTask, outcome: Dict[str, Any]) -> Dict[str, Any]:
    context = _executor_context(task, outcome)
    executor_type = context["executor_type"]
    metadata = _task_metadata(task)
    verification = outcome.get("verification_result") if isinstance(outcome.get("verification_result"), dict) else {}
    summary = str(verification.get("summary") or outcome.get("deviation_report") or "").strip()
    actual_outcome = _actual_outcome_dict(outcome)
    if actual_outcome.get("resource_recovery") == "complete":
        return {
            "root_cause": (
                "The original task was blocked because required data or preferred execution capability was unavailable. "
                f"Verification summary: {summary}"
            ),
            "actionable_adjustment": (
                "Next similar workflow should precheck required files, CLI credential health, and fallback executor readiness, "
                "then request HITL repair before dispatching the business task."
            ),
        }
    if outcome.get("overall_passed") is False and executor_type in {"", "internal"}:
        risk_signal_fields = _risk_signal_reflection_payload(task, outcome, metadata, summary)
        if risk_signal_fields:
            return risk_signal_fields
        return {
            "root_cause": (
                "Task execution reached the verification stage, but the persisted verifier result did not satisfy the "
                f"contract. The failure must be treated as real because the verifier read the submitted evidence and "
                f"reported: {summary}"
            ),
            "actionable_adjustment": (
                "Next run should keep the task failed until the physical evidence is corrected, the contract is revised, "
                "or the verifier is rerun successfully. Do not create successful Memory writeback for this task; record "
                "only failure-oriented Learning/Reflection with the remediation path."
            ),
        }
    if executor_type == "cli":
        return {
            "root_cause": (
                "CLI task quality depends on real subprocess health, argument safety, exit code, and physical evidence "
                f"verification. Capability routing also depends on registry -> Q3 -> Q4 -> Q8 propagation evidence. "
                f"Verification summary: {summary}"
            ),
            "actionable_adjustment": (
                "Next similar CLI task should block early on CLI_NOT_FOUND or dangerous arguments, retain evidence artifacts, "
                "require read-after-execute verification before writeback, and preserve Q8 selection rationale explaining "
                "why the chosen capability beat other registered candidates."
            ),
        }
    if executor_type == "external_connector":
        return {
            "root_cause": (
                "External connector task quality depends on real remote side effects, permission scope, traceable filters, "
                f"and read-after-write evidence. Verification summary: {summary}"
            ),
            "actionable_adjustment": (
                "Next MongoDB connector task should ping the real connector first, write only session-scoped documents, "
                "verify create/read/update/delete with post-query evidence, and clean up by the same unique filter."
            ),
        }
    if executor_type == "mcp":
        return {
            "root_cause": (
                "MCP task quality depends on real server health, tool availability, schema stability, permission scope, "
                f"and JSON path verification. Verification summary: {summary}"
            ),
            "actionable_adjustment": (
                "Next similar MCP task should run a health probe first, block on MCP_SERVER_UNAVAILABLE or "
                "MCP_TOOL_NOT_FOUND, use only replacement capabilities with Q5/Q6 authorization evidence, retain a "
                "redacted response evidence file, and require JSON path assertion coverage before writeback."
            ),
        }
    if executor_type == "agent":
        return {
            "root_cause": (
                "Agent task quality depends on a live Agent health probe, a bidirectional invocation ledger, matching "
                f"external_task_ref, stable trace_id, and Agent-side business object readback. Verification summary: {summary}"
            ),
            "actionable_adjustment": (
                "Next Agent task should block if health or scope fails, call the Agent readback API by external_task_ref, "
                "verify the returned object id/title/content and Zentex trace metadata, reject wrong-token or unknown-ref "
                "callbacks in callback mode, and verify replay before writing successful memory, learning, and reflection records."
            ),
        }
    return {
        "root_cause": f"Task outcome was determined from executor output and verification result. {summary}",
        "actionable_adjustment": (
            "Next similar task should keep explicit evidence_ref, verification_result, and failure reason attached to the "
            "task outcome before memory, learning, and reflection writeback."
        ),
    }


def write_task_outcome_to_reflection(task_service: Any, reflection_service: Any, task_id: str) -> Dict[str, Any]:
    if not task_id:
        raise TaskStateError("task_id is required for task outcome reflection writeback")
    outcome_dao = _require_outcome_dao(task_service)
    if reflection_service is None or not callable(
        getattr(reflection_service, "record_nine_question_reflection", None)
    ):
        raise TaskStateError("Reflection service with record_nine_question_reflection is required")

    outcome = _require_outcome(task_service, task_id, "reflection")
    existing_reflection_id = str(outcome.get("reflection_id") or "").strip()
    if existing_reflection_id:
        existing_reflection = reflection_service.get_reflection(existing_reflection_id)
        if getattr(existing_reflection, "reflection_id", None) != existing_reflection_id:
            raise TaskStateError(f"Persisted reflection_id does not resolve for task outcome: {task_id}")
        return {"created": False, "reflection_id": existing_reflection_id, "task_outcome": outcome}

    task = _require_task(task_service, task_id, "reflection")
    from zentex.reflection.models import ReflectionType

    trace_id = str(outcome.get("trace_id") or task.metadata.get("trace_id") or "") or None
    actual_outcome = outcome.get("actual_outcome")
    overall_passed = outcome.get("overall_passed")
    summary = f"Task outcome {'passed' if overall_passed else 'failed'} for {task.title}: {actual_outcome}"
    reflection_fields = _derive_reflection_fields(task, outcome)
    reflection = reflection_service.record_nine_question_reflection(
        subject=f"Task outcome reflection: {task.title}",
        reflection_type=ReflectionType.OUTCOME_REFLECTION,
        trace_id=trace_id,
        context={
            "source": "task_outcome_writeback",
            "question_id": task.metadata.get("question_id"),
            "task_id": task.task_id,
            "task_title": task.title,
            "task_status": _status_value(task),
            "overall_passed": overall_passed,
            "expected_outcome": outcome.get("expected_outcome"),
            "actual_outcome": actual_outcome,
            "success_criteria": outcome.get("success_criteria"),
            "acceptance_conditions": outcome.get("acceptance_conditions"),
            "deviation_report": outcome.get("deviation_report"),
            "verification_result": outcome.get("verification_result"),
            "summary": summary,
            **reflection_fields,
        },
    )
    reflection_id = str(getattr(reflection, "reflection_id", "") or "")
    if not reflection_id:
        raise TaskStateError(f"Reflection writeback did not return a reflection_id for task {task_id}")

    queried_reflection = reflection_service.get_reflection(reflection_id)
    if getattr(queried_reflection, "context", {}).get("task_id") != task_id:
        raise TaskStateError(f"Reflection writeback query verification failed for task {task_id}")

    if not outcome_dao.mark_reflection_written(task_id, reflection_id):
        raise TaskStateError(f"Failed to mark task outcome reflection writeback for {task_id}")
    updated_outcome = _verify_updated_outcome(task_service, task_id, "reflection_id", reflection_id)
    if updated_outcome.get("written_back_to_reflection") is not True:
        raise TaskStateError(f"Task outcome reflection flag query verification failed for {task_id}")
    return {"created": True, "reflection_id": reflection_id, "task_outcome": updated_outcome}


def write_task_outcome_to_memory(task_service: Any, memory_service: Any, task_id: str) -> Dict[str, Any]:
    if not task_id:
        raise TaskStateError("task_id is required for task outcome memory writeback")
    outcome_dao = _require_outcome_dao(task_service)
    if memory_service is None or not callable(getattr(memory_service, "remember", None)):
        raise TaskStateError("Memory service with remember is required")
    if not callable(getattr(memory_service, "get_record", None)):
        raise TaskStateError("Memory service with get_record is required")

    outcome = _require_outcome(task_service, task_id, "memory")
    existing_memory_id = str(outcome.get("memory_id") or "").strip()
    if existing_memory_id:
        existing_memory = memory_service.get_record(existing_memory_id)
        if getattr(existing_memory, "memory_id", None) != existing_memory_id:
            raise TaskStateError(f"Persisted memory_id does not resolve for task outcome: {task_id}")
        return {"created": False, "memory_id": existing_memory_id, "task_outcome": outcome}

    task = _require_task(task_service, task_id, "memory")
    trace_id = str(outcome.get("trace_id") or task.metadata.get("trace_id") or "")
    actual_outcome = outcome.get("actual_outcome")
    overall_passed = outcome.get("overall_passed")
    title = f"Task outcome memory: {task.title}"
    summary = f"Task outcome {'passed' if overall_passed else 'failed'} for {task.title}"
    content = (
        f"{summary}\n"
        f"task_id: {task.task_id}\n"
        f"success_criteria: {outcome.get('success_criteria')}\n"
        f"actual_outcome: {actual_outcome}\n"
        f"deviation_report: {outcome.get('deviation_report')}"
    )
    memory = memory_service.remember(
        title=title,
        summary=summary,
        content=content,
        layer="procedural",
        source="task_outcome_writeback",
        trace_id=trace_id or None,
        target_id=task.task_id,
        tags=["task_outcome", "q8", "verified" if overall_passed else "failed"],
        task_id=task.task_id,
        question_id=task.metadata.get("question_id"),
        expected_outcome=outcome.get("expected_outcome"),
        actual_outcome=actual_outcome,
        success_criteria=outcome.get("success_criteria"),
        acceptance_conditions=outcome.get("acceptance_conditions"),
        deviation_report=outcome.get("deviation_report"),
        verification_result=outcome.get("verification_result"),
        overall_passed=overall_passed,
    )
    memory_id = str(getattr(memory, "memory_id", "") or "")
    if not memory_id:
        raise TaskStateError(f"Memory writeback did not return a memory_id for task {task_id}")

    queried_memory = memory_service.get_record(memory_id)
    if getattr(queried_memory, "memory_id", None) != memory_id:
        raise TaskStateError(f"Memory writeback query verification failed for task {task_id}")
    if getattr(queried_memory, "target_id", None) != task_id:
        raise TaskStateError(f"Memory writeback target query verification failed for task {task_id}")

    if not outcome_dao.mark_memory_written(task_id, memory_id):
        raise TaskStateError(f"Failed to mark task outcome memory writeback for {task_id}")
    updated_outcome = _verify_updated_outcome(task_service, task_id, "memory_id", memory_id)
    if updated_outcome.get("written_back_to_memory") is not True:
        raise TaskStateError(f"Task outcome memory flag query verification failed for {task_id}")
    return {"created": True, "memory_id": memory_id, "task_outcome": updated_outcome}


def write_task_outcome_to_learning(task_service: Any, learning_service: Any, task_id: str) -> Dict[str, Any]:
    if not task_id:
        raise TaskStateError("task_id is required for task outcome learning writeback")
    outcome_dao = _require_outcome_dao(task_service)
    if learning_service is None or not callable(
        getattr(learning_service, "record_nine_question_learning", None)
    ):
        raise TaskStateError("Learning service with record_nine_question_learning is required")
    if not callable(getattr(learning_service, "query_overall_records", None)):
        raise TaskStateError("Learning service with query_overall_records is required")

    outcome = _require_outcome(task_service, task_id, "learning")
    existing_learning_trace_id = str(outcome.get("learning_trace_id") or "").strip()
    if existing_learning_trace_id:
        existing_records = learning_service.query_overall_records(limit=20, trace_id=existing_learning_trace_id)
        if not any(record.detail.get("task_id") == task_id for record in existing_records):
            raise TaskStateError(f"Persisted learning_trace_id does not resolve for task outcome: {task_id}")
        return {"created": False, "learning_trace_id": existing_learning_trace_id, "task_outcome": outcome}

    task = _require_task(task_service, task_id, "learning")
    source_trace_id = str(outcome.get("trace_id") or task.metadata.get("trace_id") or "")
    overall_passed = outcome.get("overall_passed")
    actual_outcome = outcome.get("actual_outcome")
    summary = f"Learned from task outcome {'passed' if overall_passed else 'failed'}: {task.title}"
    learning_fields = _derive_learning_fields(task, outcome)
    learning = learning_service.record_nine_question_learning(
        question_id=str(task.metadata.get("question_id") or "q8"),
        learning_kind="task_outcome_writeback",
        trace_id=source_trace_id or task.task_id,
        detail={
            "summary": summary,
            "source": "task_outcome_writeback",
            "source_trace_id": source_trace_id,
            "task_id": task.task_id,
            "task_title": task.title,
            "task_status": _status_value(task),
            "overall_passed": overall_passed,
            "expected_outcome": outcome.get("expected_outcome"),
            "actual_outcome": actual_outcome,
            "success_criteria": outcome.get("success_criteria"),
            "acceptance_conditions": outcome.get("acceptance_conditions"),
            "deviation_report": outcome.get("deviation_report"),
            "verification_result": outcome.get("verification_result"),
            "question_driver_refs": [str(task.metadata.get("question_id") or "q8")],
            **learning_fields,
        },
    )
    learning_trace_id = str(getattr(learning, "trace_id", "") or "")
    if not learning_trace_id:
        raise TaskStateError(f"Learning writeback did not return a trace_id for task {task_id}")

    queried_records = learning_service.query_overall_records(limit=20, trace_id=learning_trace_id)
    matching_records = [record for record in queried_records if record.detail.get("task_id") == task_id]
    if len(matching_records) != 1:
        raise TaskStateError(f"Learning writeback query verification failed for task {task_id}")
    if matching_records[0].detail.get("actual_outcome") != actual_outcome:
        raise TaskStateError(f"Learning writeback actual outcome mismatch for task {task_id}")

    if not outcome_dao.mark_learning_written(task_id, learning_trace_id):
        raise TaskStateError(f"Failed to mark task outcome learning writeback for {task_id}")
    updated_outcome = _verify_updated_outcome(task_service, task_id, "learning_trace_id", learning_trace_id)
    if updated_outcome.get("written_back_to_learning") is not True:
        raise TaskStateError(f"Task outcome learning flag query verification failed for {task_id}")
    return {"created": True, "learning_trace_id": learning_trace_id, "task_outcome": updated_outcome}


def _require_outcome_dao(task_service: Any) -> Any:
    outcome_dao = getattr(task_service, "_outcome_dao", None)
    if not outcome_dao:
        raise TaskStateError("Task outcome DAO is unavailable")
    return outcome_dao


def _require_outcome(task_service: Any, task_id: str, target: str) -> Dict[str, Any]:
    outcome = task_service.get_task_outcome(task_id)
    if outcome is None:
        raise TaskStateError(f"Task outcome not found for {target} writeback: {task_id}")
    return outcome


def _require_task(task_service: Any, task_id: str, target: str) -> ZentexTask:
    task = task_service.get_task(task_id)
    if task is None:
        raise TaskStateError(f"Task not found for {target} writeback: {task_id}")
    return task


def _verify_updated_outcome(
    task_service: Any,
    task_id: str,
    field_name: str,
    expected_value: str,
) -> Dict[str, Any]:
    updated_outcome = task_service.get_task_outcome(task_id)
    if not updated_outcome or updated_outcome.get(field_name) != expected_value:
        raise TaskStateError(f"Task outcome {field_name} marker query verification failed for {task_id}")
    return updated_outcome


def _status_value(task: ZentexTask) -> str:
    return task.status.value if hasattr(task.status, "value") else str(task.status)

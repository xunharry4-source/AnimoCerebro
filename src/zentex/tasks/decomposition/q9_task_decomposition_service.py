from __future__ import annotations

from zentex.tasks.management.service_context import *
from zentex.tasks.decomposition.q9_child_payload_builder import build_q9_child_payload
from zentex.tasks.decomposition.q9_task_decomposition_helpers import (
    q9_assignment_result_payload,
    q9_candidate_registry_payload,
    q9_created_dependency_graph,
    q9_existing_assignment_results,
    q9_existing_dependency_graph,
)
from zentex.common.observable_logging import observable_event


def _task_split_log(event: str, **fields: Any) -> None:
    observable_event(
        logger,
        event,
        component="zentex.tasks.q9_subtask_splitter",
        question_id="q9",
        **fields,
    )


def _q9_blueprint_step_details(step_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    for index, record in enumerate(step_records):
        details.append(
            {
                "step_index": index,
                "step_name": record.get("title"),
                "step_goal": record.get("objective"),
                "verification_method": record.get("verification_method") or "",
                "q9_verification_hint": record.get("q9_verification_hint") or "",
                "required_resources": record.get("required_resources") if isinstance(record.get("required_resources"), list) else [],
            }
        )
    return details


def _q9_routable_required_resources(
    resources: List[str],
    *,
    plan_type: str,
    target_id: str,
    executor_type: str,
    required_capabilities: List[str],
) -> List[str]:
    if plan_type != "external" or target_id or executor_type != "external_connector":
        return list(resources)
    explicit_capabilities = [
        str(item or "").strip()
        for item in required_capabilities
        if str(item or "").strip() and not str(item or "").strip().startswith(("external_connector:", "connector:"))
    ]
    if not explicit_capabilities:
        return list(resources)
    cleaned: List[str] = []
    for resource in resources:
        text = str(resource or "").strip()
        if not text:
            continue
        owner_text = text
        for prefix in ("执行方钦定：", "执行方钦定:"):
            if owner_text.startswith(prefix):
                owner_text = owner_text[len(prefix):].strip()
                break
        if owner_text.startswith(("external_connector:", "connector:")):
            continue
        cleaned.append(text)
    for capability in explicit_capabilities:
        if capability not in cleaned:
            cleaned.append(capability)
    return cleaned


def _strip_q9_resource_prefix(value: Any) -> str:
    text = str(value or "").strip()
    for prefix in (
        "功能：",
        "功能:",
        "任务资源：",
        "任务资源:",
        "能力需求：",
        "能力需求:",
        "执行方钦定：",
        "执行方钦定:",
    ):
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _q9_external_owner_only_blueprint_violations(step_records: List[Dict[str, Any]], blueprint: Dict[str, Any]) -> List[Dict[str, Any]]:
    invalid: List[Dict[str, Any]] = []
    blueprint_resources = list(blueprint.get("required_resources") or [])
    for index, record in enumerate(step_records):
        raw_resources = [
            *list(record.get("required_resources") or []),
            *blueprint_resources,
        ]
        resources = [_strip_q9_resource_prefix(item) for item in raw_resources if str(item or "").strip()]
        owner_refs = [
            item for item in resources
            if item.startswith(("external_connector:", "connector:"))
        ]
        concrete_capabilities = [
            item for item in resources
            if item
            and not item.startswith(("internal:", "cli:", "mcp:", "agent:", "external_connector:", "connector:"))
            and item not in {"external", "external:g31a_task_center"}
        ]
        if owner_refs and not concrete_capabilities:
            invalid.append(
                {
                    "subtask_index": index,
                    "violation_type": "fake_execution_party",
                    "violation_detail": (
                        "Q9 外部蓝图只指定了 connector owner，没有指定该 connector registry 声明的具体业务 capability；"
                        "G31A 禁止创建 owner-only 外部子任务。"
                    ),
                }
            )
    return invalid


def _q9_external_connector_arguments(metadata: Dict[str, Any], *, capability: str) -> Dict[str, Any]:
    mapping = metadata.get("q9_external_connector_arguments")
    if isinstance(mapping, dict):
        candidate = mapping.get(capability) or mapping.get("*")
        if isinstance(candidate, dict):
            return dict(candidate)
    direct = metadata.get("external_connector_arguments")
    if isinstance(direct, dict):
        return dict(direct)
    return {}


async def _fail_q9_subtask_split_validation_before_child_creation(
    self: Any,
    q9_task: ZentexTask,
    *,
    metadata: Dict[str, Any],
    plan_type: str,
    invalid_subtasks: List[Dict[str, Any]],
) -> None:
    validation_report = {
        "SubtaskSplittingValidationReport": {
            "is_compliant": False,
            "compliance_score": 0.0,
            "invalid_subtasks": invalid_subtasks,
            "improvement_suggestion": (
                "Q9 外部蓝图缺少具体可执行业务 capability；必须修正 Q9 输出或上游 Q8 capability 后重新生成，"
                "禁止创建 owner-only 外部子任务。"
            ),
            "original_task_intent": metadata.get("q9_q8_task") or {},
            "checked_dimensions": [
                "objective_alignment",
                "execution_party_authenticity",
                "zero_trust_verification_method",
                "granularity_check",
            ],
        }
    }
    q9_task.status = TaskStatus.FAILED
    q9_task.last_error = "Q9 subtask splitting compliance validation failed"
    q9_task.metadata = {
        **q9_task.metadata,
        "worker_dispatch_enabled": False,
        "q9_subtask_splitting_validation": validation_report,
        "g31a_decomposition": {
            "status": "failed",
            "error_code": "q9_subtask_splitting_validation_failed",
            "validation_report": validation_report,
            "subtask_ids": [],
            "pre_child_creation": True,
        },
    }
    q9_task.last_updated_at = datetime.now(timezone.utc)
    self._shared_tasks.set(q9_task.task_id, q9_task)
    self._tasks[q9_task.task_id] = q9_task
    if self.use_database and not self._sync_task_to_database(q9_task):
        raise TaskStateError(f"Failed to persist Q9 subtask validation failure for task {q9_task.task_id}")
    self._record_audit(
        q9_task.task_id,
        "Q9_SUBTASK_SPLITTING_VALIDATION_FAILED",
        {
            "event": "q9_subtask_splitting_validation_failed",
            "plan_type": plan_type,
            "validation_report": validation_report,
            "pre_child_creation": True,
        },
    )
    _task_split_log(
        "q9_subtask_split_validation_failed",
        parent_task_id=q9_task.task_id,
        session_id=metadata.get("session_id"),
        trace_id=metadata.get("q9_trace_id"),
        plan_type=plan_type,
        child_task_ids=[],
        validation_report=validation_report,
        pre_child_creation=True,
    )
    raise TaskStateError(q9_task.last_error)


def _q9_subtask_detail(child: ZentexTask, *, parent_task_id: str, plan_type: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    child_metadata = child.metadata if isinstance(child.metadata, dict) else {}
    contract = getattr(child, "contract", None)
    q9_verification_hint = str(child_metadata.get("q9_verification_hint") or child_metadata.get("q9_blueprint_verification_hint") or "").strip()
    verification_method = q9_verification_hint
    if not verification_method and contract is not None:
        verification_method = str(getattr(contract, "verification_method", "") or "").strip()
    if not verification_method:
        acceptance = child_metadata.get("acceptance_criteria")
        verification_method = "；".join(str(item or "").strip() for item in acceptance if str(item or "").strip()) if isinstance(acceptance, list) else ""
    return {
        "parent_task_id": parent_task_id,
        "child_task_id": child.task_id,
        "session_id": metadata.get("session_id"),
        "trace_id": metadata.get("q9_trace_id"),
        "plan_type": plan_type,
        "step_index": child_metadata.get("q9_blueprint_step_index"),
        "subtask_name": child.title,
        "executor_ref": child_metadata.get("owner_ref") or child.target_id,
        "assignment_status": child_metadata.get("assignment_status"),
        "executor_type": child_metadata.get("executor_type"),
        "subtask_goal": child_metadata.get("objective") or child.remarks or child.title,
        "verification_method": verification_method,
        "q9_verification_hint": q9_verification_hint,
        "internal_verification_contract": child_metadata.get("internal_verification_contract"),
        "status": child.status.value,
        "depends_on": list(child.depends_on or []),
    }


async def decompose_q9_blueprint_task(service: Any, q9_task: ZentexTask) -> List[ZentexTask]:
    self = service
    """
    Decompose a Q9 blueprint handoff into G31A-owned executable subtasks.

    Q9 only synchronizes the strategy blueprint. This task-center method owns
    concrete subtask registration, dependency ordering, and executor binding.
    """
    metadata = q9_task.metadata if isinstance(q9_task.metadata, dict) else {}
    if metadata.get("source_module") != "nine_questions.q9":
        return []
    if metadata.get("sync_boundary") != "blueprint_only":
        return []

    plan_type = str(metadata.get("q9_plan_type") or "").strip().lower()
    if plan_type not in {"internal", "external"}:
        return []
    blueprint = metadata.get("q9_action_blueprint")
    blueprint = blueprint if isinstance(blueprint, dict) else {}
    step_records = self._q9_blueprint_step_records(blueprint, plan_type)
    lines = [record["line"] for record in step_records]
    capabilities = self._q9_blueprint_capabilities(blueprint, plan_type)
    designated_executors = self._q9_blueprint_designated_executors(blueprint)
    _task_split_log(
        "q9_task_detail",
        parent_task_id=q9_task.task_id,
        session_id=metadata.get("session_id"),
        trace_id=metadata.get("q9_trace_id"),
        request_id=metadata.get("q9_request_id"),
        decision_id=metadata.get("q9_decision_id"),
        plan_type=plan_type,
        q9_task_key=metadata.get("q9_task_key"),
        q9_task_index=metadata.get("q9_task_index"),
        plan_objective=blueprint.get("plan_objective") or blueprint.get("action_objective"),
        q8_task=metadata.get("q9_q8_task"),
        blueprint_step_count=len(lines),
        blueprint_steps=_q9_blueprint_step_details(step_records),
        capabilities=capabilities,
        designated_executors=designated_executors,
    )
    existing_children = sorted(
        self.list_tasks(parent_task_id=q9_task.task_id, limit=500, offset=0),
        key=lambda task: int((task.metadata or {}).get("q9_blueprint_step_index", 0)),
    )
    if existing_children:
        _task_split_log(
            "q9_subtask_split_reuse_detected",
            parent_task_id=q9_task.task_id,
            session_id=metadata.get("session_id"),
            trace_id=metadata.get("q9_trace_id"),
            plan_type=plan_type,
            child_count=len(existing_children),
            child_task_ids=[task.task_id for task in existing_children],
        )
        existing_ids = [task.task_id for task in existing_children]
        existing_dependency_graph = q9_existing_dependency_graph(existing_children)
        existing_assignment_results = q9_existing_assignment_results(existing_children)
        available_tools_registry = q9_candidate_registry_payload(
            self._build_assignment_router().matcher._collect_candidates()
        )
        validation_report = await validate_q9_subtask_splitting_against_llm_output(
            original_task_intent=metadata.get("q9_q8_task") or blueprint.get("plan_objective"),
            q9_action_blueprint=blueprint,
            child_tasks=existing_children,
            available_tools_registry=available_tools_registry,
            plan_type=plan_type,
            llm_service=getattr(self, "_llm_service", None),
        )
        validation_payload = validation_report["SubtaskSplittingValidationReport"]
        if validation_payload.get("is_compliant") is not True:
            for child in existing_children:
                await self.update_task_status(
                    child.task_id,
                    TaskStatus.CANCELLED,
                    "Q9 subtask splitting compliance validation failed",
                )
            q9_task.status = TaskStatus.FAILED
            q9_task.last_error = "Q9 subtask splitting compliance validation failed"
            q9_task.metadata = {
                **q9_task.metadata,
                "worker_dispatch_enabled": False,
                "q9_subtask_splitting_validation": validation_report,
                "g31a_decomposition": {
                    "status": "failed",
                    "error_code": "q9_subtask_splitting_validation_failed",
                    "validation_report": validation_report,
                    "subtask_ids": existing_ids,
                    "idempotent_reuse": True,
                },
            }
            q9_task.last_updated_at = datetime.now(timezone.utc)
            self._shared_tasks.set(q9_task.task_id, q9_task)
            self._tasks[q9_task.task_id] = q9_task
            if self.use_database and not self._sync_task_to_database(q9_task):
                raise TaskStateError(f"Failed to persist idempotent Q9 subtask validation failure for task {q9_task.task_id}")
            self._record_audit(
                q9_task.task_id,
                "Q9_SUBTASK_SPLITTING_VALIDATION_FAILED",
                {
                    "event": "q9_subtask_splitting_validation_failed",
                    "plan_type": plan_type,
                    "validation_report": validation_report,
                    "idempotent_reuse": True,
                },
            )
            _task_split_log(
                "q9_subtask_split_validation_failed",
                parent_task_id=q9_task.task_id,
                session_id=metadata.get("session_id"),
                trace_id=metadata.get("q9_trace_id"),
                plan_type=plan_type,
                child_task_ids=existing_ids,
                idempotent_reuse=True,
                validation_report=validation_report,
            )
            raise TaskStateError(q9_task.last_error)
        for child in existing_children:
            await self.update_task_metadata(
                child.task_id,
                {
                    "q9_subtask_validation": {
                        "status": "passed",
                        "validator": "Zentex 认知蓝图与子任务合规验证器",
                        "checked_dimensions": validation_payload.get("checked_dimensions", []),
                    }
                },
                remarks="Q9 subtask splitting compliance validation passed",
            )
        q9_task.subtask_ids = list(dict.fromkeys([*q9_task.subtask_ids, *existing_ids]))
        q9_task.status = TaskStatus.DONE
        q9_task.progress = 1.0
        q9_task.metadata = {
            **q9_task.metadata,
            "worker_dispatch_enabled": False,
            "q9_subtask_splitting_validation": validation_report,
            "g31a_decomposition": {
                "status": "completed",
                "task_splitter": "G31A.TaskSplitter",
                "subtask_record_type": "SubtaskRecord",
                "initial_status_transition": {
                    "from_status": TaskStatus.SPLIT_REQUIRED.value,
                    "to_status": TaskStatus.ASSIGNMENT_PENDING.value,
                },
                "dependency_builder": "G31A.DependencyBuilder",
                "dependency_graph": existing_dependency_graph,
                "dependency_graph_is_dag": self._dependency_graph_is_dag(existing_dependency_graph),
                "subtask_ids": q9_task.subtask_ids,
                "executor_binding_owner": "G31A.ResourceMatcher",
                "assignment_results": existing_assignment_results,
                "idempotent_reuse": True,
                "subtask_splitting_validation": validation_report,
            },
        }
        q9_task.last_updated_at = datetime.now(timezone.utc)
        self._shared_tasks.set(q9_task.task_id, q9_task)
        self._tasks[q9_task.task_id] = q9_task
        if self.use_database and not self._sync_task_to_database(q9_task):
            raise TaskStateError(f"Failed to persist idempotent Q9 blueprint decomposition for task {q9_task.task_id}")
        self._record_audit(
            q9_task.task_id,
            "Q9_BLUEPRINT_DECOMPOSITION_REUSED",
            {
                "event": "q9_blueprint_decomposition_reused",
                "subtask_ids": existing_ids,
                "plan_type": plan_type,
            },
        )
        _task_split_log(
            "q9_subtask_split_reused",
            parent_task_id=q9_task.task_id,
            session_id=metadata.get("session_id"),
            trace_id=metadata.get("q9_trace_id"),
            plan_type=plan_type,
            child_count=len(existing_children),
            child_task_ids=existing_ids,
        )
        for child in existing_children:
            _task_split_log("q9_subtask_detail", **_q9_subtask_detail(child, parent_task_id=q9_task.task_id, plan_type=plan_type, metadata=metadata))
        return existing_children
    if not step_records:
        q9_task.status = TaskStatus.FAILED
        q9_task.last_error = "Q9 blueprint has no valid action_steps/current_action_plan for task-center splitting"
        q9_task.metadata = {
            **q9_task.metadata,
            "g31a_decomposition": {
                "status": "failed",
                "error_code": "q9_blueprint_missing_action_steps",
                "message": q9_task.last_error,
            },
        }
        q9_task.last_updated_at = datetime.now(timezone.utc)
        self._shared_tasks.set(q9_task.task_id, q9_task)
        self._tasks[q9_task.task_id] = q9_task
        if self.use_database and not self._sync_task_to_database(q9_task):
            raise TaskStateError(f"Failed to persist Q9 blueprint split failure for task {q9_task.task_id}")
        self._record_audit(
            q9_task.task_id,
            "Q9_BLUEPRINT_DECOMPOSITION_FAILED",
            {
                "event": "q9_blueprint_decomposition_failed",
                "error_code": "q9_blueprint_missing_action_steps",
                "plan_type": plan_type,
            },
        )
        _task_split_log(
            "q9_subtask_split_failed",
            parent_task_id=q9_task.task_id,
            session_id=metadata.get("session_id"),
            trace_id=metadata.get("q9_trace_id"),
            plan_type=plan_type,
            error_code="q9_blueprint_missing_action_steps",
            error_message=q9_task.last_error,
        )
        raise TaskStateError(q9_task.last_error)
    _task_split_log(
        "q9_subtask_split_start",
        parent_task_id=q9_task.task_id,
        session_id=metadata.get("session_id"),
        trace_id=metadata.get("q9_trace_id"),
        plan_type=plan_type,
        blueprint_step_count=len(lines),
        capability_count=len(capabilities),
        capabilities=capabilities,
        designated_executor_count=len(designated_executors),
        designated_executors=designated_executors,
    )
    if plan_type == "external":
        preflight_invalid_subtasks = _q9_external_owner_only_blueprint_violations(step_records, blueprint)
        if preflight_invalid_subtasks:
            await _fail_q9_subtask_split_validation_before_child_creation(
                self,
                q9_task,
                metadata=metadata,
                plan_type=plan_type,
                invalid_subtasks=preflight_invalid_subtasks,
            )
    self._record_audit(
        q9_task.task_id,
        "Q9_BLUEPRINT_DECOMPOSITION_STARTED",
        {
            "event": "q9_blueprint_decomposition_started",
            "session_id": metadata.get("session_id"),
            "q9_trace_id": metadata.get("q9_trace_id"),
            "plan_type": plan_type,
            "blueprint_step_count": len(lines),
            "capabilities": capabilities,
            "designated_executors": designated_executors,
            "splitter_owner": "task_center",
        },
    )
    fallback_capability = capabilities[0] if capabilities else ""
    created: List[ZentexTask] = []
    previous_task_id = ""
    assignment_router = self._build_assignment_router()
    assignment_results: List[Dict[str, Any]] = []
    for index, step_record in enumerate(step_records):
        line = step_record["line"]
        physical_subtask_id = f"g31a-subtask-{uuid4().hex[:8]}"
        step_required_resources = [
            str(resource or "").strip()
            for resource in step_record.get("required_resources", [])
            if str(resource or "").strip()
        ]
        capability = step_required_resources[0] if step_required_resources else (
            capabilities[min(index, len(capabilities) - 1)] if capabilities else fallback_capability
        )
        capability = self._q9_effective_step_capability(step_record, capability, plan_type)
        designated_executor = (
            designated_executors[min(index, len(designated_executors) - 1)]
            if designated_executors
            else ""
        )
        assignment = (
            self._q9_executor_for_designation(designated_executor, plan_type, capability)
            if designated_executor
            else self._q9_executor_for_capability(capability, plan_type)
        )
        task_scope = assignment["task_scope"]
        target_id = assignment["target_id"]
        executor_type = assignment["executor_type"]
        required_capabilities = assignment["required_capabilities"]
        assignment_required_resources = _q9_routable_required_resources(
            [
                *step_record["required_resources"],
                *list(blueprint.get("required_resources") or []),
            ],
            plan_type=plan_type,
            target_id=target_id,
            executor_type=executor_type,
            required_capabilities=required_capabilities,
        )
        runtime_metadata = self._q9_executor_runtime_metadata(
            executor_type=executor_type,
            target_id=target_id,
            required_capabilities=required_capabilities,
            trace_id=str(metadata.get("q9_trace_id") or f"q9-blueprint:{q9_task.task_id}:{index}"),
        )
        runtime_metadata = {
            **runtime_metadata,
            "worker_dispatch_enabled": False,
            "q9_proposed_owner_ref": target_id,
            "q9_proposed_executor_type": executor_type,
            "g31a_routable_required_resources": assignment_required_resources,
        }
        if executor_type == "external_connector":
            connector_capability = required_capabilities[0] if required_capabilities else capability
            connector_arguments = _q9_external_connector_arguments(metadata, capability=connector_capability)
            if connector_arguments:
                runtime_metadata["external_connector_arguments"] = connector_arguments
                runtime_metadata["q9_execution_parameters_source"] = "q9_parent_external_connector_arguments"
        child_payload = build_q9_child_payload(
            q9_task=q9_task,
            metadata=metadata,
            step_record=step_record,
            index=index,
            plan_type=plan_type,
            physical_subtask_id=physical_subtask_id,
            previous_task_id=previous_task_id,
            task_scope=task_scope,
            target_id=target_id,
            executor_type=executor_type,
            required_capabilities=required_capabilities,
            runtime_metadata=runtime_metadata,
            designated_executor=designated_executor if target_id else "",
        )
        child = await self.create_task(child_payload)
        _task_split_log(
            "q9_subtask_created",
            parent_task_id=q9_task.task_id,
            child_task_id=child.task_id,
            session_id=metadata.get("session_id"),
            trace_id=metadata.get("q9_trace_id"),
            plan_type=plan_type,
            step_index=index,
            proposed_owner_ref=target_id,
            executor_type=executor_type,
            required_capabilities=required_capabilities,
            depends_on=[previous_task_id] if previous_task_id else [],
        )
        decision = await assignment_router.route_assignment_pending_task(
            self,
            child,
            required_capabilities=required_capabilities,
            required_resources=assignment_required_resources,
            designated_owner=target_id,
            target_status=TaskStatus.QUEUED,
        )
        child = self.get_task(child.task_id)
        if child is None:
            raise TaskStateError("Q9 subtask disappeared after G31A assignment routing")
        subtask_record = dict(child.metadata.get("subtask_record") or {})
        subtask_record.update(
            {
                "task_id": child.task_id,
                "current_status_after_assignment_gate": child.status.value,
            }
        )
        dependency_graph_node = dict(child.metadata.get("dependency_graph_node") or {})
        dependency_graph_node.update(
            {
                "task_id": child.task_id,
                "depends_on": list(child.depends_on or []),
            }
        )
        child = await self.update_task_metadata(
            child.task_id,
            {"subtask_record": subtask_record, "dependency_graph_node": dependency_graph_node},
            remarks="G31A SubtaskRecord physical ids read-after-write persisted",
        )
        assignment_results.append(q9_assignment_result_payload(child, decision))
        if decision.assigned:
            _task_split_log(
                "q9_subtask_assignment_completed",
                parent_task_id=q9_task.task_id,
                child_task_id=child.task_id,
                session_id=metadata.get("session_id"),
                trace_id=metadata.get("q9_trace_id"),
                plan_type=plan_type,
                step_index=index,
                owner_ref=decision.owner_ref,
                executor_type=executor_type,
                candidate_owners=decision.candidate_owners,
                status=child.status.value,
            )
            self._record_audit(
                child.task_id,
                "Q9_BLUEPRINT_SUBTASK_ASSIGNED",
                {
                    "event": "q9_blueprint_subtask_assigned",
                    "parent_task_id": q9_task.task_id,
                    "step_index": index,
                    "from_status": TaskStatus.ASSIGNMENT_PENDING.value,
                    "to_status": TaskStatus.QUEUED.value,
                    "owner_ref": decision.owner_ref,
                    "candidate_owners": decision.candidate_owners,
                    "precondition_checker": "G31A.PreconditionChecker",
                },
            )
        else:
            _task_split_log(
                "q9_subtask_assignment_suspended",
                parent_task_id=q9_task.task_id,
                child_task_id=child.task_id,
                session_id=metadata.get("session_id"),
                trace_id=metadata.get("q9_trace_id"),
                plan_type=plan_type,
                step_index=index,
                proposed_owner_ref=target_id,
                missing_resources=decision.missing_resources,
                status=child.status.value,
            )
            self._record_audit(
                child.task_id,
                "Q9_BLUEPRINT_SUBTASK_RESOURCE_GAP_SUSPENDED",
                {
                    "event": "q9_blueprint_subtask_resource_gap_suspended",
                    "parent_task_id": q9_task.task_id,
                    "step_index": index,
                    "proposed_owner_ref": target_id,
                    "missing_resources": decision.missing_resources,
                    "negotiation_id": (decision.negotiation or {}).get("negotiation_id") if decision.negotiation else None,
                },
            )
        created.append(child)
        self._record_audit(
            child.task_id,
            "Q9_BLUEPRINT_SUBTASK_REGISTERED",
            {
                "event": "q9_blueprint_subtask_registered",
                "parent_task_id": q9_task.task_id,
                "session_id": metadata.get("session_id"),
                "q9_trace_id": metadata.get("q9_trace_id"),
                "plan_type": plan_type,
                "step_index": index,
                "blueprint_step": line,
                "target_id": child.target_id,
                "proposed_target_id": target_id,
                "executor_type": executor_type,
                "required_capabilities": required_capabilities,
                "q9_designated_executor": designated_executor,
                "depends_on": [previous_task_id] if previous_task_id else [],
                "assignment_status": child.metadata.get("assignment_status"),
                "registered_by": "task_center",
            },
        )
        self._record_audit(
            q9_task.task_id,
            "Q9_BLUEPRINT_SUBTASK_LINKED",
            {
                "event": "q9_blueprint_subtask_linked",
                "child_task_id": child.task_id,
                "step_index": index,
                "plan_type": plan_type,
                "target_id": child.target_id,
                "proposed_target_id": target_id,
                "executor_type": executor_type,
            },
        )
        _task_split_log(
            "q9_subtask_registered",
            parent_task_id=q9_task.task_id,
            child_task_id=child.task_id,
            session_id=metadata.get("session_id"),
            trace_id=metadata.get("q9_trace_id"),
            plan_type=plan_type,
            step_index=index,
            executor_ref=(child.metadata or {}).get("owner_ref") or child.target_id,
            assignment_status=child.metadata.get("assignment_status"),
            executor_type=executor_type,
        )
        previous_task_id = child.task_id

    q9_task.subtask_ids = list(dict.fromkeys([*q9_task.subtask_ids, *[task.task_id for task in created]]))
    dependency_graph = q9_created_dependency_graph(created)
    dependency_graph_is_dag = self._dependency_graph_is_dag(dependency_graph)
    if not dependency_graph_is_dag:
        raise TaskStateError(f"G31A DependencyBuilder produced a cyclic graph for Q9 task {q9_task.task_id}")
    available_tools_registry = q9_candidate_registry_payload(assignment_router.matcher._collect_candidates())
    validation_report = await validate_q9_subtask_splitting_against_llm_output(
        original_task_intent=metadata.get("q9_q8_task") or blueprint.get("plan_objective"),
        q9_action_blueprint=blueprint,
        child_tasks=created,
        available_tools_registry=available_tools_registry,
        plan_type=plan_type,
        llm_service=getattr(self, "_llm_service", None),
    )
    validation_payload = validation_report["SubtaskSplittingValidationReport"]
    if validation_payload.get("is_compliant") is not True:
        for child in created:
            await self.update_task_status(
                child.task_id,
                TaskStatus.CANCELLED,
                "Q9 subtask splitting compliance validation failed",
            )
        q9_task.status = TaskStatus.FAILED
        q9_task.last_error = "Q9 subtask splitting compliance validation failed"
        q9_task.metadata = {
            **q9_task.metadata,
            "worker_dispatch_enabled": False,
            "q9_subtask_splitting_validation": validation_report,
            "g31a_decomposition": {
                "status": "failed",
                "error_code": "q9_subtask_splitting_validation_failed",
                "validation_report": validation_report,
                "subtask_ids": [task.task_id for task in created],
            },
        }
        q9_task.last_updated_at = datetime.now(timezone.utc)
        self._shared_tasks.set(q9_task.task_id, q9_task)
        self._tasks[q9_task.task_id] = q9_task
        if self.use_database and not self._sync_task_to_database(q9_task):
            raise TaskStateError(f"Failed to persist Q9 subtask validation failure for task {q9_task.task_id}")
        self._record_audit(
            q9_task.task_id,
            "Q9_SUBTASK_SPLITTING_VALIDATION_FAILED",
            {
                "event": "q9_subtask_splitting_validation_failed",
                "plan_type": plan_type,
                "validation_report": validation_report,
                "available_tool_count": len(available_tools_registry),
            },
        )
        _task_split_log(
            "q9_subtask_split_validation_failed",
            parent_task_id=q9_task.task_id,
            session_id=metadata.get("session_id"),
            trace_id=metadata.get("q9_trace_id"),
            plan_type=plan_type,
            child_task_ids=[task.task_id for task in created],
            validation_report=validation_report,
            available_tool_count=len(available_tools_registry),
        )
        raise TaskStateError(q9_task.last_error)
    for child_index, child in enumerate(created):
        await self.update_task_metadata(
            child.task_id,
            {
                "q9_subtask_validation": {
                    "status": "passed",
                    "validator": "Zentex 认知蓝图与子任务合规验证器",
                    "checked_dimensions": validation_payload.get("checked_dimensions", []),
                }
            },
            remarks="Q9 subtask splitting compliance validation passed",
        )
        refreshed_child = self.get_task(child.task_id)
        if refreshed_child is not None:
            created[child_index] = refreshed_child
    q9_task.status = TaskStatus.DONE
    q9_task.progress = 1.0
    q9_task.completed_at = datetime.now(timezone.utc)
    q9_task.metadata = {
        **q9_task.metadata,
        "worker_dispatch_enabled": False,
        "q9_subtask_splitting_validation": validation_report,
        "g31a_decomposition": {
            "status": "completed",
            "task_splitter": "G31A.TaskSplitter",
            "subtask_record_type": "SubtaskRecord",
            "initial_status_transition": {
                "from_status": TaskStatus.SPLIT_REQUIRED.value,
                "to_status": TaskStatus.ASSIGNMENT_PENDING.value,
            },
            "dependency_builder": "G31A.DependencyBuilder",
            "dependency_graph": dependency_graph,
            "dependency_graph_is_dag": dependency_graph_is_dag,
            "subtask_ids": q9_task.subtask_ids,
            "executor_binding_owner": "G31A.ResourceMatcher",
            "assignment_results": assignment_results,
            "subtask_splitting_validation": validation_report,
        },
    }
    q9_task.last_updated_at = datetime.now(timezone.utc)
    self._shared_tasks.set(q9_task.task_id, q9_task)
    self._tasks[q9_task.task_id] = q9_task
    if self.use_database and not self._sync_task_to_database(q9_task):
        raise TaskStateError(f"Failed to persist Q9 blueprint decomposition for task {q9_task.task_id}")
    self._record_audit(
        q9_task.task_id,
        "Q9_BLUEPRINT_DECOMPOSED",
        {"subtask_ids": q9_task.subtask_ids, "plan_type": plan_type},
    )
    _task_split_log(
        "q9_subtask_split_completed",
        parent_task_id=q9_task.task_id,
        session_id=metadata.get("session_id"),
        trace_id=metadata.get("q9_trace_id"),
        plan_type=plan_type,
        child_count=len(created),
        subtask_ids=q9_task.subtask_ids,
        dependency_graph_is_dag=dependency_graph_is_dag,
        validation_report=validation_report,
    )
    for child in sorted(created, key=lambda task: int((task.metadata or {}).get("q9_blueprint_step_index", 0))):
        _task_split_log("q9_subtask_detail", **_q9_subtask_detail(child, parent_task_id=q9_task.task_id, plan_type=plan_type, metadata=metadata))
    return created

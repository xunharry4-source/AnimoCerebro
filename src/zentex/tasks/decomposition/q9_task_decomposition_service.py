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
    existing_children = sorted(
        self.list_tasks(parent_task_id=q9_task.task_id, limit=500, offset=0),
        key=lambda task: int((task.metadata or {}).get("q9_blueprint_step_index", 0)),
    )
    if existing_children:
        existing_ids = [task.task_id for task in existing_children]
        existing_dependency_graph = q9_existing_dependency_graph(existing_children)
        existing_assignment_results = q9_existing_assignment_results(existing_children)
        available_tools_registry = q9_candidate_registry_payload(
            self._build_assignment_router().matcher._collect_candidates()
        )
        validation_report = validate_q9_subtask_splitting_against_llm_output(
            original_task_intent=metadata.get("q9_q8_task") or blueprint.get("plan_objective"),
            q9_action_blueprint=blueprint,
            child_tasks=existing_children,
            available_tools_registry=available_tools_registry,
            plan_type=plan_type,
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
        return existing_children
    step_records = self._q9_blueprint_step_records(blueprint, plan_type)
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
        raise TaskStateError(q9_task.last_error)
    lines = [record["line"] for record in step_records]

    capabilities = self._q9_blueprint_capabilities(blueprint, plan_type)
    designated_executors = self._q9_blueprint_designated_executors(blueprint)
    logger.info(
        "Task center started Q9 blueprint decomposition.",
        extra={
            "task_id": q9_task.task_id,
            "session_id": metadata.get("session_id"),
            "q9_trace_id": metadata.get("q9_trace_id"),
            "q9_plan_type": plan_type,
            "blueprint_step_count": len(lines),
            "designated_executor_count": len(designated_executors),
        },
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
        }
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
            designated_executor=designated_executor,
        )
        child = await self.create_task(child_payload)
        decision = await assignment_router.route_assignment_pending_task(
            self,
            child,
            required_capabilities=required_capabilities,
            required_resources=[*step_record["required_resources"], *list(blueprint.get("required_resources") or [])],
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
        logger.info(
            "Task center registered Q9 blueprint subtask.",
            extra={
                "parent_task_id": q9_task.task_id,
                "child_task_id": child.task_id,
                "q9_plan_type": plan_type,
                "step_index": index,
                "target_id": child.target_id,
                "assignment_status": child.metadata.get("assignment_status"),
                "executor_type": executor_type,
            },
        )
        previous_task_id = child.task_id

    q9_task.subtask_ids = list(dict.fromkeys([*q9_task.subtask_ids, *[task.task_id for task in created]]))
    dependency_graph = q9_created_dependency_graph(created)
    dependency_graph_is_dag = self._dependency_graph_is_dag(dependency_graph)
    if not dependency_graph_is_dag:
        raise TaskStateError(f"G31A DependencyBuilder produced a cyclic graph for Q9 task {q9_task.task_id}")
    available_tools_registry = q9_candidate_registry_payload(assignment_router.matcher._collect_candidates())
    validation_report = validate_q9_subtask_splitting_against_llm_output(
        original_task_intent=metadata.get("q9_q8_task") or blueprint.get("plan_objective"),
        q9_action_blueprint=blueprint,
        child_tasks=created,
        available_tools_registry=available_tools_registry,
        plan_type=plan_type,
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
    logger.info(
        "Task center completed Q9 blueprint decomposition.",
        extra={
            "task_id": q9_task.task_id,
            "q9_plan_type": plan_type,
            "subtask_ids": q9_task.subtask_ids,
        },
    )
    return created

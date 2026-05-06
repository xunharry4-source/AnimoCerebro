from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceMissionDecompositionMixin:
    async def decompose_and_dispatch_mission(self, mission_task: ZentexTask):
        """
        Step 2 & 3: Mission Decomposition & Dispatch.
        """
        try:
            decomposition_context = DecompositionContext(
                mission_query=" ".join(
                    part
                    for part in (mission_task.title, mission_task.remarks or "")
                    if str(part or "").strip()
                ),
                task_type=mission_task.task_type.value,
                priority=mission_task.priority.value,
                tags=list(mission_task.tags),
                execution_constraints=list(mission_task.metadata.get("execution_constraints") or []),
                metadata={
                    "q9_contract": mission_task.metadata.get("q9_contract"),
                    "q9_action_blueprint": mission_task.metadata.get("q9_action_blueprint"),
                    "q9_task_profile": mission_task.metadata.get("q9_task_profile"),
                    "q9_constraints": mission_task.metadata.get("q9_constraints"),
                },
            )
            subtask_result = self.decomposer.decompose_mission(
                mission_task.title,
                mission_task.remarks or "",
                decomposition_context,
            )
            subtask_data = await subtask_result if inspect.isawaitable(subtask_result) else subtask_result
        except Exception as exc:
            mission_task.status = TaskStatus.FAILED
            mission_task.last_error = str(exc)
            mission_task.metadata = {
                **mission_task.metadata,
                "g31a_decomposition": {
                    "status": "failed",
                    "error_code": "mission_decomposition_exception",
                    "decomposer": self.decomposer.__class__.__name__,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            }
            mission_task.last_updated_at = datetime.now(timezone.utc)
            self._shared_tasks.set(mission_task.task_id, mission_task)
            self._tasks[mission_task.task_id] = mission_task
            if self.use_database and not self._sync_task_to_database(mission_task):
                raise TaskStateError(f"Failed to persist mission decomposition exception for task {mission_task.task_id}") from exc
            self._record_audit(
                mission_task.task_id,
                "MISSION_DECOMPOSITION_FAILED",
                mission_task.metadata["g31a_decomposition"],
            )
            raise
        if not isinstance(subtask_data, list) or not subtask_data:
            mission_task.status = TaskStatus.FAILED
            mission_task.last_error = "Mission decomposition produced no valid atomic subtasks"
            mission_task.metadata = {
                **mission_task.metadata,
                "g31a_decomposition": {
                    "status": "failed",
                    "error_code": "mission_decomposition_empty",
                    "decomposer": self.decomposer.__class__.__name__,
                },
            }
            mission_task.last_updated_at = datetime.now(timezone.utc)
            self._shared_tasks.set(mission_task.task_id, mission_task)
            self._tasks[mission_task.task_id] = mission_task
            if self.use_database and not self._sync_task_to_database(mission_task):
                raise TaskStateError(f"Failed to persist failed mission decomposition for task {mission_task.task_id}")
            self._record_audit(
                mission_task.task_id,
                "MISSION_DECOMPOSITION_FAILED",
                mission_task.metadata["g31a_decomposition"],
            )
            raise TaskStateError(mission_task.last_error)
        
        logger.info(f"Dispatching {len(subtask_data)} subtasks for mission {mission_task.task_id}")
        
        local_id_map: Dict[str, str] = {} # local step id -> physical task_id

        # Pass 1: Creation
        normalized_subtasks: List[Dict[str, Any]] = [dict(item) for item in subtask_data]
        for item in normalized_subtasks:
            local_id = str(item.pop("local_id"))
            item["parent_task_id"] = mission_task.task_id
            item["originator_id"] = mission_task.originator_id
            item["idempotency_key"] = f"sub-{mission_task.task_id}-{local_id}"
            item.setdefault("status", TaskStatus.ASSIGNMENT_PENDING)
            item.setdefault("metadata", {})
            item["metadata"] = {
                **dict(item.get("metadata") or {}),
                "g31a_mission_parent_task_id": mission_task.task_id,
                "g31a_local_id": local_id,
                "minimum_granularity": dict(item.get("metadata") or {}).get("minimum_granularity", "atomic_subtask"),
            }
            acceptance_criteria = list(item["metadata"].get("acceptance_criteria") or [])
            required_resources = list(item["metadata"].get("required_resources") or item.get("requirements") or [])
            
            # Subtask contract enforcement
            contract = TaskContract(
                coordination_mode=item.get("coordination_mode", CoordinationMode.PARALLEL),
                success_criteria=acceptance_criteria,
                acceptance_conditions=acceptance_criteria,
                expected_outcome={
                    "objective": item.get("objective"),
                    "required_resources": required_resources,
                    "minimum_granularity": item["metadata"]["minimum_granularity"],
                },
                verification_method="g31a_atomic_subtask_acceptance_criteria",
                # If step-1 fails, mission fails (halt)
                failure_strategy="halt" if "step-1" in local_id else "retry_all"
            )
            
            st = await self.create_task({**item, "contract": contract})
            local_id_map[local_id] = st.task_id
            mission_task.subtask_ids.append(st.task_id)

        # Pass 2: Dependency Linkage
        for item, st_id in zip(normalized_subtasks, mission_task.subtask_ids):
            st = self._tasks[st_id]
            st.depends_on = [local_id_map[dep] for dep in item.get("depends_on", []) if dep in local_id_map]
            self._shared_tasks.set(st_id, st)
            self._tasks[st_id] = st
            if self.use_database and not self._sync_task_to_database(st):
                raise TaskStateError(f"Failed to persist dependency linkage for subtask {st_id}")

        mission_task.last_updated_at = datetime.now(timezone.utc)
        mission_task.metadata = {
            **mission_task.metadata,
            "g31a_decomposition": {
                "status": "completed",
                "decomposer": self.decomposer.__class__.__name__,
                "minimum_granularity": "atomic_subtask",
                "subtask_ids": mission_task.subtask_ids,
            },
        }
        self._shared_tasks.set(mission_task.task_id, mission_task)
        self._tasks[mission_task.task_id] = mission_task
        if self.use_database and not self._sync_task_to_database(mission_task):
            raise TaskStateError(f"Failed to persist mission decomposition for task {mission_task.task_id}")

        self._record_audit(
            mission_task.task_id,
            "MISSION_DECOMPOSED",
            {
                "subtask_ids": mission_task.subtask_ids,
                "decomposer": self.decomposer.__class__.__name__,
                "minimum_granularity": "atomic_subtask",
            },
        )



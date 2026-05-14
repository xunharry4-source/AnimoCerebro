from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceAssignmentGateMixin:
    @staticmethod
    def _q9_blueprint_lines(blueprint: Dict[str, Any], plan_type: str) -> List[str]:
        return q9_blueprint_lines(blueprint, plan_type)

    @staticmethod
    def _dependency_graph_is_dag(dependency_graph: List[Dict[str, Any]]) -> bool:
        return dependency_graph_is_dag(dependency_graph)

    @staticmethod
    def _q9_blueprint_step_records(blueprint: Dict[str, Any], plan_type: str) -> List[Dict[str, Any]]:
        return q9_blueprint_step_records(blueprint, plan_type)

    @staticmethod
    def _q9_blueprint_capabilities(blueprint: Dict[str, Any], plan_type: str) -> List[str]:
        return q9_blueprint_capabilities(blueprint, plan_type)

    @staticmethod
    def _q9_blueprint_designated_executors(blueprint: Dict[str, Any]) -> List[str]:
        return q9_blueprint_designated_executors(blueprint)

    @staticmethod
    def _q9_executor_for_designation(designation: str, plan_type: str, capability: str = "") -> Dict[str, Any]:
        return q9_executor_for_designation(designation, plan_type, capability)

    @staticmethod
    def _q9_executor_for_capability(capability: str, plan_type: str) -> Dict[str, Any]:
        return q9_executor_for_capability(capability, plan_type)

    @staticmethod
    def _q9_effective_step_capability(
        step_record: Dict[str, Any],
        fallback_capability: str,
        plan_type: str = "external",
    ) -> str:
        return q9_effective_step_capability(step_record, fallback_capability, plan_type)

    @staticmethod
    def _q9_executor_runtime_metadata(
        *,
        executor_type: str,
        target_id: str,
        required_capabilities: List[str],
        trace_id: str,
    ) -> Dict[str, Any]:
        return q9_executor_runtime_metadata(
            executor_type=executor_type,
            target_id=target_id,
            required_capabilities=required_capabilities,
            trace_id=trace_id,
        )

    def _build_assignment_router(self) -> TaskAssignmentRouter:
        if self._cli_service is None:
            try:
                from zentex.cli.service import get_service as get_cli_service

                self._cli_service = get_cli_service(transcript_store=self._transcript_store)
            except Exception:
                self._cli_service = None
        if self._external_connector_service is None:
            try:
                from zentex.external_connectors.service import get_service as get_external_connector_service

                self._external_connector_service = get_external_connector_service()
            except Exception:
                self._external_connector_service = None
        if self._agent_service is None:
            try:
                from zentex.agents.service import get_service as get_agent_service

                self._agent_service = get_agent_service()
            except Exception:
                self._agent_service = None
        return TaskAssignmentRouter(
            ResourceMatcher(
                plugin_service=self._plugin_service,
                cli_service=self._cli_service,
                mcp_service=self._mcp_service,
                external_connector_service=self._external_connector_service,
                agent_service=self._agent_service,
            )
        )

    @staticmethod
    def _metadata_list(value: Any) -> List[str]:
        from zentex.tasks.execution.assignment_projection import metadata_list

        return metadata_list(value)

    @staticmethod
    def _candidate_counts_by_registry(candidates: List[Any]) -> Dict[str, int]:
        from zentex.tasks.execution.assignment_projection import candidate_counts_by_registry

        return candidate_counts_by_registry(candidates)

    @staticmethod
    def _declared_owner_ref(task: ZentexTask, metadata: Dict[str, Any]) -> str:
        from zentex.tasks.execution.assignment_projection import declared_owner_ref

        return declared_owner_ref(task, metadata)

    @staticmethod
    def _executor_type_from_owner_ref(owner_ref: str) -> str:
        from zentex.tasks.execution.assignment_projection import executor_type_from_owner_ref

        return executor_type_from_owner_ref(owner_ref)

    def validate_execution_assignment(self, task: ZentexTask) -> Dict[str, Any]:
        return validate_execution_assignment_projection(
            task=task,
            plugin_service=self._plugin_service,
            cli_service=self._cli_service,
            mcp_service=self._mcp_service,
            external_connector_service=self._external_connector_service,
            agent_service=self._agent_service,
        )

    def _attach_validated_execution_assignment(self, task: ZentexTask) -> ZentexTask:
        return attach_validated_execution_assignment_projection(
            task=task,
            plugin_service=self._plugin_service,
            cli_service=self._cli_service,
            mcp_service=self._mcp_service,
            external_connector_service=self._external_connector_service,
            agent_service=self._agent_service,
        )

    async def route_assignment_pending_task(
        self,
        task_id: str,
        *,
        required_capabilities: Optional[List[str]] = None,
        required_resources: Optional[List[str]] = None,
        designated_owner: Optional[str] = None,
        target_status: TaskStatus = TaskStatus.QUEUED,
    ) -> ZentexTask:
        """Run the task-flow assignment gate for one physical subtask."""
        task = self.get_task(task_id)
        if task is None:
            raise TaskStateError(f"Task {task_id} not found for assignment routing")
        metadata = task.metadata if isinstance(task.metadata, dict) else {}
        decision = await self._build_assignment_router().route_assignment_pending_task(
            self,
            task,
            required_capabilities=required_capabilities if required_capabilities is not None else list(metadata.get("required_capabilities") or []),
            required_resources=required_resources if required_resources is not None else list(metadata.get("required_resources") or []),
            designated_owner=designated_owner if designated_owner is not None else str(metadata.get("q9_proposed_owner_ref") or task.target_id or ""),
            target_status=target_status,
        )
        refreshed = self.get_task(task_id)
        if refreshed is None:
            raise TaskStateError(f"Task {task_id} disappeared after assignment routing")
        if decision.assigned and refreshed.status != target_status:
            raise TaskStateError(f"Task {task_id} assignment did not reach {target_status.value}")
        if not decision.assigned and refreshed.status != TaskStatus.SUSPENDED:
            raise TaskStateError(f"Task {task_id} resource gap did not enter suspended state")
        return refreshed

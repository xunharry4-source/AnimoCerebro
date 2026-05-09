from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceWiringMixin:
    def close(self) -> None:
        close = getattr(self._db, "close", None)
        if callable(close):
            close()

    def _reconcile_shared_task_state_with_database(self) -> None:
        """Drop shared task caches whose backing SQLite rows no longer exist.

        The task table is the source of truth. DiskCache/Redis shared state is a
        hot cache for cross-worker lookup and must not preserve orphan task IDs
        after task cleanup or database resets.
        """
        if not self._task_dao:
            return
        stale_task_cache = 0
        stale_idempotency_cache = 0
        try:
            for task_id in list(self._shared_tasks.list_all().keys()):
                if not self._task_dao.get_task(str(task_id)):
                    self._shared_tasks.delete(str(task_id))
                    self._tasks.pop(str(task_id), None)
                    stale_task_cache += 1
            for idempotency_key, task_id in list(self._shared_idempotency.list_all().items()):
                if not task_id or not self._task_dao.get_task(str(task_id)):
                    self._shared_idempotency.delete(str(idempotency_key))
                    self._idempotency_log.pop(str(idempotency_key), None)
                    stale_idempotency_cache += 1
        except Exception:
            logger.warning("Failed to reconcile shared task state with SQLite.", exc_info=True)
            return
        if stale_task_cache or stale_idempotency_cache:
            logger.warning(
                "Reconciled stale shared task state with SQLite. stale_tasks=%s stale_idempotency=%s",
                stale_task_cache,
                stale_idempotency_cache,
            )

    def attach_dependencies(
        self,
        *,
        plugin_service: Any = None,
        transcript_store: Any = None,
        cli_service: Any = None,
        mcp_service: Any = None,
        external_connector_service: Any = None,
        agent_service: Any = None,
        memory_service: Any = None,
        learning_service: Any = None,
        reflection_service: Any = None,
        audit_service: Any = None,
    ) -> None:
        """
        Inject external service references into the task management stack.
        This resolves the circular dependency between tasks and plugins.
        """
        if plugin_service is not None:
            self._plugin_service = plugin_service
            self._dispatch_manager.set_plugin_layer(plugin_service)
            logger.info("TaskManagementService: PluginService attached to dispatcher.")
        if cli_service is not None:
            self._cli_service = cli_service
        if mcp_service is not None:
            self._mcp_service = mcp_service
        if external_connector_service is not None:
            self._external_connector_service = external_connector_service
        if agent_service is not None:
            self._agent_service = agent_service
        self._dispatch_manager.attach_external_services(
            task_service=self,
            cli_service=cli_service,
            mcp_service=mcp_service,
            external_connector_service=external_connector_service,
            agent_service=agent_service,
        )
        for external_service in (cli_service, mcp_service, external_connector_service):
            if external_service is None or getattr(external_service, "_is_stub", False):
                continue
            attach_task_service = getattr(external_service, "attach_task_service", None)
            if callable(attach_task_service):
                attach_task_service(self)
        if memory_service is not None:
            self._memory_service = memory_service
        if learning_service is not None:
            self._learning_service = learning_service
        if reflection_service is not None:
            self._reflection_service = reflection_service
        if audit_service is not None:
            self._workflow_audit_service = audit_service
        
        if transcript_store is not None:
            # Update transcript store if it was missing during init
            resolved_store = self._resolve_transcript_store(transcript_store)
            self.transcript_store = resolved_store
            self._transcript_store = resolved_store
            # UnifiedTaskRouter also needs a transcript store
            if hasattr(self._dispatch_manager, "_router"):
                self._dispatch_manager._router.transcript_store = resolved_store

    def _resolve_transcript_store(self, transcript_store: Any) -> Any:
        if transcript_store is None:
            return None
        if isinstance(transcript_store, NullTranscriptStore):
            logger.warning(
                "TaskManagementService received NullTranscriptStore; creating a local TranscriptStore fallback for task audits"
            )
            return TranscriptStore(session_id="task-management-runtime")
        return transcript_store



from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceDiagnosticsMixin:
    def _list_tasks_for_internal_scan(self, *, page_size: int = 500) -> List[ZentexTask]:
        """Read task rows in bounded database pages for whole-state diagnostics."""
        tasks: List[ZentexTask] = []
        offset = 0
        capped_page_size = max(1, min(int(page_size), 500))
        while True:
            page = self.list_tasks(limit=capped_page_size, offset=offset)
            tasks.extend(page)
            if len(page) < capped_page_size:
                return tasks
            offset += capped_page_size

    def _list_suspended_tasks_for_internal_scan(self, *, page_size: int = 500) -> List[SuspendedTask]:
        """Read suspended task rows in bounded database pages for diagnostics."""
        suspended_tasks: List[SuspendedTask] = []
        offset = 0
        capped_page_size = max(1, min(int(page_size), 500))
        while True:
            page = self.list_suspended_tasks(limit=capped_page_size, offset=offset)
            suspended_tasks.extend(page)
            if len(page) < capped_page_size:
                return suspended_tasks
            offset += capped_page_size

    def diagnose_task_management_closure(self, *, stale_after_seconds: int = 300) -> Dict[str, Any]:
        """Return the feature-61 task lifecycle diagnostic report."""
        tasks = self._list_tasks_for_internal_scan()
        suspended_tasks = self._list_suspended_tasks_for_internal_scan()
        audit_history = self._collect_task_audit_history(tasks)
        report = build_task_lifecycle_diagnostic_report(
            tasks=tasks,
            suspended_tasks=suspended_tasks,
            audit_history_by_task_id=audit_history,
            stale_after_seconds=stale_after_seconds,
        )
        self._record_audit(
            "task_management",
            "TASK_MANAGEMENT_CLOSURE_DIAGNOSED",
            report.model_dump(mode="json"),
        )
        return report.model_dump(mode="json")

    def analyze_task_garbage_and_duplicates(
        self,
        *,
        stale_after_seconds: int = 300,
        enable_llm_semantic_scoring: bool = False,
        max_llm_groups: int = 8,
    ) -> Dict[str, Any]:
        """Return a read-only task quality report for garbage and duplicates.

        Deterministic rule hits are scored locally. Semantic duplicate/noise
        decisions are only made when LLM scoring is explicitly enabled and the
        model returns a valid structured score.
        """
        tasks = self._list_tasks_for_internal_scan()
        report = build_task_garbage_analysis_report(
            tasks=tasks,
            stale_after_seconds=stale_after_seconds,
            enable_llm_semantic_scoring=enable_llm_semantic_scoring,
            max_llm_groups=max_llm_groups,
        )
        self._record_audit(
            "task_management",
            "TASK_GARBAGE_DUPLICATION_ANALYZED",
            {
                "summary": report.get("summary", {}),
                "llm_semantic_scoring": report.get("llm_semantic_scoring", {}),
                "execution_plan": report.get("execution_plan", {}),
            },
        )
        return report

    def run_task_fault_injection_matrix(self, *, stale_after_seconds: int = 300) -> Dict[str, Any]:
        """Return the feature-61 fault injection matrix derived from real task state."""
        tasks = self._list_tasks_for_internal_scan()
        diagnostic = build_task_lifecycle_diagnostic_report(
            tasks=tasks,
            suspended_tasks=self._list_suspended_tasks_for_internal_scan(),
            audit_history_by_task_id=self._collect_task_audit_history(tasks),
            stale_after_seconds=stale_after_seconds,
        )
        report = build_task_fault_injection_report(diagnostic)
        self._record_audit(
            "task_management",
            "TASK_MANAGEMENT_FAULT_MATRIX_EXECUTED",
            report.model_dump(mode="json"),
        )
        return report.model_dump(mode="json")

    def _collect_task_audit_history(self, tasks: List[ZentexTask]) -> Dict[str, List[Dict[str, Any]]]:
        if not self._audit_dao:
            return {task.task_id: [] for task in tasks}
        return {
            task.task_id: self._audit_dao.get_audit_history(task.task_id, limit=200)
            for task in tasks
        }





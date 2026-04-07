from __future__ import annotations

"""
Execution service for real LLM and plugin upgrade jobs.

This module bridges planning, real runtimes, and the upgrade management store.
It only marks jobs as completed after a real runner executes. When the runtime
or worker is missing, execution fails closed and the management ledger records
the failure instead of pretending that rules or planning equal execution.
"""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from zentex.upgrade.evidence import UpgradeEvidenceService
from zentex.upgrade.llm.runtime import LLMUpgradeRuntime
from zentex.upgrade.management import (
    UpgradeLifecycleStatus,
    UpgradeManagementRecord,
    UpgradeManagementStore,
    UpgradeTargetKind,
    utc_now,
)
from zentex.upgrade.models import (
    LLMUpgradeIntentRequest,
    PluginEvolutionIntentRequest,
    UpgradeDecisionAction,
)
from zentex.upgrade.plugin.runtime import PluginEvolutionRuntime
from zentex.upgrade.service import UpgradeFacade


class UpgradeExecutionService:
    """Executes real upgrade jobs and persists their lifecycle records."""

    def __init__(
        self,
        *,
        facade: UpgradeFacade | None = None,
        management_store: UpgradeManagementStore | None = None,
        llm_runtime: LLMUpgradeRuntime | None = None,
        plugin_runtime: PluginEvolutionRuntime | None = None,
        plugin_worker: Callable[[Any], dict[str, Any]] | None = None,
        evidence_service: UpgradeEvidenceService | None = None,
    ) -> None:
        self._evidence_service = evidence_service or UpgradeEvidenceService()
        self._facade = facade or UpgradeFacade(
            enhanced_memory_service=self._evidence_service.enhanced_memory_service,
        )
        self._management_store = management_store or UpgradeManagementStore()
        self._llm_runtime = llm_runtime or LLMUpgradeRuntime()
        self._plugin_runtime = plugin_runtime or PluginEvolutionRuntime()
        self._plugin_worker = plugin_worker

    @property
    def management_store(self) -> UpgradeManagementStore:
        return self._management_store

    @property
    def evidence_service(self) -> UpgradeEvidenceService:
        return self._evidence_service

    def _resolve_trace_context(
        self,
        request: LLMUpgradeIntentRequest | PluginEvolutionIntentRequest,
        *,
        prefix: str,
    ) -> tuple[str, str]:
        trace_id = str(request.trace_id or f"{prefix}:{uuid4().hex}")
        request_id = str(request.request_id or uuid4().hex)
        return trace_id, request_id

    def _apply_failure_profile(
        self,
        record: UpgradeManagementRecord,
        *,
        stage: str,
        exc: Exception,
        failed_command: str | None = None,
        failed_artifact_refs: list[str] | None = None,
    ) -> None:
        error_message = str(exc).strip() or exc.__class__.__name__
        error_type = exc.__class__.__name__
        record.failure_reason = error_message
        record.failure_stage = stage
        record.failure_code = error_type.lower()
        record.failure_summary = f"{stage} failed with {error_type}."
        record.root_cause_hypothesis = (
            f"{stage} could not complete because the runtime raised {error_type}: "
            f"{error_message}"
        )
        record.failed_command = failed_command
        record.failed_artifact_refs = list(failed_artifact_refs or [])
        record.retryable = isinstance(exc, (TimeoutError, ConnectionError))
        record.prevention_hint = (
            "Validate runner availability, command contracts, and candidate inputs "
            "before retrying the next evolution cycle."
        )
        record.learning_tags = [
            record.target_kind.value,
            record.action,
            stage,
            error_type.lower(),
        ]

    def _apply_success_profile(
        self,
        record: UpgradeManagementRecord,
        *,
        stage: str,
        successful_command: str | None = None,
        success_artifact_refs: list[str] | None = None,
        reusable_insight: str,
    ) -> None:
        record.success_stage = stage
        record.success_summary = f"{stage} completed successfully."
        record.successful_command = successful_command
        record.success_artifact_refs = list(success_artifact_refs or [])
        record.reusable_insight = reusable_insight
        record.promotion_hint = (
            "Reuse the same execution path and validation evidence when a similar "
            "upgrade objective appears again."
        )
        record.success_tags = [
            record.target_kind.value,
            record.action,
            stage,
            "success",
        ]

    def execute_llm_upgrade(
        self,
        request: LLMUpgradeIntentRequest,
    ) -> UpgradeManagementRecord | None:
        decision = self._facade.plan_llm_upgrade(request)
        if decision.action is UpgradeDecisionAction.SKIP or decision.candidate is None:
            return None

        candidate = decision.candidate
        trace_id, request_id = self._resolve_trace_context(
            request,
            prefix="upgrade-llm",
        )
        record = UpgradeManagementRecord(
            record_id=f"llm-upgrade-{uuid4().hex[:12]}",
            target_kind=UpgradeTargetKind.LLM,
            action="upgrade",
            target_id=candidate.program_id,
            title=f"LLM upgrade for {candidate.target_component}",
            reason=request.reason,
            trace_id=trace_id,
            request_id=request_id,
            source_event_id=request.source_event_id,
            parent_record_id=request.parent_record_id,
            evidence_refs=list(request.evidence_refs),
            memory_recall_query=(
                decision.memory_context.query
                if decision.memory_context is not None
                else None
            ),
            recalled_memory_ids=(
                list(decision.memory_context.recalled_memory_ids)
                if decision.memory_context is not None
                else []
            ),
            recalled_success_patterns=(
                list(decision.memory_context.success_patterns)
                if decision.memory_context is not None
                else []
            ),
            recalled_failure_patterns=(
                list(decision.memory_context.failure_patterns)
                if decision.memory_context is not None
                else []
            ),
            recalled_suspect_patterns=(
                list(decision.memory_context.suspect_patterns)
                if decision.memory_context is not None
                else []
            ),
            memory_recall_summary=(
                decision.memory_context.summary
                if decision.memory_context is not None
                else None
            ),
            change_summary=candidate.objective_summary,
            function_summary=(
                f"Optimize {candidate.target_component} using "
                f"{candidate.execution_plan.optimizer_name}."
            ),
            previous_version=candidate.baseline_version,
            current_version=candidate.baseline_version,
            candidate_version=candidate.candidate_version,
            current_status=UpgradeLifecycleStatus.RUNNING,
            current_progress=10,
            audit_status="running",
            memory_status="queued",
            started_at=utc_now(),
        )
        self._management_store.upsert(record)
        self._evidence_service.record_event(
            record,
            event_type="llm_upgrade_started",
            summary="LLM upgrade execution started with a real optimizer runner.",
        )

        try:
            result = self._llm_runtime.execute_candidate(candidate)
            record.current_status = UpgradeLifecycleStatus.COMPLETED
            record.current_progress = 100
            record.audit_status = "completed"
            record.memory_status = "persisted"
            record.finished_at = utc_now()
            record.change_summary = str(result.get("status") or record.change_summary)
            self._apply_success_profile(
                record,
                stage="llm_execution",
                successful_command=(
                    candidate.execution_plan.validation_commands[0]
                    if candidate.execution_plan.validation_commands
                    else None
                ),
                success_artifact_refs=list(candidate.execution_plan.required_artifacts),
                reusable_insight=(
                    "A real optimizer runner completed the LLM upgrade and produced "
                    "candidate artifacts that can be reused as a validated baseline."
                ),
            )
            self._evidence_service.record_event(
                record,
                event_type="llm_upgrade_completed",
                summary="LLM upgrade execution completed successfully.",
                payload=result,
            )
        except Exception as exc:
            record.current_status = UpgradeLifecycleStatus.FAILED
            record.current_progress = 100
            self._apply_failure_profile(
                record,
                stage="llm_execution",
                exc=exc,
                failed_command=(
                    candidate.execution_plan.validation_commands[0]
                    if candidate.execution_plan.validation_commands
                    else None
                ),
                failed_artifact_refs=list(candidate.execution_plan.required_artifacts),
            )
            record.audit_status = "failed"
            record.memory_status = "persisted"
            record.finished_at = utc_now()
            self._management_store.upsert(record)
            self._evidence_service.record_event(
                record,
                event_type="llm_upgrade_failed",
                summary="LLM upgrade execution failed.",
                payload={"error": str(exc)},
            )
            raise

        return self._management_store.upsert(record)

    def execute_plugin_evolution(
        self,
        request: PluginEvolutionIntentRequest,
    ) -> UpgradeManagementRecord | None:
        decision = self._facade.plan_plugin_evolution(request)
        if decision.action is UpgradeDecisionAction.SKIP:
            return None
        if self._plugin_worker is None:
            raise RuntimeError(
                "Plugin evolution execution requires a real plugin worker; "
                "rule-based fallback is not allowed."
            )

        if decision.action is UpgradeDecisionAction.CREATE and decision.creation_candidate is not None:
            candidate = decision.creation_candidate
            trace_id, request_id = self._resolve_trace_context(
                request,
                prefix="upgrade-plugin-create",
            )
            record = UpgradeManagementRecord(
                record_id=f"plugin-create-{uuid4().hex[:12]}",
                target_kind=UpgradeTargetKind.PLUGIN,
                action="create",
                target_id=candidate.plugin_id,
                title=f"Plugin creation for {candidate.plugin_id}",
                reason=request.reason,
                trace_id=trace_id,
                request_id=request_id,
                source_event_id=request.source_event_id,
                parent_record_id=request.parent_record_id,
                evidence_refs=list(request.evidence_refs),
                memory_recall_query=(
                    decision.memory_context.query
                    if decision.memory_context is not None
                    else None
                ),
                recalled_memory_ids=(
                    list(decision.memory_context.recalled_memory_ids)
                    if decision.memory_context is not None
                    else []
                ),
                recalled_success_patterns=(
                    list(decision.memory_context.success_patterns)
                    if decision.memory_context is not None
                    else []
                ),
                recalled_failure_patterns=(
                    list(decision.memory_context.failure_patterns)
                    if decision.memory_context is not None
                    else []
                ),
                recalled_suspect_patterns=(
                    list(decision.memory_context.suspect_patterns)
                    if decision.memory_context is not None
                    else []
                ),
                memory_recall_summary=(
                    decision.memory_context.summary
                    if decision.memory_context is not None
                    else None
                ),
                change_summary=candidate.goal,
                function_summary="Create a new plugin candidate with a real worker.",
                previous_version=None,
                current_version=candidate.initial_version,
                candidate_version=candidate.candidate_version,
                current_status=UpgradeLifecycleStatus.SCAFFOLDING_CANDIDATE,
                current_progress=10,
                candidate_path=candidate.candidate_plugin_path,
                audit_status="running",
                memory_status="queued",
                started_at=utc_now(),
            )
            self._management_store.upsert(record)
            self._evidence_service.record_event(
                record,
                event_type="plugin_creation_scaffolding_started",
                summary="Plugin creation started by scaffolding a candidate directory.",
            )
            try:
                self._plugin_runtime.scaffold_new_plugin_candidate(
                    candidate_plugin_path=candidate.candidate_plugin_path,
                )
                record.current_status = UpgradeLifecycleStatus.RUNNING
                record.current_progress = 40
                self._management_store.upsert(record)
                self._evidence_service.record_event(
                    record,
                    event_type="plugin_creation_worker_started",
                    summary="Plugin creation candidate scaffold completed; real worker started.",
                )
                result = self._plugin_worker(candidate)
                record.current_status = UpgradeLifecycleStatus.COMPLETED
                record.current_progress = 100
                record.audit_status = "completed"
                record.memory_status = "persisted"
                record.finished_at = utc_now()
                record.change_summary = str(result.get("status") or record.change_summary)
                self._apply_success_profile(
                    record,
                    stage="plugin_creation",
                    successful_command=(
                        candidate.execution_plan.validation_commands[0]
                        if candidate.execution_plan.validation_commands
                        else None
                    ),
                    success_artifact_refs=[candidate.candidate_plugin_path],
                    reusable_insight=(
                        "The candidate scaffold and worker flow succeeded, so this "
                        "plugin creation pattern can be reused for similar plugins."
                    ),
                )
                self._evidence_service.record_event(
                    record,
                    event_type="plugin_creation_completed",
                    summary="Plugin creation completed successfully.",
                    payload=result,
                )
            except Exception as exc:
                record.current_status = UpgradeLifecycleStatus.FAILED
                record.current_progress = 100
                self._apply_failure_profile(
                    record,
                    stage="plugin_creation",
                    exc=exc,
                    failed_command=(
                        candidate.execution_plan.validation_commands[0]
                        if candidate.execution_plan.validation_commands
                        else None
                    ),
                    failed_artifact_refs=[candidate.candidate_plugin_path],
                )
                record.audit_status = "failed"
                record.memory_status = "persisted"
                record.finished_at = utc_now()
                self._management_store.upsert(record)
                self._evidence_service.record_event(
                    record,
                    event_type="plugin_creation_failed",
                    summary="Plugin creation failed.",
                    payload={"error": str(exc)},
                )
                raise
            return self._management_store.upsert(record)

        if decision.upgrade_candidate is None:
            return None

        candidate = decision.upgrade_candidate
        trace_id, request_id = self._resolve_trace_context(
            request,
            prefix="upgrade-plugin",
        )
        record = UpgradeManagementRecord(
            record_id=f"plugin-upgrade-{uuid4().hex[:12]}",
            target_kind=UpgradeTargetKind.PLUGIN,
            action="upgrade",
            target_id=candidate.plugin_id,
            title=f"Plugin upgrade for {candidate.plugin_id}",
            reason=request.reason,
            trace_id=trace_id,
            request_id=request_id,
            source_event_id=request.source_event_id,
            parent_record_id=request.parent_record_id,
            evidence_refs=list(request.evidence_refs),
            memory_recall_query=(
                decision.memory_context.query
                if decision.memory_context is not None
                else None
            ),
            recalled_memory_ids=(
                list(decision.memory_context.recalled_memory_ids)
                if decision.memory_context is not None
                else []
            ),
            recalled_success_patterns=(
                list(decision.memory_context.success_patterns)
                if decision.memory_context is not None
                else []
            ),
            recalled_failure_patterns=(
                list(decision.memory_context.failure_patterns)
                if decision.memory_context is not None
                else []
            ),
            recalled_suspect_patterns=(
                list(decision.memory_context.suspect_patterns)
                if decision.memory_context is not None
                else []
            ),
            memory_recall_summary=(
                decision.memory_context.summary
                if decision.memory_context is not None
                else None
            ),
            change_summary=candidate.goal,
            function_summary="Copy source plugin and execute a real evolution worker.",
            previous_version=candidate.baseline_version,
            current_version=candidate.baseline_version,
            candidate_version=candidate.candidate_version,
            current_status=UpgradeLifecycleStatus.COPYING_SOURCE,
            current_progress=10,
            source_path=candidate.source_plugin_path,
            candidate_path=candidate.candidate_plugin_path,
            audit_status="running",
            memory_status="queued",
            started_at=utc_now(),
        )
        self._management_store.upsert(record)
        self._evidence_service.record_event(
            record,
            event_type="plugin_upgrade_copy_started",
            summary="Plugin upgrade started by copying the source plugin into a candidate directory.",
        )

        try:
            self._plugin_runtime.copy_plugin_candidate(
                source_plugin_path=candidate.source_plugin_path,
                candidate_plugin_path=candidate.candidate_plugin_path,
            )
            record.current_status = UpgradeLifecycleStatus.RUNNING
            record.current_progress = 40
            self._management_store.upsert(record)
            self._evidence_service.record_event(
                record,
                event_type="plugin_upgrade_worker_started",
                summary="Plugin candidate copy completed; real worker started.",
            )
            result = self._plugin_worker(candidate)
            record.current_status = UpgradeLifecycleStatus.COMPLETED
            record.current_progress = 100
            record.audit_status = "completed"
            record.memory_status = "persisted"
            record.finished_at = utc_now()
            record.change_summary = str(result.get("status") or record.change_summary)
            self._apply_success_profile(
                record,
                stage="plugin_upgrade",
                successful_command=(
                    candidate.execution_plan.validation_commands[0]
                    if candidate.execution_plan.validation_commands
                    else None
                ),
                success_artifact_refs=[candidate.candidate_plugin_path],
                reusable_insight=(
                    "Copy-then-evolve succeeded without mutating the source plugin, "
                    "so this upgrade path is safe to reuse for future plugin versions."
                ),
            )
            self._evidence_service.record_event(
                record,
                event_type="plugin_upgrade_completed",
                summary="Plugin upgrade completed successfully.",
                payload=result,
            )
        except Exception as exc:
            record.current_status = UpgradeLifecycleStatus.FAILED
            record.current_progress = 100
            self._apply_failure_profile(
                record,
                stage="plugin_upgrade",
                exc=exc,
                failed_command=(
                    candidate.execution_plan.validation_commands[0]
                    if candidate.execution_plan.validation_commands
                    else None
                ),
                failed_artifact_refs=[candidate.candidate_plugin_path],
            )
            record.audit_status = "failed"
            record.memory_status = "persisted"
            record.finished_at = utc_now()
            self._management_store.upsert(record)
            self._evidence_service.record_event(
                record,
                event_type="plugin_upgrade_failed",
                summary="Plugin upgrade failed.",
                payload={"error": str(exc)},
            )
            raise

        return self._management_store.upsert(record)

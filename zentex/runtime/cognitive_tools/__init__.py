from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.plugin_registry import PluginNotBoundError
from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.runtime.cognitive_tools.registry import (
    CognitiveToolRegistration,
    CognitiveToolRegistry,
)
from zentex.runtime.transcript import BrainTranscriptEntryType


class SecurityBlockError(RuntimeError):
    """Raised when a cognitive tool attempts to cross the no-side-effects boundary."""


class CognitiveToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_id: str
    summary: str
    proposals: List[Dict[str, Any]] = Field(default_factory=list)
    ranked_options: List[Dict[str, Any]] = Field(default_factory=list)
    risks: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    uncertainties: List[Dict[str, Any]] = Field(default_factory=list)
    context_updates: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


@dataclass(frozen=True)
class CognitiveToolInvocation:
    invocation_id: str
    tool_id: str
    session_id: str
    turn_id: str
    phase: str
    started_at: datetime
    finished_at: datetime
    status: str
    trigger_matches: List[str]


@dataclass(frozen=True)
class CognitiveToolOrchestrationReport:
    selected_tools: List[str]
    skipped_tools: List[str]
    parallel_groups: List[List[str]]
    serial_groups: List[List[str]]
    invocations: List[CognitiveToolInvocation]
    merged_result: CognitiveToolResult


@dataclass(frozen=True)
class ToolInvocationPlan:
    session_id: str
    turn_id: str
    phase: str
    context: Dict[str, Any]
    requested_tool_ids: List[str] = field(default_factory=list)


class CognitiveToolOrchestrator:
    """
    Execute active cognitive tools under read-only, side-effect-free constraints.

    This layer is purely cognitive. It may inspect and synthesize internal
    reasoning artifacts, but it must never execute or emit external actions.
    """

    _FORBIDDEN_ACTION_KEYS = {
        "write_file",
        "network_call",
        "execute_shell",
        "external_action",
        "mutate_host",
        "system_command",
        "shell_command",
        "http_post",
    }

    def __init__(
        self,
        *,
        registry: CognitiveToolRegistry,
        transcript_store: Any,
        session_id: str,
        turn_id: str,
        phase: str = "phase_7_orchestrate_cognitive_tools",
    ) -> None:
        self._registry = registry
        self._transcript_store = transcript_store
        self._session_id = session_id
        self._turn_id = turn_id
        self._phase = phase
        
        # Priority 3: Systematic invocation logging (0% gap)
        self._log_path = Path("app_data/logs/cognitive_tool_invocations.jsonl")
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def run(self, context: Dict[str, Any]) -> CognitiveToolOrchestrationReport:
        registrations = self._resolve_registrations(context)
        selected_tools = [registration.plugin_id for registration in registrations]
        skipped_tools = self._derive_skipped_tools(context, selected_tools)
        parallel_groups, serial_groups = self._build_execution_groups(registrations)

        invocations: List[CognitiveToolInvocation] = []
        results: List[CognitiveToolResult] = []
        for registration in registrations:
            result, invocation = self._invoke_tool(registration, context)
            results.append(result)
            invocations.append(invocation)

        return CognitiveToolOrchestrationReport(
            selected_tools=selected_tools,
            skipped_tools=skipped_tools,
            parallel_groups=parallel_groups,
            serial_groups=serial_groups,
            invocations=invocations,
            merged_result=self._merge_results(results),
        )

    def _resolve_registrations(
        self,
        context: Dict[str, Any],
    ) -> List[CognitiveToolRegistration]:
        requested_tool_ids = [
            tool_id
            for tool_id in context.get("requested_tool_ids", [])
            if isinstance(tool_id, str) and tool_id
        ]
        requested_feature_codes = [
            f_code
            for f_code in context.get("requested_feature_codes", [])
            or context.get("requested_behavior_keys", [])
            if isinstance(f_code, str) and f_code
        ]

        active_registrations = [
            registration
            for registration in self._registry.list_registrations()
            if registration.status == PluginLifecycleStatus.ACTIVE
        ]

        matching_registrations: List[CognitiveToolRegistration] = []
        for registration in active_registrations:
            if requested_tool_ids and registration.plugin_id not in requested_tool_ids:
                continue
            if (
                requested_feature_codes
                and registration.spec.feature_code not in requested_feature_codes
            ):
                continue
            trigger_matches = self._matching_trigger_conditions(registration.spec, context)
            if not trigger_matches:
                continue
            if self._is_blocked_by_forbidden_conditions(registration.spec, context):
                continue
            matching_registrations.append(registration)

        if requested_feature_codes:
            missing_feature_codes = [
                f_code
                for f_code in requested_feature_codes
                if not any(
                    registration.spec.feature_code == f_code
                    for registration in matching_registrations
                )
            ]
            if missing_feature_codes:
                raise PluginNotBoundError(
                    "No active bound plugin is available for runtime use: "
                    + ", ".join(sorted(missing_feature_codes))
                )

        return sorted(
            matching_registrations,
            key=lambda registration: (
                registration.spec.feature_code,
                registration.plugin_id,
            ),
        )

    def _derive_skipped_tools(
        self,
        context: Dict[str, Any],
        selected_tools: List[str],
    ) -> List[str]:
        skipped: List[str] = []
        for registration in self._registry.list_registrations():
            if registration.status != PluginLifecycleStatus.ACTIVE:
                continue
            if registration.plugin_id in selected_tools:
                continue
            if self._matching_trigger_conditions(registration.spec, context):
                skipped.append(registration.plugin_id)
        return skipped

    def _build_execution_groups(
        self,
        registrations: List[CognitiveToolRegistration],
    ) -> Tuple[List[List[str]], List[List[str]]]:
        parallel_tools: List[str] = []
        serial_groups: List[List[str]] = []
        for registration in registrations:
            if self._must_run_serial(registration.spec):
                serial_groups.append([registration.plugin_id])
            else:
                parallel_tools.append(registration.plugin_id)
        parallel_groups = [parallel_tools] if parallel_tools else []
        return parallel_groups, serial_groups

    def _must_run_serial(self, spec: CognitiveToolSpec) -> bool:
        if spec.read_only is not True or spec.side_effect_free is not True:
            return True
        if not spec.is_concurrency_safe:
            return True
        return False

    def _invoke_tool(
        self,
        registration: CognitiveToolRegistration,
        context: Dict[str, Any],
    ) -> Tuple[CognitiveToolResult, CognitiveToolInvocation]:
        plugin = registration.spec
        self._validate_plugin_boundary(plugin)
        executor = getattr(plugin, "run_tool", None)
        if not callable(executor):
            raise SecurityBlockError(
                f"Cognitive tool plugin does not expose run_tool(): {plugin.plugin_id}"
            )

        invocation_id = str(uuid4())
        trace_id = invocation_id
        trigger_matches = self._matching_trigger_conditions(plugin, context)
        started_at = datetime.now(timezone.utc)
        self._transcript_store.write_entry(
            session_id=self._session_id,
            turn_id=self._turn_id,
            entry_type=BrainTranscriptEntryType.COGNITIVE_TOOL_INVOKED,
            payload={
                "invocation_id": invocation_id,
                "tool_id": plugin.plugin_id,
                "feature_code": plugin.feature_code,
                "phase": self._phase,
                "trigger_matches": trigger_matches,
                "context": self._json_safe(context),
            },
            source="cognitive_tool_orchestrator",
            trace_id=trace_id,
        )

        raw_result = executor(context)
        result = CognitiveToolResult.model_validate(raw_result)
        self._validate_result_boundary(plugin, result)
        finished_at = datetime.now(timezone.utc)

        self._transcript_store.write_entry(
            session_id=self._session_id,
            turn_id=self._turn_id,
            entry_type=BrainTranscriptEntryType.COGNITIVE_TOOL_COMPLETED,
            payload={
                "invocation_id": invocation_id,
                "tool_id": plugin.plugin_id,
                "feature_code": plugin.feature_code,
                "phase": self._phase,
                "summary": result.summary,
                "result": result.model_dump(mode="json"),
            },
            source="cognitive_tool_orchestrator",
            trace_id=trace_id,
        )

        self._registry.record_tool_usage(plugin.plugin_id, used_at=finished_at)
        
        invocation = CognitiveToolInvocation(
            invocation_id=invocation_id,
            tool_id=plugin.plugin_id,
            session_id=self._session_id,
            turn_id=self._turn_id,
            phase=self._phase,
            started_at=started_at,
            finished_at=finished_at,
            status="completed",
            trigger_matches=trigger_matches,
        )
        
        # Priority 3: Persistence for post-promotion tracking
        self._persist_invocation_log(invocation, result)
        
        return result, invocation

    def _persist_invocation_log(self, invocation: CognitiveToolInvocation, result: CognitiveToolResult):
        """Append invocation record to a durable JSONL log for monitoring (Priority 3)."""
        import json
        try:
            with self._log_path.open("a", encoding="utf-8") as f:
                entry = {
                    "invocation_id": invocation.invocation_id,
                    "tool_id": invocation.tool_id,
                    "session_id": invocation.session_id,
                    "turn_id": invocation.turn_id,
                    "started_at": invocation.started_at.isoformat(),
                    "finished_at": invocation.finished_at.isoformat(),
                    "status": invocation.status,
                    "confidence": result.confidence,
                    "summary": result.summary
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass # Fail-silent for logging

    def _validate_plugin_boundary(self, plugin: CognitiveToolSpec) -> None:
        if plugin.status != PluginLifecycleStatus.ACTIVE:
            raise PluginNotBoundError(
                f"No active bound plugin is available for runtime use: {plugin.plugin_id}"
            )
        if plugin.read_only is not True or plugin.side_effect_free is not True:
            raise SecurityBlockError(
                f"Cognitive tool must remain read-only and side-effect-free: {plugin.plugin_id}"
            )

    def _validate_result_boundary(
        self,
        plugin: CognitiveToolSpec,
        result: CognitiveToolResult,
    ) -> None:
        if result.tool_id != plugin.plugin_id:
            raise ValueError(
                f"Tool result mismatch: expected {plugin.plugin_id}, got {result.tool_id}"
            )
        self._scan_for_forbidden_actions(result.model_dump(mode="json"))

    def _scan_for_forbidden_actions(self, value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in self._FORBIDDEN_ACTION_KEYS:
                    raise SecurityBlockError(
                        f"Cognitive tool attempted forbidden external action: {key}"
                    )
                self._scan_for_forbidden_actions(nested)
            return
        if isinstance(value, list):
            for nested in value:
                self._scan_for_forbidden_actions(nested)

    def _matching_trigger_conditions(
        self,
        spec: CognitiveToolSpec,
        context: Dict[str, Any],
    ) -> List[str]:
        matches: List[str] = []
        for condition in spec.trigger_conditions:
            if self._condition_matches(condition, context):
                matches.append(condition)
        return matches

    def _is_blocked_by_forbidden_conditions(
        self,
        spec: CognitiveToolSpec,
        context: Dict[str, Any],
    ) -> bool:
        return any(self._condition_matches(condition, context) for condition in spec.do_not_use_when)

    def _condition_matches(self, condition: str, context: Dict[str, Any]) -> bool:
        if condition == "always":
            return True
        if condition == "multi_stage_goal":
            goal_stages = context.get("goal_stages")
            if isinstance(goal_stages, list) and len(goal_stages) > 1:
                return True
            task_description = context.get("task_description")
            if isinstance(task_description, str):
                lowered = task_description.lower()
                return " then " in lowered or " and " in lowered or "->" in lowered
            return False
        if condition == "multiple_candidate_paths":
            candidate_paths = context.get("candidate_paths")
            return isinstance(candidate_paths, list) and len(candidate_paths) > 1
        state_flags = context.get("state_flags", [])
        if isinstance(state_flags, list) and condition in state_flags:
            return True
        value = context.get(condition)
        return value is True

    def _merge_results(self, results: List[CognitiveToolResult]) -> CognitiveToolResult:
        if not results:
            return CognitiveToolResult(
                tool_id="merged",
                summary="No cognitive tools were triggered",
            )

        merged_proposals: List[Dict[str, Any]] = []
        merged_ranked_options: List[Dict[str, Any]] = []
        merged_risks: List[Dict[str, Any]] = []
        merged_evidence: List[Dict[str, Any]] = []
        merged_uncertainties: List[Dict[str, Any]] = []
        merged_context_updates: Dict[str, Any] = {}
        for result in results:
            merged_proposals.extend(result.proposals)
            merged_ranked_options.extend(result.ranked_options)
            merged_risks.extend(result.risks)
            merged_evidence.extend(result.evidence)
            merged_uncertainties.extend(result.uncertainties)
            merged_context_updates.update(result.context_updates)

        return CognitiveToolResult(
            tool_id="merged",
            summary="Merged cognitive tool outputs",
            proposals=merged_proposals,
            ranked_options=merged_ranked_options,
            risks=merged_risks,
            evidence=merged_evidence,
            uncertainties=merged_uncertainties,
            context_updates=merged_context_updates,
            confidence=sum(result.confidence for result in results) / len(results),
        )

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, dict):
            return {str(key): self._json_safe(nested) for key, nested in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, BaseModel):
            return self._json_safe(value.model_dump(mode="json"))
        return str(value)


__all__ = [
    "CognitiveToolInvocation",
    "CognitiveToolOrchestrationReport",
    "CognitiveToolOrchestrator",
    "CognitiveToolRegistry",
    "CognitiveToolRegistration",
    "CognitiveToolResult",
    "CognitiveToolSpec",
    "PluginNotBoundError",
    "SecurityBlockError",
    "ToolInvocationPlan",
]

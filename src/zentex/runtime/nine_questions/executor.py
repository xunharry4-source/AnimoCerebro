import logging
from datetime import datetime, timezone
from typing import Any, List

logger = logging.getLogger(__name__)

from zentex.common.plugin_registry import PluginNotBoundError
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.runtime.cognitive_tools import CognitiveToolResult
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.runtime.nine_questions.state import NineQuestionId, NineQuestionState
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _feature_code_for_question(question_id: NineQuestionId) -> str:
    return f"nine_questions.{str(question_id).replace('q', 'q')}"


def _resolve_active_model_provider(runtime: Any) -> Any:
    records = getattr(runtime, "managed_plugin_records", None)
    if not isinstance(records, dict):
        raise PluginNotBoundError("Managed plugin records are not attached to the runtime")
    candidates: List[Any] = []
    for record in records.values():
        plugin = getattr(record, "plugin", None)
        if plugin is None:
            continue
        if not callable(getattr(plugin, "plugin_kind", None)):
            continue
        if plugin.plugin_kind() != "model_provider":
            continue
        if getattr(plugin, "status", None) != PluginLifecycleStatus.ACTIVE:
            continue
        if not hasattr(plugin, "generate_json"):
            continue
        candidates.append(plugin)
    if not candidates:
        raise PluginNotBoundError("No active bound plugin is available for runtime use: model_provider")
    candidates.sort(key=lambda plugin: (getattr(plugin, "version", "0.0.0"), getattr(plugin, "plugin_id", "")), reverse=True)
    return candidates[0]


def _resolve_active_managed_plugin(runtime: Any, feature_code: str) -> Any | None:
    records = getattr(runtime, "managed_plugin_records", None)
    if not isinstance(records, dict):
        return None
    candidates: list[Any] = []
    for record in records.values():
        if getattr(record, "feature_code", None) != feature_code:
            continue
        plugin = getattr(record, "plugin", None)
        if plugin is None:
            continue
        if getattr(plugin, "status", None) != PluginLifecycleStatus.ACTIVE:
            continue
        candidates.append(plugin)
    if not candidates:
        return None
    candidates.sort(
        key=lambda plugin: (getattr(plugin, "version", "0.0.0"), getattr(plugin, "plugin_id", "")),
        reverse=True,
    )
    return candidates[0]


def _resolve_active_tools_by_feature_code(
    registry: CognitiveToolRegistry,
    feature_code: str,
) -> List[Any]:
    registrations = [
        registration
        for registration in registry.list_registrations()
        if registration.status == PluginLifecycleStatus.ACTIVE
        and getattr(registration.spec, "feature_code", None) == feature_code
    ]
    if not registrations:
        raise PluginNotBoundError(
            f"No active bound plugin is available for runtime use: {feature_code}"
        )
    registrations.sort(
        key=lambda registration: (
            getattr(registration.spec, "version", "0.0.0"),
            registration.plugin_id,
        ),
        reverse=True,
    )
    return [registration.spec for registration in registrations]


class NineQuestionExecutor:
    def __init__(
        self,
        *,
        registry: CognitiveToolRegistry,
        transcript_store: BrainTranscriptStore,
    ) -> None:
        self._registry = registry
        self._transcript_store = transcript_store

    def run_questions(
        self,
        *,
        runtime: Any,
        session: Any,
        state: NineQuestionState,
        question_ids: List[NineQuestionId],
        trace_id: str,
        refresh_reason: str,
        driver_refs: List[str],
        turn_id: str,
    ) -> None:
        provider = _resolve_active_model_provider(runtime)
        refreshed_at = _now()

        for qid in question_ids:
            logger.info(f"[Nine Questions Executor] Starting execution of {qid}")
            feature_code = f"nine_questions.{qid}"
            tools = _resolve_active_tools_by_feature_code(self._registry, feature_code)
            question_trace_id = f"{trace_id}:{qid}"
            
            if not tools:
                logger.warning(
                    f"[Nine Questions Executor] No tools found for {qid} (feature_code: {feature_code}). "
                    f"Skipping this question."
                )
                continue

            context_snapshot = {}
            last_context_snapshot = getattr(session, "last_context_snapshot", None)
            if isinstance(last_context_snapshot, dict):
                context_snapshot.update(last_context_snapshot)
            context_snapshot.update(state.current_context)
            context_snapshot["snapshot_version"] = state.snapshot_version

            question_driver_refs = list(driver_refs) or []
            if not question_driver_refs:
                question_driver_refs = [f"{refresh_reason} triggers {qid}"]

            nine_question_state_payload = {
                f"q{i}": (
                    state.question_snapshots.get(f"q{i}", {}).get("context_updates", {})
                    if isinstance(state.question_snapshots.get(f"q{i}"), dict)
                    else {}
                )
                for i in range(1, 10)
            }
            execution_context = {
                "session_id": getattr(session, "session_id", "unknown-session"),
                "turn_id": str(turn_id),
                "trace_id": question_trace_id,
                "decision_id": f"{turn_id}:{qid}",
                "inspection": True,
                "context_snapshot": context_snapshot,
                "model_provider": provider,
                "transcript_store": self._transcript_store,
                "question_driver_refs": question_driver_refs,
                # Some nine-question plugins still depend on this registry-shaped context.
                "plugin_registry": getattr(runtime, "plugin_registry", None),
                "managed_plugin_records": getattr(runtime, "managed_plugin_records", None),
                "cognitive_tool_registry_runtime": self._registry,
                "nine_questions": dict(state.current_context.get("nine_questions", {}) or {}),
                "persistent_task_state": list(state.current_context.get("persistent_task_state", []) or []),
                "nine_question_state": nine_question_state_payload,
                "host_telemetry_plugin": _resolve_active_managed_plugin(runtime, "host.telemetry"),
                **dict(state.current_context),
            }
            if (
                "q5_authorization_boundary_profile" in execution_context
                and "q5_permission_boundary" not in execution_context
            ):
                execution_context["q5_permission_boundary"] = execution_context[
                    "q5_authorization_boundary_profile"
                ]

            general_plugin_registry = getattr(runtime, "plugin_registry", None)

            for tool in tools:
                if general_plugin_registry is not None and hasattr(
                    general_plugin_registry,
                    "plugin_call_scope",
                ):
                    with general_plugin_registry.plugin_call_scope(tool):
                        result = tool.run_tool(execution_context)
                else:
                    result = tool.run_tool(execution_context)
                if isinstance(result, CognitiveToolResult):
                    context_updates = dict(result.context_updates or {})
                    state.apply_question_result(
                        question_id=qid,
                        tool_id=str(result.tool_id),
                        summary=str(result.summary),
                        confidence=float(result.confidence),
                        context_updates=context_updates,
                        trace_id=question_trace_id,
                        refreshed_at=refreshed_at,
                        refresh_reason=refresh_reason,
                        driver_refs=question_driver_refs,
                    )
                    context_snapshot.update(context_updates)
                    execution_context.update(context_updates)
                    execution_context["context_snapshot"] = context_snapshot
                    execution_context["nine_questions"] = dict(
                        state.current_context.get("nine_questions", {}) or {}
                    )
                    execution_context["nine_question_state"] = {
                        f"q{i}": (
                            state.question_snapshots.get(f"q{i}", {}).get("context_updates", {})
                            if isinstance(state.question_snapshots.get(f"q{i}"), dict)
                            else {}
                        )
                        for i in range(1, 10)
                    }
                    if (
                        "q5_authorization_boundary_profile" in execution_context
                        and "q5_permission_boundary" not in execution_context
                    ):
                        execution_context["q5_permission_boundary"] = execution_context[
                            "q5_authorization_boundary_profile"
                        ]

            # Persist state snapshot after each question so replay can follow partial updates.
            self._transcript_store.write_entry(
                session_id=getattr(session, "session_id", "unknown-session"),
                turn_id=str(turn_id),
                entry_type=BrainTranscriptEntryType.NINE_QUESTION_STATE_UPDATED,
                timestamp=refreshed_at,
                payload=state.to_payload(),
                source="runtime.nine_questions",
                trace_id=question_trace_id,
            )
            logger.info(
                f"[Nine Questions Executor] Completed {qid}. "
                f"State now has {len(state.question_snapshots)} snapshots: {sorted(state.question_snapshots.keys())}"
            )

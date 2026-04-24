from __future__ import annotations
"""
Execution Service: Plugin Execution Management

Handles:
- Plugin execution with real results
- Call hierarchy validation
- Execution statistics tracking
- Automatic degradation on failures
"""


import logging
import json
import inspect
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from zentex.foundation.contracts import ActionIntent

from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.errors import PluginExecutionError
from zentex.common.protocol import TaskFeedback
from zentex.plugins.service.manage import _is_always_active

logger = logging.getLogger(__name__)


class ExecutionService:
    """
    Provides plugin execution capabilities.
    
    Responsibilities:
    - Execute plugins with real logic
    - Validate call hierarchy
    - Track execution statistics
    - Handle failures and auto-degradation
    """
    
    def __init__(self, storage, plugin_instances, execution_stats, determine_category_fn=None, promote_fn=None, public_service=None):
        """
        Initialize execution service.
        
        Args:
            storage: PluginStorage instance
            plugin_instances: In-memory plugin registry
            execution_stats: Execution statistics cache
            determine_category_fn: Function to determine plugin category
            promote_fn: Function to promote plugin to new status
        """
        self._storage = storage
        self._plugin_instances = plugin_instances
        self._execution_stats = execution_stats
        self._determine_category = determine_category_fn
        self._promote_plugin = promote_fn
        self._public_service = public_service

        # Cognitive services for integration (Reflection, Memory, Learning, Audit)
        self._audit_service: Any = None
        self._memory_service: Any = None
        self._reflection_service: Any = None
        self._learning_service: Any = None
        self._transcript_store: Any = None
        self._llm_service: Any = None
        self._foundation_service: Any = None
        self._environment_service: Any = None

    def attach_cognitive_services(
        self,
        *,
        audit_service: Any = None,
        memory_service: Any = None,
        reflection_service: Any = None,
        learning_service: Any = None,
        transcript_store: Any = None,
        llm_service: Any = None,
        foundation_service: Any = None,
        environment_service: Any = None,
    ) -> None:
        """Inject cognitive services for plugin integration context enrichment."""
        if audit_service is not None:
            self._audit_service = audit_service
        if memory_service is not None:
            self._memory_service = memory_service
        if reflection_service is not None:
            self._reflection_service = reflection_service
        if learning_service is not None:
            self._learning_service = learning_service
        if transcript_store is not None:
            self._transcript_store = transcript_store
        if llm_service is not None:
            self._llm_service = llm_service
        if foundation_service is not None:
            self._foundation_service = foundation_service
        if environment_service is not None:
            self._environment_service = environment_service

    @staticmethod
    def _normalize_lifecycle_status(value: object) -> str:
        return str(getattr(value, "value", value) or "").strip().lower()

    @staticmethod
    def _normalize_operational_status(value: object) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _normalize_result_payload(result: Any) -> Dict[str, Any]:
        if result is None:
            return {}
        if isinstance(result, dict):
            return result
        if hasattr(result, "model_dump"):
            dumped = result.model_dump(mode="json")
            if isinstance(dumped, dict):
                return dumped
        return {"value": result}

    @staticmethod
    def _contract_failure(*, error_code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "_execution_contract": True,
            "status": "failed",
            "error_code": error_code,
            "error_message": message,
            "data": dict(details or {}),
        }

    @staticmethod
    def _extract_nine_question_id(parameters: Dict[str, Any]) -> str:
        question_id = str((parameters or {}).get("question_id") or "").strip().lower()
        if question_id in {f"q{i}" for i in range(1, 10)}:
            return question_id
        return ""

    @staticmethod
    def _serialize_state_payload(state: Any) -> Dict[str, Any]:
        if isinstance(state, dict):
            return deepcopy(state)
        if hasattr(state, "to_dict") and callable(getattr(state, "to_dict", None)):
            payload = state.to_dict()
            return deepcopy(payload) if isinstance(payload, dict) else {}
        if hasattr(state, "model_dump") and callable(getattr(state, "model_dump", None)):
            payload = state.model_dump(mode="json")
            return deepcopy(payload) if isinstance(payload, dict) else {}
        return {}

    async def _inject_nine_question_state_if_needed(self, parameters: Dict[str, Any]) -> None:
        question_id = self._extract_nine_question_id(parameters)
        if not question_id:
            return
        existing = parameters.get("nine_question_state")
        if isinstance(existing, dict) and isinstance(existing.get("question_snapshots"), dict):
            return

        try:
            from zentex.web_console.di_container import WebConsoleContainer
            from zentex.nine_questions.service import NineQuestionService
            facade = WebConsoleContainer.get_kernel_service()
            state_manager = facade.get_nine_question_state_manager()
            nq_service = NineQuestionService(
                facade=facade,
                state_manager=state_manager,
            )
            payload = await nq_service.assert_latest_qualified_upstreams(question_id)
            if payload:
                parameters.setdefault("nine_question_state", payload)
        except Exception:
            logger.exception(
                "[Plugins] Failed injecting validated nine_question_state into execution context for %s",
                question_id,
            )
            raise

    async def _persist_nine_question_snapshot_from_result(
        self,
        *,
        question_id: str,
        plugin_id: str,
        trace_id: str,
        result_payload: Dict[str, Any],
    ) -> None:
        if not question_id:
            return
        try:
            from zentex.web_console.di_container import WebConsoleContainer
            from zentex.nine_questions.service import NineQuestionService
        except Exception:
            return

        try:
            facade = WebConsoleContainer.get_kernel_service()
        except Exception:
            return

        state_manager = facade.get_nine_question_state_manager()
        nq_service = NineQuestionService(
            facade=facade,
            state_manager=state_manager,
        )
        context_updates = result_payload.get("context_updates")
        context_updates = deepcopy(context_updates) if isinstance(context_updates, dict) else {}
        diagnosis = context_updates.get(f"{question_id}_execution_diagnosis")
        module_runs = diagnosis.get("module_runs") if isinstance(diagnosis, dict) else []
        module_runs = deepcopy(module_runs) if isinstance(module_runs, list) else []

        patch = {
            "tool_id": plugin_id,
            "trace_id": trace_id,
            "summary": str(result_payload.get("summary") or ""),
            "confidence": float(result_payload.get("confidence") or 0.0),
            "result": deepcopy(result_payload),
            "context_updates": context_updates,
            "module_runs": module_runs,
        }

        try:
            await nq_service.persist_question_snapshot_patch(
                question_id,
                patch,
                refresh_reason=f"plugin_execute:{question_id}:{plugin_id}",
            )
        except ValueError:
            state = await nq_service.get_state()
            snapshot_map = nq_service.get_question_snapshot_map(state)
            snapshot_map[question_id] = patch
            snapshot_map = nq_service._normalize_snapshot_map_metadata(  # type: ignore[attr-defined]
                snapshot_map,
                touch_updated_at=False,
            )
            snapshot_map[question_id] = nq_service._normalize_snapshot_metadata(  # type: ignore[attr-defined]
                snapshot_map[question_id],
                now_iso=nq_service._now_iso(),  # type: ignore[attr-defined]
                touch_updated_at=True,
            )
            if isinstance(state, dict):
                snapshot_version = int(state.get("snapshot_version", len(snapshot_map)) or len(snapshot_map))
                current_dirty = state.get("dirty_questions", [])
            else:
                snapshot_version = int(getattr(state, "snapshot_version", len(snapshot_map)) or len(snapshot_map))
                current_dirty = getattr(state, "dirty_questions", [])
            dirty_questions = nq_service._normalize_dirty_questions(  # type: ignore[attr-defined]
                [item for item in current_dirty if str(item).strip() != question_id]
            )
            await state_manager.update_state(
                "nq-baseline",
                question_snapshots=snapshot_map,
                snapshot_version=snapshot_version,
                dirty_questions=dirty_questions,
                last_refresh_reason=f"plugin_execute_bootstrap:{question_id}:{plugin_id}",
            )

    def _derive_operational_status(self, db_plugin: Dict[str, Any]) -> str:
        plugin_id = str(db_plugin.get("plugin_id") or "").strip()
        lifecycle_status = self._normalize_lifecycle_status(db_plugin.get("lifecycle_status"))
        if lifecycle_status != PluginLifecycleStatus.ACTIVE.value:
            return "unavailable"

        if db_plugin.get("stopped_at"):
            return "stopped"

        persisted_operational_status = self._normalize_operational_status(
            db_plugin.get("operational_status")
        )
        if persisted_operational_status == "stopped":
            return "stopped"

        plugin_instance = self._plugin_instances.get(plugin_id)
        if plugin_instance is None:
            # Runtime instance loading is handled later in execute_plugin_once().
            # Do not preemptively mark ACTIVE plugins as stopped here, otherwise
            # functional/governance plugins are rejected before on-demand rehydrate.
            return persisted_operational_status or "enabled"

        health = getattr(plugin_instance, "health_status", None)
        normalized_health = str(getattr(health, "value", health) or "").strip().lower()
        if normalized_health in {"degraded", "unhealthy", "abnormal"}:
            return "abnormal"

        if persisted_operational_status in {"enabled", "abnormal"}:
            return persisted_operational_status
        return "enabled"

    async def execute_plugin_once(
        self,
        *,
        plugin_id: str,
        task_id: str,
        parameters: Dict[str, Any],
        trace_id: str,
        originator_id: str,
        caller_plugin_id: Optional[str] = None,
    ) -> TaskFeedback:
        """
        Execute exactly one registered plugin instance.
        
        Flow:
        1. Validate plugin_id
        2. Validate call hierarchy constraints (classification rules)
        3. Check plugin is ACTIVE
        4. Get plugin instance from _plugin_instances
        5. Call plugin's execute method
        6. Return real execution result
        
        Note: caller_plugin_id is optional. If provided, verifies that the call
        hierarchy follows plugin classification rules (cognitive can call functional,
        functional cannot call anything, etc.)
        
        Args:
            plugin_id: ID of plugin to execute
            task_id: Task identifier
            parameters: Parameters to pass to plugin
            trace_id: Trace identifier for logging
            originator_id: ID of request originator
            caller_plugin_id: Optional caller plugin ID for hierarchy validation
            
        Returns:
            TaskFeedback with execution result
        """
        if not plugin_id:
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_found",
                remarks="Missing plugin_id."
            )

        # Validate plugin exists in database
        db_plugin = self._storage.get_plugin(plugin_id)
        if not db_plugin:
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_found",
                remarks=f"Plugin {plugin_id} not registered in database."
            )

        # Validate call hierarchy constraints if caller is a plugin
        if caller_plugin_id:
            constraint_error = self._validate_plugin_call_hierarchy(
                caller_plugin_id=caller_plugin_id,
                target_plugin_id=plugin_id,
                trace_id=trace_id
            )
            if constraint_error:
                return constraint_error

        lifecycle_status = self._normalize_lifecycle_status(db_plugin.get("lifecycle_status"))
        if (
            lifecycle_status != PluginLifecycleStatus.ACTIVE.value
            and _is_always_active(plugin_id)
            and self._public_service is not None
            and callable(getattr(self._public_service, "enable_plugin", None))
        ):
            try:
                self._public_service.enable_plugin(
                    plugin_id,
                    reason="auto-activation on execution for always-active cognitive plugin",
                )
                refreshed = self._storage.get_plugin(plugin_id)
                if isinstance(refreshed, dict):
                    db_plugin = refreshed
                    lifecycle_status = self._normalize_lifecycle_status(
                        db_plugin.get("lifecycle_status")
                    )
            except Exception as exc:
                logger.error(
                    "[Plugins] Auto-activation failed for always-active plugin %s: %s",
                    plugin_id,
                    exc,
                )

        if lifecycle_status != PluginLifecycleStatus.ACTIVE.value:
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_active",
                remarks=f"Plugin {plugin_id} lifecycle_status is {lifecycle_status or 'unknown'}, not ACTIVE."
            )

        operational_status = self._derive_operational_status(db_plugin)
        if operational_status != "enabled":
            logger.warning(
                "[Plugins] Refusing execution for %s trace=%s session=%s turn=%s: lifecycle=%s operational=%s in_memory=%s stopped_at=%s",
                plugin_id,
                trace_id,
                parameters.get("session_id"),
                parameters.get("turn_id"),
                lifecycle_status,
                operational_status,
                plugin_id in self._plugin_instances,
                db_plugin.get("stopped_at"),
            )
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_enabled",
                remarks=(
                    f"Plugin {plugin_id} is ACTIVE but operational_status is "
                    f"{operational_status}, so it cannot execute."
                ),
            )

        # Get plugin instance from memory (with on-demand rehydration)
        plugin_instance = self._plugin_instances.get(plugin_id)
        if not plugin_instance and self._public_service is not None:
            if hasattr(self._public_service, "ensure_runtime_instance_loaded"):
                if self._public_service.ensure_runtime_instance_loaded(plugin_id):
                    plugin_instance = self._plugin_instances.get(plugin_id)

        if not plugin_instance:
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="plugin_not_instantiated",
                remarks=(
                    f"Plugin {plugin_id} is ACTIVE in the library but failed to instantiate "
                    "in memory. Check logs for rehydration errors."
                )
            )

        try:
            if isinstance(parameters, dict) and self._public_service is not None:
                parameters.setdefault("plugin_service", self._public_service)
                
                # Enrich context with authentic cognitive services for integration
                if self._audit_service is not None:
                    parameters.setdefault("audit_service", self._audit_service)
                if self._memory_service is not None:
                    parameters.setdefault("memory_service", self._memory_service)
                if self._reflection_service is not None:
                    parameters.setdefault("reflection_service", self._reflection_service)
                if self._learning_service is not None:
                    parameters.setdefault("learning_service", self._learning_service)
                if self._transcript_store is not None:
                    parameters.setdefault("transcript_store", self._transcript_store)
                    parameters.setdefault("root_transcript_store", self._transcript_store)
                if self._llm_service is not None:
                    parameters.setdefault("llm_service", self._llm_service)
                if self._foundation_service is not None:
                    parameters.setdefault("foundation_service", self._foundation_service)
                if self._environment_service is not None:
                    parameters.setdefault("environment_service", self._environment_service)

                await self._inject_nine_question_state_if_needed(parameters)
            # Call actual plugin execution
            result = await self._call_plugin_execute(
                plugin_instance=plugin_instance,
                task_id=task_id,
                parameters=parameters,
                trace_id=trace_id,
                originator_id=originator_id,
                category=db_plugin.get("category", "functional")
            )
            if isinstance(result, dict) and result.get("_execution_contract") is True:
                error_code = str(result.get("error_code") or "plugin_execution_failed")
                error_message = str(result.get("error_message") or "Plugin execution failed.")
                self._record_failed_execution(plugin_id, error_message)
                return TaskFeedback(
                    task_id=task_id,
                    status="failed",
                    error=error_code,
                    result={
                        "plugin_id": plugin_id,
                        "trace_id": trace_id,
                        "contract_status": result.get("status"),
                        "details": result.get("data", {}),
                    },
                    remarks=error_message,
                )

            if result is None:
                # 严禁把插件返回 None 伪装成成功执行。
                # 这里如果继续拼一个“executed successfully”的默认 payload，
                # 就会把真实后台故障伪装成成功，严重破坏系统稳定性和审计可信度。
                error_message = (
                    f"Plugin {plugin_id} returned None after _call_plugin_execute; "
                    "structured output is required."
                )
                logger.error("[Plugins] Contract Violation: %s", error_message)
                self._record_failed_execution(plugin_id, error_message)
                return TaskFeedback(
                    task_id=task_id,
                    status="failed",
                    error="plugin_contract_violation_none",
                    result={
                        "plugin_id": plugin_id,
                        "trace_id": trace_id,
                        "details": {},
                    },
                    remarks=error_message,
                )
            
            # Update execution stats
            self._record_successful_execution(plugin_id)
            question_id = self._extract_nine_question_id(parameters if isinstance(parameters, dict) else {})
            if question_id:
                try:
                    await self._persist_nine_question_snapshot_from_result(
                        question_id=question_id,
                        plugin_id=plugin_id,
                        trace_id=trace_id,
                        result_payload=self._normalize_result_payload(result),
                    )
                except Exception:
                    logger.exception(
                        "[Plugins] Failed to persist nine-question snapshot from plugin execution: %s",
                        question_id,
                    )
            
            return TaskFeedback(
                task_id=task_id,
                status="done",
                result=self._normalize_result_payload(result),
                progress=1.0,
                remarks=f"Plugin {plugin_id} executed successfully."
            )
            
        except PluginExecutionError as p_exc:
             logger.error(f"[Plugins] Structured execution error in {plugin_id}: {p_exc}")
             self._record_failed_execution(plugin_id, str(p_exc))
             return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="execution_error",
                result={
                    "plugin_id": plugin_id,
                    "error": str(p_exc),
                    "trace_id": trace_id
                },
                remarks=f"Plugin {plugin_id} execution failed: {p_exc}"
            )
        except Exception as exc:
            logger.error(f"[Plugins] Execution error in {plugin_id}: {exc}", exc_info=True)
            
            # Update failure stats
            self._record_failed_execution(plugin_id, str(exc))
            
            return TaskFeedback(
                task_id=task_id,
                status="failed",
                error="execution_error",
                result={
                    "plugin_id": plugin_id,
                    "error": str(exc),
                },
                remarks=f"Plugin {plugin_id} execution failed: {exc}"
            )

    async def _call_plugin_execute(
        self,
        *,
        plugin_instance: Any,
        task_id: str,
        parameters: Dict[str, Any],
        trace_id: str,
        originator_id: str,
        category: str = "functional",
    ) -> Optional[Dict[str, Any]]:
        """
        Call the plugin's execute method with proper parameter mapping.
        Supports multiple method signatures and enforces category-based timeouts.
        
        Args:
            plugin_instance: The instantiated plugin object
            task_id: Task identifier
            parameters: Parameters dict
            trace_id: Trace identifier
            originator_id: Originator identifier
            category: Plugin category for timeout logic
            
        Returns:
            Plugin execution result
        """
        # G12: Enforce timeouts (Cognitive: 60s, Functional: 20s)
        timeout = 60 if category == "cognitive" else 20
        # Try to find the canonical execution entrypoint for the plugin type.
        execute_method = None
        selected_method_name = None
        for method_name in ['execute', 'process', 'run', 'handle', 'run_tool']:
            if hasattr(plugin_instance, method_name):
                execute_method = getattr(plugin_instance, method_name)
                selected_method_name = method_name
                break

        family_call_kwargs: Dict[str, Any] = {}
        if execute_method is None:
            execute_method, selected_method_name, family_call_kwargs = self._resolve_functional_family_method(
                plugin_instance=plugin_instance,
                parameters=parameters,
            )

        if not execute_method:
            logger.warning(
                "[Plugins] Plugin instance has no execute/process/run/handle/run_tool method"
            )
            return self._contract_failure(
                error_code="plugin_execute_method_missing",
                message="Plugin instance has no supported execution entrypoint.",
            )
        
        # Build parameters based on method signature
        sig = inspect.signature(execute_method)
        call_kwargs = dict(family_call_kwargs)
        
        for param_name in sig.parameters:
            if param_name == 'self':
                continue
            elif param_name == 'task_id':
                call_kwargs['task_id'] = task_id
            elif param_name == 'parameters' or param_name == 'input':
                call_kwargs[param_name] = parameters
            elif param_name == 'trace_id':
                call_kwargs['trace_id'] = trace_id
            elif param_name == 'originator_id':
                call_kwargs['originator_id'] = originator_id
            elif param_name == 'context':
                call_kwargs['context'] = parameters
            elif param_name in parameters:
                # Use parameter from input if available
                call_kwargs[param_name] = parameters[param_name]

        if selected_method_name == 'run_tool' and 'context' not in call_kwargs:
            call_kwargs['context'] = parameters

        # Phase G: Authentic Cognitive Service Injection
        if isinstance(call_kwargs.get('context'), dict):
            ctx = call_kwargs['context']
            if self._audit_service and 'audit_service' not in ctx:
                ctx['audit_service'] = self._audit_service
            if self._memory_service and 'memory_service' not in ctx:
                ctx['memory_service'] = self._memory_service
            if self._reflection_service and 'reflection_service' not in ctx:
                ctx['reflection_service'] = self._reflection_service
            if self._learning_service and 'learning_service' not in ctx:
                ctx['learning_service'] = self._learning_service
            if self._transcript_store and 'transcript_store' not in ctx:
                ctx['transcript_store'] = self._transcript_store
            if hasattr(self, '_llm_service') and self._llm_service and 'llm_service' not in ctx:
                ctx['llm_service'] = self._llm_service
            
            # Also inject plugin_service if available for recursive execution
            if self._public_service and 'plugin_service' not in ctx:
                ctx['plugin_service'] = self._public_service

        # G12 & G14: Call with async support and timeout
        try:
            if inspect.iscoroutinefunction(execute_method):
                result = await asyncio.wait_for(execute_method(**call_kwargs), timeout=timeout)
            else:
                # Sync methods are still wrapped in wait_for but they block the thread
                # unless offloaded. For now, we wrap to handle logical timeouts if possible,
                # but real thread-blocking sync methods will still block.
                result = execute_method(**call_kwargs)
        except asyncio.TimeoutError:
            raise PluginExecutionError(
                f"Plugin reached execution timeout of {timeout}s",
                trace_id=trace_id
            )
        except Exception as exc:
            if isinstance(exc, PluginExecutionError):
                raise exc
            raise PluginExecutionError(
                f"Plugin execution failed internally: {exc}",
                original_exc=exc,
                trace_id=trace_id
            )

        # G11: Enforce strict contract (No None allowed)
        if result is None:
            msg = f"Plugin '{getattr(plugin_instance, 'plugin_id', 'unknown')}' (method: {selected_method_name}) returned None."
            logger.error(f"[Plugins] Contract Violation: {msg}")
            return self._contract_failure(
                error_code="plugin_contract_violation_none",
                message=f"Plugin execution returned None; structured output is required. {msg}",
                details={
                    "selected_method": selected_method_name,
                    "trace_id": trace_id,
                },
            )
        
        # G11: Reject empty results for cognitive plugins if they don't explicitly declare success
        if category == "cognitive" and isinstance(result, dict) and not result:
            msg = f"Cognitive plugin '{getattr(plugin_instance, 'plugin_id', 'unknown')}' returned an empty dict."
            logger.warning(f"[Plugins] Stability Guard: {msg} Treating as failure.")
            return self._contract_failure(
                error_code="cognitive_pseudo_success",
                message=f"Cognitive plugin returned empty result without contract. {msg}",
                details={"trace_id": trace_id}
            )

        # G11: If result is a dict but contains 'error' without being a contract, 
        # it might be a masked failure.
        if isinstance(result, dict) and "error" in result and result.get("_execution_contract") is not True:
             return self._contract_failure(
                error_code=str(result.get("error_code") or "plugin_internal_error"),
                message=str(result.get("error_message") or result.get("error") or "Internal plugin error"),
                details=result
            )

        return result

    def _resolve_functional_family_method(
        self,
        *,
        plugin_instance: Any,
        parameters: Dict[str, Any],
    ) -> tuple[Optional[Any], Optional[str], Dict[str, Any]]:
        family_methods: list[tuple[str, Any]] = [
            ("ingest_signal", lambda: {}),
            (
                "sanitize_signal",
                lambda: {"raw_signal": parameters.get("raw_signal", parameters.get("signal", ""))},
            ),
            (
                "interpret_signal",
                lambda: {"signal": parameters.get("signal", parameters.get("sanitized_signal"))},
            ),
            ("capture_host_state", lambda: {"context": parameters}),
            ("get_payload", lambda: {}),
            ("get_forbidden_zones", lambda: {}),
            ("get_downgrade_options", lambda: {"block_context": parameters.get("block_context", parameters)}),
            (
                "refine_task_queue",
                lambda: {
                    "task_queue": parameters.get("task_queue", []),
                    "context": parameters.get("context", parameters),
                },
            ),
            ("apply_posture", lambda: {"decision_trace": parameters.get("decision_trace", parameters)}),
            ("calculate_weight", lambda: {"task_context": parameters.get("task_context", parameters)}),
            ("check_compliance", lambda: {"action_trace": parameters.get("action_trace", parameters)}),
            ("get_whitelist", lambda: {}),
            ("get_agent_scope", lambda: {"agent_id": parameters.get("agent_id", "")}),
            (
                "execute_action",
                lambda: {
                    "intent": self._build_action_intent(parameters),
                    "context": parameters.get("context", parameters),
                },
            ),
        ]

        for method_name, kwargs_factory in family_methods:
            if not hasattr(plugin_instance, method_name):
                continue
            method = getattr(plugin_instance, method_name)
            if not callable(method):
                continue
            return method, method_name, kwargs_factory()
        return None, None, {}

    @staticmethod
    def _build_action_intent(parameters: Dict[str, Any]) -> ActionIntent:
        raw_intent = parameters.get("intent")
        if isinstance(raw_intent, ActionIntent):
            return raw_intent
        if isinstance(raw_intent, dict):
            return ActionIntent.model_validate(raw_intent)
        return ActionIntent(
            action_type=str(parameters.get("action_type") or parameters.get("action_name") or "describe_capability"),
            target=str(parameters.get("target") or ""),
            parameters=dict(parameters.get("parameters") or parameters.get("action_payload") or {}),
            requester_id=str(parameters.get("requester_id") or parameters.get("originator_id") or ""),
        )

    def _validate_plugin_call_hierarchy(
        self,
        *,
        caller_plugin_id: str,
        target_plugin_id: str,
        trace_id: str,
    ) -> Optional[TaskFeedback]:
        """
        Validate that a plugin call respects the classification constraints.
        
        Rules:
        - Cognitive → Cognitive: ❌ DENIED
        - Cognitive → Functional: ✅ ALLOWED
        - Functional → Anything: ❌ DENIED
        
        Args:
            caller_plugin_id: The plugin attempting to call
            target_plugin_id: The plugin being called
            trace_id: For logging
            
        Returns:
            TaskFeedback with error if constraint violated, None if allowed
        """
        # Get caller's category
        caller_db = self._storage.get_plugin(caller_plugin_id)
        if not caller_db:
            logger.warning(
                f"[Plugins] Call attempt from unregistered plugin {caller_plugin_id} "
                f"to {target_plugin_id} (trace: {trace_id})"
            )
            return TaskFeedback(
                task_id=trace_id,
                status="failed",
                error="caller_plugin_not_registered",
                remarks=f"Caller plugin {caller_plugin_id} is not registered."
            )

        caller_category = caller_db.get("category", "functional")
        
        # Get target's category  
        target_db = self._storage.get_plugin(target_plugin_id)
        if not target_db:
            return TaskFeedback(
                task_id=trace_id,
                status="failed",
                error="target_plugin_not_registered",
                remarks=f"Target plugin {target_plugin_id} is not registered."
            )
        
        target_category = target_db.get("category", "functional")

        # Rule 1: Cognitive cannot call Cognitive
        if caller_category == "cognitive" and target_category == "cognitive":
            log_msg = (
                f"[Plugins] CONSTRAINT VIOLATION: Cognitive plugin {caller_plugin_id} "
                f"attempted to call cognitive plugin {target_plugin_id} (trace: {trace_id})"
            )
            logger.error(log_msg)
            return TaskFeedback(
                task_id=trace_id,
                status="failed",
                error="call_hierarchy_violation",
                remarks=f"Cognitive plugin cannot call another cognitive plugin. "
                        f"Caller: {caller_plugin_id}, Target: {target_plugin_id}"
            )

        # Rule 2: Functional cannot call anything
        if caller_category == "functional":
            log_msg = (
                f"[Plugins] CONSTRAINT VIOLATION: Functional plugin {caller_plugin_id} "
                f"attempted to call {target_category} plugin {target_plugin_id} (trace: {trace_id})"
            )
            logger.error(log_msg)
            return TaskFeedback(
                task_id=trace_id,
                status="failed",
                error="call_hierarchy_violation",
                remarks=f"Functional plugin cannot call other plugins. "
                        f"Caller: {caller_plugin_id}, Target: {target_plugin_id}"
            )

        # Rule 3: All others are allowed (cognitive → functional)
        logger.debug(
            f"[Plugins] Call allowed: {caller_category} plugin {caller_plugin_id} "
            f"→ {target_category} plugin {target_plugin_id} (trace: {trace_id})"
        )
        return None

    def _record_successful_execution(self, plugin_id: str) -> None:
        """
        Record successful plugin execution.
        
        Args:
            plugin_id: The plugin that was executed
        """
        if plugin_id not in self._execution_stats:
            self._execution_stats[plugin_id] = {
                'usage_count': 0,
                'failure_count': 0,
                'last_executed_at': None,
            }
        
        stats = self._execution_stats[plugin_id]
        stats['usage_count'] += 1
        stats['failure_count'] = 0  # Reset on success
        stats['last_executed_at'] = datetime.now(timezone.utc).isoformat()
        
        # Update database
        db_plugin = self._storage.get_plugin(plugin_id)
        if db_plugin:
            spec_dict = json.loads(db_plugin['spec_json'])
            self._storage.upsert_plugin(
                category=db_plugin['category'],
                plugin_id=plugin_id,
                spec_dict=spec_dict,
                registration_dict={**db_plugin, 'usage_count': stats['usage_count']}
            )

    def _record_failed_execution(self, plugin_id: str, error_msg: str) -> None:
        """
        Record failed plugin execution and possibly degrade.
        
        Args:
            plugin_id: The plugin that failed
            error_msg: Error message
        """
        if plugin_id not in self._execution_stats:
            self._execution_stats[plugin_id] = {
                'usage_count': 0,
                'failure_count': 0,
                'last_executed_at': None,
            }
        
        stats = self._execution_stats[plugin_id]
        stats['failure_count'] += 1
        stats['last_executed_at'] = datetime.now(timezone.utc).isoformat()

        if _is_always_active(plugin_id):
            logger.warning(
                "[Plugins] Skipping auto-degrade for always-active cognitive plugin %s after %s failures",
                plugin_id,
                stats['failure_count'],
            )
        # Auto-degrade after 3 consecutive failures
        elif stats['failure_count'] >= 3 and self._promote_plugin:
            logger.warning(f"[Plugins] Auto-degrading {plugin_id} after 3 failures")
            try:
                self._promote_plugin(
                    plugin_id=plugin_id,
                    target_lifecycle_status=PluginLifecycleStatus.DEGRADED,
                    reason=f"Auto-degraded after 3 consecutive failures: {error_msg}"
                )
            except Exception as e:
                logger.error(f"[Plugins] Failed to auto-degrade {plugin_id}: {e}")
        
        # Update database
        db_plugin = self._storage.get_plugin(plugin_id)
        if db_plugin:
            spec_dict = json.loads(db_plugin['spec_json'])
            self._storage.upsert_plugin(
                category=db_plugin['category'],
                plugin_id=plugin_id,
                spec_dict=spec_dict,
                registration_dict={**db_plugin, 'failure_count': stats['failure_count']}
            )

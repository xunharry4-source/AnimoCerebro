from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict
from uuid import uuid4

from zentex.tasks.execution.graph_edges import (
    route_after_act,
    route_after_context,
    route_after_execution_check_after,
    route_after_execution_check_before,
    route_after_observe,
    route_after_preflight,
    route_after_reason,
    route_after_resolve_parameters,
    route_after_result_validate,
    route_after_retry_decision,
    route_after_verify,
)
from zentex.tasks.execution.graph_nodes.act_node import act_node
from zentex.tasks.execution.graph_nodes.complete_node import complete_node
from zentex.tasks.execution.graph_nodes.execution_check_node import execution_check_after_node, execution_check_before_node
from zentex.tasks.execution.graph_nodes.load_context_node import load_context_node
from zentex.tasks.execution.graph_nodes.observe_node import observe_node
from zentex.tasks.execution.graph_nodes.preflight_node import preflight_node
from zentex.tasks.execution.graph_nodes.reason_node import reason_node
from zentex.tasks.execution.graph_nodes.recover_node import recover_node
from zentex.tasks.execution.graph_nodes.resolve_parameters_node import resolve_parameters_node
from zentex.tasks.execution.graph_nodes.result_validate_node import result_validate_node
from zentex.tasks.execution.graph_nodes.retry_decision_node import retry_decision_node
from zentex.tasks.execution.graph_nodes.verify_node import verify_node
from zentex.tasks.execution.graph_state import ExecutionGraphState
from zentex.tasks.execution.persistence import mark_react_terminal, utc_now


@dataclass
class ReactExecutorConfig:
    execution_timeout_seconds: float = 300.0
    max_attempts: int = 1


class LangGraphReactExecutor:
    def __init__(
        self,
        *,
        task_dao: Any,
        task_service: Any = None,
        cli_service: Any = None,
        mcp_service: Any = None,
        external_connector_service: Any = None,
        agent_service: Any = None,
        internal_executor: Any = None,
        subtask_intent_builder: Any = None,
        llm_reason_gateway: Any = None,
        llm_validation_gateway: Any = None,
        config: ReactExecutorConfig | None = None,
    ) -> None:
        self._runtime = {
            "task_dao": task_dao,
            "task_service": task_service,
            "cli_service": cli_service,
            "mcp_service": mcp_service,
            "external_connector_service": external_connector_service,
            "agent_service": agent_service,
            "internal_executor": internal_executor,
            "llm_reason_gateway": llm_reason_gateway,
            "llm_validation_gateway": llm_validation_gateway,
        }
        self._subtask_intent_builder = subtask_intent_builder
        self._config = config or ReactExecutorConfig()
        self._runtime["execution_timeout_seconds"] = self._config.execution_timeout_seconds

    async def execute(self, task_id: str) -> Dict[str, Any]:
        run_id = f"react-run-{uuid4().hex}"
        runtime = dict(self._runtime)
        if self._subtask_intent_builder is not None and runtime.get("task_dao") is not None:
            task = runtime["task_dao"].get_task(task_id)
            if task is not None:
                runtime["subtask_intent"] = self._subtask_intent_builder(task)
        try:
            graph = self._build_graph()
        except ModuleNotFoundError as exc:
            if exc.name != "langgraph":
                raise
            return self._fail_langgraph_missing(task_id=task_id, run_id=run_id)

        initial_state: ExecutionGraphState = {
            "task_id": task_id,
            "run_id": run_id,
            "phase": "starting",
            "runtime": runtime,
            "retry_state": {"attempt_count": 0, "max_attempts": self._config.max_attempts},
            "observations": [],
            "audit_events": [],
            "failure": None,
        }
        final_state = await graph.ainvoke(initial_state)
        result = final_state.get("result") or {}
        return result if isinstance(result, dict) else {"succeeded": False, "error": "LangGraph returned invalid result"}

    def _build_graph(self) -> Any:
        from langgraph.graph import END, StateGraph

        graph = StateGraph(ExecutionGraphState)
        graph.add_node("load_context", load_context_node)
        graph.add_node("reason", reason_node)
        graph.add_node("resolve_parameters", resolve_parameters_node)
        graph.add_node("preflight", preflight_node)
        graph.add_node("execution_check_before", execution_check_before_node)
        graph.add_node("act", act_node)
        graph.add_node("observe", observe_node)
        graph.add_node("execution_check_after", execution_check_after_node)
        graph.add_node("result_validate", result_validate_node)
        graph.add_node("verify", verify_node)
        graph.add_node("retry_decision", retry_decision_node)
        graph.add_node("recover", recover_node)
        graph.add_node("complete", complete_node)

        graph.set_entry_point("load_context")
        graph.add_conditional_edges("load_context", route_after_context, {"reason": "reason", "recover": "recover"})
        graph.add_conditional_edges("reason", route_after_reason, {"resolve_parameters": "resolve_parameters", "recover": "recover"})
        graph.add_conditional_edges("resolve_parameters", route_after_resolve_parameters, {"preflight": "preflight", "recover": "recover"})
        graph.add_conditional_edges("preflight", route_after_preflight, {"execution_check_before": "execution_check_before", "retry_decision": "retry_decision"})
        graph.add_conditional_edges("execution_check_before", route_after_execution_check_before, {"act": "act", "recover": "recover"})
        graph.add_conditional_edges("act", route_after_act, {"observe": "observe", "retry_decision": "retry_decision"})
        graph.add_conditional_edges("observe", route_after_observe, {"execution_check_after": "execution_check_after", "retry_decision": "retry_decision"})
        graph.add_conditional_edges("execution_check_after", route_after_execution_check_after, {"result_validate": "result_validate", "retry_decision": "retry_decision"})
        graph.add_conditional_edges("result_validate", route_after_result_validate, {"verify": "verify", "retry_decision": "retry_decision"})
        graph.add_conditional_edges("verify", route_after_verify, {"complete": "complete", "retry_decision": "retry_decision"})
        graph.add_conditional_edges("retry_decision", route_after_retry_decision, {"preflight": "preflight", "recover": "recover"})
        graph.add_edge("recover", END)
        graph.add_edge("complete", END)
        return graph.compile()

    def _fail_langgraph_missing(self, *, task_id: str, run_id: str) -> Dict[str, Any]:
        result = {
            "succeeded": False,
            "status": "failed",
            "task_center_synchronized": True,
            "error": "LangGraph runtime is not installed; ReAct execution is fail-closed",
            "error_code": "LANGGRAPH_RUNTIME_MISSING",
            "finished_at": utc_now(),
        }
        task_dao = self._runtime.get("task_dao")
        if task_dao is not None:
            task_dao.update_task(
                task_id,
                {
                    "status": "failed",
                    "last_error": result["error"],
                    "execution_output": json.dumps(result, ensure_ascii=False, default=str),
                    "execution_finished_at": result["finished_at"],
                },
            )
            mark_react_terminal(task_dao=task_dao, task_id=task_id, run_id=run_id, status="failed", result=result)
        return result

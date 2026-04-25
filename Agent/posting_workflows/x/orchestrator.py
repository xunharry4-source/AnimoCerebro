"""
LangGraph orchestrator for X posting.

Purpose:
    Wire the X posting nodes into a LangGraph StateGraph.

Main responsibilities:
    - Define node order: browser -> topic -> enter X -> write -> verify -> document.
    - Stop the graph on fail-closed node errors.
    - Return XPostingState with evidence and error details.

Not responsible for:
    - Implementing node internals.
    - Installing LangGraph dependencies.
    - Treating unverified posts as successful.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, TypedDict

from Agent.posting_workflows.browser_node import OpenBrowserNode
from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.state import WorkflowContext, XPostingState
from Agent.posting_workflows.x.enter_x import EnterXNode
from Agent.posting_workflows.x.get_daily_topic import GetDailyTopicNode
from Agent.posting_workflows.x.update_document import UpdateXPostingDocumentNode
from Agent.posting_workflows.x.verify_success import VerifyXPostSuccessNode
from Agent.posting_workflows.x.write_post import WriteXPostNode


class XGraphState(TypedDict):
    state: XPostingState


class XPostingWorkflow:
    """LangGraph-backed X posting workflow."""

    def __init__(self, context: WorkflowContext | None = None) -> None:
        self.context = context or WorkflowContext()
        self.nodes = {
            "open_browser": OpenBrowserNode(),
            "get_daily_topic": GetDailyTopicNode(),
            "enter_x": EnterXNode(),
            "write_post": WriteXPostNode(),
            "verify_success": VerifyXPostSuccessNode(),
            "update_document": UpdateXPostingDocumentNode(),
        }
        self.graph = self._build_graph()

    def run(self, initial_state: XPostingState | None = None) -> XPostingState:
        """Run the LangGraph and return final X posting state."""
        result = self.graph.invoke({"state": initial_state or XPostingState()})
        return result["state"]

    def _build_graph(self) -> Any:
        try:
            from langgraph.graph import END, StateGraph
        except Exception as exc:
            raise PostingWorkflowError(
                f"LangGraph is required for XPostingWorkflow: {exc}",
                node="x_langgraph_build",
                code="langgraph_unavailable",
            ) from exc

        graph = StateGraph(XGraphState)
        for name, node in self.nodes.items():
            graph.add_node(name, self._wrap_node(node))

        graph.set_entry_point("open_browser")
        self._guarded_edge(graph, "open_browser", "get_daily_topic", END)
        self._guarded_edge(graph, "get_daily_topic", "enter_x", END)
        self._guarded_edge(graph, "enter_x", "write_post", END)
        self._guarded_edge(graph, "write_post", "verify_success", END)
        graph.add_edge("verify_success", "update_document")
        graph.add_edge("update_document", END)
        return graph.compile()

    def _wrap_node(self, node: Any) -> Callable[[XGraphState], Dict[str, XPostingState]]:
        def _runner(graph_state: XGraphState) -> Dict[str, XPostingState]:
            state = graph_state["state"]
            if state.error and node.name != "x_update_document":
                return {"state": state}
            try:
                node.run(self.context, state)
            except PostingWorkflowError as exc:
                state.status = "failed"
                state.error = exc.to_dict()
                state.add_evidence(node.name, False, str(exc), error=exc.to_dict())
            except Exception as exc:
                state.status = "failed"
                error = {
                    "node": node.name,
                    "code": "unexpected_exception",
                    "message": f"{exc.__class__.__name__}: {exc}",
                    "details": {},
                }
                state.error = error
                state.add_evidence(node.name, False, error["message"], error=error)
            return {"state": state}

        return _runner

    def _guarded_edge(self, graph: Any, source: str, next_node: str, end_node: Any) -> None:
        graph.add_conditional_edges(
            source,
            self._route_after_node,
            {"next": next_node, "end": end_node},
        )

    def _route_after_node(self, graph_state: XGraphState) -> str:
        return "end" if graph_state["state"].error else "next"

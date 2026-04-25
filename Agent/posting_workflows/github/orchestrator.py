"""
LangGraph orchestrator for GitHub Discussions posting.

Purpose:
    Wire GitHub Discussions posting nodes into a small LangGraph StateGraph.

Main responsibilities:
    - Define node order: repository -> topic -> write Discussion -> submit -> verify -> document.
    - Stop on fail-closed structured errors.
    - Route every success claim through GitHub API verification evidence.

Not responsible for:
    - Installing LangGraph dependencies.
    - Managing GITHUB_TOKEN.
    - Creating Discussions during import.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, TypedDict

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.github.get_repository import GetGitHubRepositoryNode
from Agent.posting_workflows.github.get_topic import GetGitHubTopicNode
from Agent.posting_workflows.github.submit_discussion import SubmitGitHubDiscussionNode
from Agent.posting_workflows.github.update_document import UpdateGitHubPostingDocumentNode
from Agent.posting_workflows.github.verify_success import VerifyGitHubDiscussionSuccessNode
from Agent.posting_workflows.github.write_discussion import WriteGitHubDiscussionNode
from Agent.posting_workflows.state import GitHubPostingState, WorkflowContext
from Agent.social_promotion.github_smart_poster import DEFAULT_GITHUB_REPOSITORY


class GitHubGraphState(TypedDict):
    state: GitHubPostingState


class GitHubPostingWorkflow:
    """LangGraph-backed GitHub Discussions posting workflow."""

    def __init__(
        self,
        context: WorkflowContext | None = None,
        repository: str | None = None,
    ) -> None:
        self.context = context or WorkflowContext()
        self.nodes = {
            "get_repository": GetGitHubRepositoryNode(repository or DEFAULT_GITHUB_REPOSITORY),
            "get_topic": GetGitHubTopicNode(),
            "write_discussion": WriteGitHubDiscussionNode(),
            "submit_discussion": SubmitGitHubDiscussionNode(),
            "verify_success": VerifyGitHubDiscussionSuccessNode(),
            "update_document": UpdateGitHubPostingDocumentNode(),
        }
        self.graph = self._build_graph()

    def run(self, initial_state: GitHubPostingState | None = None) -> GitHubPostingState:
        """Run the LangGraph and return final GitHub posting state."""
        result = self.graph.invoke({"state": initial_state or GitHubPostingState()})
        return result["state"]

    def _build_graph(self) -> Any:
        try:
            from langgraph.graph import END, StateGraph
        except Exception as exc:
            raise PostingWorkflowError(
                f"LangGraph is required for GitHubPostingWorkflow: {exc}",
                node="github_langgraph_build",
                code="langgraph_unavailable",
            ) from exc

        graph = StateGraph(GitHubGraphState)
        for name, node in self.nodes.items():
            graph.add_node(name, self._wrap_node(node))

        graph.set_entry_point("get_repository")
        self._guarded_edge(graph, "get_repository", "get_topic", END)
        self._guarded_edge(graph, "get_topic", "write_discussion", END)
        self._guarded_edge(graph, "write_discussion", "submit_discussion", END)
        self._guarded_edge(graph, "submit_discussion", "verify_success", END)
        graph.add_edge("verify_success", "update_document")
        graph.add_edge("update_document", END)
        return graph.compile()

    def _wrap_node(self, node: Any) -> Callable[[GitHubGraphState], Dict[str, GitHubPostingState]]:
        def _runner(graph_state: GitHubGraphState) -> Dict[str, GitHubPostingState]:
            state = graph_state["state"]
            if state.error and node.name != "github_update_document":
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

    def _route_after_node(self, graph_state: GitHubGraphState) -> str:
        return "end" if graph_state["state"].error else "next"

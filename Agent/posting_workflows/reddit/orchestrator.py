"""
LangGraph orchestrator for Reddit posting.

Purpose:
    Wire Reddit posting nodes into a loop-capable LangGraph StateGraph.

Main responsibilities:
    - Define the requested node order and retry loop.
    - Stop on fail-closed structured errors.
    - Route every success claim through an active verification node.
    - Route failed submissions through revision until success or max retries.

Not responsible for:
    - Implementing browser/OCR/LLM node details.
    - Installing LangGraph dependencies.
    - Claiming success without Reddit verification evidence.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, TypedDict

from Agent.posting_workflows.browser_node import OpenBrowserNode
from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.reddit.analyze_flair_popup import AnalyzeFlairPopupNode
from Agent.posting_workflows.reddit.analyze_submission_popup import AnalyzeSubmissionPopupNode
from Agent.posting_workflows.reddit.choose_community_open_page import ChooseCommunityOpenPageNode
from Agent.posting_workflows.reddit.close_flair_popup import CloseFlairPopupNode
from Agent.posting_workflows.reddit.get_communities import GetRedditCommunitiesNode
from Agent.posting_workflows.reddit.get_rules import GetCommunityRulesNode
from Agent.posting_workflows.reddit.open_flair import OpenFlairDialogNode
from Agent.posting_workflows.reddit.revise_after_failure import ReviseAfterFailureNode
from Agent.posting_workflows.reddit.select_flair import SelectFlairNode
from Agent.posting_workflows.reddit.submit_post import SubmitRedditPostNode
from Agent.posting_workflows.reddit.update_document import UpdateRedditPostingDocumentNode
from Agent.posting_workflows.reddit.verify_success import VerifyRedditPostSuccessNode
from Agent.posting_workflows.reddit.write_content import WriteRedditContentNode
from Agent.posting_workflows.state import RedditPostingState, WorkflowContext


class RedditGraphState(TypedDict):
    state: RedditPostingState


class RedditPostingWorkflow:
    """LangGraph-backed Reddit posting workflow with retry loop."""

    def __init__(
        self,
        context: WorkflowContext | None = None,
        community_candidates: List[str] | None = None,
    ) -> None:
        self.context = context or WorkflowContext()
        self.nodes = {
            "open_browser": OpenBrowserNode(),
            "get_communities": GetRedditCommunitiesNode(community_candidates),
            "choose_community_open_page": ChooseCommunityOpenPageNode(),
            "get_rules": GetCommunityRulesNode(),
            "write_content": WriteRedditContentNode(),
            "open_flair": OpenFlairDialogNode(),
            "analyze_flair_popup": AnalyzeFlairPopupNode(),
            "select_flair": SelectFlairNode(),
            "close_flair_popup": CloseFlairPopupNode(),
            "submit_post": SubmitRedditPostNode(),
            "analyze_submission_popup": AnalyzeSubmissionPopupNode(),
            "verify_success": VerifyRedditPostSuccessNode(),
            "revise_after_failure": ReviseAfterFailureNode(),
            "update_document": UpdateRedditPostingDocumentNode(),
        }
        self.graph = self._build_graph()

    def run(self, initial_state: RedditPostingState | None = None) -> RedditPostingState:
        """Run the LangGraph and return final Reddit posting state."""
        result = self.graph.invoke({"state": initial_state or RedditPostingState()})
        return result["state"]

    def _build_graph(self) -> Any:
        try:
            from langgraph.graph import END, StateGraph
        except Exception as exc:
            raise PostingWorkflowError(
                f"LangGraph is required for RedditPostingWorkflow: {exc}",
                node="reddit_langgraph_build",
                code="langgraph_unavailable",
            ) from exc

        graph = StateGraph(RedditGraphState)
        for name, node in self.nodes.items():
            graph.add_node(name, self._wrap_node(node))

        graph.set_entry_point("open_browser")
        self._guarded_edge(graph, "open_browser", "get_communities", END)
        self._guarded_edge(graph, "get_communities", "choose_community_open_page", END)
        self._guarded_edge(graph, "choose_community_open_page", "get_rules", END)
        self._guarded_edge(graph, "get_rules", "write_content", END)
        self._guarded_edge(graph, "write_content", "open_flair", END)
        self._guarded_edge(graph, "open_flair", "analyze_flair_popup", END)
        self._guarded_edge(graph, "analyze_flair_popup", "select_flair", END)
        self._guarded_edge(graph, "select_flair", "close_flair_popup", END)
        self._guarded_edge(graph, "close_flair_popup", "submit_post", END)
        self._guarded_edge(graph, "submit_post", "analyze_submission_popup", END)
        self._guarded_edge(graph, "analyze_submission_popup", "verify_success", END)

        graph.add_conditional_edges(
            "verify_success",
            self._route_after_submission_analysis,
            {
                "success": "update_document",
                "retry": "revise_after_failure",
                "failed": "update_document",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "revise_after_failure",
            self._route_after_revision,
            {
                "retry_same": "open_flair",
                "retry_new": "choose_community_open_page",
                "failed": "update_document",
                "end": END,
            },
        )
        graph.add_edge("update_document", END)
        return graph.compile()

    def _wrap_node(self, node: Any) -> Callable[[RedditGraphState], Dict[str, RedditPostingState]]:
        def _runner(graph_state: RedditGraphState) -> Dict[str, RedditPostingState]:
            state = graph_state["state"]
            if state.error:
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

    def _route_after_node(self, graph_state: RedditGraphState) -> str:
        return "end" if graph_state["state"].error else "next"

    def _route_after_submission_analysis(self, graph_state: RedditGraphState) -> str:
        state = graph_state["state"]
        if state.error:
            return "end"
        if state.status == "success":
            return "success"
        if state.status == "needs_retry" and state.attempts < self.context.max_retries:
            return "retry"
        return "failed"

    def _route_after_revision(self, graph_state: RedditGraphState) -> str:
        state = graph_state["state"]
        if state.error:
            return "end"
        if state.status == "failed":
            return "failed"
        if state.status == "retrying_new_community":
            state.subreddit = None
            state.rules = None
            state.selected_flair = None
            state.flair_options = []
            return "retry_new"
        return "retry_same"

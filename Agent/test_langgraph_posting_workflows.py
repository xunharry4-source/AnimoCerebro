#!/usr/bin/env python3
"""
LangGraph posting workflow tests.

Purpose:
    Verify the node-based posting workflow pieces without touching real X,
    Reddit, browser sessions, or live model providers.

Main responsibilities:
    - Cover normal document update only after explicit verification evidence.
    - Cover fail-closed LLM invocation behavior.
    - Cover active browser permalink verification nodes.
    - Cover retry-loop edge routing.

Not responsible for:
    - Proving real LangGraph runtime execution when dependency is absent.
    - Proving real social platform posting.
    - Using production credentials or live browser profiles.
"""

from pathlib import Path

import pytest

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.llm_client import WorkflowLLMClient
from Agent.posting_workflows.reddit.orchestrator import RedditPostingWorkflow
from Agent.posting_workflows.reddit.revise_after_failure import ReviseAfterFailureNode
from Agent.posting_workflows.reddit.update_document import UpdateRedditPostingDocumentNode
from Agent.posting_workflows.reddit.verify_success import VerifyRedditPostSuccessNode
from Agent.posting_workflows.state import RedditPostingState, WorkflowContext, XPostingState
from Agent.posting_workflows.x.update_document import UpdateXPostingDocumentNode
from Agent.posting_workflows.x.verify_success import VerifyXPostSuccessNode


class RaisingLLMService:
    def generate_json(self, **kwargs):
        raise RuntimeError("provider unavailable")


class FakeResponse:
    def __init__(self, status: int = 200):
        self.status = status


class FakeBodyLocator:
    def __init__(self, text: str):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text


class FakeVerificationPage:
    def __init__(self, *, url: str, title: str, body_text: str, status: int = 200):
        self.url = url
        self._title = title
        self._body_text = body_text
        self._status = status
        self.goto_calls = []

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append({"url": url, "wait_until": wait_until, "timeout": timeout})
        self.url = url
        return FakeResponse(self._status)

    def title(self):
        return self._title

    def locator(self, selector):
        assert selector == "body"
        return FakeBodyLocator(self._body_text)


def test_x_update_document_normal_records_success(tmp_path: Path):
    post_url = "https://x.com/example/status/123"
    context = WorkflowContext(
        ledger_path=tmp_path / "ledger.json",
        status_doc_path=tmp_path / "status.md",
    )
    state = XPostingState(
        topic="Daily technical update",
        content="Short X post",
        post_url=post_url,
        status="success",
        attempts=1,
    )
    state.add_evidence("x_write_post", True, "X content submitted", content=state.content)
    state.add_evidence(
        "x_verify_success",
        True,
        "X post actively verified",
        post_url=post_url,
        verification_source="active_browser_permalink_open",
    )

    UpdateXPostingDocumentNode().run(context, state)

    assert context.ledger_path.exists()
    status_doc = context.status_doc_path.read_text(encoding="utf-8")
    assert "X 发帖成功" in status_doc
    assert post_url in status_doc


def test_x_update_document_abnormal_rejects_success_without_verification_evidence(tmp_path: Path):
    context = WorkflowContext(
        ledger_path=tmp_path / "ledger.json",
        status_doc_path=tmp_path / "status.md",
    )
    state = XPostingState(
        topic="Daily technical update",
        content="Short X post",
        post_url="https://x.com/example/status/123",
        status="success",
        attempts=1,
    )

    with pytest.raises(PostingWorkflowError) as exc_info:
        UpdateXPostingDocumentNode().run(context, state)

    assert exc_info.value.code == "success_evidence_missing"
    assert not context.status_doc_path.exists()


def test_x_verify_success_normal_actively_opens_permalink():
    post_url = "https://x.com/example/status/123"
    content = "Active verification text for X"
    context = WorkflowContext(
        page=FakeVerificationPage(
            url=post_url,
            title="X post",
            body_text=f"Timeline content {content}",
        )
    )
    state = XPostingState(content=content, attempts=1)
    state.add_evidence("x_write_post", True, "X content submitted", content=content)

    VerifyXPostSuccessNode().run(context, state)

    assert state.status == "success"
    assert state.post_url == post_url
    assert context.page.goto_calls[0]["url"] == post_url
    assert state.evidence[-1].data["active_evidence"]["content_match"] is True


def test_x_verify_success_abnormal_rejects_permalink_without_expected_content():
    post_url = "https://x.com/example/status/123"
    context = WorkflowContext(
        page=FakeVerificationPage(
            url=post_url,
            title="X post",
            body_text="A different post is visible here",
        )
    )
    state = XPostingState(content="Expected X content", attempts=1)

    with pytest.raises(PostingWorkflowError) as exc_info:
        VerifyXPostSuccessNode().run(context, state)

    assert exc_info.value.code == "active_verification_content_missing"


def test_workflow_llm_client_abnormal_provider_failure_is_fail_closed():
    client = WorkflowLLMClient(llm_service=RaisingLLMService())

    with pytest.raises(PostingWorkflowError) as exc_info:
        client.generate_json(
            prompt="Return JSON",
            context={},
            node="test_node",
            trace_id="trace-test",
            phase="test_phase",
        )

    assert exc_info.value.code == "llm_invocation_failed"
    assert exc_info.value.node == "test_node"


def test_reddit_revision_edge_stops_at_max_retries():
    context = WorkflowContext(max_retries=2)
    state = RedditPostingState(
        subreddit="AnimoCerebro",
        title="Title",
        content="Content",
        attempts=2,
        status="needs_retry",
    )

    ReviseAfterFailureNode().run(context, state)

    assert state.status == "failed"
    assert state.evidence[-1].node == "reddit_revise_after_failure"
    assert state.evidence[-1].success is False


def test_reddit_verify_success_normal_actively_opens_permalink():
    post_url = "https://www.reddit.com/r/AnimoCerebro/comments/abc123/test_post/"
    title = "Real Reddit verification title"
    context = WorkflowContext(
        page=FakeVerificationPage(
            url=post_url,
            title="Reddit post",
            body_text=f"r/AnimoCerebro {title} comment area",
        )
    )
    state = RedditPostingState(
        subreddit="AnimoCerebro",
        title=title,
        content="Body",
        post_url=post_url,
        status="success",
        attempts=1,
    )
    state.add_evidence("reddit_submit_post", True, "Reddit submit attempted", result={"post_url": post_url})
    state.add_evidence("reddit_analyze_submission_popup", True, "Popup analyzed", post_url=post_url)

    VerifyRedditPostSuccessNode().run(context, state)

    assert state.evidence[-1].node == "reddit_verify_success"
    assert state.evidence[-1].success is True
    assert state.evidence[-1].data["active_evidence"]["content_match"] is True


def test_reddit_update_document_normal_records_success_after_active_verification(tmp_path: Path):
    post_url = "https://www.reddit.com/r/AnimoCerebro/comments/abc123/test_post/"
    context = WorkflowContext(
        ledger_path=tmp_path / "ledger.json",
        status_doc_path=tmp_path / "status.md",
    )
    state = RedditPostingState(
        subreddit="AnimoCerebro",
        title="Verified Reddit title",
        content="Content",
        post_url=post_url,
        status="success",
        attempts=1,
    )
    state.add_evidence("reddit_submit_post", True, "Reddit submit attempted", result={"post_url": post_url})
    state.add_evidence("reddit_analyze_submission_popup", True, "Popup analyzed", post_url=post_url)
    state.add_evidence(
        "reddit_verify_success",
        True,
        "Reddit active verification succeeded",
        post_url=post_url,
        verification_source="active_browser_permalink_open",
    )

    UpdateRedditPostingDocumentNode().run(context, state)

    status_doc = context.status_doc_path.read_text(encoding="utf-8")
    assert "Reddit 发帖成功" in status_doc
    assert post_url in status_doc


def test_reddit_update_document_abnormal_rejects_success_without_active_verification(tmp_path: Path):
    post_url = "https://www.reddit.com/r/AnimoCerebro/comments/abc123/test_post/"
    context = WorkflowContext(
        ledger_path=tmp_path / "ledger.json",
        status_doc_path=tmp_path / "status.md",
    )
    state = RedditPostingState(
        subreddit="AnimoCerebro",
        title="Title",
        content="Content",
        post_url=post_url,
        status="success",
        attempts=1,
    )
    state.add_evidence("reddit_submit_post", True, "Reddit submit attempted", result={"post_url": post_url})
    state.add_evidence("reddit_analyze_submission_popup", True, "Popup analyzed", post_url=post_url)

    with pytest.raises(PostingWorkflowError) as exc_info:
        UpdateRedditPostingDocumentNode().run(context, state)

    assert exc_info.value.code == "success_evidence_missing"
    assert not context.status_doc_path.exists()


def test_reddit_langgraph_route_edge_respects_retry_limit():
    workflow = object.__new__(RedditPostingWorkflow)
    workflow.context = WorkflowContext(max_retries=3)

    retry_state = RedditPostingState(status="needs_retry", attempts=1)
    exhausted_state = RedditPostingState(status="needs_retry", attempts=3)
    success_state = RedditPostingState(status="success", attempts=1)

    assert workflow._route_after_submission_analysis({"state": retry_state}) == "retry"
    assert workflow._route_after_submission_analysis({"state": exhausted_state}) == "failed"
    assert workflow._route_after_submission_analysis({"state": success_state}) == "success"

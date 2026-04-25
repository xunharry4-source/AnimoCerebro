"""
Posting workflow state models.

Purpose:
    Define explicit state passed between X, Reddit, and GitHub workflow nodes.

Main responsibilities:
    - Carry browser, LLM, rules, evidence, and retry context across nodes.
    - Make workflow completion and failure states inspectable.

Not responsible for:
    - Calling browser automation.
    - Calling LLM providers.
    - Persisting posting history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from Agent.posting_workflows.errors import PostingWorkflowError


def utc_now_iso() -> str:
    """Return a stable UTC timestamp string for node evidence."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class NodeEvidence:
    node: str
    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now_iso)


@dataclass
class WorkflowContext:
    page: Any = None
    browser_manager: Any = None
    llm_client: Any = None
    rules_manager: Any = None
    reddit_recognizer: Any = None
    github_poster: Any = None
    ledger: Any = None
    trace_id: str = field(default_factory=lambda: f"posting-{uuid4().hex[:12]}")
    today: date = field(default_factory=date.today)
    max_retries: int = 3
    ledger_path: Path = Path("Agent/data/social_posting_ledger.json")
    status_doc_path: Path = Path("Agent/docs/SOCIAL_POSTING_STATUS.md")

    def require_page(self, node: str) -> Any:
        if self.page is None:
            raise PostingWorkflowError(
                "Browser page is not initialized",
                node=node,
                code="missing_page",
            )
        return self.page

    def require_llm(self, node: str) -> Any:
        if self.llm_client is None:
            from Agent.posting_workflows.llm_client import WorkflowLLMClient

            self.llm_client = WorkflowLLMClient()
        return self.llm_client

    def require_ledger(self, node: str) -> Any:
        if self.ledger is None:
            from Agent.posting_workflows.ledger import SocialPostingLedger

            self.ledger = SocialPostingLedger(
                ledger_path=self.ledger_path,
                status_doc_path=self.status_doc_path,
            )
        return self.ledger


@dataclass
class XPostingState:
    topic: Optional[str] = None
    topic_details: Dict[str, Any] = field(default_factory=dict)
    content: Optional[str] = None
    post_url: Optional[str] = None
    status: str = "pending"
    attempts: int = 0
    evidence: List[NodeEvidence] = field(default_factory=list)
    error: Optional[Dict[str, Any]] = None

    def add_evidence(self, node: str, success: bool, message: str, **data: Any) -> None:
        self.evidence.append(NodeEvidence(node=node, success=success, message=message, data=data))


@dataclass
class RedditPostingState:
    community_candidates: List[str] = field(default_factory=list)
    attempted_communities: List[str] = field(default_factory=list)
    subreddit: Optional[str] = None
    rules: Optional[Dict[str, Any]] = None
    title: Optional[str] = None
    content: Optional[str] = None
    flair_options: List[Dict[str, Any]] = field(default_factory=list)
    selected_flair: Optional[str] = None
    flair_required: Optional[bool] = None
    post_url: Optional[str] = None
    status: str = "pending"
    attempts: int = 0
    last_popup_analysis: Dict[str, Any] = field(default_factory=dict)
    last_submission_result: Dict[str, Any] = field(default_factory=dict)
    evidence: List[NodeEvidence] = field(default_factory=list)
    error: Optional[Dict[str, Any]] = None

    def add_evidence(self, node: str, success: bool, message: str, **data: Any) -> None:
        self.evidence.append(NodeEvidence(node=node, success=success, message=message, data=data))


@dataclass
class GitHubPostingState:
    repository: Optional[str] = None
    topic: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    category_name: Optional[str] = None
    category_id: Optional[str] = None
    discussion_id: Optional[str] = None
    discussion_number: Optional[int] = None
    post_url: Optional[str] = None
    status: str = "pending"
    attempts: int = 0
    last_submission_result: Dict[str, Any] = field(default_factory=dict)
    evidence: List[NodeEvidence] = field(default_factory=list)
    error: Optional[Dict[str, Any]] = None

    def add_evidence(self, node: str, success: bool, message: str, **data: Any) -> None:
        self.evidence.append(NodeEvidence(node=node, success=success, message=message, data=data))

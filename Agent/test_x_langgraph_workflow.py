#!/usr/bin/env python3
"""
X LangGraph workflow contract tests.

文件用途:
    验证 X LangGraph 节点的证据闸门，不触碰真实 X.com、浏览器会话或生产 LLM。

主要职责:
    - 覆盖 X permalink 主动验证的正常路径。
    - 覆盖缺少验证证据时拒绝写入成功文档的异常路径。
    - 覆盖非 X status URL 不能被当成成功帖子的边界路径。

不负责:
    - 不创建真实 X 帖子。
    - 不检查真实 X 登录态。
    - 不把 fixture 页面或示例 URL 当成真实发帖成功证据。
"""

from pathlib import Path

import pytest

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.state import WorkflowContext, XPostingState
from Agent.posting_workflows.verification_gate import is_platform_post_url
from Agent.posting_workflows.x.update_document import UpdateXPostingDocumentNode
from Agent.posting_workflows.x.verify_success import VerifyXPostSuccessNode


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


def test_x_verify_success_normal_actively_opens_permalink_fixture():
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


def test_x_update_document_abnormal_rejects_success_without_verification_evidence_fixture(tmp_path: Path):
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


def test_x_verify_success_edge_rejects_non_status_url_fixture():
    context = WorkflowContext(
        page=FakeVerificationPage(
            url="https://x.com/home",
            title="X home",
            body_text="home timeline",
        )
    )
    state = XPostingState(content="Expected X content", attempts=1)

    VerifyXPostSuccessNode().run(context, state)

    assert state.status == "failed"
    assert state.error["code"] == "x_post_unverified"
    assert not is_platform_post_url("x", state.post_url)

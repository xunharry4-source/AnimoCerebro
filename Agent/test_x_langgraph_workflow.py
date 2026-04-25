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
from Agent.posting_workflows.x.write_post import WriteXPostNode


class FakeResponse:
    def __init__(self, status: int = 200):
        self.status = status


class FakeBodyLocator:
    def __init__(self, text: str):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text


class FakeHydratingBodyLocator:
    def __init__(self, page):
        self.page = page

    def inner_text(self, timeout=None):
        return self.page.current_body_text()


class FakeClickableLocator:
    def __init__(self):
        self.click_calls = []
        self.fill_calls = []
        self.scrolled = False

    @property
    def first(self):
        return self

    def click(self, **kwargs):
        self.click_calls.append(kwargs)

    def fill(self, text):
        self.fill_calls.append(text)

    def scroll_into_view_if_needed(self, **kwargs):
        self.scrolled = True

    def count(self):
        return 1

    def is_visible(self):
        return True

    def is_enabled(self):
        return True

    def inner_text(self, timeout=None):
        return "Post"

    def bounding_box(self, **kwargs):
        return {"x": 320, "y": 96, "width": 220, "height": 56}


class FakeXLLMClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        if not self.payloads:
            raise AssertionError("FakeXLLMClient payloads exhausted")
        return self.payloads.pop(0)


class FakeWritePage:
    url = "https://x.com/compose/post"

    def __init__(self):
        self.timeouts = []
        self.keyboard = self.FakeKeyboard()
        self.mouse = self.FakeMouse()

    class FakeKeyboard:
        def __init__(self):
            self.presses = []

        def press(self, key):
            self.presses.append(key)

    class FakeMouse:
        def __init__(self):
            self.clicks = []

        def click(self, x, y):
            self.clicks.append({"x": x, "y": y})

    def wait_for_timeout(self, timeout):
        self.timeouts.append(timeout)

    def locator(self, selector):
        raise AssertionError(f"Unexpected raw locator call for selector: {selector}")


class FakeVerificationPage:
    def __init__(self, *, url: str, title: str, body_text: str, status: int = 200, recovered_url: str | None = None):
        self.url = url
        self._title = title
        self._body_text = body_text
        self._status = status
        self._recovered_url = recovered_url
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

    def wait_for_timeout(self, timeout):
        return None

    def evaluate(self, script, expected):
        return self._recovered_url


class FakeHydratingVerificationPage(FakeVerificationPage):
    def __init__(self, *, url: str, title: str, body_texts: list[str], status: int = 200):
        super().__init__(url=url, title=title, body_text=body_texts[0], status=status)
        self._body_texts = body_texts
        self._body_index = 0
        self.wait_calls = []

    def current_body_text(self):
        return self._body_texts[min(self._body_index, len(self._body_texts) - 1)]

    def locator(self, selector):
        assert selector == "body"
        return FakeHydratingBodyLocator(self)

    def wait_for_timeout(self, timeout):
        self.wait_calls.append(timeout)
        self._body_index += 1


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


def test_x_verify_success_normal_recovers_permalink_from_visible_timeline_fixture():
    post_url = "https://x.com/example/status/456"
    content = "Recovered X post text from timeline"
    context = WorkflowContext(
        page=FakeVerificationPage(
            url="https://x.com/home",
            title="X home",
            body_text=f"timeline {content}",
            recovered_url=post_url,
        )
    )
    state = XPostingState(content=content, attempts=1)
    state.add_evidence("x_write_post", True, "X content submitted", content=content)

    VerifyXPostSuccessNode().run(context, state)

    assert state.status == "success"
    assert state.post_url == post_url
    assert state.evidence[-1].data["active_evidence"]["content_match"] is True


def test_x_verify_success_normal_waits_for_permalink_content_hydration_fixture():
    post_url = "https://x.com/example/status/789"
    content = "Hydrated permalink content for active X verification"
    context = WorkflowContext(
        page=FakeHydratingVerificationPage(
            url=post_url,
            title="X",
            body_texts=[
                "To view keyboard shortcuts, press question mark",
                f"AnimoCerebro {content}",
            ],
        )
    )
    state = XPostingState(content=content, attempts=1)
    state.add_evidence("x_write_post", True, "X content submitted", content=content)

    VerifyXPostSuccessNode().run(context, state)

    assert state.status == "success"
    assert state.post_url == post_url
    assert context.page.wait_calls == [1000]


def test_x_write_post_normal_clicks_composer_button_and_requires_transition_fixture(monkeypatch):
    node = WriteXPostNode()
    page = FakeWritePage()
    textbox = FakeClickableLocator()
    button = FakeClickableLocator()

    monkeypatch.setattr(node, "_open_composer", lambda _page: None)
    monkeypatch.setattr(
        node,
        "_first_usable_locator",
        lambda _page, selectors, require_enabled: textbox if selectors == node.TEXTBOX_SELECTORS else button,
    )
    monkeypatch.setattr(
        node,
        "_snapshot_submission_state",
        lambda _page, _content, stage: {"stage": stage, "composer_content_visible": True},
    )
    monkeypatch.setattr(node, "_capture_screenshot", lambda _page, _trace_id, stage: {"path": f"{stage}.png"})
    monkeypatch.setattr(
        node,
        "_wait_for_submission_transition",
        lambda _page, _content: {"confirmed": True, "reason": "sent_toast_visible"},
    )

    result = node._fill_and_submit(page, "real composer text", trace_id="fixture")

    assert textbox.fill_calls == ["real composer text"]
    assert button.scrolled is True
    assert button.click_calls == [{"timeout": 10000}]
    assert result["confirmed"]["reason"] == "sent_toast_visible"


def test_x_write_post_normal_retries_with_new_content_after_duplicate_rejection_fixture(monkeypatch):
    node = WriteXPostNode()
    context = WorkflowContext(page=FakeWritePage(), llm_client=FakeXLLMClient([]), max_retries=2)
    state = XPostingState(topic="Topic")
    generated = iter(["duplicate text", "novel text"])
    submitted = []

    def fake_submit(_page, content, trace_id):
        submitted.append(content)
        if content == "duplicate text":
            raise PostingWorkflowError(
                "duplicate",
                node=node.name,
                code="x_duplicate_content_rejected",
                details={"click_attempts": [{"clicked": True}]},
            )
        return {"confirmed": {"confirmed": True, "reason": "sent_toast_visible"}}

    monkeypatch.setattr(node, "_generate_content", lambda _context, _state, avoid_contents=(): next(generated))
    monkeypatch.setattr(node, "_fill_and_submit", fake_submit)

    node.run(context, state)

    assert state.status == "pending"
    assert state.content == "novel text"
    assert state.attempts == 2
    assert submitted == ["duplicate text", "novel text"]
    assert state.evidence[0].success is False
    assert state.evidence[0].message == "X rejected duplicate content; retrying with new LLM content"
    assert state.evidence[-1].success is True


def test_x_write_post_abnormal_detects_duplicate_platform_message_fixture(monkeypatch):
    node = WriteXPostNode()
    page = FakeWritePage()
    monkeypatch.setattr(node, "_find_visible_status_url", lambda _page, _content: None)
    monkeypatch.setattr(node, "_has_sent_toast", lambda _page: False)
    monkeypatch.setattr(node, "_read_duplicate_platform_message", lambda _page: "Whoops! You already said that.")

    result = node._wait_for_submission_transition(page, "duplicate text")

    assert result == {
        "confirmed": False,
        "reason": "duplicate_content_rejected",
        "platform_message": "Whoops! You already said that.",
    }


def test_x_write_post_abnormal_preserves_duplicate_rejection_from_post_click_fixture(monkeypatch):
    node = WriteXPostNode()
    page = FakeWritePage()
    textbox = FakeClickableLocator()
    button = FakeClickableLocator()

    monkeypatch.setattr(node, "_open_composer", lambda _page: None)
    monkeypatch.setattr(
        node,
        "_first_usable_locator",
        lambda _page, selectors, require_enabled: textbox if selectors == node.TEXTBOX_SELECTORS else button,
    )
    monkeypatch.setattr(
        node,
        "_snapshot_submission_state",
        lambda _page, _content, stage: {"stage": stage, "composer_content_visible": True},
    )
    monkeypatch.setattr(node, "_capture_screenshot", lambda _page, _trace_id, stage: {"path": f"{stage}.png"})
    monkeypatch.setattr(
        node,
        "_wait_for_submission_transition",
        lambda _page, _content: {
            "confirmed": False,
            "reason": "duplicate_content_rejected",
            "platform_message": "Whoops! You already said that.",
        },
    )

    with pytest.raises(PostingWorkflowError) as exc_info:
        node._fill_and_submit(page, "duplicate text", trace_id="fixture")

    assert exc_info.value.code == "x_duplicate_content_rejected"
    assert exc_info.value.details["click_attempts"][0]["clicked"] is True
    assert exc_info.value.details["confirmed"]["reason"] == "duplicate_content_rejected"


def test_x_write_post_edge_skips_recent_ledger_content_fixture(tmp_path: Path):
    recent = "Already posted exact text"
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        '[{"platform":"x","data":{"content":"Already posted exact text"}}]',
        encoding="utf-8",
    )
    llm = FakeXLLMClient(
        [
            {"content": recent},
            {"content": "A different concrete angle for X"},
        ]
    )
    context = WorkflowContext(page=FakeWritePage(), llm_client=llm, ledger_path=ledger_path)
    state = XPostingState(topic="Topic", topic_details={"angle": "Angle"})

    content = WriteXPostNode()._generate_content(context, state)

    assert content == "A different concrete angle for X"
    assert len(llm.calls) == 2
    assert llm.calls[0]["context"]["avoid_recent_contents"] == [recent]


def test_x_write_post_abnormal_fails_when_click_does_not_submit_fixture(monkeypatch):
    node = WriteXPostNode()
    page = FakeWritePage()
    textbox = FakeClickableLocator()
    button = FakeClickableLocator()

    monkeypatch.setattr(node, "_open_composer", lambda _page: None)
    monkeypatch.setattr(
        node,
        "_first_usable_locator",
        lambda _page, selectors, require_enabled: textbox if selectors == node.TEXTBOX_SELECTORS else button,
    )
    monkeypatch.setattr(
        node,
        "_snapshot_submission_state",
        lambda _page, _content, stage: {"stage": stage, "composer_content_visible": True},
    )
    monkeypatch.setattr(node, "_capture_screenshot", lambda _page, _trace_id, stage: {"path": f"{stage}.png"})
    monkeypatch.setattr(
        node,
        "_wait_for_submission_transition",
        lambda _page, _content: {"confirmed": False, "reason": "timeout_waiting_for_submission_transition"},
    )

    with pytest.raises(PostingWorkflowError) as exc_info:
        node._fill_and_submit(page, "text stays in composer", trace_id="fixture")

    assert exc_info.value.code == "x_post_submit_not_confirmed"
    assert exc_info.value.details["click_attempts"][0]["clicked"] is True
    assert exc_info.value.details["confirmed"]["confirmed"] is False


def test_x_write_post_normal_dismisses_hashtag_typeahead_fixture(monkeypatch):
    node = WriteXPostNode()
    page = FakeWritePage()
    textbox = FakeClickableLocator()
    overlay_states = iter([True, True, False, False, False])

    monkeypatch.setattr(node, "_has_typeahead_overlay", lambda _page: next(overlay_states))
    monkeypatch.setattr(node, "_is_composer_content_visible", lambda _page, _content: True)

    result = node._dismiss_typeahead_overlay(page, textbox, "#AI #AGI")

    assert result["detected_before"] is True
    assert result["detected_after"] is False
    assert "adjacent_composer_click" in result["actions"]
    assert page.mouse.clicks == [{"x": 556, "y": 120}]
    assert page.keyboard.presses == []


def test_x_write_post_edge_post_button_selectors_do_not_match_sidebar_post_fixture():
    selectors = WriteXPostNode.POST_BUTTON_SELECTORS

    assert all('button:has-text("Post")' not in selector for selector in selectors)
    assert all('span:has-text("Post")' not in selector for selector in selectors)
    assert all("tweetButton" in selector and ("dialog" in selector or "main" in selector) for selector in selectors)

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
from Agent.posting_workflows.reddit.analyze_flair_popup import AnalyzeFlairPopupNode
from Agent.posting_workflows.reddit.analyze_submission_popup import AnalyzeSubmissionPopupNode
from Agent.posting_workflows.reddit.check_flair_requirement import CheckFlairRequirementNode
from Agent.posting_workflows.reddit.click_exit_dialog import ClickExitDialogNode
from Agent.posting_workflows.reddit.close_exit_dialog import CloseExitDialogNode
from Agent.posting_workflows.reddit.get_rules import GetCommunityRulesNode
from Agent.posting_workflows.reddit.orchestrator import RedditPostingWorkflow
from Agent.posting_workflows.reddit.post_submission_dispatch import PostSubmissionDispatchNode
from Agent.posting_workflows.reddit.revise_after_failure import ReviseAfterFailureNode
from Agent.posting_workflows.reddit.select_flair import SelectFlairNode
from Agent.posting_workflows.reddit.submit_post import SubmitRedditPostNode
from Agent.posting_workflows.reddit.update_document import UpdateRedditPostingDocumentNode
from Agent.posting_workflows.reddit.verify_success import VerifyRedditPostSuccessNode
from Agent.reddit_visual_recognizer import RedditVisualRecognizer
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


class FixedJsonLLMService:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


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


class FakeScreenshotPage:
    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path

    def screenshot(self, path, full_page=True):
        Path(path).write_bytes(b"fixture screenshot")


class FakeKeyboard:
    def __init__(self):
        self.pressed = []

    def press(self, key):
        self.pressed.append(key)

    def type(self, value, delay=0):
        self.pressed.append(f"type:{len(value)}")


class FakeMouse:
    def __init__(self):
        self.clicks = []

    def click(self, x, y):
        self.clicks.append((x, y))


class FakeLocator:
    def __init__(self, visible=False, value=""):
        self.visible = visible
        self.value = value
        self.filled = []
        self.first = self

    def count(self):
        return 1 if self.visible else 0

    def is_visible(self):
        return self.visible

    def fill(self, value):
        self.value = value
        self.filled.append(value)

    def input_value(self, timeout=None):
        return self.value

    def click(self):
        return None


class FakeSubmitFormPage:
    def __init__(self):
        self.keyboard = FakeKeyboard()
        self.mouse = FakeMouse()
        self.locator_calls = []
        self.title = FakeLocator(visible=True)
        self.body = FakeLocator(visible=True)
        self.empty = FakeLocator(visible=False)

    def locator(self, selector):
        self.locator_calls.append(selector)
        if selector == 'textarea[name="title"]#innerTextArea':
            return self.title
        if selector in {
            'textarea[name="text"], div[contenteditable="true"]',
            'textarea[name="text"], [data-testid="post-body-text"], div[contenteditable="true"]',
        }:
            return self.body
        return self.empty

    def evaluate(self, script):
        return None


class FakeExitDialogKeyboard:
    def __init__(self, page):
        self.page = page
        self.pressed = []

    def press(self, key):
        self.pressed.append(key)
        if key == "Escape":
            self.page.dialog_open = False


class FakeExitDialogPage:
    def __init__(self):
        self.dialog_open = True
        self.clicked_target = None
        self.keyboard = FakeExitDialogKeyboard(self)

    def evaluate(self, script, *args):
        if "target_button_missing" in script:
            self.clicked_target = args[0]
            self.dialog_open = False
            return {"clicked": True, "button_text": "Keep editing", "reason": "matched_target"}
        if "buttons.map" in script:
            if not self.dialog_open:
                return None
            return {
                "found": True,
                "text": "Discard post? Your draft has unsaved changes.",
                "buttons": ["Discard", "Keep editing"],
            }
        if "return dialogs.some" in script:
            return self.dialog_open
        if "querySelector(" in script:
            return False
        return None


class FakePostCheckModalPage:
    def __init__(self):
        self.modal_open = True

    def evaluate(self, script, *args):
        if "edit_post_clicked" in script:
            self.modal_open = False
            return {"found": True, "clicked": True, "reason": "edit_post_clicked", "button_text": "Edit Post"}
        if "return modals.some" in script:
            return self.modal_open
        return False


class FakeRecognizer:
    def __init__(self, page=None, *, popup_result=None, flair_requirement=None, page_rules=None):
        self.page = page
        self.popup_result = popup_result or {"status": "none", "source": "none"}
        self.page_rules = page_rules or []
        self.flair_requirement = flair_requirement or {
            "required": False,
            "reason": "no_required_signal",
            "has_flair_control": False,
            "alert_text": "",
        }

    def detect_submission_popup_result(self, wait_time=2, use_ocr=True):
        return self.popup_result

    def detect_flair_requirement(self):
        return self.flair_requirement

    def extract_community_rules_from_submit_page_dom(self):
        return self.page_rules


class FakeFlairDialogRecognizer:
    def __init__(self, tmp_path: Path, *, dom_candidates):
        self.page = FakeScreenshotPage(tmp_path)
        self.screenshot_dir = tmp_path
        self.ocr_helper = None
        self.dom_candidates = dom_candidates
        self.expanded = False

    def _is_flair_dialog_open(self):
        return True

    def expand_all_flair_options(self):
        self.expanded = True
        return True

    def extract_flair_candidates_from_dom(self):
        return self.dom_candidates

    def extract_visible_flair_candidates(self, screenshot_path=None):
        return []


def _reddit_flair_recognizer(tmp_path: Path, candidates):
    recognizer = RedditVisualRecognizer(FakeScreenshotPage(tmp_path), screenshot_dir=str(tmp_path))
    recognizer._is_flair_dialog_open = lambda: True
    recognizer.extract_visible_flair_candidates = lambda screenshot_path=None: candidates
    recognizer._click_flair_candidate = lambda selected: True
    recognizer._click_apply_button = lambda: True
    recognizer._wait_for_flair_dialog_closed = lambda timeout=5: True
    recognizer._verify_flair_applied = lambda selected_text, target_flair=None: True
    return recognizer


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


def test_reddit_flair_nodes_normal_select_exact_visible_project_build_fixture(tmp_path: Path):
    candidates = [
        {"text": "📰 News", "confidence": 100, "center_x": 10, "center_y": 10},
        {"text": "🔬 Research", "confidence": 100, "center_x": 10, "center_y": 20},
        {"text": "🛠️ Project / Build", "confidence": 100, "center_x": 10, "center_y": 30},
    ]
    context = WorkflowContext(
        page=FakeScreenshotPage(tmp_path),
        reddit_recognizer=_reddit_flair_recognizer(tmp_path, candidates),
        llm_client=FixedJsonLLMService({"selected_flair": "Project / Build"}),
    )
    state = RedditPostingState(
        subreddit="ArtificialInteligence",
        title="Design question: should agent memory be a nine-step loop?",
        content="An open-source agent runtime architecture question with GitHub context.",
        flair_required=True,
    )

    AnalyzeFlairPopupNode().run(context, state)
    SelectFlairNode().run(context, state)

    assert state.flair_options == candidates
    assert state.selected_flair == "🛠️ Project / Build"
    assert state.evidence[-1].node == "reddit_select_flair"


def test_reddit_click_exit_dialog_normal_selects_flair_dialog_from_analyze_result_fixture(tmp_path: Path):
    candidates = [
        {"text": "📰 News", "confidence": 100, "center_x": 10, "center_y": 10},
        {"text": "🔬 Research", "confidence": 100, "center_x": 10, "center_y": 20},
        {"text": "🛠️ Project / Build", "confidence": 100, "center_x": 10, "center_y": 30},
    ]
    context = WorkflowContext(
        page=FakeScreenshotPage(tmp_path),
        reddit_recognizer=_reddit_flair_recognizer(tmp_path, candidates),
    )
    state = RedditPostingState(
        subreddit="ArtificialInteligence",
        flair_required=True,
        flair_options=candidates,
        selected_flair="Project / Build",
    )

    ClickExitDialogNode().run(context, state)

    assert state.selected_flair == "🛠️ Project / Build"
    assert state.evidence[-1].node == "reddit_click_exit_dialog"
    assert state.evidence[-1].data["dialog_type"] == "flair_selection_dialog"
    assert state.evidence[-1].data["source_node"] == "reddit_analyze_flair_popup"


def test_reddit_click_exit_dialog_abnormal_required_flair_without_analysis_fails_closed_fixture(tmp_path: Path):
    candidates = [
        {"text": "📰 News", "confidence": 100, "center_x": 10, "center_y": 10},
        {"text": "🔬 Research", "confidence": 100, "center_x": 10, "center_y": 20},
    ]
    context = WorkflowContext(
        page=FakeScreenshotPage(tmp_path),
        reddit_recognizer=_reddit_flair_recognizer(tmp_path, candidates),
    )
    state = RedditPostingState(
        subreddit="ArtificialInteligence",
        flair_required=True,
        flair_options=candidates,
        selected_flair="",
    )

    with pytest.raises(PostingWorkflowError) as exc_info:
        ClickExitDialogNode().run(context, state)

    assert exc_info.value.code == "required_flair_selection_missing_for_click_node"


def test_reddit_analyze_flair_popup_normal_expands_and_filters_no_flair_fixture(tmp_path: Path):
    dom_candidates = [
        {"text": "无标识", "is_none_option": True, "source": "reddit_flair_dialog_radio"},
        {"text": "📰 News", "source": "reddit_flair_dialog_radio"},
        {"text": "🔬 Research", "source": "reddit_flair_dialog_radio"},
        {"text": "🛠️ Project / Build", "source": "reddit_flair_dialog_radio"},
        {"text": "📚 Tutorial / Guide", "source": "reddit_flair_dialog_radio"},
        {"text": "📊 Analysis / Opinion", "source": "reddit_flair_dialog_radio"},
        {"text": "🤖 New Model / Tool", "source": "reddit_flair_dialog_radio"},
        {"text": "😂 Fun / Meme", "source": "reddit_flair_dialog_radio"},
    ]
    recognizer = FakeFlairDialogRecognizer(tmp_path, dom_candidates=dom_candidates)
    llm = FixedJsonLLMService({"selected_flair": "Research"})
    context = WorkflowContext(reddit_recognizer=recognizer, llm_client=llm)
    state = RedditPostingState(
        subreddit="ArtificialInteligence",
        title="New benchmark paper for agent evaluation",
        content="A concise summary of a research benchmark and why it matters.",
        flair_required=True,
    )

    AnalyzeFlairPopupNode().run(context, state)

    assert recognizer.expanded is True
    assert [item["text"] for item in state.flair_options] == [
        "📰 News",
        "🔬 Research",
        "🛠️ Project / Build",
        "📚 Tutorial / Guide",
        "📊 Analysis / Opinion",
        "🤖 New Model / Tool",
        "😂 Fun / Meme",
    ]
    assert "无标识" not in llm.calls[-1]["context"]["flair_options"]
    assert state.selected_flair == "Research"
    assert state.evidence[-1].data["expanded_all_options"] is True


def test_reddit_flair_nodes_abnormal_fail_when_required_candidates_missing_fixture(tmp_path: Path):
    context = WorkflowContext(
        page=FakeScreenshotPage(tmp_path),
        reddit_recognizer=_reddit_flair_recognizer(tmp_path, []),
        llm_client=FixedJsonLLMService({"selected_flair": ""}),
    )
    state = RedditPostingState(
        subreddit="ArtificialInteligence",
        title="Title",
        content="Content",
        flair_required=True,
    )

    with pytest.raises(PostingWorkflowError) as exc_info:
        AnalyzeFlairPopupNode().run(context, state)

    assert exc_info.value.code == "required_flair_candidates_missing"


def test_reddit_get_rules_normal_prefers_current_submit_page_rules_fixture():
    page_rules = [
        {
            "number": "2",
            "title": "High-Signal Content Only",
            "description": "Every post should teach something, share something new, or spark substantive discussion.",
            "source": "reddit_submit_page_dom",
        },
        {
            "number": "7",
            "title": "Use Correct Flair",
            "description": "Choose the most specific flair that fits. When in doubt, use Discussion.",
            "source": "reddit_submit_page_dom",
        },
    ]
    context = WorkflowContext(page=object(), reddit_recognizer=FakeRecognizer(page_rules=page_rules))
    state = RedditPostingState(subreddit="ArtificialInteligence")

    GetCommunityRulesNode().run(context, state)

    assert state.rules["source"] == "reddit_submit_page_dom"
    assert state.rules["rule_count"] == 2
    assert state.rules["rules"][0]["title"] == "High-Signal Content Only"


def test_reddit_submit_fill_edge_prefers_exact_title_textarea_fixture():
    page = FakeSubmitFormPage()

    SubmitRedditPostNode()._fill_form(page, "Expected title", "Expected body")

    assert page.locator_calls[0] == 'textarea[name="title"]#innerTextArea'
    assert page.title.value == "Expected title"
    assert page.body.value == "Expected body"
    assert "input[name=\"q\"]" not in page.locator_calls
    assert "Escape" in page.keyboard.pressed


def test_reddit_check_flair_requirement_normal_rule_text_alone_not_required_fixture():
    recognizer = FakeRecognizer(
        flair_requirement={
            "required": False,
            "reason": "no_required_signal",
            "has_flair_control": False,
            "alert_text": "Use Correct Flair",
        }
    )
    context = WorkflowContext(reddit_recognizer=recognizer)
    state = RedditPostingState(subreddit="ArtificialInteligence")

    CheckFlairRequirementNode().run(context, state)

    assert state.flair_required is False
    assert state.evidence[-1].data["requirement"]["alert_text"] == "Use Correct Flair"


def test_reddit_check_flair_requirement_normal_hidden_required_modal_is_required_fixture():
    recognizer = FakeRecognizer(
        flair_requirement={
            "required": True,
            "reason": "flair_required_signal_detected",
            "has_flair_control": True,
            "markup_required": True,
            "markup_options": ["📰 News", "🛠️ Project / Build"],
        }
    )
    context = WorkflowContext(reddit_recognizer=recognizer)
    state = RedditPostingState(subreddit="ArtificialInteligence")

    CheckFlairRequirementNode().run(context, state)

    assert state.flair_required is True
    assert state.evidence[-1].data["requirement"]["markup_required"] is True


def test_reddit_analyze_flair_popup_abnormal_required_without_ocr_or_dom_fails_closed_fixture(tmp_path: Path):
    recognizer = _reddit_flair_recognizer(tmp_path, [])
    delattr(recognizer, "extract_visible_flair_candidates")
    recognizer.ocr_helper = None
    context = WorkflowContext(
        page=FakeScreenshotPage(tmp_path),
        reddit_recognizer=recognizer,
        llm_client=FixedJsonLLMService({"selected_flair": "Project / Build"}),
    )
    state = RedditPostingState(flair_required=True)

    with pytest.raises(PostingWorkflowError) as exc_info:
        AnalyzeFlairPopupNode().run(context, state)

    assert exc_info.value.code == "required_flair_ocr_unavailable"


def test_reddit_exit_dialog_edge_keep_draft_then_close_fixture():
    page = FakeExitDialogPage()
    context = WorkflowContext(reddit_recognizer=FakeRecognizer(page=page))
    state = RedditPostingState(status="needs_retry")

    ClickExitDialogNode().run(context, state)
    CloseExitDialogNode().run(context, state)

    assert page.clicked_target == "Keep"
    assert page.dialog_open is False
    assert page.keyboard.pressed == ["Escape"]
    assert state.evidence[-2].node == "reddit_click_exit_dialog"
    assert state.evidence[-1].node == "reddit_close_exit_dialog"


def test_reddit_close_exit_dialog_normal_closes_post_check_modal_with_edit_post_fixture():
    page = FakePostCheckModalPage()
    context = WorkflowContext(reddit_recognizer=FakeRecognizer(page=page))
    state = RedditPostingState(status="needs_retry")

    CloseExitDialogNode().run(context, state)

    assert page.modal_open is False
    assert state.evidence[-1].data["modal_type"] == "reddit_post_check_rule_warning"
    assert state.evidence[-1].data["close_result"]["button_text"] == "Edit Post"


def test_reddit_analyze_submission_popup_normal_flair_error_sets_retry_state_fixture():
    popup = {
        "status": "error",
        "message": "Your post must contain post flair.",
        "category": "flair_required",
        "should_retry": True,
        "needs_flair": True,
        "recommended_action": "select_flair",
        "source": "dom",
        "screenshot_path": "fixture.png",
    }
    context = WorkflowContext(reddit_recognizer=FakeRecognizer(popup_result=popup))
    state = RedditPostingState()

    AnalyzeSubmissionPopupNode().run(context, state)

    assert state.last_popup_analysis["status"] == "error"
    assert state.last_popup_analysis["needs_flair"] is True
    assert state.flair_required is True


def test_reddit_analyze_submission_popup_normal_preserves_post_check_modal_fixture():
    popup = {
        "status": "error",
        "message": (
            "Reddit post-check modal: your post may violate rules. "
            "Rule 2: High-Signal Content Only. Rule 7: Use Correct Flair."
        ),
        "category": "community_rule",
        "should_retry": True,
        "needs_flair": True,
        "recommended_action": "edit_post",
        "source": "dom_post_check_modal",
        "screenshot_path": "fixture.png",
        "post_check_modal": {
            "type": "reddit_post_check_rule_warning",
            "rules": [
                {"title": "Rule 2: High-Signal Content Only", "description": "Every post should teach something."},
                {"title": "Rule 7: Use Correct Flair", "description": "Choose the most specific flair."},
            ],
            "buttons": ["Submit without editing", "Edit Post"],
        },
    }
    context = WorkflowContext(reddit_recognizer=FakeRecognizer(popup_result=popup))
    state = RedditPostingState()

    AnalyzeSubmissionPopupNode().run(context, state)

    assert state.last_popup_analysis["category"] == "community_rule"
    assert state.last_popup_analysis["recommended_action"] == "edit_post"
    assert state.last_popup_analysis["post_check_modal"]["buttons"] == ["Submit without editing", "Edit Post"]


def test_reddit_post_submission_dispatch_normal_verified_url_routes_success_fixture():
    state = RedditPostingState(
        last_popup_analysis={"status": "none", "should_retry": False},
        last_submission_result={
            "success": True,
            "post_url": "https://www.reddit.com/r/AnimoCerebro/comments/abc123/title/",
        },
    )

    PostSubmissionDispatchNode().run(WorkflowContext(), state)

    assert state.status == "success"
    assert state.post_url == "https://www.reddit.com/r/AnimoCerebro/comments/abc123/title/"


def test_reddit_post_submission_dispatch_abnormal_popup_success_without_url_fails_fixture():
    state = RedditPostingState(last_popup_analysis={"status": "success"}, last_submission_result={})

    with pytest.raises(PostingWorkflowError) as exc_info:
        PostSubmissionDispatchNode().run(WorkflowContext(), state)

    assert exc_info.value.code == "popup_success_without_post_url"


def test_reddit_post_submission_dispatch_edge_flair_error_routes_retry_fixture():
    state = RedditPostingState(
        last_popup_analysis={
            "status": "error",
            "message": "Post flair is required",
            "needs_flair": True,
            "should_retry": False,
        },
        last_submission_result={"success": False},
    )

    PostSubmissionDispatchNode().run(WorkflowContext(), state)

    assert state.status == "needs_retry"
    assert state.evidence[-1].data["should_retry"] is True


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

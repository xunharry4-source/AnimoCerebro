#!/usr/bin/env python3
"""
RedditSmartPoster contract tests.

文件用途:
    验证 RedditSmartPoster 入口层的同步调用契约和 Flair 必选判断策略。

主要职责:
    - 覆盖 Flair 必选、非必选、检测失败三类路径
    - 防止同步调用 post_custom_content 时返回 coroutine 被误判为成功
    - 明确这些测试是非真实运行结果，不作为 Reddit 发帖成功证据

不负责:
    - 不创建真实 Reddit 帖子
    - 不替代真实浏览器 E2E 和 permalink 主动验证
    - 不伪造 real_posting_success_evidence.json
"""

import inspect

from Agent.social_promotion.reddit_smart_poster import RedditSmartPoster
from Agent.reddit_visual_recognizer import RedditVisualRecognizer


class _SyncPage:
    def goto(self, *args, **kwargs):
        return None


class _RecordingEvaluatePage(_SyncPage):
    def __init__(self, result):
        self.result = result
        self.script = ""

    def evaluate(self, script, *args):
        self.script = script
        return self.result


def test_should_select_flair_when_required_normal_fixture():
    poster = RedditSmartPoster(_SyncPage())

    assert poster._should_select_flair({"required": True, "reason": "explicit_required_text"}) is True


def test_should_skip_flair_when_not_required_abnormal_fixture():
    poster = RedditSmartPoster(_SyncPage())

    assert poster._should_select_flair({"required": False, "reason": "no_required_signal"}) is False


def test_should_skip_flair_when_detection_failed_edge_fixture():
    poster = RedditSmartPoster(_SyncPage())

    assert poster._should_select_flair({"reason": "detection_failed_default_skip"}) is False


def test_detect_flair_requirement_supports_chinese_identifier_marker_normal_fixture():
    page = _RecordingEvaluatePage(
        {
            "required": True,
            "reason": "flair_control_required_marker",
            "submit_disabled": True,
            "has_flair_control": True,
        }
    )
    poster = RedditSmartPoster(page)

    result = poster._detect_flair_requirement_sync()

    assert result["required"] is True
    assert result["reason"] == "flair_control_required_marker"
    assert "添加标识" in page.script
    assert "标识和标记" in page.script


def test_choose_flair_candidate_matches_emoji_prefixed_project_build_normal_fixture():
    recognizer = RedditVisualRecognizer(_SyncPage())
    candidates = [
        {"text": "📰 News", "confidence": 90},
        {"text": "🔬 Research", "confidence": 90},
        {"text": "🛠️ Project / Build", "confidence": 90},
    ]

    selected = recognizer._choose_flair_candidate(
        candidates=candidates,
        target_flair="Project / Build",
        preferred_keywords=["Project / Build"],
    )

    assert selected is not None
    assert selected["text"] == "🛠️ Project / Build"


def test_sync_post_custom_content_returns_bool_not_coroutine_fixture(monkeypatch):
    poster = RedditSmartPoster(_SyncPage())

    monkeypatch.setattr(
        poster,
        "post_custom_content_with_evidence",
        lambda **kwargs: {"success": False, "error_message": "fixture failure"},
    )

    result = poster.post_custom_content(
        subreddit="AnimoCerebro",
        title="fixture title",
        content="fixture content",
        flair="Discussion",
        max_retries=1,
    )

    assert result is False
    assert inspect.iscoroutine(result) is False

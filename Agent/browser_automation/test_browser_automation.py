"""
Browser Automation Tests - 浏览器自动化测试

测试覆盖:
1. 正常场景 (Normal) - 基本功能正常工作
2. 异常场景 (Abnormal) - 错误处理和边界情况
3. 特殊边界 (Edge) - 极限值和特殊情况

注意: 这些测试大部分是模拟测试，因为真实的浏览器自动化需要:
- Playwright安装
- 有效的账号凭据
- 人工交互处理CAPTCHA
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Agent.promotion_agent import PromotionAgent


def test_enable_browser_automation():
    """测试启用浏览器自动化 - 正常场景（模拟）"""
    print("\n=== Test: Enable Browser Automation (Normal - Mocked) ===")

    agent = PromotionAgent()

    # 模拟BrowserAutomationManager
    with patch('Agent.browser_automation.BrowserAutomationManager') as mock_manager_class:
        mock_manager = Mock()
        mock_manager_class.return_value = mock_manager

        # 启用浏览器自动化
        result = agent.enable_browser_automation(headless=False, slow_mo=500)

        assert result["success"] is True
        assert agent.use_browser_automation is True
        assert agent.browser_manager is not None

        print(f"[已验证] ✅ Browser automation enabled")
        print(f"   Headless: False")
        print(f"   Slow mo: 500ms")


def test_disable_browser_automation():
    """测试禁用浏览器自动化 - 正常场景"""
    print("\n=== Test: Disable Browser Automation (Normal) ===")

    agent = PromotionAgent()

    # 先设置为启用状态（模拟）
    agent.use_browser_automation = True
    agent.browser_manager = Mock()

    # 禁用
    result = agent.disable_browser_automation()

    assert result["success"] is True
    assert agent.use_browser_automation is False

    print(f"[已验证] ✅ Browser automation disabled")


def test_disable_when_not_enabled():
    """测试禁用未启用的浏览器自动化 - 边界场景"""
    print("\n=== Test: Disable When Not Enabled (Edge) ===")

    agent = PromotionAgent()
    agent.browser_manager = None
    agent.use_browser_automation = False

    result = agent.disable_browser_automation()

    assert result["success"] is True
    assert "not enabled" in result["message"].lower()

    print(f"[已验证] ✅ Handles disable when not enabled")
    print(f"   Message: {result['message']}")


def test_login_without_browser():
    """测试未启用浏览器时登录 - 异常场景"""
    print("\n=== Test: Login Without Browser (Abnormal) ===")

    agent = PromotionAgent()
    agent.use_browser_automation = False
    agent.browser_manager = None

    result = agent.login_to_platform("x", "username", "password")

    assert result["success"] is False
    assert "not enabled" in result["error"].lower()

    print(f"[已验证] ✅ Correctly rejects login without browser")
    print(f"   Error: {result['error']}")


def test_publish_with_browser_mocked():
    """测试使用浏览器发布帖子 - 正常场景（模拟）"""
    print("\n=== Test: Publish Post With Browser (Normal - Mocked) ===")

    agent = PromotionAgent()

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Browser Publish Test",
        description="Test browser publishing",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content="Test post via browser"
    )
    post_id = schedule_result["post_id"]

    # 模拟浏览器管理器
    mock_browser = Mock()
    mock_browser.post_to_x.return_value = {
        "success": True,
        "url": "https://twitter.com/test/status/123456"
    }

    agent.browser_manager = mock_browser
    agent.use_browser_automation = True

    # 发布帖子
    result = agent.publish_post_with_browser(post_id)

    assert result["success"] is True
    assert agent.posts[post_id]["status"] == "published"
    assert agent.posts[post_id]["publish_method"] == "browser_automation"

    print(f"[已验证] ✅ Post published via browser (mocked)")
    print(f"   Post ID: {post_id}")
    print(f"   Status: {agent.posts[post_id]['status']}")
    print(f"   Method: {agent.posts[post_id]['publish_method']}")


def test_publish_reddit_with_browser_mocked():
    """测试使用浏览器发布Reddit帖子 - 正常场景（模拟）"""
    print("\n=== Test: Publish Reddit Post With Browser (Normal - Mocked) ===")

    agent = PromotionAgent()

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Reddit Browser Publish Test",
        description="Test Reddit browser publishing",
        platforms=["reddit"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="reddit",
        content="Test Reddit content",
        subreddit="technology",
        title="Test Reddit Title"
    )
    post_id = schedule_result["post_id"]

    # 模拟浏览器管理器
    mock_browser = Mock()
    mock_browser.post_to_reddit.return_value = {
        "success": True,
        "url": "https://reddit.com/r/technology/comments/test123"
    }

    agent.browser_manager = mock_browser
    agent.use_browser_automation = True

    # 发布帖子
    result = agent.publish_post_with_browser(post_id)

    assert result["success"] is True
    assert agent.posts[post_id]["status"] == "published"

    print(f"[已验证] ✅ Reddit post published via browser (mocked)")
    print(f"   Post ID: {post_id}")
    print(f"   Subreddit: {agent.posts[post_id]['subreddit']}")


def test_publish_failure_handling():
    """测试发布失败处理 - 异常场景"""
    print("\n=== Test: Publish Failure Handling (Abnormal) ===")

    agent = PromotionAgent()

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Failure Test",
        description="Test failure handling",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content="Test post"
    )
    post_id = schedule_result["post_id"]

    # 模拟浏览器管理器返回失败
    mock_browser = Mock()
    mock_browser.post_to_x.return_value = {
        "success": False,
        "error": "Failed to post: Rate limit exceeded"
    }

    agent.browser_manager = mock_browser
    agent.use_browser_automation = True

    # 尝试发布
    result = agent.publish_post_with_browser(post_id)

    assert result["success"] is False
    assert agent.posts[post_id]["status"] == "failed"
    assert "error" in agent.posts[post_id]

    print(f"[已验证] ✅ Failure handled correctly")
    print(f"   Post status: {agent.posts[post_id]['status']}")
    print(f"   Error: {agent.posts[post_id]['error']}")


def test_save_session_mocked():
    """测试保存会话 - 正常场景（模拟）"""
    print("\n=== Test: Save Session (Normal - Mocked) ===")

    agent = PromotionAgent()

    # 模拟浏览器管理器
    mock_browser = Mock()
    mock_browser.save_session.return_value = "browser_sessions/test_session.json"

    agent.browser_manager = mock_browser
    agent.use_browser_automation = True

    result = agent.save_browser_session("test_session")

    assert result["success"] is True
    assert "session_file" in result

    print(f"[已验证] ✅ Session saved (mocked)")
    print(f"   Session file: {result['session_file']}")


def test_load_session_mocked():
    """测试加载会话 - 正常场景（模拟）"""
    print("\n=== Test: Load Session (Normal - Mocked) ===")

    agent = PromotionAgent()

    # 模拟浏览器管理器
    mock_browser = Mock()
    mock_browser.load_session.return_value = True

    agent.browser_manager = mock_browser
    agent.use_browser_automation = True

    result = agent.load_browser_session("test_session")

    assert result["success"] is True
    assert "loaded" in result["message"].lower()

    print(f"[已验证] ✅ Session loaded (mocked)")
    print(f"   Message: {result['message']}")


def test_take_screenshot_mocked():
    """测试截图 - 正常场景（模拟）"""
    print("\n=== Test: Take Screenshot (Normal - Mocked) ===")

    agent = PromotionAgent()

    # 模拟浏览器管理器
    mock_browser = Mock()
    mock_browser.take_screenshot.return_value = "screenshot_test.png"

    agent.browser_manager = mock_browser
    agent.use_browser_automation = True

    result = agent.take_browser_screenshot("screenshot_test.png")

    assert result["success"] is True
    assert "screenshot_path" in result

    print(f"[已验证] ✅ Screenshot taken (mocked)")
    print(f"   Path: {result['screenshot_path']}")


def test_unsupported_platform():
    """测试不支持的平台 - 异常场景"""
    print("\n=== Test: Unsupported Platform (Abnormal) ===")

    agent = PromotionAgent()

    # 模拟浏览器管理器
    mock_browser = Mock()
    agent.browser_manager = mock_browser
    agent.use_browser_automation = True

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Unsupported Platform Test",
        description="Test unsupported platform",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="facebook",  # 不支持的平台
        content="Test content"
    )
    post_id = schedule_result["post_id"]

    # 尝试发布
    result = agent.publish_post_with_browser(post_id)

    assert result["success"] is False
    assert "unsupported" in result["error"].lower()

    print(f"[已验证] ✅ Unsupported platform rejected")
    print(f"   Error: {result['error']}")


def test_bot_detection_handler():
    """测试机器人检测处理器 - 正常场景"""
    print("\n=== Test: Bot Detection Handler (Normal) ===")

    try:
        from Agent.browser_automation import BotDetectionHandler

        # 模拟Page对象
        mock_page = Mock()
        mock_page.content.return_value = "<html><body>normal page</body></html>"
        mock_page.frames = []

        handler = BotDetectionHandler(mock_page)

        # 检查无CAPTCHA的情况
        has_captcha = handler.check_for_captcha()
        assert has_captcha is False

        print(f"[已验证] ✅ Bot detection works (no CAPTCHA)")

        # 模拟有CAPTCHA的情况
        mock_page.content.return_value = """
        <html>
        <body>
            <div class="g-recaptcha"></div>
        </body>
        </html>
        """

        has_captcha = handler.check_for_captcha()
        assert has_captcha is True
        assert handler.detected is True

        print(f"[已验证] ✅ CAPTCHA detected correctly")

    except ImportError:
        print("[未验证] ⚠️ Playwright not available, skipping bot detection test")


def test_audit_logging_for_browser_actions():
    """测试浏览器操作的审计日志 - 正常场景"""
    print("\n=== Test: Audit Logging for Browser Actions (Normal) ===")

    agent = PromotionAgent()

    # 模拟浏览器管理器
    mock_browser = Mock()
    mock_browser.post_to_x.return_value = {"success": True, "url": "https://test.com"}

    agent.browser_manager = mock_browser
    agent.use_browser_automation = True

    # 创建计划和帖子
    plan_result = agent.create_promotion_plan(
        title="Audit Log Test",
        description="Test audit logging",
        platforms=["x"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=datetime.now(timezone.utc).isoformat()
    )
    plan_id = plan_result["plan"]["plan_id"]

    schedule_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content="Test content"
    )
    post_id = schedule_result["post_id"]

    # 发布帖子（会记录审计日志）
    agent.publish_post_with_browser(post_id)

    # 检查审计日志
    audit_result = agent.get_audit_log(action_filter="publish_via_browser")

    assert audit_result["success"] is True
    assert audit_result["total_entries"] >= 1

    print(f"[已验证] ✅ Audit log recorded for browser action")
    print(f"   Entries: {audit_result['total_entries']}")
    if audit_result["total_entries"] > 0:
        entry = audit_result["audit_log"][0]
        print(f"   Action: {entry['action']}")
        print(f"   Trace ID: {entry['trace_id']}")


def run_all_tests():
    """运行所有测试"""
    print("=" * 70)
    print("Browser Automation Test Suite")
    print("=" * 70)

    tests = [
        ("Enable Browser Automation", test_enable_browser_automation),
        ("Disable Browser Automation", test_disable_browser_automation),
        ("Disable When Not Enabled", test_disable_when_not_enabled),
        ("Login Without Browser", test_login_without_browser),
        ("Publish With Browser", test_publish_with_browser_mocked),
        ("Publish Reddit With Browser", test_publish_reddit_with_browser_mocked),
        ("Publish Failure Handling", test_publish_failure_handling),
        ("Save Session", test_save_session_mocked),
        ("Load Session", test_load_session_mocked),
        ("Take Screenshot", test_take_screenshot_mocked),
        ("Unsupported Platform", test_unsupported_platform),
        ("Bot Detection Handler", test_bot_detection_handler),
        ("Audit Logging", test_audit_logging_for_browser_actions),
    ]

    passed = 0
    failed = 0
    errors = []

    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test_name, str(e)))
            print(f"\n❌ FAILED: {test_name}")
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Total tests: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if errors:
        print("\nFailed Tests:")
        for test_name, error in errors:
            print(f"  - {test_name}: {error}")

    print("\n" + "=" * 70)
    if failed == 0:
        print("✅ All tests passed!")
    else:
        print(f"⚠️ {failed} test(s) failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

"""
Browser Automation Example - 浏览器自动化使用示例

展示如何使用基于Playwright的浏览器自动化功能进行社交媒体发帖，
包括处理机器人验证和人工协助。

使用前请确保:
1. 安装Playwright: pip install playwright
2. 安装浏览器: playwright install
3. 设置环境变量或配置文件中的账号密码
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Agent.promotion_agent import PromotionAgent


def example_browser_automation_workflow():
    """浏览器自动化完整工作流示例"""
    print("=" * 70)
    print("Browser Automation Workflow Example")
    print("=" * 70)

    # 创建Agent实例
    agent = PromotionAgent()

    # 步骤1: 启用浏览器自动化（显示浏览器窗口，便于人工协助）
    print("\n📌 Step 1: Enabling browser automation...")
    enable_result = agent.enable_browser_automation(headless=False, slow_mo=500)

    if not enable_result["success"]:
        print(f"❌ Failed to enable browser automation: {enable_result['error']}")
        print("\nPlease install Playwright:")
        print("  pip install playwright")
        print("  playwright install")
        return

    print(f"✅ {enable_result['message']}")

    # 步骤2: 登录到X平台
    print("\n📌 Step 2: Logging in to X (Twitter)...")
    x_username = os.getenv("X_USERNAME", "your_x_username")
    x_password = os.getenv("X_PASSWORD", "your_x_password")

    # 注意：实际使用时应该从安全的地方获取凭据
    # 这里仅作演示
    if x_username != "your_x_username":
        login_result = agent.login_to_platform("x", x_username, x_password)
        if login_result["success"]:
            print(f"✅ {login_result['message']}")
        else:
            print(f"⚠️ Login failed: {login_result['error']}")
            print("   You can manually login in the opened browser window")
    else:
        print("⚠️ Using default credentials. Please set X_USERNAME and X_PASSWORD environment variables.")
        print("   The browser window is open. You can manually login.")
        input("Press Enter after you've logged in manually...")

    # 步骤3: 创建宣传计划
    print("\n📌 Step 3: Creating promotion plan...")
    plan_result = agent.create_promotion_plan(
        title="Browser Automation Campaign",
        description="Campaign using browser automation for posting",
        platforms=["x", "reddit"],
        start_date=datetime.now(timezone.utc).isoformat(),
        end_date=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        target_audience="Tech community",
        goals=["Increase visibility", "Generate engagement"]
    )
    plan_id = plan_result["plan"]["plan_id"]
    print(f"✅ Plan created: {plan_id}")

    # 步骤4: 调度帖子
    print("\n📌 Step 4: Scheduling posts...")

    # X平台帖子
    x_post_result = agent.schedule_post(
        plan_id=plan_id,
        platform="x",
        content="Excited to share our latest AI innovation! 🚀 #AI #Tech #Innovation"
    )
    x_post_id = x_post_result["post_id"]
    print(f"✅ X post scheduled: {x_post_id}")

    # Reddit帖子
    reddit_post_result = agent.schedule_post(
        plan_id=plan_id,
        platform="reddit",
        content="""
## New AI Tool Launch

We've been working on an exciting new AI-powered tool that helps developers write better code faster.

### Key Features
- Intelligent code completion
- Real-time bug detection
- Performance optimization suggestions

Would love to get feedback from the community!
""",
        subreddit="technology",
        title="New AI-Powered Development Tool"
    )
    reddit_post_id = reddit_post_result["post_id"]
    print(f"✅ Reddit post scheduled: {reddit_post_id}")

    # 步骤5: 提交审核（可选）
    print("\n📌 Step 5: Submitting posts for review...")
    agent.submit_for_review(post_id=x_post_id, reviewer_id="manager_001")
    agent.submit_for_review(post_id=reddit_post_id, reviewer_id="manager_001")

    # 批准帖子
    agent.review_post(
        post_id=x_post_id,
        reviewer_id="manager_001",
        decision="approved",
        notes="Approved for posting"
    )
    agent.review_post(
        post_id=reddit_post_id,
        reviewer_id="manager_001",
        decision="approved",
        notes="Approved for posting"
    )
    print("✅ Posts approved")

    # 步骤6: 使用浏览器发布帖子
    print("\n📌 Step 6: Publishing posts via browser...")
    print("⚠️ Note: If CAPTCHA appears, the browser will pause and wait for your assistance.")

    # 发布X帖子
    print(f"\n📝 Publishing X post: {x_post_id}")
    x_publish_result = agent.publish_post_with_browser(x_post_id)

    if x_publish_result["success"]:
        print(f"✅ X post published successfully!")
        print(f"   URL: {x_publish_result.get('url', 'N/A')}")
    else:
        print(f"⚠️ X post publishing issue: {x_publish_result.get('error', 'Unknown error')}")
        print("   You can take a screenshot to see the current state:")
        screenshot_result = agent.take_browser_screenshot("x_post_issue.png")
        if screenshot_result["success"]:
            print(f"   Screenshot saved: {screenshot_result['screenshot_path']}")

    # 等待一下再发布下一个
    import time
    print("\n⏳ Waiting 5 seconds before next post...")
    time.sleep(5)

    # 发布Reddit帖子
    print(f"\n📝 Publishing Reddit post: {reddit_post_id}")
    reddit_publish_result = agent.publish_post_with_browser(reddit_post_id)

    if reddit_publish_result["success"]:
        print(f"✅ Reddit post published successfully!")
        print(f"   URL: {reddit_publish_result.get('url', 'N/A')}")
    else:
        print(f"⚠️ Reddit post publishing issue: {reddit_publish_result.get('error', 'Unknown error')}")
        screenshot_result = agent.take_browser_screenshot("reddit_post_issue.png")
        if screenshot_result["success"]:
            print(f"   Screenshot saved: {screenshot_result['screenshot_path']}")

    # 步骤7: 保存浏览器会话
    print("\n📌 Step 7: Saving browser session...")
    session_result = agent.save_browser_session("my_social_media_session")
    if session_result["success"]:
        print(f"✅ {session_result['message']}")

    # 步骤8: 查看审计日志
    print("\n📌 Step 8: Reviewing audit log...")
    audit_result = agent.get_audit_log(limit=10)
    print(f"\nRecent activities ({audit_result['total_entries']} entries):")
    for entry in audit_result["audit_log"][:5]:
        print(f"  - [{entry['timestamp']}] {entry['action']} by {entry['user_id']}")

    # 步骤9: 清理
    print("\n📌 Step 9: Cleaning up...")
    print("Closing browser...")
    agent.disable_browser_automation()

    print("\n" + "=" * 70)
    print("✅ Browser automation workflow completed!")
    print("=" * 70)


def example_manual_assistance_scenario():
    """人工协助场景示例"""
    print("\n" + "=" * 70)
    print("Manual Assistance Scenario Example")
    print("=" * 70)

    print("""
This example demonstrates how the system handles CAPTCHA verification:

1. Browser opens and navigates to the platform
2. When posting, if CAPTCHA is detected:
   - System pauses execution
   - Displays a message requesting human assistance
   - Takes a screenshot of the CAPTCHA
   - Waits for you to complete the verification
   - Checks every 5 seconds if CAPTCHA is cleared
   - Continues automatically once verified

3. If timeout (default 10 minutes):
   - System reports failure
   - You can retry later

Key Features:
- headless=False: Shows browser window for manual interaction
- slow_mo=500: Slows down actions to appear more human-like
- Automatic CAPTCHA detection
- Screenshot capture for debugging
- Audit trail of all actions
""")

    print("\nTo use this feature:")
    print("1. Enable browser automation with headless=False")
    print("2. Attempt to post content")
    print("3. If CAPTCHA appears, complete it in the browser window")
    print("4. System will automatically continue after verification")


def main():
    """运行示例"""
    print("\n" + "=" * 70)
    print("Browser Automation Examples")
    print("=" * 70)

    try:
        # 运行完整工作流示例
        example_browser_automation_workflow()

        # 显示人工协助场景说明
        example_manual_assistance_scenario()

    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        print("If browser is still open, please close it manually")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

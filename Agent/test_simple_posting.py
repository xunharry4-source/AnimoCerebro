#!/usr/bin/env python3
"""
简化的 X.com 和 Reddit 发帖测试

不依赖 LangGraph/CrewAI，直接测试浏览器自动化功能
"""

import os
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_browser_automation():
    """测试浏览器自动化基本功能"""
    print("\n" + "="*80)
    print("🧪 测试浏览器自动化")
    print("="*80)
    
    try:
        from Agent.browser_automation.browser_automation import BrowserAutomationManager
        print("✅ 导入成功")
        
        # 创建管理器
        manager = BrowserAutomationManager()
        
        # 启动浏览器
        print("\n1️⃣  启动浏览器...")
        manager.start_browser(browser_type="chromium")
        
        if manager.page:
            print("✅ 浏览器启动成功")
            
            # 访问 Reddit
            print("\n2️⃣  访问 Reddit...")
            manager.page.goto("https://www.reddit.com", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # 截图
            screenshot_path = Path("screenshots/test_reddit.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            manager.page.screenshot(path=str(screenshot_path))
            print(f"   📸 Reddit 截图: {screenshot_path}")
            
            # 访问 X.com
            print("\n3️⃣  访问 X.com...")
            manager.page.goto("https://twitter.com/home", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # 截图
            screenshot_path = Path("screenshots/test_x.png")
            manager.page.screenshot(path=str(screenshot_path))
            print(f"   📸 X.com 截图: {screenshot_path}")
            
            print("\n✅ 浏览器自动化测试成功！")
            
            # 关闭浏览器
            print("\n4️⃣  关闭浏览器...")
            manager.stop_browser()
            
            return True
        else:
            print("❌ 浏览器启动失败")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_reddit_smart_poster():
    """测试 Reddit 智能发帖器"""
    print("\n" + "="*80)
    print("🧪 测试 Reddit 智能发帖器")
    print("="*80)
    
    try:
        from Agent.browser_automation.browser_automation import BrowserAutomationManager
        from Agent.social_promotion.reddit_smart_poster import RedditSmartPoster
        from Agent.social_promotion.community_rules_manager import CommunityRulesManager
        
        print("✅ 导入成功")
        
        # 启动浏览器
        print("\n1️⃣  启动浏览器...")
        manager = BrowserAutomationManager()
        manager.start_browser(browser_type="chromium")
        
        if not manager.page:
            print("❌ 浏览器启动失败")
            return False
        
        # 手动登录提示
        print("\n2️⃣  请确保已登录 Reddit")
        print("   如果未登录，请在打开的浏览器中登录")
        input("   按 Enter 继续...")
        
        # 创建发帖器
        rules_manager = CommunityRulesManager()
        poster = RedditSmartPoster(manager.page, rules_manager)
        
        # 测试发帖
        print("\n3️⃣  测试发帖到 r/AnimoCerebro...")
        test_title = f"Test Post - {time.strftime('%Y-%m-%d %H:%M:%S')}"
        test_content = """
This is an automated test post from AnimoCerebro.

Testing the integration of browser automation with Reddit posting.

Please ignore this test.
"""
        
        success = poster.post_custom_content(
            subreddit="AnimoCerebro",
            title=test_title,
            content=test_content,
            flair="Discussion",
            max_retries=1
        )
        
        if success:
            print("   ✅ Reddit 发帖成功！")
        else:
            print("   ❌ Reddit 发帖失败")
        
        # 关闭浏览器
        print("\n4️⃣  关闭浏览器...")
        manager.stop_browser()
        
        return success
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("\n" + "🎯"*40)
    print("X.com 和 Reddit 发帖功能测试（简化版）")
    print("🎯"*40)
    
    # 测试 1: 浏览器自动化
    print("\n" + "="*80)
    print("测试 1: 浏览器自动化")
    print("="*80)
    browser_result = test_browser_automation()
    
    if not browser_result:
        print("\n❌ 浏览器自动化失败，无法继续")
        return False
    
    # 等待一下
    print("\n⏳ 等待 3 秒...")
    time.sleep(3)
    
    # 测试 2: Reddit 发帖
    print("\n" + "="*80)
    print("测试 2: Reddit 发帖")
    print("="*80)
    reddit_result = test_reddit_smart_poster()
    
    # 总结
    print("\n" + "="*80)
    print("📊 测试结果总结")
    print("="*80)
    print(f"浏览器自动化: {'✅ 成功' if browser_result else '❌ 失败'}")
    print(f"Reddit 发帖:   {'✅ 成功' if reddit_result else '❌ 失败'}")
    
    if browser_result and reddit_result:
        print("\n🎉 所有测试通过！")
    else:
        print("\n⚠️  部分测试失败，请查看上面的错误信息")
    
    return browser_result and reddit_result


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

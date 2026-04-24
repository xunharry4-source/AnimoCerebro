#!/usr/bin/env python3
"""
X.com 和 Reddit 发帖功能测试脚本

用于诊断和修复发帖问题
"""

import os
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from Agent.browser_automation.browser_automation import BrowserAutomation
from Agent.social_promotion.reddit_smart_poster import RedditSmartPoster
from Agent.social_promotion.community_rules_manager import CommunityRulesManager


def test_x_com_posting():
    """测试 X.com 发帖功能"""
    print("\n" + "="*80)
    print("🧪 测试 X.com 发帖功能")
    print("="*80)
    
    browser = None
    try:
        # 初始化浏览器
        print("\n1️⃣  初始化浏览器...")
        browser = BrowserAutomation()
        browser.initialize()
        page = browser.page
        
        # 检查是否登录
        print("\n2️⃣  检查登录状态...")
        page.goto("https://twitter.com/home", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        
        # 截图检查
        screenshot_path = Path("screenshots/x_login_check.png")
        screenshot_path.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot_path))
        print(f"   📸 截图已保存: {screenshot_path}")
        
        # 检查是否在登录页面
        current_url = page.url
        if "login" in current_url or "signin" in current_url:
            print("   ❌ 未登录，需要先手动登录")
            print("   💡 请在打开的浏览器中登录 X.com")
            input("   按 Enter 继续...")
            page.goto("https://twitter.com/home", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
        
        # 尝试发推文
        print("\n3️⃣  尝试发推文...")
        test_content = f"Test tweet from AnimoCerebro - {time.strftime('%Y-%m-%d %H:%M:%S')}"
        
        # 方法 1: 直接访问 compose 页面
        print("   方法 1: 访问 compose 页面...")
        page.goto("https://twitter.com/compose/tweet", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        
        # 查找推文输入框
        print("   查找推文输入框...")
        selectors = [
            'div[role="textbox"][data-testid="tweetTextarea_0"]',
            'div[contenteditable="true"][data-testid="tweetTextarea_0"]',
            'div[role="textbox"]',
            'textarea',
        ]
        
        tweet_box = None
        for selector in selectors:
            try:
                elements = page.locator(selector).all()
                if elements:
                    tweet_box = elements[0]
                    print(f"   ✅ 找到输入框: {selector}")
                    break
            except Exception as e:
                print(f"   ⚠️  选择器 {selector} 失败: {e}")
                continue
        
        if not tweet_box:
            print("   ❌ 未找到推文输入框")
            print("   💡 可能需要点击 'Tweet' 按钮")
            
            # 尝试点击 Tweet 按钮
            try:
                tweet_button = page.locator('button:has-text("Tweet"), button:has-text("发推")').first
                if tweet_button.count() > 0:
                    print("   点击 Tweet 按钮...")
                    tweet_button.click()
                    time.sleep(2)
                    
                    # 再次查找输入框
                    tweet_box = page.locator('div[role="textbox"]').first
            except Exception as e:
                print(f"   ❌ 点击 Tweet 按钮失败: {e}")
        
        if tweet_box:
            try:
                print(f"   填写内容: {test_content[:50]}...")
                tweet_box.fill(test_content)
                time.sleep(2)
                
                # 截图
                screenshot_path = Path("screenshots/x_tweet_filled.png")
                page.screenshot(path=str(screenshot_path))
                print(f"   📸 已填写内容的截图: {screenshot_path}")
                
                # 查找发布按钮
                print("   查找发布按钮...")
                post_selectors = [
                    'button[data-testid="tweetButton"]',
                    'button:has-text("Post")',
                    'button:has-text("发布")',
                    'div[role="button"]:has-text("Post")',
                ]
                
                post_button = None
                for selector in post_selectors:
                    try:
                        btn = page.locator(selector).first
                        if btn.count() > 0 and btn.is_enabled():
                            post_button = btn
                            print(f"   ✅ 找到发布按钮: {selector}")
                            break
                    except:
                        continue
                
                if post_button:
                    print("   点击发布按钮...")
                    post_button.click()
                    time.sleep(5)
                    
                    # 检查是否成功
                    current_url = page.url
                    screenshot_path = Path("screenshots/x_after_post.png")
                    page.screenshot(path=str(screenshot_path))
                    
                    if "status" in current_url or "home" in current_url:
                        print("   ✅ X.com 发布成功！")
                        print(f"   当前 URL: {current_url}")
                        return True
                    else:
                        print(f"   ⚠️  发布状态未知")
                        print(f"   当前 URL: {current_url}")
                        return False
                else:
                    print("   ❌ 未找到发布按钮")
                    return False
                    
            except Exception as e:
                print(f"   ❌ 发布过程出错: {e}")
                import traceback
                traceback.print_exc()
                return False
        else:
            print("   ❌ 无法找到推文输入框")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if browser:
            print("\n4️⃣  关闭浏览器...")
            browser.close()


def test_reddit_posting():
    """测试 Reddit 发帖功能"""
    print("\n" + "="*80)
    print("🧪 测试 Reddit 发帖功能")
    print("="*80)
    
    browser = None
    try:
        # 初始化浏览器
        print("\n1️⃣  初始化浏览器...")
        browser = BrowserAutomation()
        browser.initialize()
        page = browser.page
        
        # 检查是否登录
        print("\n2️⃣  检查登录状态...")
        page.goto("https://www.reddit.com", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        
        # 截图检查
        screenshot_path = Path("screenshots/reddit_login_check.png")
        screenshot_path.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot_path))
        print(f"   📸 截图已保存: {screenshot_path}")
        
        # 检查是否登录
        current_url = page.url
        if "login" in current_url:
            print("   ❌ 未登录，需要先手动登录")
            print("   💡 请在打开的浏览器中登录 Reddit")
            input("   按 Enter 继续...")
            page.goto("https://www.reddit.com", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
        
        # 测试 Reddit 发帖
        print("\n3️⃣  测试 Reddit 发帖...")
        rules_manager = CommunityRulesManager()
        reddit_poster = RedditSmartPoster(page, rules_manager)
        
        # 使用简单的测试内容
        test_title = f"Test Post - {time.strftime('%Y-%m-%d %H:%M:%S')}"
        test_content = """
This is a test post from AnimoCerebro automated system.

Testing the integration of:
- LangGraph workflow
- CrewAI content creation
- Browser automation

Please ignore this test post.
"""
        
        print(f"   标题: {test_title}")
        print(f"   社区: r/AnimoCerebro")
        
        # 尝试发帖
        success = reddit_poster.post_custom_content(
            subreddit="AnimoCerebro",
            title=test_title,
            content=test_content,
            flair="Discussion",
            max_retries=1
        )
        
        if success:
            print("   ✅ Reddit 发帖成功！")
            return True
        else:
            print("   ❌ Reddit 发帖失败")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if browser:
            print("\n4️⃣  关闭浏览器...")
            browser.close()


def main():
    """主函数"""
    print("\n" + "🎯"*40)
    print("X.com 和 Reddit 发帖功能测试")
    print("🎯"*40)
    
    # 设置环境变量
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    
    # 测试 X.com
    print("\n" + "="*80)
    print("开始测试 X.com...")
    print("="*80)
    x_result = test_x_com_posting()
    
    # 等待一下
    print("\n⏳ 等待 5 秒...")
    time.sleep(5)
    
    # 测试 Reddit
    print("\n" + "="*80)
    print("开始测试 Reddit...")
    print("="*80)
    reddit_result = test_reddit_posting()
    
    # 总结
    print("\n" + "="*80)
    print("📊 测试结果总结")
    print("="*80)
    print(f"X.com:  {'✅ 成功' if x_result else '❌ 失败'}")
    print(f"Reddit: {'✅ 成功' if reddit_result else '❌ 失败'}")
    
    if x_result and reddit_result:
        print("\n🎉 所有测试通过！")
    else:
        print("\n⚠️  部分测试失败，请查看上面的错误信息")
    
    return x_result and reddit_result


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

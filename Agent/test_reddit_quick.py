#!/usr/bin/env python3
"""
Reddit 自动化测试 - 使用已验证的方案

测试 Shadow DOM 穿透 + 状态轮询方案（已验证成功）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from Agent.reddit_advanced_helper import RedditAdvancedHelper


def test_reddit_posting_with_advanced_helper():
    """使用 RedditAdvancedHelper 测试发帖流程"""
    
    print("\n" + "="*80)
    print("🧪 Reddit 自动化测试 - Advanced Helper 方案")
    print("="*80)
    
    # 启动浏览器
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=False,
        args=['--start-maximized']
    )
    
    context = browser.new_context(
        viewport={'width': 1280, 'height': 800}
    )
    page = context.new_page()
    
    try:
        # 初始化高级助手
        print("\n🤖 初始化 RedditAdvancedHelper...")
        helper = RedditAdvancedHelper(page)
        
        # 访问 Reddit 提交页面
        print("\n🌐 访问 Reddit 提交页面...")
        page.goto("https://www.reddit.com/r/AnimoCerebro/submit", 
                 wait_until="domcontentloaded", timeout=30000)
        
        # 等待页面加载
        print("   ⏳ 等待页面加载...")
        page.wait_for_timeout(3000)
        
        # 检查是否已登录
        current_url = page.url
        if "login" in current_url.lower():
            print("\n⚠️  检测到未登录，请先手动登录 Reddit")
            print("   登录后按回车继续...")
            input()
        
        # 测试完整工作流
        print("\n🚀 执行完整发帖工作流...")
        result = helper.complete_posting_workflow(
            title="测试帖子 - Advanced Helper 方案",
            content="""
这是一个测试帖子，使用 RedditAdvancedHelper 的完整工作流。

测试内容：
1. 标题和内容填写
2. Post 按钮检测和点击
3. 提交结果分析

这个方案使用 Shadow DOM 穿透和状态轮询技术。
            """,
            subreddit="AnimoCerebro",
            flair_text=None,  # 暂时跳过 Flair
            max_retries=2
        )
        
        # 输出结果
        print("\n" + "="*80)
        print("📊 测试结果")
        print("="*80)
        
        if result['success']:
            print("\n✅✅✅ 测试成功！")
            print(f"\n🎉 帖子 URL: {result.get('final_status', {}).get('post_url', 'N/A')}")
            print(f"📈 尝试次数: {len(result.get('attempts', []))}")
            
            # 保存成功报告
            import json
            report = {
                'success': True,
                'post_url': result['final_status'].get('post_url'),
                'attempts': len(result['attempts']),
                'timestamp': str(Path.now())
            }
            
            report_path = Path("screenshots/test_success_report.json")
            report_path.parent.mkdir(exist_ok=True)
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2)
            
            print(f"\n💾 测试报告已保存: {report_path}")
            return True
            
        else:
            print("\n❌ 测试失败")
            print(f"\n📝 失败原因: {result.get('final_status', {}).get('message', '未知')}")
            
            # 保存失败详情
            import json
            report = {
                'success': False,
                'message': result['final_status'].get('message'),
                'attempts_count': len(result['attempts']),
                'attempts_detail': [
                    {
                        'attempt': a['attempt'],
                        'steps': {k: str(v) for k, v in a.get('steps', {}).items()}
                    }
                    for a in result['attempts']
                ]
            }
            
            report_path = Path("screenshots/test_failure_report.json")
            report_path.parent.mkdir(exist_ok=True)
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            print(f"\n💾 失败报告已保存: {report_path}")
            return False
        
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        
        # 截图保存错误状态
        error_screenshot = Path("screenshots/test_error_state.png")
        error_screenshot.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(error_screenshot), full_page=True)
        print(f"📸 错误截图已保存: {error_screenshot}")
        
        return False
        
    finally:
        # 清理
        print("\n🧹 清理资源...")
        browser.close()
        playwright.stop()
        print("✅ 测试完成")


if __name__ == "__main__":
    print("\n⚠️  注意: 此测试需要您已经登录 Reddit")
    print("   如果未登录，请在浏览器中手动登录后按回车继续\n")
    
    success = test_reddit_posting_with_advanced_helper()
    
    if success:
        print("\n🎊 所有测试通过！")
        sys.exit(0)
    else:
        print("\n⚠️  测试未完全通过，请查看报告")
        sys.exit(1)

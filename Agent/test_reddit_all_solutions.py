#!/usr/bin/env python3
"""
Reddit 多方案综合测试

测试所有高级自动化方案的有效性
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_all_solutions():
    """测试所有解决方案"""
    print("\n" + "="*80)
    print("🧪 Reddit 多方案综合测试")
    print("="*80)
    
    from playwright.sync_api import sync_playwright
    from Agent.browser_automation.test_auto_stealth_wait import STEALTH_JS, get_chrome_path
    from Agent.reddit_advanced_helper import RedditAdvancedHelper
    
    try:
        # 启动浏览器
        user_data_dir = Path("./chrome_custom_profile").resolve()
        executable_path = get_chrome_path()
        
        playwright = sync_playwright().start()
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=executable_path,
            headless=False,
            slow_mo=500,
        )
        
        context.add_init_script(STEALTH_JS)
        page = context.new_page()
        
        # 创建高级助手
        helper = RedditAdvancedHelper(page)
        
        print("\n1️⃣  访问 Reddit 提交页面...")
        page.goto("https://www.reddit.com/r/AnimoCerebro/submit", 
                 wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)
        
        print("\n2️⃣  填写标题和内容...")
        title_input = page.locator('textarea[name="title"]').first
        if title_input.count() > 0:
            title_input.fill("Multi-Solution Test")
            print("   ✓ 标题已填写")
        
        composer = page.locator('shreddit-composer').first
        if composer.count() > 0:
            composer.click()
            time.sleep(1)
            page.keyboard.type("Testing all advanced solutions.")
            print("   ✓ 内容已填写")
            time.sleep(3)
        
        # ==================== 方案1测试 ====================
        print("\n" + "="*80)
        print("📋 方案1: Shadow DOM 穿透测试")
        print("="*80)
        
        print("\n测试 1.1: 获取 Shadow DOM 按钮...")
        shadow_buttons = helper.get_composer_shadow_buttons()
        print(f"   🔍 找到 {len(shadow_buttons)} 个按钮")
        for btn in shadow_buttons[:5]:
            print(f"      - {btn['text'][:50] if btn['text'] else 'N/A'} (type={btn['type']})")
        
        print("\n测试 1.2: 强制点击 Flair 按钮...")
        click_result = helper.force_click_shadow_element(
            'shreddit-composer',
            "b => b.textContent.includes('flair') || b.textContent.includes('标记')"
        )
        if click_result:
            print("   ✅ 成功点击 Flair 按钮")
            time.sleep(2)
        else:
            print("   ❌ 未能点击 Flair 按钮")
        
        # ==================== 方案2测试 ====================
        print("\n" + "="*80)
        print("📋 方案2: 网络响应拦截测试")
        print("="*80)
        
        print("\n测试 2.1: 拦截 Flair 数据...")
        # 注意：这个测试会刷新页面，所以放在后面
        # flairs = helper.intercept_flair_data(timeout=5)
        # print(f"   📊 捕获到 {len(flairs)} 个 Flair")
        print("   ⏭️  跳过（需要刷新页面）")
        
        # ==================== 方案3测试 ====================
        print("\n" + "="*80)
        print("📋 方案3: Post 按钮状态轮询测试")
        print("="*80)
        
        print("\n测试 3.1: 轮询 Post 按钮状态...")
        button_state = helper.poll_post_button_state(max_attempts=5, interval=1)
        print(f"   结果: {button_state}")
        
        if button_state.get('found'):
            print(f"   ✅ 找到 Post 按钮")
            print(f"      类型: {button_state.get('type')}")
            print(f"      禁用: {button_state.get('disabled')}")
        else:
            print(f"   ❌ 未找到 Post 按钮")
        
        print("\n测试 3.2: 尝试提交帖子...")
        submit_result = helper.try_submit_post()
        print(f"   结果: {submit_result}")
        
        if submit_result.get('success'):
            print(f"   ✅ 提交成功 (方法: {submit_result.get('method')})")
            time.sleep(5)
            
            # 检查 URL
            current_url = page.url
            print(f"   当前 URL: {current_url}")
            
            if "/comments/" in current_url or "/posts/" in current_url:
                print("   ✅✅✅ 帖子发布成功！")
            else:
                print("   ⚠️  URL 未变化")
        else:
            print(f"   ❌ 提交失败: {submit_result.get('reason')}")
        
        # ==================== 方案4测试 ====================
        print("\n" + "="*80)
        print("📋 方案4: 深度序列化测试")
        print("="*80)
        
        print("\n测试 4.1: 获取所有 Flair 选项...")
        flairs = helper.get_all_flair_options()
        print(f"   🔍 找到 {len(flairs)} 个 Flair 选项")
        for flair in flairs[:10]:
            print(f"      - {flair['text']} (ID: {flair['id'][:20] if flair['id'] else 'N/A'}...)")
        
        print("\n测试 4.2: 序列化 Flair Modal...")
        modal_structure = helper.serialize_flair_modal()
        if 'error' not in modal_structure:
            print(f"   ✅ 成功序列化 Flair Modal")
            print(f"      标签: {modal_structure.get('tag')}")
            print(f"      子元素数: {len(modal_structure.get('children', []))}")
        else:
            print(f"   ⚠️  序列化失败: {modal_structure.get('error')}")
        
        # ==================== 综合工作流测试 ====================
        print("\n" + "="*80)
        print("📋 综合工作流测试")
        print("="*80)
        
        print("\n测试 5.1: 完整发帖工作流...")
        # 重新加载页面
        page.goto("https://www.reddit.com/r/AnimoCerebro/submit", 
                 wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)
        
        workflow_result = helper.complete_posting_workflow(
            title="Comprehensive Workflow Test",
            content="Testing the complete posting workflow with all solutions.",
            subreddit="AnimoCerebro",
            flair_text=None  # 不选择 Flair
        )
        
        print(f"\n   工作流结果:")
        print(f"      成功: {workflow_result['success']}")
        print(f"      步骤:")
        for step, status in workflow_result.get('steps', {}).items():
            print(f"         - {step}: {status}")
        
        if workflow_result.get('success'):
            print(f"   ✅✅✅ 综合工作流测试成功！")
            print(f"      帖子 URL: {workflow_result.get('post_url')}")
        else:
            print(f"   ❌ 工作流失败")
            if 'error' in workflow_result:
                print(f"      错误: {workflow_result['error']}")
        
        # 截图
        screenshot_path = Path("screenshots/test_all_solutions_final.png")
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"\n   📸 最终截图: {screenshot_path}")
        
        print("\n" + "="*80)
        print("✅ 所有测试完成！")
        print("="*80)
        
        input("\n按 Enter 关闭浏览器...")
        
        # 清理
        page.close()
        context.close()
        playwright.stop()
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_all_solutions()
    sys.exit(0 if success else 1)

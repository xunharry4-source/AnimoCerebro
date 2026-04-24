#!/usr/bin/env python3
"""
Reddit 提交页面元素诊断脚本

用于分析 Reddit 提交页面的 HTML 结构，找出正确的选择器
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def diagnose_reddit_submit_page():
    """诊断 Reddit 提交页面的元素结构"""
    print("\n" + "="*80)
    print("🔍 Reddit 提交页面元素诊断")
    print("="*80)
    
    from playwright.sync_api import sync_playwright
    from Agent.browser_automation.test_auto_stealth_wait import STEALTH_JS, get_chrome_path
    
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
        
        print("\n1️⃣  访问 Reddit 提交页面...")
        page.goto("https://www.reddit.com/r/AnimoCerebro/submit", 
                 wait_until="networkidle", timeout=60000)
        time.sleep(5)
        
        # 截图
        screenshot_path = Path("screenshots/reddit_submit_page.png")
        screenshot_path.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot_path))
        print(f"   📸 截图已保存: {screenshot_path}")
        
        print("\n2️⃣  查找所有输入框和文本区域...")
        
        # 查找所有 input 元素
        inputs = page.locator('input').all()
        print(f"\n   找到 {len(inputs)} 个 input 元素:")
        for i, inp in enumerate(inputs[:10]):  # 只显示前10个
            try:
                name = inp.get_attribute('name') or 'N/A'
                placeholder = inp.get_attribute('placeholder') or 'N/A'
                aria_label = inp.get_attribute('aria-label') or 'N/A'
                input_type = inp.get_attribute('type') or 'N/A'
                elem_id = inp.get_attribute('id') or 'N/A'
                
                print(f"      {i+1}. type={input_type}, name={name}, id={elem_id}")
                print(f"         placeholder={placeholder[:50] if len(placeholder) > 50 else placeholder}")
                print(f"         aria-label={aria_label[:50] if len(aria_label) > 50 else aria_label}")
            except:
                continue
        
        # 查找所有 textarea 元素
        print(f"\n   查找 textarea 元素...")
        textareas = page.locator('textarea').all()
        print(f"   找到 {len(textareas)} 个 textarea 元素:")
        for i, ta in enumerate(textareas[:10]):
            try:
                name = ta.get_attribute('name') or 'N/A'
                placeholder = ta.get_attribute('placeholder') or 'N/A'
                aria_label = ta.get_attribute('aria-label') or 'N/A'
                elem_id = ta.get_attribute('id') or 'N/A'
                role = ta.get_attribute('role') or 'N/A'
                
                print(f"      {i+1}. name={name}, id={elem_id}, role={role}")
                print(f"         placeholder={placeholder[:50] if len(placeholder) > 50 else placeholder}")
                print(f"         aria-label={aria_label[:50] if len(aria_label) > 50 else aria_label}")
            except:
                continue
        
        # 查找所有可编辑的 div
        print(f"\n   查找可编辑的 div 元素...")
        editable_divs = page.locator('div[contenteditable="true"]').all()
        print(f"   找到 {len(editable_divs)} 个可编辑 div:")
        for i, div in enumerate(editable_divs[:10]):
            try:
                aria_label = div.get_attribute('aria-label') or 'N/A'
                placeholder = div.text_content()[:50] if div.text_content() else 'N/A'
                elem_id = div.get_attribute('id') or 'N/A'
                data_testid = div.get_attribute('data-testid') or 'N/A'
                
                print(f"      {i+1}. id={elem_id}, data-testid={data_testid}")
                print(f"         aria-label={aria_label[:50] if len(aria_label) > 50 else aria_label}")
            except:
                continue
        
        # 查找特定的标题和内容字段
        print("\n3️⃣  尝试常见选择器...")
        
        test_selectors = [
            'input[name="title"]',
            'input[placeholder*="Title"]',
            'input[aria-label*="Title"]',
            'textarea[name="title"]',
            '#post-title',
            'textarea[name="text"]',
            'div[role="textbox"]',
            'textarea[placeholder*="Text"]',
            '#post-text',
            'shreddit-composer',
            '[data-testid="post-title"]',
            '[data-testid="post-body"]',
        ]
        
        for selector in test_selectors:
            try:
                elem = page.locator(selector).first
                count = elem.count()
                if count > 0:
                    is_visible = elem.is_visible()
                    print(f"   ✅ {selector}: 找到 {count} 个, 可见={is_visible}")
                    
                    # 如果是输入框，尝试获取更多信息
                    try:
                        tag = elem.evaluate("el => el.tagName")
                        print(f"      标签: {tag}")
                        if tag == 'INPUT' or tag == 'TEXTAREA':
                            placeholder = elem.get_attribute('placeholder')
                            if placeholder:
                                print(f"      Placeholder: {placeholder[:50]}")
                    except:
                        pass
                else:
                    print(f"   ❌ {selector}: 未找到")
            except Exception as e:
                print(f"   ⚠️  {selector}: 错误 - {str(e)[:50]}")
        
        # 检查是否有 Shadow DOM
        print("\n4️⃣  检查 Shadow DOM...")
        has_shadow = page.evaluate("""
            () => {
                const elements = document.querySelectorAll('*');
                for (let el of elements) {
                    if (el.shadowRoot) {
                        return true;
                    }
                }
                return false;
            }
        """)
        print(f"   检测到 Shadow DOM: {has_shadow}")
        
        # 获取页面标题和 URL
        print(f"\n5️⃣  页面信息:")
        print(f"   URL: {page.url}")
        print(f"   标题: {page.title()}")
        
        print("\n✅ 诊断完成！")
        print("💡 请查看上面的输出，找到正确的选择器")
        input("\n按 Enter 关闭浏览器...")
        
        # 清理
        page.close()
        context.close()
        playwright.stop()
        
        return True
        
    except Exception as e:
        print(f"\n❌ 诊断失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = diagnose_reddit_submit_page()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
Reddit Shadow DOM 真实内容提取

使用 JavaScript 直接从浏览器中提取 Shadow DOM 的真实 HTML
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def extract_real_shadow_dom():
    """提取真实的 Shadow DOM 内容"""
    print("\n" + "="*80)
    print("🔍 Reddit Shadow DOM 真实内容提取")
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
                 wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)
        
        print("\n2️⃣  填写标题和内容...")
        title_input = page.locator('textarea[name="title"]').first
        if title_input.count() > 0:
            title_input.fill("Real Shadow DOM Test")
            print("   ✓ 标题已填写")
        
        composer = page.locator('shreddit-composer').first
        if composer.count() > 0:
            composer.click()
            time.sleep(1)
            page.keyboard.type("Testing real shadow DOM extraction.")
            print("   ✓ 内容已填写")
            time.sleep(3)
        
        print("\n3️⃣  使用 JavaScript 提取 shreddit-composer 的 Shadow DOM...")
        
        # 方法 1: 提取整个 Shadow DOM 的 outerHTML
        shadow_html = page.evaluate("""
            () => {
                const composer = document.querySelector('shreddit-composer');
                if (!composer) {
                    return 'ERROR: shreddit-composer not found';
                }
                
                if (!composer.shadowRoot) {
                    return 'ERROR: shadowRoot not available';
                }
                
                // 递归克隆 Shadow DOM 为普通 HTML
                function cloneShadowDOM(element) {
                    const clone = element.cloneNode(false);
                    
                    // 如果有 shadow root，将其内容添加到 clone 中
                    if (element.shadowRoot) {
                        const shadowContent = document.createElement('div');
                        shadowContent.setAttribute('data-shadow-root', 'true');
                        
                        const children = Array.from(element.shadowRoot.children || []);
                        for (const child of children) {
                            shadowContent.appendChild(cloneShadowDOM(child));
                        }
                        
                        clone.appendChild(shadowContent);
                    }
                    
                    // 处理普通子元素
                    const regularChildren = Array.from(element.children || []);
                    for (const child of regularChildren) {
                        clone.appendChild(cloneShadowDOM(child));
                    }
                    
                    return clone;
                }
                
                const cloned = cloneShadowDOM(composer);
                return cloned.outerHTML;
            }
        """)
        
        # 保存 Shadow DOM HTML
        shadow_html_path = Path("screenshots/reddit_shadow_dom_real.html")
        shadow_html_path.write_text(shadow_html, encoding='utf-8')
        print(f"   📄 Shadow DOM HTML 已保存: {shadow_html_path}")
        print(f"      大小: {len(shadow_html)} 字节")
        
        # 方法 2: 提取所有按钮的详细信息
        print("\n4️⃣  提取所有按钮信息...")
        buttons_info = page.evaluate("""
            () => {
                const composer = document.querySelector('shreddit-composer');
                if (!composer || !composer.shadowRoot) {
                    return [];
                }
                
                // 在 shadow root 中查找所有按钮
                const buttons = Array.from(composer.shadowRoot.querySelectorAll('button'));
                
                return buttons.map((btn, index) => {
                    const rect = btn.getBoundingClientRect();
                    return {
                        index: index,
                        text: btn.textContent?.trim(),
                        innerText: btn.innerText?.trim(),
                        ariaLabel: btn.getAttribute('aria-label'),
                        type: btn.getAttribute('type'),
                        role: btn.getAttribute('role'),
                        className: btn.className,
                        id: btn.id,
                        dataTestId: btn.getAttribute('data-testid'),
                        tagName: btn.tagName,
                        isVisible: rect.width > 0 && rect.height > 0,
                        isDisabled: btn.disabled,
                        parentTag: btn.parentElement?.tagName,
                        htmlSnippet: btn.outerHTML.substring(0, 500)
                    };
                });
            }
        """)
        
        import json
        buttons_json_path = Path("screenshots/reddit_shadow_buttons.json")
        buttons_json_path.write_text(json.dumps(buttons_info, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"   📄 按钮信息已保存: {buttons_json_path}")
        
        print(f"\n   🔍 找到 {len(buttons_info)} 个按钮:")
        post_button_found = False
        for btn in buttons_info:
            print(f"\n      按钮 #{btn['index']}:")
            print(f"         文本: {btn['text'][:80] if btn['text'] else 'N/A'}")
            print(f"         Aria: {btn['ariaLabel'][:80] if btn['ariaLabel'] else 'N/A'}")
            print(f"         Type: {btn['type']}")
            print(f"         Class: {btn['className'][:80] if btn['className'] else 'N/A'}")
            print(f"         ID: {btn['id']}")
            print(f"         Data-TestID: {btn['dataTestId']}")
            print(f"         Visible: {btn['isVisible']}, Disabled: {btn['isDisabled']}")
            
            # 检查是否是 Post/Submit 按钮
            text_lower = (btn['text'] or '').lower()
            aria_lower = (btn['ariaLabel'] or '').lower()
            
            if any(keyword in text_lower or keyword in aria_lower 
                   for keyword in ['post', 'submit', '发布', '提交']):
                print(f"         ✅✅✅ 这很可能是 Post/Submit 按钮！")
                post_button_found = True
        
        if not post_button_found:
            print("\n   ⚠️  未找到明显的 Post/Submit 按钮")
            print("   💡 显示所有按钮供分析:")
            for btn in buttons_info[:10]:
                print(f"      #{btn['index']}: '{btn['text']}' (type={btn['type']}, class={btn['className'][:50]})")
        
        # 方法 3: 尝试直接点击可能的提交按钮
        print("\n5️⃣  尝试定位并点击提交按钮...")
        
        click_result = page.evaluate("""
            () => {
                const composer = document.querySelector('shreddit-composer');
                if (!composer || !composer.shadowRoot) {
                    return { success: false, error: 'composer not found' };
                }
                
                // 策略 1: 查找 type="submit" 的按钮
                let submitBtn = composer.shadowRoot.querySelector('button[type="submit"]');
                if (submitBtn) {
                    console.log('找到 type=submit 按钮');
                    submitBtn.click();
                    return { success: true, method: 'type_submit', button: submitBtn.outerHTML.substring(0, 200) };
                }
                
                // 策略 2: 查找包含 "Post" 文本的按钮
                const allButtons = Array.from(composer.shadowRoot.querySelectorAll('button'));
                for (const btn of allButtons) {
                    const text = btn.textContent || '';
                    if (text.includes('Post') || text.includes('post')) {
                        console.log('找到 Post 按钮:', text);
                        btn.click();
                        return { success: true, method: 'text_post', button: btn.outerHTML.substring(0, 200) };
                    }
                }
                
                // 策略 3: 查找第一个可见且启用的按钮（可能是提交按钮）
                for (const btn of allButtons) {
                    const rect = btn.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && !btn.disabled) {
                        const text = btn.textContent || '';
                        // 跳过明显不是提交的按钮
                        if (!text.includes('Cancel') && !text.includes('取消') && !text.includes('Close')) {
                            console.log('尝试点击按钮:', text);
                            btn.click();
                            return { success: true, method: 'first_visible', button: btn.outerHTML.substring(0, 200) };
                        }
                    }
                }
                
                return { success: false, error: 'no suitable button found', totalButtons: allButtons.length };
            }
        """)
        
        print(f"   点击结果: {json.dumps(click_result, indent=2, ensure_ascii=False)}")
        
        if click_result.get('success'):
            print("   ✅ 按钮已点击！")
            print("   ⏳ 等待 10 秒观察结果...")
            time.sleep(10)
            
            # 截图
            screenshot_path = Path("screenshots/reddit_after_click.png")
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"   📸 截图已保存: {screenshot_path}")
            
            # 检查 URL 变化
            current_url = page.url
            print(f"   当前 URL: {current_url}")
            
            if "/comments/" in current_url or "/posts/" in current_url:
                print("   ✅✅✅ 帖子发布成功！")
            else:
                print("   ⚠️  URL 未变化，可能发布失败或有错误")
        else:
            print(f"   ❌ 未能点击按钮: {click_result.get('error')}")
        
        # 最终截图
        final_screenshot = Path("screenshots/reddit_final_state.png")
        page.screenshot(path=str(final_screenshot), full_page=True)
        print(f"\n   📸 最终状态截图: {final_screenshot}")
        
        print("\n✅ 诊断完成！")
        print("\n📁 生成的文件:")
        print("   - screenshots/reddit_shadow_dom_real.html (完整的 Shadow DOM HTML)")
        print("   - screenshots/reddit_shadow_buttons.json (所有按钮的详细信息)")
        print("   - screenshots/reddit_after_click.png (点击后的截图，如果点击成功)")
        print("   - screenshots/reddit_final_state.png (最终状态)")
        
        print("\n💡 下一步:")
        print("   1. 查看 reddit_shadow_dom_real.html 了解完整结构")
        print("   2. 查看 reddit_shadow_buttons.json 找到正确的按钮")
        print("   3. 根据实际结构调整代码中的选择器")
        
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
    success = extract_real_shadow_dom()
    sys.exit(0 if success else 1)

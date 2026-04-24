#!/usr/bin/env python3
"""
Reddit Shadow DOM 深度诊断

专门检查 shreddit-composer 的 Shadow DOM 结构
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def diagnose_shadow_dom():
    """深度诊断 Shadow DOM 结构"""
    print("\n" + "="*80)
    print("🔍 Reddit Shadow DOM 深度诊断")
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
            title_input.fill("Shadow DOM Test")
            print("   ✓ 标题已填写")
        
        composer = page.locator('shreddit-composer').first
        if composer.count() > 0:
            composer.click()
            time.sleep(1)
            page.keyboard.type("Test content for shadow DOM diagnosis.")
            print("   ✓ 内容已填写")
            time.sleep(2)
        
        print("\n3️⃣  分析 shreddit-composer 的 Shadow DOM 结构...")
        
        # 获取 shreddit-composer 的完整 Shadow DOM 结构
        shadow_structure = page.evaluate("""
            () => {
                const composer = document.querySelector('shreddit-composer');
                if (!composer) {
                    return { error: 'shreddit-composer not found' };
                }
                
                if (!composer.shadowRoot) {
                    return { error: 'shadowRoot not available' };
                }
                
                // 递归获取 Shadow DOM 结构
                function getElementInfo(element, depth = 0) {
                    if (depth > 5) return null; // 限制深度
                    
                    const info = {
                        tag: element.tagName.toLowerCase(),
                        id: element.id,
                        class: element.className,
                        text: element.textContent?.trim().substring(0, 100),
                        attributes: {},
                        children: []
                    };
                    
                    // 获取关键属性
                    const attrs = ['type', 'name', 'role', 'aria-label', 'data-testid', 'class'];
                    for (const attr of attrs) {
                        const value = element.getAttribute(attr);
                        if (value) {
                            info.attributes[attr] = value;
                        }
                    }
                    
                    // 如果是 button 或 input，特别标记
                    if (element.tagName === 'BUTTON') {
                        info.isButton = true;
                        info.buttonText = element.textContent?.trim();
                    }
                    
                    // 递归处理子元素
                    const children = Array.from(element.children || []);
                    for (const child of children) {
                        const childInfo = getElementInfo(child, depth + 1);
                        if (childInfo) {
                            info.children.push(childInfo);
                        }
                    }
                    
                    // 如果有 shadow root，也获取
                    if (element.shadowRoot) {
                        info.hasShadowRoot = true;
                        const shadowChildren = Array.from(element.shadowRoot.children || []);
                        for (const child of shadowChildren) {
                            const childInfo = getElementInfo(child, depth + 1);
                            if (childInfo) {
                                info.children.push({
                                    ...childInfo,
                                    inShadowRoot: true
                                });
                            }
                        }
                    }
                    
                    return info;
                }
                
                return getElementInfo(composer);
            }
        """)
        
        # 保存完整的 Shadow DOM 结构
        import json
        shadow_json_path = Path("screenshots/shadow_dom_structure.json")
        shadow_json_path.write_text(json.dumps(shadow_structure, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"   📄 Shadow DOM 结构已保存: {shadow_json_path}")
        
        # 查找所有按钮
        all_buttons_in_shadow = page.evaluate("""
            () => {
                const composer = document.querySelector('shreddit-composer');
                if (!composer || !composer.shadowRoot) {
                    return [];
                }
                
                const buttons = Array.from(composer.shadowRoot.querySelectorAll('button'));
                return buttons.map((btn, index) => ({
                    index: index,
                    text: btn.textContent?.trim(),
                    aria: btn.getAttribute('aria-label'),
                    type: btn.getAttribute('type'),
                    class: btn.className,
                    id: btn.id,
                    role: btn.getAttribute('role'),
                    dataTestId: btn.getAttribute('data-testid')
                }));
            }
        """)
        
        print(f"\n   🔍 在 Shadow DOM 中找到 {len(all_buttons_in_shadow)} 个按钮:")
        for btn in all_buttons_in_shadow:
            print(f"\n      按钮 #{btn['index']}:")
            print(f"         文本: {btn['text'][:100] if btn['text'] else 'N/A'}")
            print(f"         Aria: {btn['aria'][:100] if btn['aria'] else 'N/A'}")
            print(f"         Type: {btn['type']}")
            print(f"         Class: {btn['class'][:100] if btn['class'] else 'N/A'}")
            print(f"         ID: {btn['id']}")
            print(f"         Role: {btn['role']}")
            print(f"         Data-TestID: {btn['dataTestId']}")
            
            # 检查是否是 Post/Submit 按钮
            text_lower = (btn['text'] or '').lower()
            aria_lower = (btn['aria'] or '').lower()
            if any(keyword in text_lower or keyword in aria_lower 
                   for keyword in ['post', 'submit', '发布', '提交']):
                print(f"         ✅ 这可能是 Post/Submit 按钮！")
        
        # 保存按钮列表
        buttons_json_path = Path("screenshots/shadow_dom_buttons.json")
        buttons_json_path.write_text(json.dumps(all_buttons_in_shadow, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"\n   📄 Shadow DOM 按钮列表已保存: {buttons_json_path}")
        
        # 截图
        screenshot_path = Path("screenshots/shadow_dom_diagnosis.png")
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"   📸 截图已保存: {screenshot_path}")
        
        print("\n✅ Shadow DOM 诊断完成！")
        print("\n💡 下一步:")
        print("   1. 查看 shadow_dom_buttons.json 找到 Post 按钮的确切信息")
        print("   2. 根据按钮的 class/id/data-testid 构建正确的选择器")
        print("   3. 更新 reddit_smart_poster.py 使用正确的选择器")
        
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
    success = diagnose_shadow_dom()
    sys.exit(0 if success else 1)

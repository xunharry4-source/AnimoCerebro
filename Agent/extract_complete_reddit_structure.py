#!/usr/bin/env python3
"""
Reddit 完整页面结构提取器

解决 Shadow DOM 和 Web Components 导致的页面结构获取不完整问题
"""

import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def extract_complete_page_structure():
    """提取完整的页面结构，包括所有 Shadow DOM"""
    print("\n" + "="*80)
    print("🔍 Reddit 完整页面结构提取")
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
            title_input.fill("Complete Structure Test")
            print("   ✓ 标题已填写")
        
        composer = page.locator('shreddit-composer').first
        if composer.count() > 0:
            composer.click()
            time.sleep(1)
            page.keyboard.type("Testing complete page structure extraction.")
            print("   ✓ 内容已填写")
            time.sleep(3)
        
        print("\n3️⃣  提取完整页面结构（包括所有 Shadow DOM）...")
        
        # 使用 JavaScript 递归提取所有 Shadow DOM
        complete_structure = page.evaluate("""
            () => {
                // 递归函数：提取元素及其 Shadow DOM
                function extractElement(element, depth = 0) {
                    if (depth > 10) return null; // 限制深度避免无限递归
                    
                    const info = {
                        tag: element.tagName.toLowerCase(),
                        id: element.id || null,
                        className: element.className || null,
                        textContent: (element.textContent || '').trim().substring(0, 200),
                        attributes: {},
                        children: [],
                        shadowRoot: null
                    };
                    
                    // 提取关键属性
                    const importantAttrs = ['type', 'name', 'role', 'aria-label', 
                                          'data-testid', 'post-action-type', 
                                          'subreddit-id', 'value', 'placeholder'];
                    for (const attr of importantAttrs) {
                        const value = element.getAttribute(attr);
                        if (value !== null && value !== '') {
                            info.attributes[attr] = value;
                        }
                    }
                    
                    // 检查是否有 Shadow Root
                    if (element.shadowRoot) {
                        info.hasShadowRoot = true;
                        info.shadowRoot = {
                            mode: element.shadowRoot.mode,
                            children: []
                        };
                        
                        // 递归提取 Shadow Root 中的子元素
                        const shadowChildren = Array.from(element.shadowRoot.children || []);
                        for (const child of shadowChildren) {
                            const childInfo = extractElement(child, depth + 1);
                            if (childInfo) {
                                info.shadowRoot.children.push(childInfo);
                            }
                        }
                    }
                    
                    // 提取普通子元素
                    const regularChildren = Array.from(element.children || []);
                    for (const child of regularChildren) {
                        const childInfo = extractElement(child, depth + 1);
                        if (childInfo) {
                            info.children.push(childInfo);
                        }
                    }
                    
                    return info;
                }
                
                // 从 document.body 开始提取
                return extractElement(document.body);
            }
        """)
        
        # 保存完整结构
        structure_path = Path("screenshots/complete_page_structure.json")
        structure_path.parent.mkdir(exist_ok=True)
        structure_path.write_text(
            json.dumps(complete_structure, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        print(f"   📄 完整页面结构已保存: {structure_path}")
        print(f"      大小: {len(json.dumps(complete_structure))} 字节")
        
        # 提取所有按钮的详细信息
        print("\n4️⃣  提取所有按钮信息...")
        all_buttons = page.evaluate("""
            () => {
                const buttons = [];
                
                // 递归查找所有按钮（包括 Shadow DOM 中的）
                function findButtons(element, path = '') {
                    // 检查当前元素是否是按钮
                    if (element.tagName === 'BUTTON' || 
                        element.getAttribute('role') === 'button' ||
                        element.tagName.includes('-BUTTON')) {
                        
                        const rect = element.getBoundingClientRect();
                        buttons.push({
                            path: path,
                            tag: element.tagName,
                            id: element.id,
                            text: (element.textContent || '').trim().substring(0, 100),
                            ariaLabel: element.getAttribute('aria-label'),
                            type: element.getAttribute('type'),
                            role: element.getAttribute('role'),
                            className: element.className,
                            dataTestId: element.getAttribute('data-testid'),
                            postActionType: element.getAttribute('post-action-type'),
                            isVisible: rect.width > 0 && rect.height > 0,
                            isDisabled: element.disabled || element.hasAttribute('disabled'),
                            hasShadowRoot: !!element.shadowRoot
                        });
                    }
                    
                    // 检查 Shadow Root
                    if (element.shadowRoot) {
                        const shadowChildren = Array.from(element.shadowRoot.children || []);
                        for (const child of shadowChildren) {
                            findButtons(child, `${path} > ${element.tagName.toLowerCase()}[shadow]`);
                        }
                    }
                    
                    // 检查普通子元素
                    const children = Array.from(element.children || []);
                    for (const child of children) {
                        findButtons(child, `${path} > ${element.tagName.toLowerCase()}`);
                    }
                }
                
                findButtons(document.body, 'body');
                return buttons;
            }
        """)
        
        buttons_path = Path("screenshots/all_buttons_detailed.json")
        buttons_path.write_text(
            json.dumps(all_buttons, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        print(f"   📄 所有按钮信息已保存: {buttons_path}")
        print(f"   🔍 共找到 {len(all_buttons)} 个按钮")
        
        # 分类显示按钮
        print("\n   📊 按钮分类:")
        post_buttons = [b for b in all_buttons if 
                       any(kw in (b['text'] or '').lower() or 
                           kw in (b['ariaLabel'] or '').lower()
                           for kw in ['post', 'submit', '发布', '提交'])]
        
        submit_buttons = [b for b in all_buttons if 
                         b.get('postActionType') == 'submit' or 
                         b.get('type') == 'submit']
        
        flair_buttons = [b for b in all_buttons if 
                        any(kw in (b['text'] or '').lower() or 
                            kw in (b['ariaLabel'] or '').lower() or
                            kw in (b['className'] or '').lower()
                            for kw in ['flair', '标记', '标识'])]
        
        print(f"      - Post/Submit 相关按钮: {len(post_buttons)} 个")
        for btn in post_buttons[:5]:
            print(f"         • {btn['tag']}#{btn['id']} - 文本: '{btn['text']}'")
            print(f"           Path: {btn['path'][:100]}")
            print(f"           Disabled: {btn['isDisabled']}, Visible: {btn['isVisible']}")
        
        print(f"\n      - Type=submit 按钮: {len(submit_buttons)} 个")
        for btn in submit_buttons[:5]:
            print(f"         • {btn['tag']}#{btn['id']} - Post Action: {btn.get('postActionType')}")
            print(f"           Path: {btn['path'][:100]}")
        
        print(f"\n      - Flair 相关按钮: {len(flair_buttons)} 个")
        for btn in flair_buttons[:5]:
            print(f"         • {btn['tag']}#{btn['id']} - 文本: '{btn['text']}'")
            print(f"           Path: {btn['path'][:100]}")
        
        # 提取所有自定义 Web Components
        print("\n5️⃣  提取所有自定义 Web Components...")
        web_components = page.evaluate("""
            () => {
                const components = new Set();
                
                function findComponents(element) {
                    if (element.tagName.includes('-')) {
                        components.add(element.tagName.toLowerCase());
                    }
                    
                    if (element.shadowRoot) {
                        const shadowChildren = Array.from(element.shadowRoot.children || []);
                        for (const child of shadowChildren) {
                            findComponents(child);
                        }
                    }
                    
                    const children = Array.from(element.children || []);
                    for (const child of children) {
                        findComponents(child);
                    }
                }
                
                findComponents(document.body);
                return Array.from(components).sort();
            }
        """)
        
        print(f"   🔍 找到 {len(web_components)} 个自定义组件:")
        for comp in web_components[:30]:  # 只显示前30个
            print(f"      - {comp}")
        
        components_path = Path("screenshots/web_components_list.json")
        components_path.write_text(
            json.dumps(web_components, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        
        # 截图
        screenshot_path = Path("screenshots/complete_structure_screenshot.png")
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"\n   📸 截图已保存: {screenshot_path}")
        
        print("\n✅ 完整页面结构提取完成！")
        print("\n📁 生成的文件:")
        print("   1. screenshots/complete_page_structure.json - 完整页面结构树")
        print("   2. screenshots/all_buttons_detailed.json - 所有按钮详细信息")
        print("   3. screenshots/web_components_list.json - 所有Web Components列表")
        print("   4. screenshots/complete_structure_screenshot.png - 页面截图")
        
        print("\n💡 下一步分析:")
        print("   1. 查看 complete_page_structure.json 了解完整DOM树")
        print("   2. 查看 all_buttons_detailed.json 找到正确的按钮选择器")
        print("   3. 根据实际结构调整代码中的定位策略")
        
        input("\n按 Enter 关闭浏览器...")
        
        # 清理
        page.close()
        context.close()
        playwright.stop()
        
        return True
        
    except Exception as e:
        print(f"\n❌ 提取失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = extract_complete_page_structure()
    sys.exit(0 if success else 1)

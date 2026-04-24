#!/usr/bin/env python3
"""
Reddit Flair 按钮诊断脚本

找出正确的 Flair 按钮选择器
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from Agent.browser_automation.test_auto_stealth_wait import (
    get_chrome_path, 
    STEALTH_JS,
    HAS_STEALTH
)


def diagnose_flair_button():
    """诊断 Flair 按钮的实际 HTML 结构"""
    
    print("\n" + "="*80)
    print("🔍 Reddit Flair 按钮诊断")
    print("="*80)
    
    # 启动浏览器（使用持久化配置）
    executable_path = get_chrome_path()
    user_data_dir = Path("./chrome_custom_profile").resolve()
    user_data_dir.mkdir(exist_ok=True)
    
    playwright = sync_playwright().start()
    
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(user_data_dir),
        executable_path=executable_path,
        headless=False,
        slow_mo=500,
        viewport={"width": 1920, "height": 1080},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    )
    
    context.add_init_script(STEALTH_JS)
    page = context.new_page()
    
    try:
        # 访问 Reddit 提交页面
        print("\n🌐 访问 Reddit 提交页面...")
        page.goto("https://www.reddit.com/r/AnimoCerebro/submit", 
                 wait_until="domcontentloaded", timeout=30000)
        
        print("   ⏳ 等待页面加载...")
        page.wait_for_timeout(5000)
        
        # 检查是否已登录
        if "login" in page.url.lower():
            print("\n⚠️  需要登录，请手动登录后按回车继续...")
            input()
        
        # 填写标题和内容（触发 Composer 激活）
        print("\n📝 填写标题和内容以激活 Composer...")
        title_input = page.locator('textarea[name="title"]').first
        if title_input.count() > 0:
            title_input.fill("诊断测试")
            print("   ✓ 标题已填写")
        
        composer = page.locator('shreddit-composer').first
        if composer.count() > 0:
            composer.click()
            page.wait_for_timeout(1000)
            page.keyboard.type("这是诊断测试内容")
            print("   ✓ 内容已填写")
        
        page.wait_for_timeout(2000)
        
        # 诊断 1: 查找所有可能的 Flair 按钮
        print("\n" + "="*80)
        print("🔍 诊断 1: 查找所有可能的 Flair 按钮")
        print("="*80)
        
        flair_buttons = page.evaluate("""
            () => {
                const results = [];
                
                // 方法 1: 通过 ID 查找
                const byId = document.querySelector('#reddit-post-flair-button');
                if (byId) {
                    results.push({
                        method: 'by-id',
                        selector: '#reddit-post-flair-button',
                        text: byId.textContent?.trim(),
                        tagName: byId.tagName,
                        className: byId.className,
                        visible: byId.offsetParent !== null
                    });
                }
                
                // 方法 2: 在 Shadow DOM 中查找
                const composer = document.querySelector('shreddit-composer');
                if (composer && composer.shadowRoot) {
                    const shadowButtons = Array.from(composer.shadowRoot.querySelectorAll('button'));
                    shadowButtons.forEach((btn, index) => {
                        const text = btn.textContent?.toLowerCase() || '';
                        if (text.includes('flair') || text.includes('标记') || text.includes('add')) {
                            results.push({
                                method: 'shadow-dom',
                                selector: `shreddit-composer -> button[${index}]`,
                                text: btn.textContent?.trim(),
                                tagName: btn.tagName,
                                className: btn.className,
                                ariaLabel: btn.getAttribute('aria-label'),
                                visible: true
                            });
                        }
                    });
                }
                
                // 方法 3: 查找包含 "Flair" 或 "标记" 的所有按钮
                const allButtons = document.querySelectorAll('button');
                allButtons.forEach((btn, index) => {
                    const text = btn.textContent?.toLowerCase() || '';
                    if ((text.includes('flair') || text.includes('标记') || text.includes('标识')) && index < 50) {
                        results.push({
                            method: 'text-match',
                            selector: `button[${index}]`,
                            text: btn.textContent?.trim(),
                            tagName: btn.tagName,
                            className: btn.className,
                            ariaLabel: btn.getAttribute('aria-label'),
                            visible: btn.offsetParent !== null
                        });
                    }
                });
                
                return results;
            }
        """)
        
        if flair_buttons:
            print(f"\n✅ 找到 {len(flair_buttons)} 个可能的 Flair 按钮:\n")
            for i, btn in enumerate(flair_buttons, 1):
                print(f"{i}. 方法: {btn['method']}")
                print(f"   选择器: {btn['selector']}")
                print(f"   文本: \"{btn['text']}\"")
                print(f"   标签: {btn['tagName']}")
                print(f"   类名: {btn.get('className', 'N/A')}")
                if btn.get('ariaLabel'):
                    print(f"   Aria: {btn['ariaLabel']}")
                print(f"   可见: {btn.get('visible', 'N/A')}")
                print()
        else:
            print("\n❌ 未找到任何 Flair 按钮")
        
        # 诊断 2: 尝试点击第一个找到的按钮
        if flair_buttons:
            print("\n" + "="*80)
            print("🧪 诊断 2: 尝试点击第一个按钮")
            print("="*80)
            
            first_btn = flair_buttons[0]
            print(f"\n尝试点击: {first_btn['selector']}")
            
            if first_btn['method'] == 'by-id':
                click_result = page.evaluate("""
                    () => {
                        const btn = document.querySelector('#reddit-post-flair-button');
                        if (btn) {
                            btn.click();
                            return true;
                        }
                        return false;
                    }
                """)
            elif first_btn['method'] == 'shadow-dom':
                click_result = page.evaluate("""
                    () => {
                        const composer = document.querySelector('shreddit-composer');
                        if (composer && composer.shadowRoot) {
                            const buttons = Array.from(composer.shadowRoot.querySelectorAll('button'));
                            const target = buttons.find(b => {
                                const text = b.textContent?.toLowerCase() || '';
                                return text.includes('flair') || text.includes('标记');
                            });
                            if (target) {
                                target.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
            
            if click_result:
                print("   ✅ 点击成功")
                page.wait_for_timeout(2000)
                
                # 检查对话框是否打开
                dialog_opened = page.evaluate("""
                    () => {
                        // 检查是否有 Flair 对话框
                        const modal = document.querySelector('shreddit-post-flair-modal');
                        const overlay = document.querySelector('[class*="overlay"]');
                        const dialog = document.querySelector('[role="dialog"]');
                        
                        return {
                            hasModal: !!modal,
                            hasOverlay: !!overlay,
                            hasDialog: !!dialog,
                            url: window.location.href
                        };
                    }
                """)
                
                print(f"\n📊 对话框状态:")
                print(f"   Modal: {dialog_opened['hasModal']}")
                print(f"   Overlay: {dialog_opened['hasOverlay']}")
                print(f"   Dialog: {dialog_opened['hasDialog']}")
                
                if dialog_opened['hasModal'] or dialog_opened['hasOverlay'] or dialog_opened['hasDialog']:
                    print("\n✅✅✅ Flair 对话框已成功打开！")
                    
                    # 截图保存
                    screenshot_path = Path("screenshots/flair_dialog_opened.png")
                    screenshot_path.parent.mkdir(exist_ok=True)
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"📸 截图已保存: {screenshot_path}")
                    
                    # 分析对话框内容
                    print("\n🔍 分析对话框内容...")
                    dialog_content = page.evaluate("""
                        () => {
                            const modal = document.querySelector('shreddit-post-flair-modal');
                            if (!modal) return null;
                            
                            const rows = Array.from(modal.querySelectorAll('shreddit-post-flair-row'));
                            return rows.map(row => {
                                const span = row.querySelector('span');
                                return {
                                    text: span?.textContent?.trim(),
                                    tagName: row.tagName,
                                    className: row.className
                                };
                            }).filter(r => r.text);
                        }
                    """)
                    
                    if dialog_content:
                        print(f"\n✅ 找到 {len(dialog_content)} 个 Flair 选项:")
                        for i, flair in enumerate(dialog_content[:10], 1):
                            print(f"   {i}. {flair['text']}")
                        if len(dialog_content) > 10:
                            print(f"   ... 还有 {len(dialog_content) - 10} 个")
                    else:
                        print("   ⚠️  未找到 Flair 选项")
                else:
                    print("\n❌ Flair 对话框未打开")
            else:
                print("   ❌ 点击失败")
        
        print("\n" + "="*80)
        print("💡 建议的修复方案")
        print("="*80)
        
        if flair_buttons:
            print("\n根据诊断结果，建议更新 _open_flair_dialog() 方法:")
            print("\n```python")
            print("def _open_flair_dialog(self) -> bool:")
            print("    try:")
            
            if any(btn['method'] == 'by-id' for btn in flair_buttons):
                print("        # 方法 1: 使用 ID 选择器")
                print("        result = self.page.evaluate('''")
                print("            () => {")
                print("                const btn = document.querySelector('#reddit-post-flair-button');")
                print("                if (btn) {")
                print("                    btn.click();")
                print("                    return true;")
                print("                }")
                print("                return false;")
                print("            }")
                print("        ''')")
                print("        return result")
            else:
                print("        # 方法 1: Shadow DOM 查找")
                print("        result = self.page.evaluate('''")
                print("            () => {")
                print("                const composer = document.querySelector('shreddit-composer');")
                print("                if (composer && composer.shadowRoot) {")
                print("                    const buttons = Array.from(composer.shadowRoot.querySelectorAll('button'));")
                print("                    const flairBtn = buttons.find(b => {")
                print("                        const text = b.textContent?.toLowerCase() || '';")
                print("                        return text.includes('flair') || text.includes('标记') || text.includes('add');")
                print("                    });")
                print("                    if (flairBtn) {")
                print("                        flairBtn.click();")
                print("                        return true;")
                print("                    }")
                print("                }")
                print("                return false;")
                print("            }")
                print("        ''')")
                print("        return result")
            
            print("```")
        
        print("\n⏳ 10 秒后关闭浏览器...")
        page.wait_for_timeout(10000)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 诊断失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 截图
        error_screenshot = Path("screenshots/diagnosis_error.png")
        error_screenshot.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(error_screenshot), full_page=True)
        print(f"📸 错误截图: {error_screenshot}")
        
        return False
        
    finally:
        print("\n🧹 清理资源...")
        page.close()
        context.close()
        playwright.stop()
        print("✅ 完成")


if __name__ == "__main__":
    success = diagnose_flair_button()
    sys.exit(0 if success else 1)

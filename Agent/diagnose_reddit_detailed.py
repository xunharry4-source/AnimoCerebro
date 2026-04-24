#!/usr/bin/env python3
"""
Reddit 提交页面深度诊断脚本

保存关键状态的HTML源码和截图，用于分析正确的选择器
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def diagnose_reddit_submit():
    """深度诊断 Reddit 提交页面"""
    print("\n" + "="*80)
    print("🔍 Reddit 提交页面深度诊断")
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
        
        # 截图 1: 初始页面
        screenshot_path = Path("screenshots/diag_01_initial_page.png")
        screenshot_path.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"   📸 截图 1 已保存: {screenshot_path}")
        
        # 保存 HTML 1: 初始页面
        html_path = Path("screenshots/diag_01_initial_page.html")
        html_content = page.content()
        html_path.write_text(html_content, encoding='utf-8')
        print(f"   📄 HTML 1 已保存: {html_path} ({len(html_content)} 字节)")
        
        print("\n2️⃣  填写标题...")
        title_input = page.locator('textarea[name="title"]').first
        if title_input.count() > 0:
            title_input.fill("Diagnosis Test Title")
            print("   ✓ 标题已填写")
            time.sleep(2)
        
        print("\n3️⃣  填写内容...")
        # 点击内容区域
        composer = page.locator('shreddit-composer').first
        if composer.count() > 0:
            composer.click()
            time.sleep(1)
            page.keyboard.type("This is a diagnosis test content.")
            print("   ✓ 内容已填写")
            time.sleep(2)
        
        # 截图 2: 填写后
        screenshot_path = Path("screenshots/diag_02_after_filling.png")
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"   📸 截图 2 已保存: {screenshot_path}")
        
        print("\n4️⃣  打开 Flair 对话框...")
        flair_button = page.locator('button:has-text("标记"), button:has-text("Flair")').first
        if flair_button.count() > 0:
            flair_button.click()
            time.sleep(3)
            print("   ✓ Flair 对话框已打开")
            
            # 截图 3: Flair 对话框打开
            screenshot_path = Path("screenshots/diag_03_flair_dialog_open.png")
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"   📸 截图 3 已保存: {screenshot_path}")
            
            # 保存 HTML 2: Flair 对话框打开时
            html_path = Path("screenshots/diag_03_flair_dialog_open.html")
            html_content = page.content()
            html_path.write_text(html_content, encoding='utf-8')
            print(f"   📄 HTML 2 已保存: {html_path} ({len(html_content)} 字节)")
            
            # 获取 Flair 对话框的 HTML
            try:
                dialog_html = page.evaluate("""
                    () => {
                        const dialog = document.querySelector('[role="dialog"], [class*="modal"], [class*="popover"]');
                        return dialog ? dialog.outerHTML : 'No dialog found';
                    }
                """)
                dialog_html_path = Path("screenshots/diag_03_flair_dialog_only.html")
                dialog_html_path.write_text(dialog_html, encoding='utf-8')
                print(f"   📄 Flair 对话框 HTML 已保存: {dialog_html_path}")
            except Exception as e:
                print(f"   ⚠️  无法提取对话框 HTML: {e}")
            
            # 列出所有 Flair 选项
            try:
                flair_options = page.evaluate("""
                    () => {
                        const dialog = document.querySelector('[role="dialog"], [class*="modal"]');
                        if (!dialog) return [];
                        
                        const buttons = Array.from(dialog.querySelectorAll('button, [role="option"]'));
                        return buttons.map(btn => ({
                            text: btn.textContent?.trim(),
                            aria: btn.getAttribute('aria-label'),
                            class: btn.className
                        }));
                    }
                """)
                
                print(f"\n   🔍 找到 {len(flair_options)} 个 Flair 选项:")
                for i, opt in enumerate(flair_options[:20]):
                    print(f"      {i+1}. 文本: {opt['text'][:50] if opt['text'] else 'N/A'}")
                    if opt['aria']:
                        print(f"          Aria: {opt['aria'][:50]}")
                    if opt['class']:
                        print(f"          Class: {opt['class'][:50]}")
            except Exception as e:
                print(f"   ⚠️  无法获取 Flair 选项: {e}")
            
            # 关闭 Flair 对话框
            print("\n   🔄 关闭 Flair 对话框...")
            page.keyboard.press('Escape')
            time.sleep(2)
        else:
            print("   ❌ 未找到 Flair 按钮")
        
        print("\n5️⃣  滚动到页面底部...")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        
        # 截图 4: 滚动到底部
        screenshot_path = Path("screenshots/diag_04_scrolled_to_bottom.png")
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"   📸 截图 4 已保存: {screenshot_path}")
        
        # 保存 HTML 3: 滚动到底部
        html_path = Path("screenshots/diag_04_scrolled_to_bottom.html")
        html_content = page.content()
        html_path.write_text(html_content, encoding='utf-8')
        print(f"   📄 HTML 3 已保存: {html_path} ({len(html_content)} 字节)")
        
        print("\n6️⃣  查找 Post/Submit 按钮...")
        
        # 方法 1: 查找所有按钮
        all_buttons = page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                return buttons.map((btn, index) => ({
                    index: index,
                    text: btn.textContent?.trim(),
                    aria: btn.getAttribute('aria-label'),
                    type: btn.getAttribute('type'),
                    class: btn.className,
                    id: btn.id,
                    visible: btn.getBoundingClientRect().width > 0 && btn.getBoundingClientRect().height > 0
                })).filter(b => b.visible);
            }
        """)
        
        print(f"\n   🔍 页面上共有 {len(all_buttons)} 个可见按钮:")
        post_buttons = []
        for btn in all_buttons:
            text_lower = (btn['text'] or '').lower()
            aria_lower = (btn['aria'] or '').lower()
            
            # 查找包含 Post, Submit, 发布 的按钮
            if any(keyword in text_lower or keyword in aria_lower 
                   for keyword in ['post', 'submit', '发布', '提交']):
                post_buttons.append(btn)
                print(f"\n   ✅ 找到可能的 Post 按钮 #{btn['index']}:")
                print(f"      文本: {btn['text'][:100] if btn['text'] else 'N/A'}")
                print(f"      Aria: {btn['aria'][:100] if btn['aria'] else 'N/A'}")
                print(f"      Type: {btn['type']}")
                print(f"      Class: {btn['class'][:100] if btn['class'] else 'N/A'}")
                print(f"      ID: {btn['id']}")
        
        if not post_buttons:
            print("\n   ❌ 未找到包含 Post/Submit 的按钮")
            print("\n   显示前 20 个按钮供参考:")
            for btn in all_buttons[:20]:
                print(f"      #{btn['index']}: text={btn['text'][:50] if btn['text'] else 'N/A'}, aria={btn['aria'][:50] if btn['aria'] else 'N/A'}")
        
        # 保存按钮列表
        buttons_json_path = Path("screenshots/diag_05_all_buttons.json")
        import json
        buttons_json_path.write_text(json.dumps(all_buttons, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"\n   📄 所有按钮信息已保存: {buttons_json_path}")
        
        # 截图 5: 最终状态
        screenshot_path = Path("screenshots/diag_05_final_state.png")
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"   📸 截图 5 已保存: {screenshot_path}")
        
        print("\n✅ 诊断完成！")
        print("\n📁 生成的文件:")
        print("   - screenshots/diag_01_initial_page.png/html")
        print("   - screenshots/diag_02_after_filling.png")
        print("   - screenshots/diag_03_flair_dialog_open.png/html")
        print("   - screenshots/diag_03_flair_dialog_only.html")
        print("   - screenshots/diag_04_scrolled_to_bottom.png/html")
        print("   - screenshots/diag_05_all_buttons.json")
        print("   - screenshots/diag_05_final_state.png")
        
        print("\n💡 下一步:")
        print("   1. 查看截图了解页面结构")
        print("   2. 分析 HTML 文件找出正确的选择器")
        print("   3. 查看 diag_05_all_buttons.json 找到 Post 按钮")
        print("   4. 根据实际结构调整代码")
        
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
    success = diagnose_reddit_submit()
    sys.exit(0 if success else 1)

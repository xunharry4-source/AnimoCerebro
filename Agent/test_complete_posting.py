#!/usr/bin/env python3
"""
完整的 Reddit 自动发帖测试 - 严格按照流程执行
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from Agent.reddit_visual_recognizer import RedditVisualRecognizer
from Agent.browser_automation.test_auto_stealth_wait import get_chrome_path, STEALTH_JS


def test_complete_posting():
    """完整的发帖流程测试"""
    
    print("\n" + "="*80)
    print("🚀 Reddit 完整自动发帖测试")
    print("="*80)
    
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
        ],
    )
    
    context.add_init_script(STEALTH_JS)
    page = context.pages[0]
    
    try:
        # 初始化识别器
        print("\n🤖 初始化视觉识别器...")
        recognizer = RedditVisualRecognizer(page)
        
        # Step 1: 访问发帖页面
        print("\n📝 Step 1: 访问发帖页面...")
        page.goto("https://www.reddit.com/r/AnimoCerebro/submit", 
                 wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        
        # Step 2: 填写标题
        print("\n📝 Step 2: 填写标题...")
        title_input = page.locator('textarea[name="title"]').first
        if title_input.count() > 0:
            title_input.fill("Tesseract OCR 视觉识别测试")
            print("   ✅ 标题已填写")
        else:
            print("   ❌ 未找到标题输入框")
            return
        
        # Step 3: 填写内容
        print("\n📝 Step 3: 填写内容...")
        composer = page.locator('shreddit-composer').first
        if composer.count() > 0:
            composer.click()
            page.wait_for_timeout(1000)
            page.keyboard.type("这是一个使用 Tesseract OCR 进行视觉识别和自动发帖的测试。", delay=30)
            print("   ✅ 内容已填写")
        else:
            print("   ❌ 未找到内容编辑器")
            return
        
        # Step 4: 选择 Flair
        print("\n🏷️  Step 4: 选择 Flair...")
        flair_success = recognizer.recognize_and_select_flair(
            target_flair="不适合工作场合",
            max_attempts=1
        )
        
        if flair_success:
            print("   ✅ Flair 选择成功")
        else:
            print("   ⚠️  Flair 选择失败，继续...")
        
        # Step 5: 截图分析页面上的所有按钮
        print("\n🔍 Step 5: 分析页面上的按钮...")
        screenshot_path = "screenshots/analyze_buttons.png"
        page.screenshot(path=screenshot_path, full_page=False)
        
        ocr_results = recognizer.ocr_helper.recognize_with_position(screenshot_path, lang='chi_sim+eng')
        
        # 组合字符
        grouped = recognizer._group_nearby_texts(ocr_results)
        
        print(f"\n   识别到 {len(grouped)} 个文本行:")
        button_keywords = ['post', '发布', 'submit', '提交', '发表', 'create', '创建']
        
        potential_buttons = []
        for item in grouped:
            text_lower = item['text'].lower()
            for keyword in button_keywords:
                if keyword.lower() in text_lower and item['confidence'] > 50:
                    potential_buttons.append(item)
                    print(f"   🎯 候选按钮: \"{item['text']}\" (置信度: {item['confidence']:.1f}%, x={item['center_x']:.0f}, y={item['center_y']:.0f})")
                    break
        
        if not potential_buttons:
            print("   ❌ 未找到任何发布相关的按钮")
            print("\n   显示所有识别到的文本:")
            for i, item in enumerate(grouped[:20]):
                print(f"      [{i}] \"{item['text']}\"")
            return
        
        # Step 6: 点击最可能的发布按钮
        print("\n🖱️  Step 6: 点击发布按钮...")
        
        # 优先选择不包含"创建"的按钮（因为"创建帖子"可能只是草稿）
        real_post_button = None
        for btn in potential_buttons:
            if '创建' not in btn['text']:
                real_post_button = btn
                break
        
        # 如果没有其他选择，就用第一个
        if not real_post_button:
            real_post_button = potential_buttons[0]
        
        print(f"   选择按钮: \"{real_post_button['text']}\"")
        print(f"   点击坐标: ({real_post_button['center_x']:.0f}, {real_post_button['center_y']:.0f})")
        
        # 记录发帖前的 URL
        url_before = page.url
        print(f"   发帖前 URL: {url_before}")
        
        # 🔧 关键修复：尝试多种点击方式
        print("\n   尝试方式 1: Playwright locator click...")
        clicked = False
        
        # 尝试通过文本查找并点击
        try:
            button_text = real_post_button['text'].strip()
            button_locator = page.get_by_text(button_text).first
            if button_locator.count() > 0:
                print(f"   找到按钮元素，尝试点击...")
                button_locator.click(timeout=5000)
                clicked = True
                print("   ✅ Locator 点击成功")
        except Exception as e:
            print(f"   ⚠️  Locator 点击失败: {e}")
        
        if not clicked:
            print("\n   尝试方式 2: 坐标点击...")
            page.mouse.click(real_post_button['center_x'], real_post_button['center_y'])
            print("   ✅ 坐标点击完成")
        
        # Step 7: 等待并验证
        print("\n⏳ Step 7: 等待发帖完成...")
        
        try:
            # 等待网络空闲或页面跳转
            page.wait_for_load_state('networkidle', timeout=15000)
        except Exception as e:
            print(f"   ⚠️  等待超时: {e}")
        
        page.wait_for_timeout(3000)
        
        url_after = page.url
        print(f"   发帖后 URL: {url_after}")
        
        # 截图
        screenshot_after = "screenshots/post_result.png"
        page.screenshot(path=screenshot_after, full_page=True)
        print(f"   📸 结果截图: {screenshot_after}")
        
        # 验证
        if url_after != url_before:
            print("\n✅✅✅ 发帖成功！URL 已变化")
            print(f"   新 URL: {url_after}")
        else:
            print("\n❌ 发帖失败：URL 未变化")
            
            # 检查是否有错误提示
            error_check = page.evaluate("""
                () => {
                    const content = document.body.textContent || '';
                    const errors = [];
                    if (content.includes('error') || content.includes('错误')) errors.push('发现错误提示');
                    if (content.includes('required') || content.includes('必填')) errors.push('有必填项未完成');
                    if (content.includes('karma') || content.includes('限制')) errors.push('可能有 karma 限制');
                    return errors;
                }
            """)
            
            if error_check:
                print(f"   检测到问题: {error_check}")
            else:
                print("   未检测到明显错误，可能是其他原因")
        
        print("\n" + "="*80)
        print("测试完成")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🧹 清理资源...")
        context.close()
        playwright.stop()
        print("✅ 完成")


if __name__ == "__main__":
    test_complete_posting()

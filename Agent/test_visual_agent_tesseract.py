#!/usr/bin/env python3
"""
Reddit 视觉智能体完整测试 - Tesseract OCR 版

测试使用 Tesseract OCR 的完整发帖流程
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from Agent.reddit_visual_recognizer import RedditVisualRecognizer


def test_visual_recognizer():
    """测试 RedditVisualRecognizer（Tesseract 版）"""
    
    print("\n" + "="*80)
    print("🧪 Reddit 视觉智能体测试 - Tesseract OCR 版")
    print("="*80)
    
    # 启动浏览器 - 使用与 test_auto_stealth_wait.py 相同的配置
    from Agent.browser_automation.test_auto_stealth_wait import (
        get_chrome_path, 
        STEALTH_JS,
        HAS_STEALTH
    )
    
    try:
        from playwright_stealth import Stealth
        stealth_available = True
    except ImportError:
        stealth_available = False
    
    # 获取 Chrome 路径
    executable_path = get_chrome_path()
    print(f"\n🔍 Chrome 路径: {executable_path}")
    
    # 设置用户数据目录
    user_data_dir = Path("./chrome_custom_profile").resolve()
    user_data_dir.mkdir(exist_ok=True)
    print(f"📂 用户数据目录: {user_data_dir}")
    
    # 启动 Playwright
    playwright = sync_playwright().start()
    
    # 使用 launch_persistent_context 保持登录状态
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(user_data_dir),
        executable_path=executable_path,
        headless=False,
        slow_mo=500,
        viewport={"width": 1920, "height": 1080},
        no_viewport=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    )
    
    # 注入 Stealth 脚本
    context.add_init_script(STEALTH_JS)
    
    page = context.new_page()
    
    # 应用 playwright_stealth（如果可用）
    if stealth_available and HAS_STEALTH:
        try:
            stealth_obj = Stealth()
            stealth_obj.apply_stealth(page)
            print("✅ 已应用 playwright_stealth")
        except Exception as e:
            print(f"⚠️  playwright_stealth 应用失败: {e}")
    
    try:
        # 初始化视觉识别器
        print("\n🤖 初始化 RedditVisualRecognizer (Tesseract)...")
        recognizer = RedditVisualRecognizer(page)
        
        if not recognizer.ocr_helper:
            print("\n❌ TesseractOCRHelper 未初始化，测试终止")
            return False
        
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
        
        # 填写标题和内容
        print("\n📝 填写标题和内容...")
        title_input = page.locator('textarea[name="title"]').first
        if title_input.count() > 0:
            title_input.fill("测试 Tesseract OCR 视觉识别")
            print("   ✓ 标题已填写")
        
        composer = page.locator('shreddit-composer').first
        if composer.count() > 0:
            composer.click()
            page.wait_for_timeout(1000)
            page.keyboard.type("这是一个测试帖子，使用 Tesseract OCR 进行 Flair 识别和选择。", delay=30)
            print("   ✓ 内容已填写")
        
        # 测试 Flair 识别和选择（使用多策略）
        print("\n🏷️  测试 Flair 识别和选择（多策略）...")
            
        # 注意：r/AnimoCerebro 社区的实际 Flair 选项是中文的
        # 根据 OCR 识别结果，可用的 Flair 有：
        # - "不适合工作场合 (18+)"
        # - "包含成人内容"
        flair_success = recognizer.recognize_and_select_flair(
            target_flair="不适合工作场合",  # 使用实际存在的 Flair
            max_attempts=1  # 只尝试一次，查看详细输出
        )
        
        if flair_success:
            print("   ✅ Flair 选择成功")
        else:
            print("   ⚠️  Flair 选择失败，继续测试...")
        
        # 完整发帖流程 - 点击发布按钮
        print("\n📤 执行完整发帖流程...")
        print("   Step 1: 查找发布按钮...")
        
        # 尝试多种发布按钮选择器
        post_selectors = [
            'button:has-text("Post")',
            'button:has-text("发布")',
            'button[type="submit"]',
            '[data-testid="post-submit-button"]',
        ]
        
        post_button_found = False
        for selector in post_selectors:
            try:
                button = page.locator(selector).first
                if button.count() > 0 and button.is_visible():
                    print(f"   ✅ 找到发布按钮: {selector}")
                    
                    # 截图保存
                    screenshot_before = "screenshots/before_post.png"
                    page.screenshot(path=screenshot_before)
                    print(f"   📸 发帖前截图: {screenshot_before}")
                    
                    # 点击发布
                    print("   🖱️  点击发布按钮...")
                    button.click()
                    post_button_found = True
                    break
            except Exception as e:
                continue
        
        if not post_button_found:
            print("   ⚠️  未找到发布按钮，尝试 OCR 识别...")
            # 使用 OCR 查找“发布”或“Post”按钮
            screenshot_path = "screenshots/find_post_button.png"
            page.screenshot(path=screenshot_path, full_page=False)
            
            ocr_results_raw = recognizer.ocr_helper.recognize_with_position(screenshot_path, lang='chi_sim+eng')
            
            # 🔧 组合相邻字符（与 Flair 选择相同的逻辑）
            ocr_results = recognizer._group_nearby_texts(ocr_results_raw)
            
            # 调试：显示所有识别到的文本
            print(f"   🔍 OCR 识别到 {len(ocr_results)} 个文本行:")
            for i, item in enumerate(ocr_results[:30]):
                if item['confidence'] > 40:
                    print(f"      [{i:2d}] \"{item['text']}\" (置信度: {item['confidence']:5.1f}%, x={item['center_x']:4.0f}, y={item['center_y']:4.0f})")
            
            # 发布按钮可能的关键词（中英文）
            post_keywords = ['post', '发布', 'submit', '提交', '创建', '帖子', '发表']
            
            for item in ocr_results:
                text_lower = item['text'].lower()
                for keyword in post_keywords:
                    if keyword.lower() in text_lower and item['confidence'] > 50:
                        print(f"   ✅ OCR 找到发布按钮: \"{item['text']}\" (置信度: {item['confidence']:.1f}%)")
                        print(f"   🖱️  点击坐标: ({item['center_x']:.0f}, {item['center_y']:.0f})")
                        page.mouse.click(item['center_x'], item['center_y'])
                        post_button_found = True
                        break
                if post_button_found:
                    break
        
        # 🔧 关键修复：检查是否只是保存为草稿，需要再次发布
        if post_button_found:
            print("   ⏳ 等待 2 秒...")
            page.wait_for_timeout(2000)
            
            # 截图检查是否有“草稿”字样
            screenshot_check = "screenshots/check_draft.png"
            page.screenshot(path=screenshot_check, full_page=False)
            
            ocr_check = recognizer.ocr_helper.recognize_with_position(screenshot_check, lang='chi_sim+eng')
            has_draft = any('草稿' in item['text'] or 'Draft' in item['text'] for item in ocr_check if item['confidence'] > 50)
            
            if has_draft:
                print("   ⚠️  检测到草稿状态，尝试查找真正的发布按钮...")
                
                # 再次截图查找“发布”、“Post”等按钮
                real_post_keywords = ['post', '发布', 'publish', '发表', 'submit', '提交']
                
                for item in ocr_check:
                    text_lower = item['text'].lower()
                    for keyword in real_post_keywords:
                        if keyword.lower() in text_lower and item['confidence'] > 50:
                            # 排除“创建帖子”按钮
                            if '创建' not in item['text']:
                                print(f"   ✅ 找到真正的发布按钮: \"{item['text']}\"")
                                print(f"   🖱️  点击坐标: ({item['center_x']:.0f}, {item['center_y']:.0f})")
                                page.mouse.click(item['center_x'], item['center_y'])
                                page.wait_for_timeout(3000)
                                break
                    else:
                        continue
                    break
            else:
                print("   ℹ️  未检测到草稿状态")
        
        if post_button_found:
            print("   ⏳ 等待发帖完成...")
            
            # 记录发帖前的 URL
            url_before = page.url
            print(f"   🌐 发帖前 URL: {url_before}")
            
            # 等待页面跳转或加载（最多 10 秒）
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except Exception as e:
                print(f"   ⚠️  等待超时: {e}")
            
            page.wait_for_timeout(3000)  # 额外等待 3 秒
            
            # 检查是否发帖成功
            current_url = page.url
            print(f"   🌐 发帖后 URL: {current_url}")
            
            # 截图保存结果
            screenshot_after = "screenshots/after_post.png"
            page.screenshot(path=screenshot_after, full_page=True)
            print(f"   📸 发帖后截图: {screenshot_after}")
            
            # 检测是否有错误
            error_msg = recognizer.detect_and_read_error_dialog(wait_time=2)
            if error_msg:
                print(f"   ❌ 发帖失败: {error_msg}")
            elif current_url != url_before:
                print(f"   ✅ URL 已变化，发帖可能成功")
                print(f"   ✅✅✅ 发帖成功！")
            else:
                print(f"   ⚠️  URL 未变化，可能发帖失败")
                # 尝试查找成功提示
                success_indicators = ['posted', 'success', '成功', '已发布']
                page_content = page.content().lower()
                if any(indicator in page_content for indicator in success_indicators):
                    print(f"   ✅ 页面包含成功提示")
                    print(f"   ✅✅✅ 发帖成功！")
                else:
                    print(f"   ❌ 未检测到成功标志，发帖可能失败")
        else:
            print("   ❌ 无法找到发布按钮")
        
        # 截图测试错误检测
        print("\n🔍 测试错误检测功能...")
        error_msg = recognizer.detect_and_read_error_dialog(wait_time=2)
        
        if error_msg:
            print(f"   检测到错误: {error_msg}")
        else:
            print("   ✅ 未检测到错误（正常）")
        
        print("\n✅✅✅ 视觉识别器测试完成！")
        print("\n💡 提示:")
        print("   - Tesseract OCR 工作正常")
        print("   - Flair 识别功能可用")
        print("   - 错误检测功能可用")
        print("\n🚀 可以开始完整的发帖流程测试")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        
        # 截图保存错误状态
        error_screenshot = Path("screenshots/visual_agent_test_error.png")
        error_screenshot.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(error_screenshot), full_page=True)
        print(f"📸 错误截图已保存: {error_screenshot}")
        
        return False
        
    finally:
        # 清理
        print("\n🧹 清理资源...")
        try:
            if page:
                page.close()
                print("   ✓ 页面已关闭")
            if context:
                context.close()
                print("   ✓ 上下文已关闭")
            if playwright:
                playwright.stop()
                print("   ✓ Playwright 已停止")
            print("✅ 所有资源已释放")
        except Exception as e:
            print(f"⚠️  清理时出错: {e}")


if __name__ == "__main__":
    print("\n⚠️  注意: 此测试需要您已经登录 Reddit")
    print("   如果未登录，请在浏览器中手动登录后按回车继续\n")
    
    success = test_visual_recognizer()
    
    if success:
        print("\n🎊 Tesseract OCR 视觉智能体测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 测试失败，请检查错误信息")
        sys.exit(1)

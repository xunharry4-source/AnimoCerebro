#!/usr/bin/env python3
"""
Reddit 视觉智能体完整测试

演示从获取规则到发帖成功的完整流程
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from Agent.reddit_visual_agent import RedditVisualAgent


def test_reddit_visual_agent():
    """测试 Reddit 视觉智能体"""
    
    print("\n" + "="*80)
    print("🧪 Reddit 视觉智能体测试")
    print("="*80)
    
    # 启动浏览器
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=False,  # 显示浏览器以便观察
        args=['--start-maximized']
    )
    
    context = browser.new_context(
        viewport={'width': 1280, 'height': 800}
    )
    page = context.new_page()
    
    try:
        # 初始化视觉智能体
        print("\n🤖 初始化视觉智能体...")
        agent = RedditVisualAgent(
            page=page,
            window_size=(1280, 800)
        )
        
        # 执行发帖任务
        result = agent.execute_posting_task(
            subreddit="AnimoCerebro",
            title="测试 PaddleOCR 视觉识别功能",
            content="""
这是一个测试帖子，用于验证 PaddleOCR + Airtest 视觉识别方案。

主要测试点：
1. Flair 的视觉识别和选择
2. Post 按钮的精准点击
3. 错误提示的检测和分析
4. 自动修正和重试机制

这个方案的优势是不依赖 DOM 结构，只要文字在屏幕上就能识别和点击。
            """,
            target_flair="Discussion",  # 根据实际社区调整
            max_retries=3
        )
        
        # 输出结果
        print("\n" + "="*80)
        print("📊 测试结果")
        print("="*80)
        
        if result['success']:
            print("\n✅✅✅ 测试成功！")
            print(f"\n🎉 帖子 URL: {result['final_status'].get('post_url', 'N/A')}")
            print(f"📈 尝试次数: {len(result['attempts'])}")
        else:
            print("\n❌ 测试失败")
            print(f"\n📝 失败原因: {result['final_status'].get('message', '未知')}")
            print(f"\n📊 尝试详情:")
            for attempt in result['attempts']:
                print(f"   尝试 {attempt['attempt']}: {attempt.get('steps', {})}")
        
        # 保存详细报告
        import json
        report_path = Path("screenshots/reddit_test_report.json")
        report_path.parent.mkdir(exist_ok=True)
        
        # 清理不可序列化的对象
        serializable_result = {
            'success': result['success'],
            'final_status': result['final_status'],
            'attempts_count': len(result['attempts']),
            'attempts_summary': [
                {
                    'attempt': a['attempt'],
                    'steps': {k: str(v) for k, v in a.get('steps', {}).items()}
                }
                for a in result['attempts']
            ]
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_result, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 测试报告已保存: {report_path}")
        
        return result['success']
        
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        
        # 截图保存错误状态
        error_screenshot = Path("screenshots/test_error.png")
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


def test_ocr_only():
    """单独测试 OCR 功能"""
    
    print("\n" + "="*80)
    print("🧪 单独测试 PaddleOCR 功能")
    print("="*80)
    
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=False)
    page = browser.new_page()
    
    try:
        # 访问 Reddit
        print("\n🌐 访问 Reddit...")
        page.goto("https://www.reddit.com/r/AnimoCerebro/submit", wait_until="domcontentloaded")
        time.sleep(3)
        
        # 初始化 OCR
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
        
        # 截图
        screenshot_path = "screenshots/ocr_test.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"📸 截图已保存: {screenshot_path}")
        
        # OCR 识别
        print("\n🔍 开始 OCR 识别...")
        result = ocr.ocr(screenshot_path, cls=True)
        
        if result and result[0]:
            print(f"\n✅ 识别到 {len(result[0])} 个文本块\n")
            
            # 打印前10个结果
            for i, line in enumerate(result[0][:10]):
                text = line[1][0]
                confidence = line[1][1]
                box = line[0]
                
                print(f"{i+1}. \"{text}\"")
                print(f"   置信度: {confidence:.2f}")
                print(f"   位置: ({box[0][0]:.0f}, {box[0][1]:.0f})")
                print()
        else:
            print("\n⚠️  未识别到文字")
        
        return True
        
    except Exception as e:
        print(f"\n❌ OCR 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        browser.close()
        playwright.stop()


if __name__ == "__main__":
    import time
    
    print("\n选择测试模式:")
    print("1. 完整流程测试（需要登录）")
    print("2. 仅测试 OCR 功能")
    
    choice = input("\n请输入选择 (1/2): ").strip()
    
    if choice == "1":
        success = test_reddit_visual_agent()
        sys.exit(0 if success else 1)
    elif choice == "2":
        success = test_ocr_only()
        sys.exit(0 if success else 1)
    else:
        print("无效选择")
        sys.exit(1)

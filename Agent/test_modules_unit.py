#!/usr/bin/env python3
"""
Reddit 模块单元测试 - 验证代码结构和导入

不依赖浏览器，只测试代码逻辑
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """测试所有模块能否正常导入"""
    
    print("\n" + "="*80)
    print("🧪 Reddit 模块导入测试")
    print("="*80)
    
    tests_passed = 0
    tests_failed = 0
    
    # 测试 1: RedditAdvancedHelper
    print("\n📦 测试 1: RedditAdvancedHelper")
    try:
        from Agent.reddit_advanced_helper import RedditAdvancedHelper
        print("   ✅ 导入成功")
        
        # 检查关键方法是否存在
        methods = [
            'force_click_shadow_element',
            'poll_post_button_state',
            'try_submit_post',
            'complete_posting_workflow',
            'detect_post_submission_result',
            'handle_submission_error'
        ]
        
        for method in methods:
            if hasattr(RedditAdvancedHelper, method):
                print(f"   ✅ 方法存在: {method}")
                tests_passed += 1
            else:
                print(f"   ❌ 方法缺失: {method}")
                tests_failed += 1
        
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        tests_failed += 1
    
    # 测试 2: RedditErrorHandler
    print("\n📦 测试 2: RedditErrorHandler")
    try:
        from Agent.reddit_error_handler import RedditSubmissionErrorHandler
        print("   ✅ 导入成功")
        
        methods = [
            'detect_and_handle_error',
            '_analyze_page_html',
            '_analyze_screenshot_ocr',
            '_generate_correction'
        ]
        
        for method in methods:
            if hasattr(RedditSubmissionErrorHandler, method):
                print(f"   ✅ 方法存在: {method}")
                tests_passed += 1
            else:
                print(f"   ❌ 方法缺失: {method}")
                tests_failed += 1
        
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        tests_failed += 1
    
    # 测试 3: RedditVisualRecognizer（可选，依赖 PaddleOCR）
    print("\n📦 测试 3: RedditVisualRecognizer")
    try:
        from Agent.reddit_visual_recognizer import RedditVisualRecognizer
        print("   ✅ 导入成功")
        
        # 检查是否安装了 PaddleOCR
        try:
            import paddleocr
            print("   ✅ PaddleOCR 已安装")
            tests_passed += 1
        except ImportError:
            print("   ⚠️  PaddleOCR 未安装（可选）")
            print("   💡 安装命令: pip install paddlepaddle paddleocr")
        
        methods = [
            'recognize_and_select_flair',
            'detect_and_read_error_dialog',
            'handle_error_and_retry'
        ]
        
        for method in methods:
            if hasattr(RedditVisualRecognizer, method):
                print(f"   ✅ 方法存在: {method}")
                tests_passed += 1
            else:
                print(f"   ❌ 方法缺失: {method}")
                tests_failed += 1
        
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        tests_failed += 1
    
    # 测试 4: RedditVisualAgent
    print("\n📦 测试 4: RedditVisualAgent")
    try:
        from Agent.reddit_visual_agent import RedditVisualAgent
        print("   ✅ 导入成功")
        
        methods = [
            'execute_posting_task',
            '_get_community_rules',
            '_fill_content',
            '_visual_select_flair',
            '_scroll_and_click_post',
            '_analyze_submission_result',
            '_correct_based_on_error'
        ]
        
        for method in methods:
            if hasattr(RedditVisualAgent, method):
                print(f"   ✅ 方法存在: {method}")
                tests_passed += 1
            else:
                print(f"   ❌ 方法缺失: {method}")
                tests_failed += 1
        
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        tests_failed += 1
    
    # 测试结果汇总
    print("\n" + "="*80)
    print("📊 测试结果汇总")
    print("="*80)
    print(f"\n✅ 通过: {tests_passed}")
    print(f"❌ 失败: {tests_failed}")
    print(f"📈 通过率: {tests_passed / (tests_passed + tests_failed) * 100:.1f}%")
    
    if tests_failed == 0:
        print("\n🎊 所有测试通过！")
        return True
    else:
        print(f"\n⚠️  有 {tests_failed} 个测试失败")
        return False


def test_code_structure():
    """测试代码结构完整性"""
    
    print("\n" + "="*80)
    print("🔍 代码结构检查")
    print("="*80)
    
    required_files = [
        'Agent/reddit_visual_agent.py',
        'Agent/reddit_visual_recognizer.py',
        'Agent/reddit_advanced_helper.py',
        'Agent/reddit_error_handler.py',
        'Agent/test_reddit_quick.py',
        'Agent/README_REDDIT_VISUAL_AGENT.md',
        'Agent/REDDIT_VISUAL_AGENT_COMPLETE_SUMMARY.md',
        'Agent/PADDLEOCR_AIRTEST_GUIDE.md',
        'Agent/CREWAI_INTEGRATION_GUIDE.md',
        'Agent/INDEX.md',
    ]
    
    missing_files = []
    
    for file_path in required_files:
        full_path = Path(__file__).parent.parent / file_path
        if full_path.exists():
            size = full_path.stat().st_size
            print(f"   ✅ {file_path} ({size:,} bytes)")
        else:
            print(f"   ❌ {file_path} 不存在")
            missing_files.append(file_path)
    
    if missing_files:
        print(f"\n⚠️  缺失 {len(missing_files)} 个文件:")
        for f in missing_files:
            print(f"   - {f}")
        return False
    else:
        print("\n✅ 所有必需文件都存在")
        return True


if __name__ == "__main__":
    print("\n🚀 开始 Reddit 模块测试\n")
    
    # 测试 1: 代码结构
    structure_ok = test_code_structure()
    
    # 测试 2: 模块导入
    imports_ok = test_imports()
    
    # 最终结果
    print("\n" + "="*80)
    print("🎯 最终结果")
    print("="*80)
    
    if structure_ok and imports_ok:
        print("\n✅✅✅ 所有测试通过！代码结构完整，模块可正常导入。")
        print("\n💡 下一步:")
        print("   1. 安装 PaddleOCR: pip install paddlepaddle paddleocr")
        print("   2. 运行完整测试: python Agent/test_reddit_quick.py")
        print("   3. 查看文档: cat Agent/README_REDDIT_VISUAL_AGENT.md")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败，请检查上述错误信息")
        sys.exit(1)

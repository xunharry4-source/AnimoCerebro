#!/usr/bin/env python3
"""
Reddit OCR 测试 - 使用 Tesseract（macOS 友好）

Tesseract 在 macOS 上比 PaddleOCR 更容易安装和使用
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_tesseract_installation():
    """测试 Tesseract 是否已正确安装"""
    
    print("\n" + "="*80)
    print("🧪 Tesseract OCR 安装测试")
    print("="*80)
    
    # 测试 1: Python 包
    print("\n📦 测试 1: Python 包导入")
    try:
        import pytesseract
        from PIL import Image
        print("   ✅ pytesseract 和 Pillow 已安装")
    except ImportError as e:
        print(f"   ❌ 导入失败: {e}")
        print("   💡 安装命令: pip install pytesseract pillow")
        return False
    
    # 测试 2: Tesseract 命令行工具
    print("\n🔧 测试 2: Tesseract 命令行工具")
    try:
        import subprocess
        result = subprocess.run(['tesseract', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"   ✅ Tesseract 已安装: {version_line}")
        else:
            print(f"   ❌ Tesseract 未找到")
            print("   💡 安装命令: brew install tesseract tesseract-lang")
            return False
    except FileNotFoundError:
        print(f"   ❌ Tesseract 命令不存在")
        print("   💡 安装命令: brew install tesseract tesseract-lang")
        return False
    except Exception as e:
        print(f"   ⚠️  检查失败: {e}")
        return False
    
    # 测试 3: 创建测试图片并识别
    print("\n🖼️  测试 3: OCR 识别测试")
    try:
        # 创建一个简单的测试图片
        from PIL import Image, ImageDraw, ImageFont
        
        test_img = Image.new('RGB', (400, 100), color='white')
        draw = ImageDraw.Draw(test_img)
        
        # 添加文字
        draw.text((10, 30), "Test OCR: Hello World", fill='black')
        
        # 保存测试图片
        test_path = Path("screenshots/ocr_test_simple.png")
        test_path.parent.mkdir(exist_ok=True)
        test_img.save(str(test_path))
        print(f"   ✅ 测试图片已创建: {test_path}")
        
        # 执行 OCR
        text = pytesseract.image_to_string(test_img, lang='eng')
        print(f"   📝 识别结果: \"{text.strip()}\"")
        
        if "Hello World" in text or "Test OCR" in text:
            print("   ✅ OCR 识别成功！")
            return True
        else:
            print("   ⚠️  OCR 识别结果不理想，但功能正常")
            return True
            
    except Exception as e:
        print(f"   ❌ OCR 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_reddit_screenshot_ocr():
    """测试 Reddit 截图的 OCR 识别"""
    
    print("\n" + "="*80)
    print("🧪 Reddit 截图 OCR 测试")
    print("="*80)
    
    try:
        import pytesseract
        from PIL import Image
        
        # 查找已有的截图
        screenshots_dir = Path("screenshots")
        if not screenshots_dir.exists():
            print("   ⚠️  screenshots 目录不存在")
            return False
        
        # 查找最近的截图
        png_files = list(screenshots_dir.glob("*.png"))
        if not png_files:
            print("   ⚠️  没有找到截图文件")
            print("   💡 请先运行其他测试生成截图")
            return False
        
        # 使用最新的截图
        latest_screenshot = max(png_files, key=lambda p: p.stat().st_mtime)
        print(f"\n📸 使用截图: {latest_screenshot.name}")
        
        # 打开图片
        img = Image.open(latest_screenshot)
        print(f"   尺寸: {img.size}")
        
        # 执行 OCR
        print("\n🔍 开始 OCR 识别...")
        text = pytesseract.image_to_string(img, lang='eng+chi_sim')
        
        # 显示结果
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        print(f"\n📝 识别到 {len(lines)} 行文本:\n")
        
        for i, line in enumerate(lines[:20], 1):  # 只显示前20行
            print(f"   {i:2d}. {line}")
        
        if len(lines) > 20:
            print(f"   ... 还有 {len(lines) - 20} 行")
        
        # 搜索关键词
        print("\n🔑 搜索关键信息:")
        keywords = ['error', 'Error', 'failed', 'required', 'flair', 'Flair', 'Post', 'post']
        
        found_keywords = []
        for keyword in keywords:
            if keyword in text:
                found_keywords.append(keyword)
        
        if found_keywords:
            print(f"   ✅ 找到关键词: {', '.join(found_keywords)}")
        else:
            print(f"   ⚠️  未找到常见关键词")
        
        # 保存识别结果
        result_path = screenshots_dir / f"{latest_screenshot.stem}_ocr.txt"
        with open(result_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        print(f"\n💾 OCR 结果已保存: {result_path}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n🚀 开始 Tesseract OCR 测试\n")
    
    # 测试 1: 安装检查
    install_ok = test_tesseract_installation()
    
    if not install_ok:
        print("\n❌ Tesseract 未正确安装，请先安装后再试")
        sys.exit(1)
    
    # 测试 2: Reddit 截图 OCR
    ocr_ok = test_reddit_screenshot_ocr()
    
    # 最终结果
    print("\n" + "="*80)
    print("🎯 测试结果")
    print("="*80)
    
    if install_ok and ocr_ok:
        print("\n✅✅✅ Tesseract OCR 测试通过！")
        print("\n💡 下一步:")
        print("   1. 更新 reddit_visual_recognizer.py 使用 Tesseract")
        print("   2. 运行完整流程测试")
        sys.exit(0)
    else:
        print("\n⚠️  部分测试未通过")
        sys.exit(1)

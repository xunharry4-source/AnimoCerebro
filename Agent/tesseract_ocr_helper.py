#!/usr/bin/env python3
"""
Tesseract OCR Helper - Reddit 视觉识别辅助类

使用 Tesseract OCR 进行文字识别和定位
适用于 macOS 系统
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image


class TesseractOCRHelper:
    """Tesseract OCR 助手类"""
    
    def __init__(self):
        """初始化 Tesseract OCR Helper"""
        try:
            import pytesseract
            self.pytesseract = pytesseract
            print("   ✅ Tesseract OCR Helper 初始化成功")
        except ImportError:
            raise ImportError("pytesseract 未安装，请运行: pip install pytesseract pillow")
    
    def recognize_text(self, image_path: str, lang: str = 'eng') -> str:
        """
        识别图片中的文字
        
        Args:
            image_path: 图片路径
            lang: 语言代码 ('eng', 'chi_sim', 'eng+chi_sim')
        
        Returns:
            str: 识别的文字
        """
        try:
            img = Image.open(image_path)
            text = self.pytesseract.image_to_string(img, lang=lang)
            return text.strip()
        except Exception as e:
            print(f"   ❌ OCR 识别失败: {e}")
            return ""
    
    def recognize_with_position(self, image_path: str, lang: str = 'eng') -> List[Dict]:
        """
        识别文字并返回位置信息
        
        Args:
            image_path: 图片路径
            lang: 语言代码
        
        Returns:
            List[Dict]: [
                {
                    'text': str,           # 识别的文字
                    'confidence': int,     # 置信度 (0-100)
                    'x': int,              # x 坐标
                    'y': int,              # y 坐标
                    'width': int,          # 宽度
                    'height': int,         # 高度
                    'center_x': float,     # 中心点 x
                    'center_y': float      # 中心点 y
                }
            ]
        """
        try:
            img = Image.open(image_path)
            
            # 🔧 图片预处理：提高 OCR 精度
            # 1. 转为灰度
            img = img.convert('L')
            
            # 2. 增强对比度（不要太强，否则会丢失细节）
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)  # 适度增强
            
            # 注意：不进行二值化，因为会丢失中文字符的细节
            
            # 使用 PSM 3 (Fully automatic page segmentation) - 默认模式
            custom_config = r'--oem 3 --psm 3'
            
            # 获取详细数据
            data = self.pytesseract.image_to_data(
                img, 
                lang=lang,
                config=custom_config,
                output_type=self.pytesseract.Output.DICT
            )
            
            results = []
            n_boxes = len(data['text'])
            
            for i in range(n_boxes):
                text = data['text'][i].strip()
                confidence = data['conf'][i]
                
                # 跳过空文本或低置信度
                if not text or confidence < 30:
                    continue
                
                x = data['left'][i]
                y = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]
                
                results.append({
                    'text': text,
                    'confidence': confidence,
                    'x': x,
                    'y': y,
                    'width': w,
                    'height': h,
                    'center_x': x + w / 2,
                    'center_y': y + h / 2
                })
            
            return results
            
        except Exception as e:
            print(f"   ❌ OCR 位置识别失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def find_text(self, image_path: str, keyword: str, 
                  lang: str = 'eng', confidence_threshold: int = 50) -> Optional[Dict]:
        """
        在图片中查找特定关键词
        
        Args:
            image_path: 图片路径
            keyword: 要查找的关键词
            lang: 语言代码
            confidence_threshold: 置信度阈值
        
        Returns:
            Dict: 匹配的文本信息（包含位置），如果未找到则返回 None
        """
        results = self.recognize_with_position(image_path, lang)
        
        for item in results:
            if keyword.lower() in item['text'].lower() and item['confidence'] >= confidence_threshold:
                print(f"   ✅ 找到关键词 \"{keyword}\": \"{item['text']}\" (置信度: {item['confidence']})")
                return item
        
        print(f"   ⚠️  未找到关键词 \"{keyword}\"")
        return None
    
    def preprocess_image(self, image_path: str, output_path: str = None) -> str:
        """
        预处理图片以提高 OCR 精度
        
        Args:
            image_path: 输入图片路径
            output_path: 输出图片路径（可选）
        
        Returns:
            str: 处理后的图片路径
        """
        try:
            img = Image.open(image_path)
            
            # 转为灰度
            img = img.convert('L')
            
            # 增强对比度
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)
            
            # 保存
            if output_path is None:
                output_path = image_path.replace('.png', '_processed.png')
            
            img.save(output_path)
            print(f"   ✅ 图片已预处理: {output_path}")
            
            return output_path
            
        except Exception as e:
            print(f"   ⚠️  图片预处理失败: {e}")
            return image_path


# 使用示例
if __name__ == "__main__":
    print("\n🧪 TesseractOCRHelper 测试\n")
    
    helper = TesseractOCRHelper()
    
    # 创建测试图片
    from PIL import Image, ImageDraw
    
    test_img = Image.new('RGB', (400, 100), color='white')
    draw = ImageDraw.Draw(test_img)
    draw.text((10, 30), "Test Flair: Discussion", fill='black')
    
    test_path = "screenshots/test_ocr_helper.png"
    Path("screenshots").mkdir(exist_ok=True)
    test_img.save(test_path)
    
    # 测试 1: 基础识别
    print("\n📝 测试 1: 基础文字识别")
    text = helper.recognize_text(test_path)
    print(f"   识别结果: \"{text}\"")
    
    # 测试 2: 带位置的识别
    print("\n📍 测试 2: 带位置的识别")
    results = helper.recognize_with_position(test_path)
    for item in results:
        print(f"   文字: \"{item['text']}\"")
        print(f"   位置: ({item['center_x']:.0f}, {item['center_y']:.0f})")
        print(f"   置信度: {item['confidence']}")
    
    # 测试 3: 查找关键词
    print("\n🔍 测试 3: 查找关键词")
    match = helper.find_text(test_path, "Discussion")
    if match:
        print(f"   找到位置: ({match['center_x']:.0f}, {match['center_y']:.0f})")
    
    print("\n✅ 测试完成")

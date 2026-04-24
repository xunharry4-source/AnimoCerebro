#!/usr/bin/env python3
"""
Reddit Tesseract OCR 视觉识别模块

使用 Tesseract OCR 进行文字识别（macOS 优化版）
替代 PaddleOCR，更轻量、更易安装
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class RedditVisualRecognizer:
    """Reddit 视觉识别器 - 使用 Tesseract OCR"""
    
    def __init__(self, page, screenshot_dir: str = "screenshots"):
        self.page = page
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(exist_ok=True)
        
        # 初始化 Tesseract OCR Helper
        try:
            from Agent.tesseract_ocr_helper import TesseractOCRHelper
            self.ocr_helper = TesseractOCRHelper()
            print("   ✅ TesseractOCRHelper 初始化成功")
        except Exception as e:
            print(f"   ⚠️  TesseractOCRHelper 初始化失败: {e}")
            self.ocr_helper = None
    
    def _init_paddleocr(self):
        """初始化 PaddleOCR"""
        try:
            from paddleocr import PaddleOCR
            
            print("   🔄 初始化 PaddleOCR...")
            self.ocr = PaddleOCR(
                use_angle_cls=True,
                lang='ch',  # 支持中英文
                show_log=False,
                use_gpu=False  # macOS 使用 CPU
            )
            print("   ✅ PaddleOCR 初始化成功")
            
        except ImportError:
            print("   ⚠️  PaddleOCR 未安装")
            print("   💡 安装命令: pip install paddlepaddle paddleocr")
        except Exception as e:
            print(f"   ⚠️  PaddleOCR 初始化失败: {e}")
    
    def _init_airtest(self):
        """初始化 Airtest"""
        try:
            from airtest.core.api import connect_device, snapshot
            
            # 连接到当前浏览器窗口（需要通过 CDP）
            # 注意：Airtest 主要用于移动端，这里我们主要用其图像匹配功能
            self.airtest_initialized = True
            print("   ✅ Airtest 模块可用")
            
        except ImportError:
            print("   ⚠️  Airtest 未安装")
            print("   💡 安装命令: pip install airtest")
        except Exception as e:
            print(f"   ⚠️  Airtest 初始化失败: {e}")
    
    # ==================== PaddleOCR 文字识别 ====================
    
    def recognize_text_from_screenshot(self, screenshot_path: str = None, 
                                      region: Tuple[int, int, int, int] = None) -> List[Dict]:
        """
        使用 PaddleOCR 识别截图中的文字
        
        Args:
            screenshot_path: 截图路径，如果为 None 则自动截图
            region: 识别区域 (x, y, width, height)，如果为 None 则识别全屏
        
        Returns:
            List[Dict]: [
                {
                    'text': str,           # 识别的文字
                    'confidence': float,   # 置信度
                    'box': [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]  # 文字位置
                }
            ]
        """
        if not self.ocr:
            print("   ❌ PaddleOCR 未初始化")
            return []
        
        try:
            # 如果没有提供截图，先截图
            if screenshot_path is None:
                screenshot_path = str(self.screenshot_dir / f"ocr_{int(time.time())}.png")
                self.page.screenshot(path=screenshot_path, full_page=True)
            
            print(f"   📝 开始 OCR 识别: {screenshot_path}")
            
            # 执行 OCR
            result = self.ocr.ocr(screenshot_path, cls=True)
            
            if not result or not result[0]:
                print("   ⚠️  未识别到文字")
                return []
            
            # 解析结果
            recognized_texts = []
            for line in result[0]:
                box = line[0]  # 文字框坐标
                text_info = line[1]  # (文字, 置信度)
                
                recognized_texts.append({
                    'text': text_info[0],
                    'confidence': text_info[1],
                    'box': box
                })
            
            print(f"   ✅ 识别到 {len(recognized_texts)} 个文本块")
            
            # 打印前5个结果
            for i, item in enumerate(recognized_texts[:5]):
                print(f"      {i+1}. \"{item['text']}\" (置信度: {item['confidence']:.2f})")
            
            return recognized_texts
            
        except Exception as e:
            print(f"   ❌ OCR 识别失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def find_text_in_region(self, keyword: str, screenshot_path: str = None,
                           confidence_threshold: float = 0.6) -> Optional[Dict]:
        """
        在截图中查找特定关键词
        
        Args:
            keyword: 要查找的关键词
            screenshot_path: 截图路径
            confidence_threshold: 置信度阈值
        
        Returns:
            Dict: 匹配的文本信息，包括位置
        """
        texts = self.recognize_text_from_screenshot(screenshot_path)
        
        for item in texts:
            if keyword.lower() in item['text'].lower() and item['confidence'] >= confidence_threshold:
                print(f"   ✅ 找到关键词 \"{keyword}\": \"{item['text']}\"")
                return item
        
        print(f"   ⚠️  未找到关键词 \"{keyword}\"")
        return None
    
    def _group_nearby_texts(self, ocr_results: List[Dict], y_threshold: int = 15, x_gap_threshold: int = 80) -> List[Dict]:
        """
        将相邻的 OCR 识别结果组合成完整的文本行
        
        Tesseract 经常把中文拆成单个字符，需要将 Y 坐标相近、X 坐标连续的字符组合起来
        
        Args:
            ocr_results: OCR 识别结果列表
            y_threshold: Y 坐标差异阈值（像素）
            x_gap_threshold: X 坐标最大间隙（像素）
        
        Returns:
            组合后的文本列表
        """
        if not ocr_results:
            return []
        
        # 按 Y 坐标排序
        sorted_items = sorted(ocr_results, key=lambda x: (x['center_y'], x['center_x']))
        
        groups = []
        current_group = [sorted_items[0]]
        
        for i in range(1, len(sorted_items)):
            item = sorted_items[i]
            prev_item = current_group[-1]
            
            # 检查是否在同一行（Y 坐标相近）
            y_diff = abs(item['center_y'] - prev_item['center_y'])
            
            # 检查 X 坐标是否连续（不是太远）
            x_gap = item['center_x'] - (prev_item['center_x'] + prev_item.get('width', 0) / 2)
            
            if y_diff <= y_threshold and x_gap < x_gap_threshold:
                # 同一行，添加到当前组
                current_group.append(item)
            else:
                # 新的一行，保存当前组并开始新组
                if current_group:
                    groups.append(current_group)
                current_group = [item]
        
        # 添加最后一组
        if current_group:
            groups.append(current_group)
        
        # 将每组组合成一个文本
        combined_results = []
        for group in groups:
            # 按 X 坐标排序，确保从左到右
            group_sorted = sorted(group, key=lambda x: x['center_x'])
            
            # 组合文本
            combined_text = ''.join([item['text'] for item in group_sorted])
            
            # 计算平均置信度
            avg_confidence = sum(item['confidence'] for item in group_sorted) / len(group_sorted)
            
            # 计算中心位置
            center_x = sum(item['center_x'] for item in group_sorted) / len(group_sorted)
            center_y = sum(item['center_y'] for item in group_sorted) / len(group_sorted)
            
            combined_results.append({
                'text': combined_text,
                'confidence': avg_confidence,
                'center_x': center_x,
                'center_y': center_y,
                'items': group_sorted  # 保留原始项，用于调试
            })
        
        return combined_results
    
    # ==================== Flair 识别和选择 ====================
    
    def recognize_and_select_flair(self, target_flair: str, max_attempts: int = 3) -> bool:
        """
        识别并选择 Flair（使用 Tesseract OCR）
        
        流程：
        1. 点击 Flair 按钮打开对话框
        2. 截图
        3. Tesseract OCR 识别所有文字和位置
        4. 找到目标 Flair 的坐标
        5. 计算中心点并点击
        6. 点击 Apply 确认
        
        Args:
            target_flair: 目标 Flair 文本
            max_attempts: 最大尝试次数
        
        Returns:
            bool: 是否成功
        """
        if not self.ocr_helper:
            print("   ❌ TesseractOCRHelper 未初始化")
            return False
        
        print(f"\n🏷️  使用 Tesseract OCR 识别并选择 Flair: {target_flair}")
        
        for attempt in range(max_attempts):
            print(f"\n   尝试 {attempt + 1}/{max_attempts}")
            
            # Step 1: 打开 Flair 对话框
            print("   Step 1: 打开 Flair 对话框...")
            open_result = self._open_flair_dialog()
            if not open_result:
                print("   ❌ 无法打开 Flair 对话框")
                continue
            
            time.sleep(2)  # 等待对话框渲染
            
            # Step 2: 截图
            print("   Step 2: 截取对话框...")
            screenshot_path = str(self.screenshot_dir / f"flair_dialog_{int(time.time())}.png")
            self.page.screenshot(path=screenshot_path, full_page=True)
            
            # Step 3: Tesseract OCR 识别
            print("   Step 3: Tesseract OCR 识别...")
            ocr_results = self.ocr_helper.recognize_with_position(screenshot_path, lang='chi_sim+eng')
            
            if not ocr_results:
                print("   ⚠️  OCR 未识别到文字")
                self.page.keyboard.press('Escape')
                time.sleep(1)
                continue
            
            print(f"   ✅ 识别到 {len(ocr_results)} 个文本块")
            
            # 🔧 关键修复：将相邻的字符组合成完整的文本行
            # Tesseract 经常把中文拆成单个字符，需要按 Y 坐标分组
            print("   🔧 组合相邻字符...")
            grouped_texts = self._group_nearby_texts(ocr_results)
            print(f"   📝 组合后得到 {len(grouped_texts)} 个文本行:")
            for i, group in enumerate(grouped_texts[:15]):
                print(f"      [{i}] \"{group['text']}\" (置信度: {group['confidence']:.1f}%, y={group['center_y']:.0f})")
            
            # 使用组合后的文本进行后续处理
            ocr_results = grouped_texts
            
            # Step 4: 查找目标 Flair（中英文兼容）
            print(f"   Step 4: 查找 '{target_flair}'...")
            target_match = None
            
            # 首先尝试精确匹配或包含匹配
            for item in ocr_results:
                text_lower = item['text'].lower()
                target_lower = target_flair.lower()
                
                # 双向包含匹配：目标在文本中 或 文本在目标中
                if target_lower in text_lower or text_lower in target_lower:
                    if item['confidence'] > 40:
                        target_match = item
                        print(f"   ✅ 找到匹配: \"{item['text']}\" (置信度: {item['confidence']:.1f}%)")
                        break
            
            # 如果没找到，尝试关键词匹配（更宽松）
            if not target_match:
                print(f"   ⚠️  未找到精确匹配，尝试关键词匹配...")
                
                # 提取目标中的关键词（支持中英文）
                import re
                # 匹配中文字符或英文单词
                keywords = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', target_flair)
                
                # 如果只有一个长关键词，拆分成更小的子串
                if len(keywords) == 1 and len(keywords[0]) > 4:
                    long_keyword = keywords[0]
                    # 拆分成 2-3 个字符的子串
                    keywords = [long_keyword[i:i+2] for i in range(0, len(long_keyword), 2)]
                
                print(f"   🔍 关键词: {keywords}")
                
                for item in ocr_results:
                    text = item['text']
                    # 检查是否包含至少一个关键词
                    matched_keywords = [kw for kw in keywords if kw in text]
                    
                    if matched_keywords and item['confidence'] > 50:
                        target_match = item
                        print(f"   ✅ 关键词匹配: \"{item['text']}\" (匹配: {matched_keywords})")
                        break
            
            if not target_match:
                print(f"   ⚠️  未找到目标 Flair")
                # 关闭对话框重试
                self.page.keyboard.press('Escape')
                time.sleep(1)
                continue
            
            # Step 5: 计算点击坐标并点击
            print("   Step 5: 点击 Flair...")
            click_success = self._click_at_coordinates(
                target_match['center_x'], 
                target_match['center_y']
            )
            
            if click_success:
                print("   ✅ Flair 已点击")
                time.sleep(1)
                
                # Step 6: 点击 Apply 按钮
                print("   Step 6: 点击 Apply...")
                apply_result = self._click_apply_button()
                
                if not apply_result:
                    print("   ❌ Apply 按钮点击失败，Flair 未设置")
                    self.page.keyboard.press('Escape')
                    time.sleep(1)
                    continue
                
                # 🔧 关键验证：检查 Flair 对话框是否真的关闭了
                print("   🔍 验证 Flair 对话框是否关闭...")
                time.sleep(1)  # 使用 time.sleep 而不是 page.wait_for_timeout
                
                # 截图检查是否还有 Flair 对话框
                verify_screenshot = "screenshots/verify_flair_closed.png"
                self.page.screenshot(path=verify_screenshot, full_page=False)
                
                verify_ocr = self.ocr_helper.recognize_with_position(verify_screenshot, lang='chi_sim+eng')
                has_dialog = any('添加标记' in item['text'] or 'Apply' in item['text'] for item in verify_ocr if item['confidence'] > 50)
                
                if has_dialog:
                    print("   ⚠️  Flair 对话框仍未关闭，可能 Apply 未生效")
                    self.page.keyboard.press('Escape')
                    time.sleep(1)
                    continue
                else:
                    print("   ✅ Flair 对话框已关闭")
                
                # 🔧 验证 Flair 是否真的被选中：检查页面上是否显示 Flair 标签
                print("   🔍 验证 Flair 是否已应用到帖子...")
                flair_applied = self.page.evaluate("""
                    () => {
                        const content = document.body.textContent || '';
                        // 检查是否有 Flair 相关的文本
                        return content.includes('不适合') || 
                               content.includes('工作场合') ||
                               content.includes('Flair');
                    }
                """)
                
                if flair_applied:
                    print("   ✅✅✅ Flair 设置成功并验证通过")
                    return True
                else:
                    print("   ⚠️  无法验证 Flair 是否应用，但对话框已关闭")
                    return True  # 保守认为成功
            else:
                print("   ❌ 点击失败")
            
            # 关闭对话框重试
            self.page.keyboard.press('Escape')
            time.sleep(1)
        
        print(f"\n❌ 经过 {max_attempts} 次尝试后仍然失败")
        return False
    
    def _open_flair_dialog(self) -> bool:
        """
        打开 Flair 对话框 - 使用 OCR 视觉识别
        
        策略：
        1. 截图当前页面
        2. 用 Tesseract OCR 识别所有文字和位置
        3. 找到"添加标记"或"Flair"的坐标
        4. 点击该坐标
        """
        try:
            print("   📸 Step 1: 截图并使用 OCR 查找'添加标记'按钮...")
            
            # 截图
            screenshot_path = "screenshots/flair_button_search.png"
            self.page.screenshot(path=screenshot_path, full_page=False)
            print(f"      截图已保存: {screenshot_path}")
            
            # 使用 Tesseract OCR 识别
            results = self.ocr_helper.recognize_with_position(screenshot_path, lang='chi_sim+eng')
            print(f"      🔍 OCR 识别到 {len(results)} 个文字块")
            
            # 查找包含"添加标记"、"Flair"、"标记"的文字
            target_keywords = ['添加标记', 'flair', '标记', 'add flair']
            target_found = None
            
            for item in results:
                text_lower = item['text'].lower()
                for keyword in target_keywords:
                    if keyword.lower() in text_lower:
                        target_found = item
                        print(f"      ✅ 找到目标: \"{item['text']}\" (置信度: {item['confidence']:.1f}%)")
                        print(f"         位置: x={item['center_x']:.0f}, y={item['center_y']:.0f}")
                        break
                if target_found:
                    break
            
            if not target_found:
                print("      ❌ OCR 未找到'添加标记'按钮")
                print("      💡 可能原因:")
                print("         - 当前页面不是发帖页面")
                print("         - 按钮还未显示")
                print("         - 需要先滚动页面")
                return False
            
            # 点击找到的坐标
            print(f"      🖱️  点击坐标: ({target_found['center_x']:.0f}, {target_found['center_y']:.0f})")
            self.page.mouse.click(target_found['center_x'], target_found['center_y'])
            time.sleep(2)  # 等待对话框打开
            
            print("      ✅ Flair 对话框已打开")
            return True
            
        except Exception as e:
            print(f"      ❌ OCR 识别失败: {e}")
            import traceback
            traceback.print_exc()
            return False
            
        except Exception as e:
            print(f"   ❌ 打开 Flair 对话框异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _click_at_coordinates(self, x: float, y: float) -> bool:
        """
        在指定坐标点击
        
        Args:
            x: x 坐标
            y: y 坐标
        
        Returns:
            bool: 是否成功
        """
        try:
            print(f"   📍 点击坐标: ({x:.0f}, {y:.0f})")
            self.page.mouse.click(x, y)
            time.sleep(0.5)
            return True
        except Exception as e:
            print(f"   ❌ 点击失败: {e}")
            return False
    
    def _click_apply_button(self) -> bool:
        """点击 Apply/确认按钮"""
        try:
            # 尝试多种选择器
            apply_selectors = [
                'button:has-text("Apply")',
                'button:has-text("确认")',
                'button:has-text("确定")',
                '[class*="apply"]',
            ]
            
            for selector in apply_selectors:
                try:
                    btn = self.page.locator(selector).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click()
                        print(f"   ✅ 已点击 Apply 按钮")
                        return True
                except:
                    continue
            
            print("   ⚠️  未找到 Apply 按钮")
            return False
            
        except Exception as e:
            print(f"   ❌ Apply 按钮点击失败: {e}")
            return False
    
    # ==================== 错误提示框识别和处理 ====================
    
    def detect_and_read_error_dialog(self, wait_time: int = 5) -> Optional[str]:
        """
        检测并读取错误提示框的内容（使用 Tesseract OCR）
        
        Args:
            wait_time: 等待时间
        
        Returns:
            str: 错误消息，如果没有则返回 None
        """
        if not self.ocr_helper:
            print("   ❌ TesseractOCRHelper 未初始化")
            return None
        
        print(f"\n🔍 检测错误提示框...")
        
        # 等待
        time.sleep(wait_time)
        
        # 截图
        screenshot_path = str(self.screenshot_dir / f"error_dialog_{int(time.time())}.png")
        self.page.screenshot(path=screenshot_path, full_page=True)
        print(f"   📸 截图已保存: {screenshot_path}")
        
        # 使用 Tesseract OCR 识别
        ocr_results = self.ocr_helper.recognize_with_position(screenshot_path, lang='eng')
        
        # 查找错误相关的文本
        error_keywords = ['error', 'failed', 'invalid', 'required', 'too short']
        
        error_messages = []
        for item in ocr_results:
            text_lower = item['text'].lower()
            if any(kw in text_lower for kw in error_keywords):
                if item['confidence'] > 40:
                    error_messages.append(item['text'])
        
        if error_messages:
            error_text = '; '.join(error_messages[:3])
            print(f"   ❌ 检测到错误: {error_text}")
            return error_text
        else:
            print("   ✅ 未检测到错误提示")
            return None
    
    def handle_error_and_retry(self, original_title: str, original_content: str,
                              max_retries: int = 2) -> Dict:
        """
        处理错误并重试
        
        Args:
            original_title: 原始标题
            original_content: 原始内容
            max_retries: 最大重试次数
        
        Returns:
            Dict: 处理结果
        """
        print(f"\n🔄 开始错误处理和重试流程")
        
        for attempt in range(max_retries):
            print(f"\n{'='*80}")
            print(f"重试 {attempt + 1}/{max_retries}")
            print(f"{'='*80}")
            
            # Step 1: 检测错误
            error_message = self.detect_and_read_error_dialog()
            
            if not error_message:
                print("   ✅ 没有检测到错误，可能已成功")
                return {
                    'success': True,
                    'message': '提交成功'
                }
            
            # Step 2: 分析错误类型
            print(f"\n   分析错误类型...")
            correction = self._analyze_error_and_correct(error_message, original_title, original_content)
            
            if not correction['should_retry']:
                print(f"   ❌ 不建议重试: {correction['reason']}")
                return {
                    'success': False,
                    'message': error_message,
                    'reason': correction['reason']
                }
            
            # Step 3: 应用修正
            print(f"\n   应用修正...")
            corrected_title = correction.get('corrected_title', original_title)
            corrected_content = correction.get('corrected_content', original_content)
            
            print(f"   建议:")
            for suggestion in correction.get('suggestions', []):
                print(f"      - {suggestion}")
            
            # Step 4: 重新填写并提交
            print(f"\n   重新填写内容...")
            self._refill_form(corrected_title, corrected_content)
            
            # Step 5: 再次提交
            print(f"   再次提交...")
            submit_result = self._submit_post()
            
            if submit_result:
                # 再次检测
                time.sleep(5)
                new_error = self.detect_and_read_error_dialog(wait_time=3)
                
                if not new_error:
                    print(f"   ✅✅✅ 重试成功！")
                    return {
                        'success': True,
                        'message': '重试后提交成功',
                        'attempt': attempt + 1
                    }
            
            print(f"   ⚠️  重试 {attempt + 1} 失败，准备下一次...")
            time.sleep(2)
        
        print(f"\n❌ 经过 {max_retries} 次重试后仍然失败")
        return {
            'success': False,
            'message': error_message,
            'attempts': max_retries
        }
    
    def _analyze_error_and_correct(self, error_message: str, title: str, content: str) -> Dict:
        """分析错误并生成修正"""
        correction = {
            'should_retry': False,
            'corrected_title': title,
            'corrected_content': content,
            'suggestions': [],
            'reason': ''
        }
        
        error_lower = error_message.lower()
        
        # 标题问题
        if any(kw in error_lower for kw in ['title', '标题', 'short', '短']):
            correction['should_retry'] = True
            correction['corrected_title'] = title + " - Updated"
            correction['suggestions'].append("标题可能太短，已添加后缀")
        
        # 内容问题
        elif any(kw in error_lower for kw in ['content', '内容', 'body', '正文']):
            correction['should_retry'] = True
            correction['corrected_content'] = content + "\n\nAdditional details added."
            correction['suggestions'].append("内容可能不足，已添加补充")
        
        # Flair 问题
        elif any(kw in error_lower for kw in ['flair', '标记', '标识', 'required', '必填']):
            correction['should_retry'] = True
            correction['suggestions'].append("需要选择 Flair")
        
        # 重复
        elif any(kw in error_lower for kw in ['duplicate', '重复', 'similar']):
            correction['should_retry'] = True
            correction['corrected_title'] = title + " (v2)"
            correction['suggestions'].append("帖子可能重复，已修改标题")
        
        # 频率限制
        elif any(kw in error_lower for kw in ['rate limit', '频率', 'wait', '等待']):
            correction['should_retry'] = True
            correction['suggestions'].append("触发频率限制，建议等待 60 秒")
            time.sleep(60)
        
        # 权限
        elif any(kw in error_lower for kw in ['permission', '权限', 'banned']):
            correction['should_retry'] = False
            correction['reason'] = '没有发帖权限'
        
        else:
            correction['should_retry'] = True
            correction['suggestions'].append("未知错误，尝试简化内容")
        
        return correction
    
    def _refill_form(self, title: str, content: str):
        """重新填写表单"""
        try:
            # 填写标题
            title_input = self.page.locator('textarea[name="title"]').first
            if title_input.count() > 0:
                title_input.fill(title)
                print("   ✓ 标题已更新")
            
            # 填写内容
            composer = self.page.locator('shreddit-composer').first
            if composer.count() > 0:
                composer.click()
                time.sleep(0.5)
                self.page.keyboard.press('Control+a')
                self.page.keyboard.press('Delete')
                time.sleep(0.5)
                self.page.keyboard.type(content, delay=30)
                print("   ✓ 内容已更新")
        
        except Exception as e:
            print(f"   ⚠️  重新填写失败: {e}")
    
    def _submit_post(self) -> bool:
        """提交帖子"""
        try:
            result = self.page.evaluate("""
                () => {
                    const submitBtn = document.querySelector('r-post-form-submit-button#submit-post-button');
                    if (submitBtn && !submitBtn.hasAttribute('disabled')) {
                        const internalBtn = submitBtn.shadowRoot?.querySelector('button') || submitBtn.querySelector('button');
                        if (internalBtn) {
                            internalBtn.click();
                            return true;
                        }
                        submitBtn.click();
                        return true;
                    }
                    return false;
                }
            """)
            
            if result:
                print("   ✅ 提交指令已发出")
                return True
            else:
                print("   ❌ 提交失败")
                return False
        
        except Exception as e:
            print(f"   ❌ 提交异常: {e}")
            return False


# 使用示例
if __name__ == "__main__":
    print("Reddit Visual Recognizer - PaddleOCR + Airtest")
    print("请通过测试脚本调用此模块")

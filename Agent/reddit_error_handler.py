#!/usr/bin/env python3
"""
Reddit 提交后错误检测和智能修正模块

提供两种检测方法：
1. 页面源码分析
2. 截图 + OCR 图像分析
"""

import time
from pathlib import Path
from typing import Dict, List, Optional


class RedditSubmissionErrorHandler:
    """Reddit 提交错误处理器"""
    
    def __init__(self, page):
        self.page = page
    
    def detect_and_handle_error(self, wait_time: int = 8, use_ocr: bool = False) -> Dict:
        """
        检测提交结果并处理错误
        
        Args:
            wait_time: 等待时间（秒）
            use_ocr: 是否使用 OCR 分析截图
        
        Returns:
            Dict: {
                'status': 'success' | 'error' | 'unknown',
                'error_message': str,
                'should_retry': bool,
                'corrected_content': Dict,
                'detection_method': str,
                'evidence': Dict (截图/HTML)
            }
        """
        print(f"\n🔍 检测提交结果...")
        
        # 等待页面响应
        time.sleep(wait_time)
        
        # 方法1: 截图保存
        screenshot_path = self._take_screenshot()
        
        # 方法2: 获取页面HTML
        page_html = self.page.content()
        
        # 多策略检测
        detection_result = self._multi_strategy_detection(screenshot_path, page_html, use_ocr)
        
        # 如果检测到错误，生成修正建议
        if detection_result['status'] == 'error':
            correction = self._generate_correction(detection_result['error_message'])
            detection_result.update(correction)
        
        # 保存证据
        detection_result['evidence'] = {
            'screenshot': screenshot_path,
            'html_snapshot': page_html[:10000]  # 保存前10K字符
        }
        
        return detection_result
    
    def _take_screenshot(self) -> str:
        """截图并保存"""
        screenshot_path = Path(f"screenshots/reddit_submission_{int(time.time())}.png")
        screenshot_path.parent.mkdir(exist_ok=True)
        self.page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"   📸 截图已保存: {screenshot_path}")
        return str(screenshot_path)
    
    def _multi_strategy_detection(self, screenshot_path: str, page_html: str, 
                                  use_ocr: bool = False) -> Dict:
        """
        多策略检测结果
        
        策略优先级：
        1. URL 变化检测（最可靠）
        2. 页面源码分析（查找错误元素）
        3. OCR 图像分析（辅助验证）
        """
        result = {
            'status': 'unknown',
            'error_message': None,
            'detection_method': None
        }
        
        # 策略 1: URL 检查
        current_url = self.page.url
        print(f"   🔗 当前 URL: {current_url}")
        
        if "/comments/" in current_url or "/posts/" in current_url:
            result['status'] = 'success'
            result['post_url'] = current_url
            result['detection_method'] = 'url_change'
            print(f"   ✅ 检测到 URL 变化，发帖成功")
            return result
        
        # 策略 2: 页面源码分析
        html_analysis = self._analyze_page_html(page_html)
        if html_analysis['has_error']:
            result['status'] = 'error'
            result['error_message'] = html_analysis['error_message']
            result['detection_method'] = 'html_analysis'
            print(f"   ❌ HTML 分析检测到错误: {html_analysis['error_message'][:100]}")
            return result
        
        # 策略 3: OCR 分析（如果启用）
        if use_ocr:
            ocr_result = self._analyze_screenshot_ocr(screenshot_path)
            if ocr_result['has_error']:
                result['status'] = 'error'
                result['error_message'] = ocr_result['error_message']
                result['detection_method'] = 'ocr_analysis'
                print(f"   ❌ OCR 分析检测到错误: {ocr_result['error_message'][:100]}")
                return result
        
        # 策略 4: 检查是否仍在提交页
        if "/submit" in current_url:
            result['status'] = 'error'
            result['error_message'] = '仍在提交页面，可能提交失败'
            result['detection_method'] = 'page_check'
            print(f"   ⚠️  仍在提交页面")
            return result
        
        # 未知状态
        result['status'] = 'unknown'
        result['detection_method'] = 'inconclusive'
        print(f"   ⚠️  无法确定提交状态")
        
        return result
    
    def _analyze_page_html(self, html: str) -> Dict:
        """
        分析页面 HTML 查找错误
        
        Returns:
            Dict: {'has_error': bool, 'error_message': str}
        """
        try:
            # 使用 JavaScript 在页面中查找错误元素
            error_info = self.page.evaluate("""
                () => {
                    // 查找错误对话框
                    const errorSelectors = [
                        '[role="alert"]',
                        '[class*="error"]',
                        '[class*="Error"]',
                        'faceplate-alert',
                        '.shreddit-toast--error',
                        '[data-testid*="error"]'
                    ];
                    
                    for (const selector of errorSelectors) {
                        const elements = document.querySelectorAll(selector);
                        for (const elem of elements) {
                            if (elem.offsetParent !== null) { // 可见
                                const text = elem.textContent?.trim();
                                if (text && text.length > 5) {
                                    return {
                                        has_error: true,
                                        error_message: text.substring(0, 500)
                                    };
                                }
                            }
                        }
                    }
                    
                    // 查找包含错误关键词的文本
                    const bodyText = document.body.textContent || '';
                    const errorKeywords = ['error', '错误', 'failed', '失败', 'invalid', '无效'];
                    
                    for (const keyword of errorKeywords) {
                        const regex = new RegExp(keyword, 'i');
                        if (regex.test(bodyText)) {
                            // 找到包含关键词的段落
                            const paragraphs = Array.from(document.querySelectorAll('p, div, span'));
                            for (const p of paragraphs) {
                                const text = p.textContent?.trim();
                                if (text && regex.test(text) && text.length > 10 && text.length < 500) {
                                    return {
                                        has_error: true,
                                        error_message: text.substring(0, 500)
                                    };
                                }
                            }
                        }
                    }
                    
                    return { has_error: false };
                }
            """)
            
            return error_info
            
        except Exception as e:
            print(f"   ⚠️  HTML 分析失败: {e}")
            return {'has_error': False}
    
    def _analyze_screenshot_ocr(self, screenshot_path: str) -> Dict:
        """
        使用 OCR 分析截图
        
        Returns:
            Dict: {'has_error': bool, 'error_message': str, 'full_text': str}
        """
        result = {
            'has_error': False,
            'error_message': None,
            'full_text': ''
        }
        
        try:
            import pytesseract
            from PIL import Image
            
            print(f"   📝 开始 OCR 分析...")
            
            # 打开截图
            image = Image.open(screenshot_path)
            
            # 执行 OCR（中英文）
            text = pytesseract.image_to_string(image, lang='chi_sim+eng')
            result['full_text'] = text
            
            print(f"   📝 OCR 识别到 {len(text)} 字符")
            
            # 查找错误关键词
            error_keywords = [
                'error', '错误', 'failed', '失败',
                'invalid', '无效', 'required', '必填'
            ]
            
            lines = text.split('\n')
            error_lines = []
            
            for line in lines:
                line_lower = line.lower()
                if any(kw in line_lower for kw in error_keywords):
                    if len(line.strip()) > 5 and len(line.strip()) < 500:
                        error_lines.append(line.strip())
            
            if error_lines:
                result['has_error'] = True
                result['error_message'] = '; '.join(error_lines[:3])
                print(f"   ❌ OCR 检测到 {len(error_lines)} 个错误提示:")
                for err in error_lines[:3]:
                    print(f"      - {err[:100]}")
            else:
                print(f"   ✅ OCR 未检测到明显错误")
            
            return result
            
        except ImportError:
            print(f"   ⚠️  pytesseract 未安装，跳过 OCR 分析")
            print(f"   💡 安装命令: pip install pytesseract pillow")
            return result
        except Exception as e:
            print(f"   ⚠️  OCR 分析失败: {e}")
            return result
    
    def _generate_correction(self, error_message: str) -> Dict:
        """
        根据错误消息生成修正建议
        
        Returns:
            Dict: {
                'should_retry': bool,
                'correction_type': str,
                'suggestions': List[str]
            }
        """
        correction = {
            'should_retry': False,
            'correction_type': 'unknown',
            'suggestions': []
        }
        
        error_lower = error_message.lower()
        
        # 标题相关错误
        if any(kw in error_lower for kw in ['title', '标题', 'short', '短', 'empty', '空']):
            correction['should_retry'] = True
            correction['correction_type'] = 'title_issue'
            correction['suggestions'].append("标题可能太短或为空")
            correction['suggestions'].append("建议：添加更多描述性词汇")
        
        # 内容相关错误
        elif any(kw in error_lower for kw in ['content', '内容', 'body', '正文', 'short', '短']):
            correction['should_retry'] = True
            correction['correction_type'] = 'content_issue'
            correction['suggestions'].append("内容可能太短")
            correction['suggestions'].append("建议：添加更多细节和背景信息")
        
        # Flair 相关错误
        elif any(kw in error_lower for kw in ['flair', '标记', '标识', 'required', '必填', 'select']):
            correction['should_retry'] = True
            correction['correction_type'] = 'flair_missing'
            correction['suggestions'].append("需要选择 Flair")
            correction['suggestions'].append("建议：选择一个合适的分类标签")
        
        # 重复帖子
        elif any(kw in error_lower for kw in ['duplicate', '重复', 'similar', '相似', 'posted']):
            correction['should_retry'] = True
            correction['correction_type'] = 'duplicate'
            correction['suggestions'].append("帖子可能重复")
            correction['suggestions'].append("建议：修改标题和内容，使其更独特")
        
        # 频率限制
        elif any(kw in error_lower for kw in ['rate limit', '频率', 'too many', '太多', 'wait', '等待']):
            correction['should_retry'] = True
            correction['correction_type'] = 'rate_limit'
            correction['suggestions'].append("触发频率限制")
            correction['suggestions'].append("建议：等待 60-120 秒后重试")
        
        # 权限问题
        elif any(kw in error_lower for kw in ['permission', '权限', 'banned', '禁止', 'restricted']):
            correction['should_retry'] = False
            correction['correction_type'] = 'permission_denied'
            correction['suggestions'].append("没有发帖权限或被限制")
            correction['suggestions'].append("建议：检查社区规则或联系版主")
        
        # 未知错误
        else:
            correction['should_retry'] = True
            correction['correction_type'] = 'unknown_error'
            correction['suggestions'].append(f"未知错误: {error_message[:100]}")
            correction['suggestions'].append("建议：简化内容后重试")
        
        return correction


# 使用示例
if __name__ == "__main__":
    print("Reddit Submission Error Handler Module")
    print("请通过 reddit_advanced_helper.py 调用此模块")

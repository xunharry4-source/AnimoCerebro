#!/usr/bin/env python3
"""
Reddit 视觉智能体执行器 - PaddleOCR + Airtest 完整实现

职责：
1. 获取社区规则
2. 填写内容
3. 视觉识别并选择 Flair
4. 点击 Post 按钮
5. 分析结果并自动修正
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class RedditVisualAgent:
    """Reddit 视觉智能体执行器"""
    
    def __init__(self, page, rules_manager=None, window_size: Tuple[int, int] = (1280, 800)):
        self.page = page
        self.rules_manager = rules_manager
        self.window_size = window_size
        
        # 设置固定窗口大小（确保坐标一致性）
        self.page.set_viewport_size({"width": window_size[0], "height": window_size[1]})
        
        # 初始化 PaddleOCR
        self.ocr = None
        self._init_paddleocr()
        
        # 资产目录（存储按钮图标等）
        self.assets_dir = Path("Agent/assets/reddit")
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"✅ RedditVisualAgent 初始化完成 (窗口: {window_size[0]}x{window_size[1]})")
    
    def _init_paddleocr(self):
        """初始化 PaddleOCR"""
        try:
            from paddleocr import PaddleOCR
            
            print("   🔄 初始化 PaddleOCR...")
            self.ocr = PaddleOCR(
                use_angle_cls=True,
                lang='ch',
                show_log=False,
                use_gpu=False
            )
            print("   ✅ PaddleOCR 就绪")
            
        except ImportError:
            print("   ⚠️  PaddleOCR 未安装，将使用备用方案")
            print("   💡 pip install paddlepaddle paddleocr")
    
    # ==================== 主工作流 ====================
    
    def execute_posting_task(self, subreddit: str, title: str, content: str,
                            target_flair: Optional[str] = None,
                            max_retries: int = 3) -> Dict:
        """
        执行完整的发帖任务（视觉智能体核心方法）
        
        Args:
            subreddit: 子版块
            title: 标题
            content: 内容
            target_flair: 目标 Flair
            max_retries: 最大重试次数
        
        Returns:
            Dict: 执行结果
        """
        print("\n" + "="*80)
        print("🤖 Reddit 视觉智能体启动")
        print("="*80)
        
        result = {
            'success': False,
            'attempts': [],
            'final_status': None
        }
        
        current_title = title
        current_content = content
        
        for attempt in range(max_retries):
            print(f"\n{'='*80}")
            print(f"🔄 尝试 {attempt + 1}/{max_retries}")
            print(f"{'='*80}")
            
            attempt_result = {'attempt': attempt + 1, 'steps': {}}
            
            try:
                # Step 1: 获取社区规则
                print("\n📋 Step 1: 获取社区规则...")
                rules = self._get_community_rules(subreddit)
                attempt_result['rules'] = rules
                
                # Step 2: 填写内容
                print("\n📝 Step 2: 填写标题和内容...")
                self._fill_content(current_title, current_content)
                attempt_result['content_filled'] = True
                
                # Step 3 & 4: 视觉识别并选择 Flair
                if target_flair:
                    print(f"\n🏷️  Step 3-4: 视觉识别并选择 Flair '{target_flair}'...")
                    flair_success = self._visual_select_flair(target_flair)
                    attempt_result['flair_selected'] = flair_success
                else:
                    attempt_result['flair_selected'] = 'skipped'
                
                # Step 5: 下拉并点击 Post
                print("\n🚀 Step 5: 下拉页面并点击 Post...")
                post_clicked = self._scroll_and_click_post()
                attempt_result['post_clicked'] = post_clicked
                
                if not post_clicked:
                    print("   ❌ Post 按钮点击失败")
                    result['attempts'].append(attempt_result)
                    continue
                
                # Step 6: 分析结果
                print("\n🔍 Step 6: 分析发帖结果...")
                analysis = self._analyze_submission_result()
                attempt_result['analysis'] = analysis
                
                if analysis['status'] == 'success':
                    print("\n✅✅✅ 发帖成功！")
                    result['success'] = True
                    result['final_status'] = analysis
                    result['attempts'].append(attempt_result)
                    return result
                
                elif analysis['status'] == 'error':
                    print(f"\n❌ 检测到错误: {analysis.get('error_message')}")
                    
                    if attempt < max_retries - 1:
                        # Step 7: 修正并重试
                        print("\n🔄 Step 7: 修正内容并重试...")
                        correction = self._correct_based_on_error(
                            analysis['error_message'],
                            current_title,
                            current_content
                        )
                        
                        if correction['should_retry']:
                            current_title = correction.get('corrected_title', current_title)
                            current_content = correction.get('corrected_content', current_content)
                            
                            print(f"   💡 已修正内容")
                            print(f"      新标题: {current_title[:50]}...")
                            
                            # 关闭错误对话框
                            self._close_error_dialog()
                            time.sleep(2)
                        else:
                            print(f"   ⚠️  不建议重试: {correction.get('reason')}")
                            break
                    else:
                        print(f"   ❌ 达到最大重试次数")
                
                result['attempts'].append(attempt_result)
                
            except Exception as e:
                print(f"\n❌ 异常: {e}")
                import traceback
                traceback.print_exc()
                attempt_result['error'] = str(e)
                result['attempts'].append(attempt_result)
        
        result['final_status'] = {'status': 'failed', 'message': '所有尝试均失败'}
        return result
    
    # ==================== Step 1: 获取社区规则 ====================
    
    def _get_community_rules(self, subreddit: str) -> Dict:
        """Step 1: 获取社区规则"""
        try:
            # 访问规则页面
            rules_url = f"https://www.reddit.com/r/{subreddit}/about/rules"
            self.page.goto(rules_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # 提取规则文本
            rules_text = self.page.evaluate("""
                () => {
                    const ruleElements = document.querySelectorAll('.rule');
                    return Array.from(ruleElements).map(r => r.textContent?.trim()).filter(t => t);
                }
            """)
            
            print(f"   ✅ 获取到 {len(rules_text)} 条规则")
            return {'rules': rules_text[:5]}  # 只返回前5条关键规则
            
        except Exception as e:
            print(f"   ⚠️  规则获取失败: {e}")
            return {'rules': [], 'error': str(e)}
    
    # ==================== Step 2: 填写内容 ====================
    
    def _fill_content(self, title: str, content: str):
        """Step 2: 填写标题和内容"""
        try:
            # 访问提交页面
            submit_url = f"https://www.reddit.com/r/AnimoCerebro/submit"
            self.page.goto(submit_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # 填写标题
            title_input = self.page.locator('textarea[name="title"]').first
            if title_input.count() > 0:
                title_input.fill(title)
                print(f"   ✓ 标题已填写")
            
            # 填写内容
            composer = self.page.locator('shreddit-composer').first
            if composer.count() > 0:
                composer.click()
                time.sleep(1)
                self.page.keyboard.type(content, delay=30)
                print(f"   ✓ 内容已填写 ({len(content)} 字符)")
            
        except Exception as e:
            print(f"   ❌ 内容填写失败: {e}")
            raise
    
    # ==================== Step 3-4: 视觉识别并选择 Flair ====================
    
    def _visual_select_flair(self, target_flair: str) -> bool:
        """
        Step 3-4: 使用 PaddleOCR + Airtest 视觉选择 Flair
        
        流程：
        1. 点击 Flair 按钮
        2. 截图
        3. PaddleOCR 识别文字和坐标
        4. 计算中心点
        5. 点击坐标
        6. 点击 Apply
        """
        try:
            # 1. 打开 Flair 对话框
            print("   Step 3.1: 打开 Flair 对话框...")
            open_result = self.page.evaluate("""
                () => {
                    const flairBtn = document.querySelector('button#reddit-post-flair-button');
                    if (flairBtn) {
                        flairBtn.click();
                        return true;
                    }
                    return false;
                }
            """)
            
            if not open_result:
                print("   ❌ 无法打开 Flair 对话框")
                return False
            
            time.sleep(2)  # 等待对话框渲染
            
            # 2. 截图
            print("   Step 3.2: 截取对话框...")
            screenshot_path = str(self.assets_dir / f"flair_dialog_{int(time.time())}.png")
            self.page.screenshot(path=screenshot_path, full_page=True)
            
            # 3. PaddleOCR 识别
            if not self.ocr:
                print("   ⚠️  PaddleOCR 未初始化，使用备用方案")
                return self._fallback_flair_selection(target_flair)
            
            print("   Step 3.3: PaddleOCR 识别...")
            ocr_result = self.ocr.ocr(screenshot_path, cls=True)
            
            if not ocr_result or not ocr_result[0]:
                print("   ⚠️  OCR 未识别到文字")
                return self._fallback_flair_selection(target_flair)
            
            # 4. 查找目标 Flair
            print(f"   Step 3.4: 查找 '{target_flair}'...")
            target_box = None
            
            for line in ocr_result[0]:
                box = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                text_info = line[1]  # (text, confidence)
                text = text_info[0]
                confidence = text_info[1]
                
                # 模糊匹配
                if target_flair.lower() in text.lower() and confidence > 0.5:
                    print(f"   ✅ 找到: \"{text}\" (置信度: {confidence:.2f})")
                    target_box = box
                    break
            
            if not target_box:
                print(f"   ⚠️  未找到目标 Flair")
                self.page.keyboard.press('Escape')
                return False
            
            # 5. 计算中心坐标
            center_x = (target_box[0][0] + target_box[2][0]) / 2
            center_y = (target_box[0][1] + target_box[2][1]) / 2
            
            print(f"   Step 4.1: 点击坐标 ({center_x:.0f}, {center_y:.0f})")
            
            # 6. 执行点击（使用 Playwright mouse，与 Airtest 等效）
            self.page.mouse.click(center_x, center_y)
            time.sleep(1)
            
            # 7. 点击 Apply 按钮
            print("   Step 4.2: 点击 Apply...")
            apply_result = self._click_apply_button()
            
            if apply_result:
                print("   ✅✅✅ Flair 选择完成")
                return True
            else:
                print("   ⚠️  Apply 按钮点击失败")
                return False
            
        except Exception as e:
            print(f"   ❌ Flair 选择失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _fallback_flair_selection(self, target_flair: str) -> bool:
        """备用 Flair 选择方案（当 OCR 不可用时）"""
        try:
            print("   🔄 使用备用方案...")
            
            # 尝试 DOM 方法
            flairs = self.page.locator('shreddit-post-flair-row').all()
            for flair in flairs:
                text = flair.inner_text()
                if target_flair.lower() in text.lower():
                    flair.click()
                    time.sleep(1)
                    self._click_apply_button()
                    return True
            
            print("   ⚠️  备用方案也失败")
            return False
            
        except Exception as e:
            print(f"   ❌ 备用方案异常: {e}")
            return False
    
    def _click_apply_button(self) -> bool:
        """点击 Apply/确认按钮"""
        try:
            apply_btn = self.page.locator('button:has-text("Apply"), button:has-text("确认")').first
            if apply_btn.count() > 0 and apply_btn.is_visible():
                apply_btn.click()
                time.sleep(1)
                return True
            return False
        except:
            return False
    
    # ==================== Step 5: 下拉并点击 Post ====================
    
    def _scroll_and_click_post(self) -> bool:
        """Step 5: 下拉页面并点击 Post 按钮"""
        try:
            # 1. 下拉页面
            print("   Step 5.1: 下拉页面...")
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            
            # 2. 查找并点击 Post 按钮
            print("   Step 5.2: 点击 Post 按钮...")
            click_result = self.page.evaluate("""
                () => {
                    const submitBtn = document.querySelector('r-post-form-submit-button#submit-post-button');
                    if (submitBtn && !submitBtn.hasAttribute('disabled')) {
                        // 尝试点击内部按钮
                        const internalBtn = submitBtn.shadowRoot?.querySelector('button');
                        if (internalBtn) {
                            internalBtn.scrollIntoView();
                            internalBtn.click();
                            return true;
                        }
                        submitBtn.click();
                        return true;
                    }
                    return false;
                }
            """)
            
            if click_result:
                print("   ✅ Post 按钮已点击")
                return True
            else:
                print("   ❌ Post 按钮点击失败")
                return False
            
        except Exception as e:
            print(f"   ❌ Post 点击异常: {e}")
            return False
    
    # ==================== Step 6: 分析结果 ====================
    
    def _analyze_submission_result(self) -> Dict:
        """
        Step 6: 使用 PaddleOCR 分析发帖结果
        
        Returns:
            Dict: {
                'status': 'success' | 'error' | 'unknown',
                'error_message': str (如果有错误),
                'post_url': str (如果成功)
            }
        """
        try:
            # 等待响应
            time.sleep(5)
            
            # 检查 URL 变化（成功的标志）
            current_url = self.page.url
            if "/comments/" in current_url or "/posts/" in current_url:
                print(f"   ✅ URL 跳转成功: {current_url}")
                return {'status': 'success', 'post_url': current_url}
            
            # 截图分析
            print("   Step 6.1: 截图分析...")
            screenshot_path = str(self.assets_dir / f"result_{int(time.time())}.png")
            self.page.screenshot(path=screenshot_path, full_page=True)
            
            # PaddleOCR 识别
            if self.ocr:
                print("   Step 6.2: OCR 识别错误信息...")
                ocr_result = self.ocr.ocr(screenshot_path, cls=True)
                
                if ocr_result and ocr_result[0]:
                    error_keywords = ['error', '错误', 'failed', '失败', 'required', '必填']
                    
                    for line in ocr_result[0]:
                        text = line[1][0]
                        if any(kw in text.lower() for kw in error_keywords):
                            print(f"   ❌ 检测到错误: {text}")
                            return {
                                'status': 'error',
                                'error_message': text
                            }
            
            # 检查是否仍在提交页
            if "/submit" in current_url:
                print("   ⚠️  仍在提交页面")
                return {
                    'status': 'error',
                    'error_message': '提交后仍在原页面，可能失败'
                }
            
            return {'status': 'unknown', 'message': '无法确定状态'}
            
        except Exception as e:
            print(f"   ❌ 结果分析失败: {e}")
            return {'status': 'error', 'error_message': str(e)}
    
    # ==================== Step 7: 错误修正 ====================
    
    def _correct_based_on_error(self, error_message: str, title: str, content: str) -> Dict:
        """根据错误消息修正内容"""
        correction = {
            'should_retry': False,
            'corrected_title': title,
            'corrected_content': content,
            'reason': ''
        }
        
        error_lower = error_message.lower()
        
        # 标题问题
        if any(kw in error_lower for kw in ['title', '标题', 'short', '短']):
            correction['should_retry'] = True
            correction['corrected_title'] = title + " - Updated"
            correction['reason'] = '标题需要修改'
        
        # 内容问题
        elif any(kw in error_lower for kw in ['content', '内容', 'body']):
            correction['should_retry'] = True
            correction['corrected_content'] = content + "\n\nAdditional details."
            correction['reason'] = '内容需要补充'
        
        # Flair 问题
        elif any(kw in error_lower for kw in ['flair', '标记', 'required']):
            correction['should_retry'] = True
            correction['reason'] = '需要选择 Flair'
        
        # 重复
        elif any(kw in error_lower for kw in ['duplicate', '重复']):
            correction['should_retry'] = True
            correction['corrected_title'] = title + " (v2)"
            correction['reason'] = '帖子重复'
        
        # 频率限制
        elif any(kw in error_lower for kw in ['rate limit', '频率']):
            correction['should_retry'] = True
            correction['reason'] = '频率限制，需等待'
            time.sleep(60)
        
        else:
            correction['should_retry'] = True
            correction['reason'] = '未知错误，尝试简化'
        
        return correction
    
    def _close_error_dialog(self):
        """关闭错误对话框"""
        try:
            self.page.keyboard.press('Escape')
            time.sleep(1)
            print("   ✓ 错误对话框已关闭")
        except:
            pass


# 使用示例
if __name__ == "__main__":
    print("Reddit Visual Agent - Ready for CrewAI Integration")

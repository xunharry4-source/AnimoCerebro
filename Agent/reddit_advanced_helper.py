#!/usr/bin/env python3
"""
Reddit 高级自动化助手

整合多种方案解决 Shadow DOM、动态加载和 Web Components 问题
"""

import time
import json
from typing import Dict, List, Optional, Callable
from pathlib import Path


class RedditAdvancedHelper:
    """Reddit 高级自动化助手 - 解决复杂DOM结构问题"""
    
    def __init__(self, page):
        self.page = page
    
    # ==================== 方案1: Shadow DOM 穿透 ====================
    
    def force_click_shadow_element(self, composer_selector: str = 'shreddit-composer',
                                   element_logic: str = "b => b.textContent.includes('flair')") -> bool:
        """
        通过 JS 逻辑在 Shadow Root 中寻找并点击元素
        
        Args:
            composer_selector: Composer 选择器
            element_logic: JS 过滤逻辑，例如 "b => b.textContent.includes('flair')"
        
        Returns:
            bool: 是否成功点击
        """
        try:
            result = self.page.evaluate(f"""
                () => {{
                    const composer = document.querySelector('{composer_selector}');
                    if (!composer || !composer.shadowRoot) return false;
                    
                    const elements = Array.from(composer.shadowRoot.querySelectorAll('button, div[role="button"]'));
                    const target = elements.find({element_logic});
                    
                    if (target) {{
                        target.scrollIntoView();
                        target.click();
                        return true;
                    }}
                    return false;
                }}
            """)
            return result
        except Exception as e:
            print(f"   ⚠️  Shadow DOM 点击失败: {e}")
            return False
    
    def get_composer_shadow_buttons(self) -> List[Dict]:
        """获取 shreddit-composer Shadow DOM 中的所有按钮"""
        try:
            buttons = self.page.evaluate("""
                () => {
                    const composer = document.querySelector('shreddit-composer');
                    if (!composer || !composer.shadowRoot) return [];
                    
                    const btns = Array.from(composer.shadowRoot.querySelectorAll('button'));
                    return btns.map(b => ({
                        text: b.textContent?.trim(),
                        ariaLabel: b.getAttribute('aria-label'),
                        type: b.getAttribute('type'),
                        className: b.className,
                        id: b.id,
                        disabled: b.disabled
                    }));
                }
            """)
            return buttons
        except Exception as e:
            print(f"   ⚠️  获取 Shadow DOM 按钮失败: {e}")
            return []
    
    # ==================== 方案2: 网络响应拦截 ====================
    
    def intercept_flair_data(self, timeout: int = 10) -> List[Dict]:
        """
        拦截 Reddit Flair API 响应，获取所有可用的 Flair
        
        Args:
            timeout: 等待超时时间（秒）
        
        Returns:
            List[Dict]: Flair 列表
        """
        flairs = []
        
        def handle_response(response):
            nonlocal flairs
            try:
                url = response.url.lower()
                # 拦截 Flair 相关接口
                if any(keyword in url for keyword in ['api/v1/flair', 'gql', 'flairselector']):
                    content_type = response.headers.get('content-type', '')
                    if 'application/json' in content_type:
                        try:
                            data = response.json()
                            print(f"   📡 捕获到 Flair 数据: {response.url[:100]}")
                            
                            # 解析不同格式的 Flair 数据
                            if isinstance(data, dict):
                                # 尝试从常见字段提取
                                for key in ['data', 'flairs', 'choices', 'options']:
                                    if key in data and isinstance(data[key], list):
                                        flairs.extend(data[key])
                                        break
                            elif isinstance(data, list):
                                flairs.extend(data)
                                
                        except Exception as e:
                            pass
            except Exception:
                pass
        
        # 注册监听器
        self.page.on("response", handle_response)
        
        # 触发页面刷新以捕获请求
        print("   🔄 刷新页面以捕获 Flair 数据...")
        self.page.reload(wait_until="domcontentloaded", timeout=30000)
        time.sleep(timeout)
        
        print(f"   📊 捕获到 {len(flairs)} 个 Flair")
        return flairs
    
    def set_flair_by_id(self, flair_id: str) -> bool:
        """
        直接通过 ID 设置 Flair（跳过 UI 点击）
        
        Args:
            flair_id: Flair 的 ID
        
        Returns:
            bool: 是否成功
        """
        try:
            result = self.page.evaluate(f"""
                (flairId) => {{
                    const composer = document.querySelector('shreddit-composer');
                    if (!composer) return false;
                    
                    // 尝试设置内部属性
                    composer.flairId = flairId;
                    
                    // 或者触发事件
                    const event = new CustomEvent('flair-selected', {{
                        detail: {{ flairId: flairId }}
                    }});
                    composer.dispatchEvent(event);
                    
                    return true;
                }}
            """, flair_id)
            return result
        except Exception as e:
            print(f"   ⚠️  设置 Flair 失败: {e}")
            return False
    
    # ==================== 方案3: Post 按钮状态轮询 ====================
    
    def poll_post_button_state(self, max_attempts: int = 20, interval: float = 0.5) -> Dict:
        """
        主动轮询 Post 按钮状态
        
        Args:
            max_attempts: 最大尝试次数
            interval: 每次尝试间隔（秒）
        
        Returns:
            Dict: 包含按钮状态信息
        """
        for attempt in range(max_attempts):
            try:
                state = self.page.evaluate("""
                    () => {
                        // 策略 1: 查找 r-post-form-submit-button
                        const submitBtn = document.querySelector('r-post-form-submit-button#submit-post-button');
                        if (submitBtn) {
                            return {
                                found: true,
                                type: 'custom-component',
                                id: submitBtn.id,
                                disabled: submitBtn.hasAttribute('disabled'),
                                postActionType: submitBtn.getAttribute('post-action-type')
                            };
                        }
                        
                        // 策略 2: 在 Shadow DOM 中查找
                        const composer = document.querySelector('shreddit-composer');
                        if (composer && composer.shadowRoot) {
                            const shadowBtn = composer.shadowRoot.querySelector('button[type="submit"]');
                            if (shadowBtn) {
                                return {
                                    found: true,
                                    type: 'shadow-dom',
                                    disabled: shadowBtn.disabled,
                                    text: shadowBtn.textContent?.trim()
                                };
                            }
                        }
                        
                        return { found: false };
                    }
                """)
                
                if state.get('found'):
                    if not state.get('disabled'):
                        print(f"   ✅ Post 按钮已就绪 (尝试 {attempt + 1}/{max_attempts})")
                        return state
                    else:
                        if attempt < max_attempts - 1:
                            print(f"   ⏳ Post 按钮仍禁用，等待... ({attempt + 1}/{max_attempts})")
                            time.sleep(interval)
                else:
                    if attempt < max_attempts - 1:
                        print(f"   ⏳ 未找到 Post 按钮，等待... ({attempt + 1}/{max_attempts})")
                        time.sleep(interval)
                        
            except Exception as e:
                print(f"   ⚠️  轮询失败: {e}")
                time.sleep(interval)
        
        return {'found': False, 'error': '超时'}
    
    def try_submit_post(self) -> Dict:
        """
        尝试提交帖子（强制点击）
        
        Returns:
            Dict: 提交结果
        """
        try:
            result = self.page.evaluate("""
                () => {
                    // 策略 1: r-post-form-submit-button
                    const submitBtn = document.querySelector('r-post-form-submit-button#submit-post-button');
                    if (submitBtn) {
                        if (submitBtn.hasAttribute('disabled')) {
                            return { success: false, reason: "按钮已禁用" };
                        }
                        
                        // 尝试点击内部按钮
                        const internalBtn = submitBtn.shadowRoot?.querySelector('button') || 
                                          submitBtn.querySelector('button');
                        if (internalBtn) {
                            internalBtn.click();
                            return { success: true, method: 'internal-button-click' };
                        }
                        
                        // 直接点击组件
                        submitBtn.click();
                        return { success: true, method: 'component-click' };
                    }
                    
                    // 策略 2: Shadow DOM
                    const composer = document.querySelector('shreddit-composer');
                    if (composer && composer.shadowRoot) {
                        const postBtn = composer.shadowRoot.querySelector('button[type="submit"]');
                        if (postBtn) {
                            if (postBtn.disabled) {
                                return { success: false, reason: "Shadow DOM 按钮已禁用" };
                            }
                            postBtn.click();
                            return { success: true, method: 'shadow-dom-click' };
                        }
                    }
                    
                    return { success: false, reason: "未找到 Post 按钮" };
                }
            """)
            return result
        except Exception as e:
            return {'success': False, 'reason': f'异常: {str(e)}'}
    
    # ==================== 方案4: 深度递归序列化 ====================
    
    def serialize_flair_modal(self) -> Dict:
        """
        专门序列化 Flair 弹出框的完整结构
        
        Returns:
            Dict: Flair modal 的结构
        """
        try:
            # 先点击 Flair 按钮打开弹出框
            print("   🔄 打开 Flair 弹出框...")
            self.force_click_shadow_element(
                'shreddit-composer',
                "b => b.textContent.includes('flair') || b.textContent.includes('标记')"
            )
            time.sleep(2)
            
            # 序列化 Flair modal
            modal_structure = self.page.evaluate("""
                () => {
                    const modal = document.querySelector('shreddit-post-flair-modal');
                    if (!modal) {
                        return { error: 'Flair modal not found' };
                    }
                    
                    function extractElement(el, depth = 0) {
                        if (depth > 5) return null;
                        
                        const info = {
                            tag: el.tagName.toLowerCase(),
                            id: el.id,
                            className: el.className,
                            text: (el.textContent || '').trim().substring(0, 100),
                            attributes: {},
                            children: []
                        };
                        
                        // 提取关键属性
                        ['value', 'name', 'role', 'aria-label'].forEach(attr => {
                            const val = el.getAttribute(attr);
                            if (val) info.attributes[attr] = val;
                        });
                        
                        // 提取子元素
                        const children = Array.from(el.children || []);
                        for (const child of children) {
                            const childInfo = extractElement(child, depth + 1);
                            if (childInfo) info.children.push(childInfo);
                        }
                        
                        return info;
                    }
                    
                    return extractElement(modal);
                }
            """)
            
            # 关闭弹出框
            self.page.keyboard.press('Escape')
            time.sleep(1)
            
            return modal_structure
        except Exception as e:
            return {'error': str(e)}
    
    def get_all_flair_options(self) -> List[Dict]:
        """
        获取所有可用的 Flair 选项
        
        Returns:
            List[Dict]: Flair 选项列表
        """
        try:
            # 打开 Flair 对话框
            self.force_click_shadow_element(
                'shreddit-composer',
                "b => b.textContent.includes('flair') || b.textContent.includes('标记')"
            )
            time.sleep(2)
            
            # 获取所有 Flair 选项
            flairs = self.page.evaluate("""
                () => {
                    const rows = Array.from(document.querySelectorAll('shreddit-post-flair-row'));
                    return rows.map(row => {
                        const radio = row.querySelector('faceplate-radio-input');
                        const span = row.querySelector('span');
                        return {
                            id: radio?.getAttribute('value'),
                            text: span?.textContent?.trim(),
                            className: span?.className
                        };
                    }).filter(f => f.text);
                }
            """)
            
            # 关闭对话框
            self.page.keyboard.press('Escape')
            time.sleep(1)
            
            return flairs
        except Exception as e:
            print(f"   ⚠️  获取 Flair 选项失败: {e}")
            return []
    
    # ==================== 方案5: 提交后状态检测 ====================
    
    def detect_post_submission_result(self, wait_time: int = 8) -> Dict:
        """
        检测帖子提交后的结果（成功/失败/错误）
        
        Args:
            wait_time: 等待时间（秒）
        
        Returns:
            Dict: {
                'status': 'success' | 'error' | 'unknown',
                'error_message': str (如果有错误),
                'post_url': str (如果成功),
                'screenshot_path': str,
                'page_html_snapshot': str
            }
        """
        print(f"   ⏳ 等待 {wait_time} 秒观察结果...")
        time.sleep(wait_time)
        
        result = {
            'status': 'unknown',
            'error_message': None,
            'post_url': None,
            'screenshot_path': None,
            'page_html_snapshot': None
        }
        
        try:
            # 截图保存当前状态
            screenshot_path = Path(f"screenshots/reddit_post_result_{int(time.time())}.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            result['screenshot_path'] = str(screenshot_path)
            print(f"   📸 截图已保存: {screenshot_path}")
            
            # 获取页面 HTML 快照
            page_html = self.page.content()
            result['page_html_snapshot'] = page_html[:50000]  # 限制大小
            
            # 检查 1: URL 变化（成功的标志）
            current_url = self.page.url
            result['post_url'] = current_url
            
            if "/comments/" in current_url or "/posts/" in current_url:
                result['status'] = 'success'
                print(f"   ✅ 检测到 URL 变化，发帖成功")
                print(f"      帖子 URL: {current_url}")
                return result
            
            # 检查 2: 查找错误提示框
            error_detected = self._detect_error_dialogs()
            if error_detected:
                result['status'] = 'error'
                result['error_message'] = error_detected
                print(f"   ❌ 检测到错误提示: {error_detected}")
                return result
            
            # 检查 3: 查找常见的错误文本
            error_texts = self._find_error_texts_in_page()
            if error_texts:
                result['status'] = 'error'
                result['error_message'] = '; '.join(error_texts[:3])
                print(f"   ❌ 检测到错误文本: {result['error_message']}")
                return result
            
            # 检查 4: 页面是否仍在提交页
            if "/submit" in current_url:
                result['status'] = 'error'
                result['error_message'] = '仍在提交页面，可能提交失败'
                print(f"   ⚠️  仍在提交页面，可能提交失败")
                return result
            
            # 未知状态
            print(f"   ⚠️  无法确定提交状态")
            print(f"      当前 URL: {current_url}")
            return result
            
        except Exception as e:
            result['status'] = 'error'
            result['error_message'] = f'检测异常: {str(e)}'
            print(f"   ❌ 状态检测失败: {e}")
            return result
    
    def _detect_error_dialogs(self) -> Optional[str]:
        """
        检测错误对话框
        
        Returns:
            str: 错误消息，如果没有则返回 None
        """
        try:
            # 查找常见的错误对话框选择器
            error_selectors = [
                '[role="alert"]',
                '[class*="error"]',
                '[class*="Error"]',
                'faceplate-alert',
                'div[role="dialog"] [class*="error"]',
                '.shreddit-toast--error',
                '[data-testid*="error"]',
            ]
            
            for selector in error_selectors:
                try:
                    elements = self.page.locator(selector).all()
                    for elem in elements:
                        if elem.is_visible():
                            text = elem.text_content() or ''
                            if text and len(text.strip()) > 5:
                                return text.strip()[:500]
                except:
                    continue
            
            return None
        except Exception as e:
            print(f"   ⚠️  错误对话框检测失败: {e}")
            return None
    
    def _find_error_texts_in_page(self) -> List[str]:
        """
        在页面中查找错误文本
        
        Returns:
            List[str]: 错误文本列表
        """
        try:
            error_keywords = [
                'error', '错误', 'failed', '失败',
                'invalid', '无效', 'required', '必填',
                'too short', '太短', 'too long', '太长',
                'not allowed', '不允许', 'blocked', '被阻止'
            ]
            
            errors = []
            
            # 查找包含错误关键词的元素
            for keyword in error_keywords[:5]:  # 只检查前5个关键词
                try:
                    elements = self.page.get_by_text(keyword, exact=False).all()
                    for elem in elements[:3]:  # 每个关键词最多3个
                        if elem.is_visible():
                            text = elem.text_content() or ''
                            if text and len(text.strip()) > 10 and len(text.strip()) < 500:
                                # 避免重复
                                if text not in errors:
                                    errors.append(text.strip())
                except:
                    continue
            
            return errors[:5]  # 最多返回5个错误
        except Exception as e:
            print(f"   ⚠️  错误文本查找失败: {e}")
            return []
    
    def analyze_screenshot_with_ocr(self, screenshot_path: str) -> Dict:
        """
        使用 OCR 分析截图内容（需要安装 pytesseract）
        
        Args:
            screenshot_path: 截图路径
        
        Returns:
            Dict: OCR 分析结果
        """
        result = {
            'success': False,
            'text': '',
            'errors_found': []
        }
        
        try:
            import pytesseract
            from PIL import Image
            
            # 打开截图
            image = Image.open(screenshot_path)
            
            # 执行 OCR
            text = pytesseract.image_to_string(image, lang='chi_sim+eng')
            result['text'] = text
            result['success'] = True
            
            print(f"   📝 OCR 识别文本长度: {len(text)} 字符")
            
            # 查找错误关键词
            error_keywords = ['error', '错误', 'failed', '失败', 'invalid', '无效']
            lines = text.split('\n')
            
            for line in lines:
                line_lower = line.lower()
                if any(kw in line_lower for kw in error_keywords):
                    if len(line.strip()) > 5:
                        result['errors_found'].append(line.strip())
            
            if result['errors_found']:
                print(f"   ❌ OCR 检测到 {len(result['errors_found'])} 个错误:")
                for err in result['errors_found'][:3]:
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
    
    def handle_submission_error(self, error_message: str, original_title: str, 
                               original_content: str) -> Dict:
        """
        处理提交错误，生成修正后的内容
        
        Args:
            error_message: 错误消息
            original_title: 原始标题
            original_content: 原始内容
        
        Returns:
            Dict: 修正后的内容和建议
        """
        correction = {
            'should_retry': False,
            'corrected_title': original_title,
            'corrected_content': original_content,
            'suggestions': []
        }
        
        error_lower = error_message.lower()
        
        # 分析错误类型并给出建议
        if any(kw in error_lower for kw in ['title', '标题', 'short', '短', 'empty', '空']):
            correction['should_retry'] = True
            correction['corrected_title'] = original_title + " (Updated)"
            correction['suggestions'].append("标题可能太短或为空，已添加后缀")
        
        elif any(kw in error_lower for kw in ['content', '内容', 'body', '正文', 'short', '短']):
            correction['should_retry'] = True
            correction['corrected_content'] = original_content + "\n\nAdditional details added."
            correction['suggestions'].append("内容可能太短，已添加补充说明")
        
        elif any(kw in error_lower for kw in ['flair', '标记', '标识', 'required', '必填', 'select']):
            correction['should_retry'] = True
            correction['suggestions'].append("需要选择 Flair，请手动选择或跳过 Flair")
        
        elif any(kw in error_lower for kw in ['duplicate', '重复', 'similar', '相似', 'posted']):
            correction['should_retry'] = False
            correction['suggestions'].append("帖子可能重复，建议修改标题和内容后重试")
        
        elif any(kw in error_lower for kw in ['rate limit', '频率', 'too many', '太多', 'wait', '等待']):
            correction['should_retry'] = True
            correction['suggestions'].append("触发频率限制，建议等待 60 秒后重试")
        
        elif any(kw in error_lower for kw in ['permission', '权限', 'banned', '禁止', 'restricted']):
            correction['should_retry'] = False
            correction['suggestions'].append("没有发帖权限或被限制，请检查社区规则")
        
        else:
            correction['should_retry'] = True
            correction['suggestions'].append(f"未知错误: {error_message[:100]}")
            correction['suggestions'].append("建议简化内容后重试")
        
        return correction
    
    def complete_posting_workflow(self, title: str, content: str, 
                                  subreddit: str = "AnimoCerebro",
                                  flair_text: Optional[str] = None) -> Dict:
        """
        完整的发帖工作流
        
        Args:
            title: 标题
            content: 内容
            subreddit: 子版块
            flair_text: Flair 文本（可选）
        
        Returns:
            Dict: 执行结果
        """
        result = {
            'success': False,
            'steps': {}
        }
        
        try:
            # Step 1: 填写标题和内容
            print("\n📝 Step 1: 填写标题和内容...")
            title_input = self.page.locator('textarea[name="title"]').first
            if title_input.count() > 0:
                title_input.fill(title)
                result['steps']['title'] = True
                print("   ✓ 标题已填写")
            
            composer = self.page.locator('shreddit-composer').first
            if composer.count() > 0:
                composer.click()
                time.sleep(1)
                self.page.keyboard.type(content, delay=30)
                result['steps']['content'] = True
                print("   ✓ 内容已填写")
            
            # Step 2: 处理 Flair（如果提供）
            if flair_text:
                print(f"\n🏷️  Step 2: 选择 Flair '{flair_text}'...")
                
                # 方法 A: 尝试通过 UI 选择
                flairs = self.get_all_flair_options()
                if flairs:
                    print(f"   🔍 找到 {len(flairs)} 个 Flair 选项")
                    for flair in flairs:
                        if flair_text.lower() in flair['text'].lower():
                            # 重新打开对话框并选择
                            self.force_click_shadow_element(
                                'shreddit-composer',
                                "b => b.textContent.includes('flair') || b.textContent.includes('标记')"
                            )
                            time.sleep(1)
                            
                            # 点击对应的 Flair
                            self.page.evaluate(f"""
                                () => {{
                                    const rows = Array.from(document.querySelectorAll('shreddit-post-flair-row'));
                                    const target = rows.find(r => {{
                                        const span = r.querySelector('span');
                                        return span && span.textContent.includes('{flair_text}');
                                    }});
                                    if (target) {{
                                        const radio = target.querySelector('faceplate-radio-input');
                                        if (radio) radio.click();
                                        
                                        // 点击 Apply
                                        setTimeout(() => {{
                                            const applyBtn = document.querySelector('button:has-text("Apply"), button:has-text("确认")');
                                            if (applyBtn) applyBtn.click();
                                        }}, 500);
                                    }}
                                }}
                            """)
                            time.sleep(2)
                            result['steps']['flair'] = True
                            print(f"   ✓ 已选择 Flair: {flair['text']}")
                            break
                    else:
                        print(f"   ⚠️  未找到匹配的 Flair: {flair_text}")
                        result['steps']['flair'] = False
                else:
                    print("   ⚠️  未获取到 Flair 选项")
                    result['steps']['flair'] = False
            else:
                result['steps']['flair'] = 'skipped'
            
            # Step 3: 等待 Post 按钮就绪
            print("\n🔘 Step 3: 等待 Post 按钮就绪...")
            button_state = self.poll_post_button_state(max_attempts=10, interval=1)
            result['steps']['button_ready'] = button_state.get('found') and not button_state.get('disabled')
            
            # Step 4: 提交帖子
            print("\n🚀 Step 4: 提交帖子...")
            submit_result = self.try_submit_post()
            result['steps']['submit'] = submit_result.get('success')
            
            if submit_result.get('success'):
                print(f"   ✅ 提交成功 (方法: {submit_result.get('method')})")
                
                # 等待发布完成
                print("   ⏳ 等待发布完成...")
                time.sleep(10)
                
                # 检查 URL 变化
                current_url = self.page.url
                if "/comments/" in current_url or "/posts/" in current_url:
                    result['success'] = True
                    result['post_url'] = current_url
                    print(f"   ✅ 帖子发布成功: {current_url}")
                else:
                    print(f"   ⚠️  URL 未变化: {current_url}")
            else:
                print(f"   ❌ 提交失败: {submit_result.get('reason')}")
            
            return result
            
        except Exception as e:
            result['error'] = str(e)
            print(f"\n❌ 工作流失败: {e}")
            import traceback
            traceback.print_exc()
            return result


# 使用示例
if __name__ == "__main__":
    print("Reddit Advanced Helper - 测试模块")
    print("请通过 test_social_media_automation.py 调用此模块")

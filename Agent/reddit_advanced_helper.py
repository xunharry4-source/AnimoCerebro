#!/usr/bin/env python3
"""
Reddit 高级自动化助手

整合多种方案解决 Shadow DOM、动态加载和 Web Components 问题
"""

import asyncio
import time
import json
import logging
from typing import Dict, List, Optional, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class RedditAdvancedHelper:
    """Reddit 高级自动化助手 - 解决复杂DOM结构问题"""
    
    def __init__(self, page):
        self.page = page
    
    # ==================== 方案1: Shadow DOM 穿透 ====================
    
    async def force_click_shadow_element(self, composer_selector: str = 'shreddit-composer',
                                   element_logic: str = "b => b.textContent.includes('flair')") -> bool:
        """
        通过 JS 逻辑在 Shadow Root 中寻找并点击元素
        """
        try:
            result = await self.page.evaluate(f"""
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
    
    async def get_composer_shadow_buttons(self) -> List[Dict]:
        """获取 shreddit-composer Shadow DOM 中的所有按钮"""
        try:
            buttons = await self.page.evaluate("""
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
    
    async def intercept_flair_data(self, timeout: int = 10) -> List[Dict]:
        """拦截 Reddit Flair API 响应"""
        flairs = []
        def handle_response(response):
            nonlocal flairs
            try:
                url = response.url.lower()
                if any(keyword in url for keyword in ['api/v1/flair', 'gql', 'flairselector']):
                    if 'application/json' in response.headers.get('content-type', ''):
                        try:
                            data = response.json()
                            if isinstance(data, dict):
                                for key in ['data', 'flairs', 'choices', 'options']:
                                    if key in data and isinstance(data[key], list):
                                        flairs.extend(data[key]); break
                            elif isinstance(data, list): flairs.extend(data)
                        except: pass
            except: pass
        
        self.page.on("response", handle_response)
        await self.page.reload(wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(timeout)
        return flairs
    
    async def set_flair_by_id(self, flair_id: str) -> bool:
        """直接通过 ID 设置 Flair"""
        try:
            result = await self.page.evaluate(f"""
                (flairId) => {{
                    const composer = document.querySelector('shreddit-composer');
                    if (!composer) return false;
                    composer.flairId = flairId;
                    const event = new CustomEvent('flair-selected', {{ detail: {{ flairId: flairId }} }});
                    composer.dispatchEvent(event);
                    return true;
                }}
            """, flair_id)
            return result
        except Exception as e:
            print(f"   ⚠️  设置 Flair 失败: {e}")
            return False
    
    # ==================== 方案3: Post 按钮状态轮询 ====================
    
    async def poll_post_button_state(self, max_attempts: int = 20, interval: float = 0.5) -> Dict:
        """主动轮询 Post 按钮状态"""
        for attempt in range(max_attempts):
            try:
                state = await self.page.evaluate("""
                    () => {
                        const submitBtn = document.querySelector('r-post-form-submit-button#submit-post-button');
                        if (submitBtn) {
                            return { found: true, type: 'custom-component', id: submitBtn.id, disabled: submitBtn.hasAttribute('disabled') };
                        }
                        const composer = document.querySelector('shreddit-composer');
                        if (composer && composer.shadowRoot) {
                            const shadowBtn = composer.shadowRoot.querySelector('button[type="submit"]');
                            if (shadowBtn) {
                                return { found: true, type: 'shadow-dom', disabled: shadowBtn.disabled };
                            }
                        }
                        return { found: false };
                    }
                """)
                
                if state.get('found') and not state.get('disabled'):
                    return state
                
                await asyncio.sleep(interval)
            except Exception as e:
                await asyncio.sleep(interval)
        
        return {'found': False, 'error': '超时'}
    
    async def try_submit_post(self) -> Dict:
        """尝试提交帖子"""
        try:
            result = await self.page.evaluate("""
                () => {
                    const submitBtn = document.querySelector('r-post-form-submit-button#submit-post-button');
                    if (submitBtn) {
                        const internalBtn = submitBtn.shadowRoot?.querySelector('button') || submitBtn.querySelector('button');
                        if (internalBtn) { internalBtn.click(); return { success: true, method: 'internal-button-click' }; }
                        submitBtn.click(); return { success: true, method: 'component-click' };
                    }
                    const composer = document.querySelector('shreddit-composer');
                    if (composer && composer.shadowRoot) {
                        const postBtn = composer.shadowRoot.querySelector('button[type="submit"]');
                        if (postBtn) { postBtn.click(); return { success: true, method: 'shadow-dom-click' }; }
                    }
                    return { success: false, reason: "未找到 Post 按钮" };
                }
            """)
            return result
        except Exception as e:
            return {'success': False, 'reason': f'异常: {str(e)}'}
    
    # ==================== 方案4: 深度递归序列化 ====================
    
    async def serialize_flair_modal(self) -> Dict:
        """专门序列化 Flair 弹出框的完整结构"""
        try:
            print("   🔄 打开 Flair 弹出框...")
            await self.force_click_shadow_element(
                'shreddit-composer',
                "b => b.textContent.includes('flair') || b.textContent.includes('标记')"
            )
            await asyncio.sleep(2)
            
            modal_structure = await self.page.evaluate("""
                () => {
                    const modal = document.querySelector('shreddit-post-flair-modal');
                    if (!modal) return { error: 'Flair modal not found' };
                    function extractElement(el, depth = 0) {
                        if (depth > 5) return null;
                        const info = { tag: el.tagName.toLowerCase(), id: el.id, text: (el.textContent || '').trim().substring(0, 100), attributes: {}, children: [] };
                        ['value', 'name', 'role', 'aria-label'].forEach(attr => { const val = el.getAttribute(attr); if (val) info.attributes[attr] = val; });
                        Array.from(el.children || []).forEach(child => { const childInfo = extractElement(child, depth + 1); if (childInfo) info.children.push(childInfo); });
                        return info;
                    }
                    return extractElement(modal);
                }
            """)
            await self.page.keyboard.press('Escape')
            await asyncio.sleep(1)
            return modal_structure
        except Exception as e:
            return {'error': str(e)}
    
    async def get_all_flair_options(self) -> List[Dict]:
        """获取所有可用的 Flair 选项"""
        try:
            await self.force_click_shadow_element(
                'shreddit-composer',
                "b => b.textContent.includes('flair') || b.textContent.includes('标记')"
            )
            await asyncio.sleep(2)
            flairs = await self.page.evaluate("""
                () => {
                    const rows = Array.from(document.querySelectorAll('shreddit-post-flair-row'));
                    return rows.map(row => {
                        const radio = row.querySelector('faceplate-radio-input');
                        const span = row.querySelector('span');
                        return { id: radio?.getAttribute('value'), text: span?.textContent?.trim() };
                    }).filter(f => f.text);
                }
            """)
            await self.page.keyboard.press('Escape')
            await asyncio.sleep(1)
            return flairs
        except Exception as e:
            print(f"   ⚠️  获取 Flair 选项失败: {e}")
            return []
    
    # ==================== 方案5: 提交后状态检测 ====================
    
    async def detect_post_submission_result(self, wait_time: int = 8) -> Dict:
        """检测帖子提交后的结果"""
        print(f"   ⏳ 等待 {wait_time} 秒观察结果...")
        await asyncio.sleep(wait_time)
        
        result = { 'status': 'unknown', 'error_message': None, 'post_url': None }
        
        try:
            current_url = self.page.url
            result['post_url'] = current_url
            if "/comments/" in current_url or "/posts/" in current_url:
                result['status'] = 'success'
                return result
            
            error_detected = await self._detect_error_dialogs()
            if error_detected:
                result['status'] = 'error'
                result['error_message'] = error_detected
                return result
            
            error_texts = await self._find_error_texts_in_page()
            if error_texts:
                result['status'] = 'error'
                result['error_message'] = '; '.join(error_texts[:3])
                return result
            
            if "/submit" in current_url:
                result['status'] = 'error'
                result['error_message'] = '仍在提交页面，可能提交失败'
                return result
            
            return result
        except Exception as e:
            result['status'] = 'error'
            result['error_message'] = f'检测异常: {str(e)}'
            return result
    
    async def _detect_error_dialogs(self) -> Optional[str]:
        """检测错误对话框"""
        try:
            error_selectors = ['[role="alert"]', '[class*="error"]', '[class*="Error"]', 'faceplate-alert', '.shreddit-toast--error']
            for selector in error_selectors:
                try:
                    elements = await self.page.locator(selector).all()
                    for elem in elements:
                        if await elem.is_visible():
                            text = await elem.text_content()
                            if text and len(text.strip()) > 5: return text.strip()[:500]
                except: continue
            return None
        except: return None
    
    async def _find_error_texts_in_page(self) -> List[str]:
        """在页面中查找错误文本"""
        try:
            error_keywords = ['error', '错误', 'failed', '失败', 'invalid', '无效']
            errors = []
            for keyword in error_keywords:
                try:
                    elements = await self.page.get_by_text(keyword, exact=False).all()
                    for elem in elements[:3]:
                        if await elem.is_visible():
                            text = await elem.text_content()
                            if text and 10 < len(text.strip()) < 500:
                                if text not in errors: errors.append(text.strip())
                except: continue
            return errors[:5]
        except: return []
    
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
    
    async def complete_posting_workflow(self, title: str, content: str, 
                                   subreddit: str = "AnimoCerebro",
                                   flair_text: Optional[str] = None) -> Dict:
        """完整的发帖工作流"""
        result = { 'success': False, 'steps': {} }
        try:
            print("\n📝 Step 1: 填写标题和内容...")
            title_input = self.page.locator('textarea[name="title"]').first
            if await title_input.count() > 0:
                await title_input.fill(title)
                result['steps']['title'] = True
            
            composer = self.page.locator('shreddit-composer').first
            if await composer.count() > 0:
                await composer.click()
                await asyncio.sleep(1)
                await self.page.keyboard.type(content, delay=30)
                result['steps']['content'] = True
            
            if flair_text:
                print(f"\n🏷️  Step 2: 选择 Flair '{flair_text}'...")
                flairs = await self.get_all_flair_options()
                if flairs:
                    for flair in flairs:
                        if flair_text.lower() in flair['text'].lower():
                            await self.force_click_shadow_element('shreddit-composer', f"b => b.textContent.includes('{flair_text}')")
                            await asyncio.sleep(2)
                            result['steps']['flair'] = True; break
            
            print("\n🔘 Step 3: 等待 Post 按钮就绪...")
            button_state = await self.poll_post_button_state(max_attempts=10, interval=1)
            
            print("\n🚀 Step 4: 提交帖子...")
            submit_result = await self.try_submit_post()
            if submit_result.get('success'):
                await asyncio.sleep(10)
                if "/comments/" in self.page.url or "/posts/" in self.page.url:
                    result['success'] = True
                    result['post_url'] = self.page.url
            return result
        except Exception as e:
            result['error'] = str(e)
            return result


# 使用示例
if __name__ == "__main__":
    print("Reddit Advanced Helper - 测试模块")
    print("请通过 test_social_media_automation.py 调用此模块")

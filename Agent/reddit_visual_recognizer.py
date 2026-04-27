#!/usr/bin/env python3
"""
Reddit Tesseract OCR 视觉识别模块

文件用途:
    为 Reddit 发帖页面提供基于 Tesseract OCR 和 DOM 检查的视觉识别辅助能力。

主要职责:
    - 识别页面文字和 Flair 选项位置
    - 选择指定 Flair
    - 点击 Reddit 提交按钮
    - 在提交后验证是否真的生成了帖子 URL 或明确失败原因
    - 将发帖后弹窗文本交给 LLM 翻译和语义分类

不负责:
    - 不管理 Reddit 登录状态和账号凭据
    - 不绕过验证码、风控或社区限制
    - 不在只有点击指令、没有发布证据时宣称发帖成功
    - 不用静态关键词冒充社区弹窗语义理解
"""

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class RedditVisualRecognizer:
    """Reddit 视觉识别器 - 使用 Tesseract OCR"""
    
    def __init__(
        self,
        page,
        screenshot_dir: str = "screenshots",
        llm_popup_interpreter: Optional[Any] = None,
        enable_llm_popup_interpreter: bool = True,
    ):
        self.page = page
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(exist_ok=True)
        self.llm_popup_interpreter = llm_popup_interpreter
        self.enable_llm_popup_interpreter = enable_llm_popup_interpreter
        
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
        result = self.select_flair_with_ocr(target_flair=target_flair, max_attempts=max_attempts)
        if not result["success"]:
            print(f"   ❌ Flair 选择失败: {result.get('error')}")
        return result["success"]

    def select_flair_with_ocr(
        self,
        target_flair: str = None,
        preferred_keywords: List[str] = None,
        max_attempts: int = 3
    ) -> Dict:
        """
        打开 Flair 弹窗、OCR 识别候选项、选择目标或最合适项、点击 Apply 并验证。

        Args:
            target_flair: 首选 Flair 文本，允许为空。
            preferred_keywords: target_flair 找不到时用于选择合适 Flair 的关键词。
            max_attempts: 最大尝试次数。

        Returns:
            Dict: 选择结果，包含 success、selected_text、screenshot_path、error。
        """
        if not self.ocr_helper:
            return {'success': False, 'error': 'TesseractOCRHelper 未初始化'}

        preferred_keywords = preferred_keywords or self._default_flair_keywords(target_flair)
        print(f"\n🏷️  使用 OCR 选择 Flair: {target_flair or preferred_keywords}")

        last_error = None
        for attempt in range(1, max_attempts + 1):
            print(f"\n   Flair 尝试 {attempt}/{max_attempts}")

            print("   Step 1: 打开 Flair 对话框...")
            if not self._open_flair_dialog():
                last_error = '无法打开 Flair 对话框'
                print(f"   ❌ {last_error}")
                continue

            if not self._is_flair_dialog_open():
                time.sleep(1)
            if not self._is_flair_dialog_open():
                last_error = 'Flair 对话框未打开或无法验证'
                print(f"   ❌ {last_error}")
                continue

            print("   Step 2: 截图并 OCR 识别 Flair 选项...")
            screenshot_path = str(self.screenshot_dir / f"flair_dialog_{int(time.time())}.png")
            self.page.screenshot(path=screenshot_path, full_page=True)
            ocr_results = self.ocr_helper.recognize_with_position(screenshot_path, lang='chi_sim+eng')
            if not ocr_results:
                last_error = 'OCR 未识别到 Flair 弹窗文字'
                print(f"   ❌ {last_error}")
                self._close_flair_dialog()
                continue

            grouped_texts = self._group_nearby_texts(ocr_results)
            candidates = self._extract_flair_candidates(grouped_texts)
            print(f"   📝 OCR 候选 Flair: {len(candidates)} 个")
            for i, item in enumerate(candidates[:12]):
                print(f"      [{i}] \"{item['text']}\" score={item['score']:.2f} conf={item['confidence']:.1f}")

            selected = self._choose_flair_candidate(
                candidates=candidates,
                target_flair=target_flair,
                preferred_keywords=preferred_keywords
            )
            if not selected:
                last_error = '未找到可选择的 Flair 候选'
                print(f"   ❌ {last_error}")
                self._close_flair_dialog()
                continue

            print(f"   Step 3: 点击 Flair 候选 \"{selected['text']}\"")
            if not self._click_flair_candidate(selected):
                last_error = f"点击 Flair 候选失败: {selected['text']}"
                print(f"   ❌ {last_error}")
                self._close_flair_dialog()
                continue

            time.sleep(1)

            print("   Step 4: 点击 Apply/确认...")
            if not self._click_apply_button():
                last_error = 'Apply/确认按钮点击失败'
                print(f"   ❌ {last_error}")
                self._close_flair_dialog()
                continue

            if not self._wait_for_flair_dialog_closed(timeout=5):
                last_error = 'Apply 后 Flair 对话框未关闭'
                print(f"   ❌ {last_error}")
                self._close_flair_dialog()
                continue

            if not self._verify_flair_applied(selected['text'], target_flair):
                last_error = f"Flair 对话框已关闭，但页面未验证到已选择: {selected['text']}"
                print(f"   ❌ {last_error}")
                self._save_result_screenshot('flair_apply_unverified')
                continue

            print(f"   ✅✅✅ Flair 设置成功: {selected['text']}")
            return {
                'success': True,
                'selected_text': selected['text'],
                'match_type': selected.get('match_type'),
                'screenshot_path': screenshot_path
            }

        return {'success': False, 'error': last_error or 'Flair 选择失败'}

    def _default_flair_keywords(self, target_flair: str = None) -> List[str]:
        """生成 Flair 候选排序关键词，优先匹配目标文本。"""
        keywords = []
        if target_flair:
            keywords.extend(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', target_flair))

        keywords.extend([
            'discussion', '讨论', 'question', '问题', 'project', 'showcase',
            '技术', '分享', 'general', 'other', '其他'
        ])
        return [kw.lower() for kw in keywords if kw]

    def _is_flair_dialog_open(self) -> bool:
        """验证 Flair 弹窗是否打开。"""
        try:
            dom_detected = bool(self.page.evaluate("""
                () => {
                    const componentSelectors = [
                        'shreddit-post-flair-modal',
                        'reddit-post-flair-modal'
                    ];
                    for (const selector of componentSelectors) {
                        const node = document.querySelector(selector);
                        if (!node) continue;
                        const visible = Boolean(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
                        if (visible) return true;
                    }

                    const dialogs = Array.from(document.querySelectorAll('[role="dialog"]'));
                    for (const dialog of dialogs) {
                        const dialogText = [
                            dialog.innerText || dialog.textContent || '',
                            dialog.getAttribute('aria-label') || '',
                            ...Array.from(dialog.querySelectorAll('[role="radio"], input[type="radio"]'))
                                .map((node) => node.getAttribute('aria-label') || node.textContent || '')
                        ].join('\\n');
                        if (
                            dialogText.includes('flair') ||
                            dialogText.includes('Flair') ||
                            dialogText.includes('添加标识') ||
                            dialogText.includes('添加标记') ||
                            dialogText.includes('帖子标识') ||
                            dialogText.includes('标识和标记')
                        ) {
                            return true;
                        }
                    }

                    const text = document.body?.innerText || '';
                    const hasDialogWords = text.includes('Apply') ||
                                           text.includes('Add') ||
                                           text.includes('添加') ||
                                           text.includes('确认') ||
                                           text.includes('确定');
                    const hasAdultOption = text.includes('不适合工作场合') ||
                                           (text.includes('适合') && text.includes('工作') && text.includes('场合')) ||
                                           (text.includes('包含') && text.includes('成'));
                    const hasOptionWords = hasAdultOption ||
                                           text.includes('剧透') ||
                                           text.includes('品牌关联') ||
                                           text.includes('成人内容');
                    return hasDialogWords && hasOptionWords;
                }
            """))
            if dom_detected:
                return True
        except Exception as e:
            print(f"   ⚠️  Flair 弹窗状态检测失败: {e}")
        return self._is_flair_dialog_open_visual()

    def _is_flair_dialog_open_visual(self) -> bool:
        """
        用 OCR 视觉证据兜底判断 Flair 弹窗。

        Reddit 的中文 Flair 弹窗文本可能藏在 Web Component/Shadow DOM 中，
        DOM innerText 不稳定；视觉截图能确认用户实际看到的弹窗。
        """
        if not self.ocr_helper:
            return False
        try:
            screenshot_path = str(self.screenshot_dir / "flair_dialog_state.png")
            self.page.screenshot(path=screenshot_path, full_page=False)
            ocr_results = self.ocr_helper.recognize_with_position(screenshot_path, lang='chi_sim+eng')
            grouped = self._group_nearby_texts(ocr_results)
            text = " ".join(self._normalize_ocr_text(item.get('text', '')) for item in grouped)
            has_adult_option = (
                '不适合工作场合' in text
                or all(keyword in text for keyword in ['适合', '工作', '场合'])
                or all(keyword in text for keyword in ['包含', '成'])
            )
            has_option = has_adult_option or any(keyword in text for keyword in ['剧透', '品牌关联', '成人内容'])
            has_action = any(keyword in text for keyword in ['添加', '取消', 'Apply', 'Add'])
            return bool(has_option and has_action)
        except Exception as exc:
            print(f"   ⚠️  Flair 弹窗视觉检测失败: {exc}")
            return False

    def _close_flair_dialog(self):
        """关闭 Flair 弹窗，避免下一次 OCR 被旧弹窗污染。"""
        try:
            for selector in [
                'button[aria-label="Close"]',
                'button:has-text("Cancel")',
                'button:has-text("取消")',
                '[role="dialog"] button:has-text("Close")'
            ]:
                button = self.page.locator(selector).first
                if button.count() > 0 and button.is_visible():
                    button.click(timeout=3000)
                    time.sleep(0.5)
                    return
        except Exception:
            pass

        try:
            self.page.keyboard.press('Escape')
            time.sleep(0.5)
        except Exception:
            pass

    def detect_flair_requirement(self) -> Dict[str, Any]:
        """Detect whether Reddit currently requires a post Flair.

        The workflow needs an explicit, structured answer before deciding
        whether to open the Flair dialog. A missing optional control is not a
        failure, but a browser evaluation failure must fail closed through the
        caller rather than being reported as "not required".
        """
        result = self.page.evaluate("""
            () => {
                const selectors = [
                    'button#reddit-post-flair-button',
                    '[data-testid="flair-picker"]',
                    'shreddit-composer-flair',
                    'reddit-post-flair-button',
                    'r-post-flairs-modal',
                    'r-post-tags-section',
                    '[name="flair"]',
                    '[aria-label*="flair" i]',
                    '[aria-label*="标记"]',
                    '[aria-label*="标识"]'
                ];
                const controls = [];
                for (const selector of selectors) {
                    for (const node of document.querySelectorAll(selector)) {
                        const text = (node.innerText || node.textContent || '').trim();
                        const aria = node.getAttribute('aria-label') || '';
                        const requiredAttr = node.getAttribute('required') !== null ||
                            node.getAttribute('aria-required') === 'true' ||
                            node.hasAttribute('flairs-required');
                        const optionTexts = Array.from(node.querySelectorAll('data[data-text]'))
                            .map((item) => item.getAttribute('data-text') || '')
                            .filter(Boolean);
                        controls.push({
                            selector,
                            text,
                            aria,
                            requiredAttr,
                            visible: Boolean(node.offsetWidth || node.offsetHeight || node.getClientRects().length),
                            optionTexts
                        });
                    }
                }

                const html = document.documentElement?.outerHTML || '';
                const markupRequired = Boolean(document.querySelector(
                    'r-post-flairs-modal[flairs-required], [name="flair"][flairs-required], [flairs-required]'
                )) || /<r-post-flairs-modal[^>]*\\sflairs-required\\b/i.test(html);
                const markupOptions = Array.from(document.querySelectorAll('r-post-flairs-modal data[data-text], [name="flair"] data[data-text]'))
                    .map((item) => item.getAttribute('data-text') || '')
                    .filter(Boolean);

                const alertSelectors = [
                    '[role="alert"]',
                    '[aria-live="assertive"]',
                    '[aria-live="polite"]',
                    '.error',
                    '.text-error',
                    '[class*="error"]',
                    '[style*="red"]'
                ];
                const alertText = Array.from(document.querySelectorAll(alertSelectors.join(',')))
                    .map((node) => (node.innerText || node.textContent || '').trim())
                    .filter(Boolean)
                    .join('\\n');
                const combined = `${controls.map((item) => `${item.text} ${item.aria}`).join('\\n')}\\n${alertText}`.toLowerCase();
                const mentionsFlair = combined.includes('flair') || combined.includes('tag') ||
                    combined.includes('标记') || combined.includes('标识');
                const mentionsRequired = combined.includes('required') || combined.includes('must') ||
                    combined.includes('需要') || combined.includes('必填') || combined.includes('*');
                const attrRequired = controls.some((item) => item.requiredAttr);
                const required = attrRequired || markupRequired || (mentionsFlair && mentionsRequired);
                return {
                    required,
                    reason: required ? 'flair_required_signal_detected' : 'no_required_signal',
                    has_flair_control: controls.length > 0 || markupOptions.length > 0 || markupRequired,
                    controls,
                    markup_required: markupRequired,
                    markup_options: markupOptions,
                    alert_text: alertText.slice(0, 1000)
                };
            }
        """)
        if not isinstance(result, dict):
            return {
                "required": bool(result),
                "reason": "legacy_boolean_detection",
                "has_flair_control": False,
                "controls": [],
                "alert_text": "",
            }
        return result

    def extract_flair_candidates_from_dom(self) -> List[Dict]:
        """Read real Reddit flair options from the current Web Component DOM."""
        try:
            candidates = self.page.evaluate("""
                () => {
                    const rows = [];
                    const seen = new Set();
                    const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                    const blocked = [
                        '添加标识和标记', '添加标记', '添加标识', '帖子标识选择表',
                        '搜索', '查看所有标识', '取消', '添加', 'apply', 'cancel',
                        '标记', '不适合工作场合', '包含成人内容', '剧透', '品牌关联'
                    ];
                    const pushRow = (row) => {
                        const text = normalize(row.text);
                        const lowered = text.toLowerCase();
                        if (!text || text.length > 80) return;
                        if (blocked.some((word) => lowered === word || lowered.includes(word.toLowerCase()))) return;
                        const key = lowered.replace(/^[^\\p{L}\\p{N}]+/u, '');
                        if (seen.has(key)) return;
                        seen.add(key);
                        rows.push({
                            ...row,
                            text,
                            is_none_option: lowered.includes('无标识') ||
                                lowered.includes('no flair') ||
                                lowered.includes('none')
                        });
                    };

                    const modals = document.querySelectorAll(
                        'r-post-flairs-modal, shreddit-post-flair-modal, reddit-post-flair-modal'
                    );
                    for (const modal of modals) {
                        for (const item of modal.querySelectorAll('data[data-text]')) {
                            const text = item.getAttribute('data-text') || '';
                            if (!text.trim()) continue;
                            pushRow({
                                text,
                                id: item.getAttribute('data-id') || '',
                                background_color: item.getAttribute('data-background-color') || '',
                                text_color: item.getAttribute('data-text-color') || '',
                                editable: item.getAttribute('data-is-editable') === 'true',
                                source: 'reddit_flair_modal_dom_data'
                            });
                        }
                    }

                    const dialog = document.querySelector(
                        '[role="dialog"], shreddit-post-flair-modal, reddit-post-flair-modal, r-post-flairs-modal'
                    );
                    const root = dialog || document;
                    const radioNodes = Array.from(root.querySelectorAll('[role="radio"], input[type="radio"]'));
                    for (const node of radioNodes) {
                        const container = node.closest('label, [role="listitem"], li, div') || node;
                        const text = normalize(
                            node.getAttribute('aria-label') ||
                            node.getAttribute('title') ||
                            container.innerText ||
                            container.textContent ||
                            node.textContent
                        );
                        pushRow({
                            text,
                            id: node.getAttribute('id') || node.getAttribute('value') || '',
                            selected: node.getAttribute('aria-checked') === 'true' || node.checked === true,
                            source: 'reddit_flair_dialog_radio'
                        });
                    }
                    return rows;
                }
            """)
        except Exception as exc:
            print(f"   ⚠️  Flair DOM 候选读取失败: {exc}")
            return []
        if not isinstance(candidates, list):
            return []
        return [dict(item) for item in candidates if isinstance(item, dict) and item.get('text')]

    def expand_all_flair_options(self) -> bool:
        """Expand Reddit's collapsed Flair list when the dialog exposes a view-all control."""
        try:
            clicked = self.page.evaluate("""
                () => {
                    const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                    const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
                    const target = buttons.find((button) => {
                        const text = normalize(button.innerText || button.textContent || button.getAttribute('aria-label'));
                        return text.includes('查看所有标识') ||
                            text.includes('查看所有标记') ||
                            text.toLowerCase().includes('view all flair') ||
                            text.toLowerCase().includes('view all flairs');
                    });
                    if (!target) return false;
                    target.click();
                    return true;
                }
            """)
            if clicked:
                time.sleep(0.5)
                print("   ✅ 已展开全部 Flair 选项")
            return bool(clicked)
        except Exception as exc:
            print(f"   ⚠️  展开全部 Flair 选项失败: {exc}")
            return False

    def extract_community_rules_from_submit_page_dom(self) -> List[Dict[str, Any]]:
        """Extract real community rules already rendered on the Reddit submit page."""
        try:
            rules = self.page.evaluate("""
                () => {
                    const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                    const rightSidebar = document.querySelector('#right-sidebar-container');
                    if (!rightSidebar) return [];
                    const headings = Array.from(rightSidebar.querySelectorAll('h2, h3'));
                    const rulesHeading = headings.find((node) => {
                        const text = normalize(node.textContent).toLowerCase();
                        return text.includes('规则') || text.includes('rules');
                    });
                    const scope = rulesHeading?.closest('section') || rightSidebar;
                    const detailsNodes = Array.from(scope.querySelectorAll('details'));
                    const rows = [];
                    const seen = new Set();
                    for (const details of detailsNodes) {
                        const summary = details.querySelector('summary');
                        if (!summary) continue;
                        const number = normalize(summary.querySelector('.text-14, [class*="text-14"]')?.textContent || '');
                        const titleNode = summary.querySelector('h2, h3, [class*="i18n-translatable-text"]');
                        let title = normalize(titleNode?.textContent || summary.textContent || '');
                        if (number && title.startsWith(number)) {
                            title = normalize(title.slice(number.length));
                        }
                        title = title.replace(/^Rule\\s*\\d+\\s*:?\\s*/i, '');
                        const contentNode = details.querySelector(
                            '[faceplate-auto-height-animator-content], [id^="rule-"], .md'
                        );
                        const description = normalize(contentNode?.textContent || '');
                        if (!title || !description || title.length > 120 || description.length < 20) continue;
                        const key = title.toLowerCase();
                        if (seen.has(key)) continue;
                        seen.add(key);
                        rows.push({
                            title,
                            description,
                            number,
                            source: 'reddit_submit_page_dom'
                        });
                    }
                    return rows.slice(0, 20);
                }
            """)
        except Exception as exc:
            print(f"   ⚠️  Reddit 页面规则读取失败: {exc}")
            return []
        if not isinstance(rules, list):
            return []
        return [dict(item) for item in rules if isinstance(item, dict) and item.get("title")]

    def _extract_flair_candidates(self, grouped_texts: List[Dict]) -> List[Dict]:
        """
        从 OCR 文本行中过滤可点击 Flair 候选。

        Reddit 弹窗中会包含标题、搜索框、Apply/Cancel 等非 Flair 文案；
        这些必须排除，否则坐标点击会点错控件。
        """
        blocked = {
            'apply', 'cancel', 'search', 'flair', '添加标记', '选择标记',
            'post flair', 'clear', 'done', '确认', '取消', '搜索'
        }
        candidates = []
        bounds = self._get_flair_dialog_bounds()

        for item in grouped_texts:
            text = self._normalize_ocr_text(item.get('text', ''))
            if not text:
                continue
            if bounds and not self._point_in_bounds(item.get('center_x'), item.get('center_y'), bounds):
                continue

            lowered = text.lower()
            if any(word == lowered or word in lowered for word in blocked):
                continue
            if item.get('confidence', 0) < 35:
                continue
            if len(text) > 80:
                continue

            candidate = dict(item)
            candidate['text'] = text
            candidate['score'] = item.get('confidence', 0) / 100
            candidates.append(candidate)

        return candidates

    def _get_flair_dialog_bounds(self) -> Optional[Dict[str, float]]:
        """
        返回 Flair 弹窗的大致边界。

        优先使用真实 DOM bounding box；如果 Reddit Web Component 不暴露稳定 DOM，
        使用居中弹窗的保守视觉区域，避免 OCR 把背景规则栏当成 Flair 候选。
        """
        try:
            bounds = self.page.evaluate("""
                () => {
                    const selectors = ['[role="dialog"]', 'shreddit-post-flair-modal', 'reddit-post-flair-modal'];
                    for (const selector of selectors) {
                        const node = document.querySelector(selector);
                        if (!node) continue;
                        const rect = node.getBoundingClientRect();
                        if (rect.width > 200 && rect.height > 150) {
                            return {
                                left: rect.left,
                                top: rect.top,
                                right: rect.right,
                                bottom: rect.bottom
                            };
                        }
                    }
                    return null;
                }
            """)
            if isinstance(bounds, dict) and bounds.get('right', 0) > bounds.get('left', 0):
                parsed = {key: float(bounds[key]) for key in ['left', 'top', 'right', 'bottom']}
                width = parsed["right"] - parsed["left"]
                height = parsed["bottom"] - parsed["top"]
                if 300 <= width <= 900 and 220 <= height <= 650:
                    return parsed
        except Exception as exc:
            print(f"   ⚠️  获取 Flair 弹窗 DOM 边界失败: {exc}")

        try:
            viewport = self.page.viewport_size or {"width": 1920, "height": 1080}
        except Exception:
            viewport = {"width": 1920, "height": 1080}
        width = float(viewport.get("width") or 1920)
        height = float(viewport.get("height") or 1080)
        return {
            "left": width * 0.35,
            "top": height * 0.34,
            "right": width * 0.65,
            "bottom": height * 0.66,
        }

    def _point_in_bounds(self, x: Any, y: Any, bounds: Dict[str, float]) -> bool:
        """判断 OCR 坐标是否在 Flair 弹窗可点击区域内。"""
        try:
            px = float(x)
            py = float(y)
        except (TypeError, ValueError):
            return False
        return bounds["left"] <= px <= bounds["right"] and bounds["top"] <= py <= bounds["bottom"]

    def _choose_flair_candidate(
        self,
        candidates: List[Dict],
        target_flair: str = None,
        preferred_keywords: List[str] = None
    ) -> Optional[Dict]:
        """按目标 Flair、关键词和 OCR 置信度选择最合适的候选项。"""
        if not candidates:
            return None

        preferred_keywords = [kw.lower() for kw in (preferred_keywords or [])]
        target_norm = self._normalize_ocr_text(target_flair or '').lower()
        best = None
        best_score = -1

        for item in candidates:
            text_norm = self._normalize_ocr_text(item['text']).lower()
            score = item.get('confidence', 0) / 100
            match_type = 'confidence'

            if target_norm:
                if target_norm == text_norm:
                    score += 100
                    match_type = 'exact'
                elif target_norm in text_norm or text_norm in target_norm:
                    score += 50
                    match_type = 'contains'
                else:
                    token_score = self._flair_token_match_score(target_norm, text_norm)
                    if token_score:
                        score += token_score
                        match_type = 'token'

            matched_keywords = [kw for kw in preferred_keywords if kw and kw in text_norm]
            if matched_keywords:
                score += 10 * len(matched_keywords)
                match_type = 'keyword'

            if score > best_score:
                best = dict(item)
                best['score'] = score
                best['match_type'] = match_type
                best_score = score

        return best

    def _flair_token_match_score(self, target_norm: str, text_norm: str) -> int:
        """
        处理 OCR 对中文 Flair 的拆字/插字错误。

        例如“不适合工作场合 (18+)”在真实截图中可能被识别成
        “©包含不成适合工作场合84”，不能只依赖完整字符串包含。
        """
        if '不适合工作场合' in target_norm:
            if all(token in text_norm for token in ['适合', '工作', '场合']):
                return 80
            if all(token in text_norm for token in ['包含', '成']):
                return 40
        if '剧透' in target_norm and '剧透' in text_norm:
            return 80
        if '品牌' in target_norm and '品牌' in text_norm:
            return 80
        return 0

    def _normalize_ocr_text(self, text: str) -> str:
        """清理 OCR 文本，减少空白和符号噪声。"""
        if not text:
            return ''
        cleaned = re.sub(r'\s+', ' ', text).strip()
        return cleaned.strip('|·•[](){}')

    def _click_flair_candidate(self, selected: Dict) -> bool:
        """
        点击 Flair 候选。

        Reddit 新版弹窗里中文 Flair 行通常由左侧文字和右侧 switch 组成；
        只点 OCR 文本坐标可能不会触发选择，所以先用 DOM 找同一行的 switch。
        """
        text = self._normalize_ocr_text(selected.get('text', ''))
        if text:
            try:
                clicked = self.page.evaluate(
                    """
                    (needle) => {
                        const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                        const stripIcon = (value) => normalize(value).replace(/^[^\\p{L}\\p{N}]+/u, '').trim();
                        const wanted = normalize(needle);
                        const wantedNoIcon = stripIcon(wanted);
                        const dialog = document.querySelector(
                            '[role="dialog"], shreddit-post-flair-modal, reddit-post-flair-modal, r-post-flairs-modal'
                        );
                        const root = dialog || document.body;
                        const nodes = Array.from(root.querySelectorAll('*'))
                            .filter((node) => {
                                const nodeText = normalize([
                                    node.innerText || '',
                                    node.textContent || '',
                                    node.getAttribute?.('aria-label') || '',
                                    node.getAttribute?.('title') || ''
                                ].join(' '));
                                const nodeNoIcon = stripIcon(nodeText);
                                return nodeText.includes(wanted) ||
                                    (wantedNoIcon && nodeText.includes(wantedNoIcon)) ||
                                    (wantedNoIcon && nodeNoIcon.includes(wantedNoIcon));
                            });

                        for (const node of nodes) {
                            const container = node.closest('[role="listitem"], li, label, shreddit-post-flair-row, div');
                            const switchLike = container?.querySelector?.(
                                '[role="radio"], input[type="radio"], [role="switch"], button, svg.icon, svg'
                            );
                            if (node.getAttribute?.('role') === 'radio' || node.matches?.('input[type="radio"]')) {
                                node.click();
                                return true;
                            }
                            if (switchLike) {
                                switchLike.click();
                                return true;
                            }
                            if (container) {
                                container.click();
                                return true;
                            }
                        }
                        return false;
                    }
                    """,
                    text,
                )
                if clicked:
                    time.sleep(0.5)
                    print(f"   ✅ 已通过 DOM 点击 Flair 候选: {text}")
                    return True
            except Exception as exc:
                print(f"   ⚠️  DOM 点击 Flair 候选失败: {exc}")

        center_x = float(selected.get('center_x') or 0)
        center_y = float(selected.get('center_y') or 0)
        if center_x <= 0 or center_y <= 0:
            return False
        bounds = self._get_flair_dialog_bounds()
        if bounds and self._point_in_bounds(center_x, center_y, bounds):
            toggle_x = max(bounds["left"], bounds["right"] - 48)
            if self._click_at_coordinates(toggle_x, center_y):
                print(f"   ✅ 已点击 Flair 行右侧开关: {text or selected.get('text')}")
                return True
        return self._click_at_coordinates(center_x, center_y)

    def _wait_for_flair_dialog_closed(self, timeout: int = 5) -> bool:
        """等待 Flair 对话框关闭。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._is_flair_dialog_open():
                return True
            time.sleep(0.5)
        return False

    def _verify_flair_applied(self, selected_text: str, target_flair: str = None) -> bool:
        """验证选中的 Flair 已经出现在发帖页上。"""
        expected_tokens = [
            token.lower()
            for source in [selected_text, target_flair]
            for token in re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', source or '')
            if len(token) >= 2
        ]

        if not expected_tokens:
            return False

        try:
            page_text = (
                (self.page.locator('body').inner_text(timeout=3000) or '')
                + "\n"
                + self._collect_page_text_deep()
            ).lower()
            target_joined = f"{selected_text or ''} {target_flair or ''}".lower()
            if (
                '不适合' in target_joined
                or '工作场合' in target_joined
                or '18' in target_joined
                or all(token in target_joined for token in ['适合', '工作', '场合'])
            ):
                if any(token in page_text for token in ['18+', 'nsfw', '成人']):
                    return True
            return any(token in page_text for token in expected_tokens)
        except Exception as e:
            print(f"   ⚠️  Flair 应用状态验证失败: {e}")
            return False

    def _collect_page_text_deep(self) -> str:
        """
        递归读取普通 DOM 和 Shadow DOM 文本/可访问性属性。

        Reddit 的 Flair 有时以图标或 shadow component 呈现，body.innerText
        看不到完整标签；这里用于验证真实页面状态，不用于伪造成功。
        """
        try:
            return str(self.page.evaluate("""
                () => {
                    const parts = [];
                    const visit = (node, depth = 0) => {
                        if (!node || depth > 12) return;
                        if (node.nodeType === Node.TEXT_NODE) {
                            const text = (node.textContent || '').trim();
                            if (text) parts.push(text);
                            return;
                        }
                        if (node.nodeType !== Node.ELEMENT_NODE && node !== document) return;
                        const element = node;
                        if (element.getAttribute) {
                            for (const attr of ['aria-label', 'title', 'alt', 'data-testid', 'data-adclicklocation']) {
                                const value = element.getAttribute(attr);
                                if (value) parts.push(value);
                            }
                        }
                        if (element.shadowRoot) {
                            visit(element.shadowRoot, depth + 1);
                        }
                        const children = element.childNodes || [];
                        for (const child of children) {
                            visit(child, depth + 1);
                        }
                    };
                    visit(document);
                    return parts.join('\\n');
                }
            """))
        except Exception as exc:
            print(f"   ⚠️  Shadow DOM 文本读取失败: {exc}")
            return ""
    
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

            if self._is_flair_dialog_open():
                print("      ✅ Flair 对话框已处于打开状态")
                return True

            # 先使用 DOM 定位，OCR 作为兜底。这样可以避免按钮文字被拆字后点错位置。
            for selector in [
                'button:has-text("Add flair")',
                'button:has-text("Flair")',
                'button:has-text("Add tags")',
                'button:has-text("添加标记")',
                'button:has-text("添加标识")',
                'button:has-text("标识和标记")',
                'button:has-text("标记")',
                'button:has-text("标识")',
                'r-post-tags-section',
                '[aria-label*="flair" i]',
                '[aria-label*="标记"]',
                '[aria-label*="标识"]',
                '[data-testid*="flair" i]',
                '[name="flair"]'
            ]:
                try:
                    button = self.page.locator(selector).first
                    if button.count() > 0 and button.is_visible():
                        button.scroll_into_view_if_needed()
                        button.click(timeout=5000)
                        time.sleep(1)
                        if self._is_flair_dialog_open():
                            print(f"      ✅ 已通过 DOM 打开 Flair 对话框: {selector}")
                            return True
                except Exception as exc:
                    print(f"      ⚠️  DOM 打开 Flair 失败 {selector}: {exc}")

            # 截图
            screenshot_path = str(self.screenshot_dir / "flair_button_search.png")
            self.page.screenshot(path=screenshot_path, full_page=False)
            print(f"      截图已保存: {screenshot_path}")

            if self._is_flair_dialog_open_visual():
                print("      ✅ 已通过 OCR 视觉检测确认 Flair 对话框打开")
                return True
            
            # 使用 Tesseract OCR 识别
            results = self.ocr_helper.recognize_with_position(screenshot_path, lang='chi_sim+eng')
            print(f"      🔍 OCR 识别到 {len(results)} 个文字块")
            
            # 查找包含"添加标记"、"Flair"、"标记"的文字
            target_keywords = ['添加标记', '添加标识', '标识和标记', 'flair', '标记', '标识', 'add flair', 'add tags']
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

            if self._is_flair_dialog_open():
                print("      ✅ Flair 对话框已打开")
                return True

            print("      ❌ 点击后未检测到 Flair 对话框")
            return False
            
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
                'button:has-text("Add")',
                'button:has-text("添加")',
                'button:has-text("确认")',
                'button:has-text("确定")',
                'button:has-text("Done")',
                'button:has-text("Save")',
                '[class*="apply"]',
            ]
            
            for selector in apply_selectors:
                try:
                    btn = self.page.locator(selector).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click()
                        print(f"   ✅ 已点击 Apply 按钮")
                        return True
                except Exception:
                    continue

            if self.ocr_helper:
                screenshot_path = str(self.screenshot_dir / f"flair_apply_search_{int(time.time())}.png")
                self.page.screenshot(path=screenshot_path, full_page=True)
                ocr_results = self.ocr_helper.recognize_with_position(screenshot_path, lang='chi_sim+eng')
                grouped = self._group_nearby_texts(ocr_results)
                for item in grouped:
                    text = self._normalize_ocr_text(item.get('text', '')).lower()
                    if any(keyword in text for keyword in ['apply', 'add', '添加', '确认', '确定', 'done', 'save']):
                        if self._click_at_coordinates(item['center_x'], item['center_y']):
                            print(f"   ✅ 已通过 OCR 点击 Apply 按钮: {item['text']}")
                            return True

            bounds = self._get_flair_dialog_bounds()
            if bounds and self._is_flair_dialog_open():
                apply_x = max(bounds["left"], bounds["right"] - 42)
                apply_y = max(bounds["top"], bounds["bottom"] - 32)
                print(f"   📍 点击 Flair 弹窗右下角确认按钮: ({apply_x:.0f}, {apply_y:.0f})")
                self.page.mouse.click(apply_x, apply_y)
                time.sleep(1)
                return True
            print("   ⚠️  未找到 Apply 按钮")
            return False
            
        except Exception as e:
            print(f"   ❌ Apply 按钮点击失败: {e}")
            return False
    
    # ==================== 错误提示框识别和处理 ====================
    
    def detect_and_read_error_dialog(self, wait_time: int = 5) -> Optional[str]:
        """
        检测并读取错误提示框的内容。

        弹窗文本可能由不同社区自定义，不能只依赖固定中英文关键词。
        这里复用发帖后弹窗解释流程：DOM/OCR 负责取文本，LLM 负责翻译
        和判断是否真的是错误。
        
        Args:
            wait_time: 等待时间
        
        Returns:
            str: 错误消息，如果没有则返回 None
        """
        print(f"\n🔍 检测错误提示框...")
        popup_result = self.detect_submission_popup_result(wait_time=wait_time, use_ocr=True)

        if popup_result.get('status') == 'error':
            error_text = (
                popup_result.get('translated_message_zh')
                or popup_result.get('summary_zh')
                or popup_result.get('message')
            )
            print(f"   ❌ 检测到错误: {error_text}")
            return error_text

        if popup_result.get('status') == 'unknown' and popup_result.get('message'):
            print(f"   ⚠️  弹窗内容未能确认是错误: {popup_result.get('summary_zh') or popup_result.get('message')}")
            return None

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

    def _correction_from_popup_analysis(
        self,
        popup_analysis: Dict,
        title: str,
        content: str
    ) -> Dict:
        """Build retry instructions from the LLM popup interpretation."""
        category = str(popup_analysis.get('category') or 'unknown')
        action = str(popup_analysis.get('recommended_action') or 'manual_review')
        summary = (
            popup_analysis.get('summary_zh')
            or popup_analysis.get('translated_message_zh')
            or popup_analysis.get('reason')
            or 'LLM 未给出可执行摘要'
        )

        correction = {
            'should_retry': bool(popup_analysis.get('should_retry')),
            'corrected_title': title,
            'corrected_content': content,
            'suggestions': [summary],
            'reason': '',
            'needs_flair': bool(popup_analysis.get('needs_flair')),
        }

        if popup_analysis.get('status') != 'error':
            correction['should_retry'] = False
            correction['reason'] = '弹窗未被 LLM 判定为错误'
            return correction

        # Only make mechanical edits for categories where the provider gave a
        # specific action. Community-rule errors stay manual to avoid fake fixes.
        if action == 'select_flair' or category == 'flair_required':
            correction['should_retry'] = True
            correction['needs_flair'] = True
            correction['suggestions'].append('LLM 判定需要选择社区 Flair')
        elif action == 'edit_title' or category == 'title_issue':
            correction['should_retry'] = True
            correction['corrected_title'] = (title or "Reddit post").strip() + " - Updated"
            correction['suggestions'].append('LLM 判定标题需要调整')
        elif action in {'edit_content', 'edit_post'} or category == 'content_issue':
            correction['should_retry'] = True
            correction['corrected_content'] = (
                (content or '').strip()
                + "\n\nAdditional details added for community requirements."
            ).strip()
            correction['suggestions'].append('LLM 判定正文需要调整')
        elif action == 'wait_then_retry' or category == 'rate_limit':
            correction['should_retry'] = False
            correction['reason'] = 'LLM 判定需要等待，当前流程不自动延迟重试'
        else:
            correction['should_retry'] = False
            correction['reason'] = f'LLM 判定需要人工处理: {category}/{action}'

        return correction
    
    def _analyze_error_and_correct(self, error_message: str, title: str, content: str) -> Dict:
        """分析错误并生成修正"""
        correction = {
            'should_retry': False,
            'corrected_title': title,
            'corrected_content': content,
            'suggestions': [],
            'reason': '',
            'needs_flair': False
        }
        
        error_lower = error_message.lower()
        
        # 标题问题
        if any(kw in error_lower for kw in ['title', '标题', 'short', '短']):
            correction['should_retry'] = True
            correction['corrected_title'] = (title or "Reddit post").strip() + " - Updated"
            correction['suggestions'].append("标题可能太短或缺失，已补充标题")
        
        # 内容问题
        elif any(kw in error_lower for kw in ['content', '内容', 'body', '正文']):
            correction['should_retry'] = True
            correction['corrected_content'] = (content or "").strip() + "\n\nAdditional details added for context."
            correction['suggestions'].append("内容可能不足，已添加补充")
        
        # Flair 问题
        elif any(kw in error_lower for kw in ['flair', '标记', '标识', 'required', '必填']):
            correction['should_retry'] = True
            correction['needs_flair'] = True
            correction['suggestions'].append("需要选择 Flair")
        
        # 重复
        elif any(kw in error_lower for kw in ['duplicate', '重复', 'similar']):
            correction['should_retry'] = True
            correction['corrected_title'] = (title or "Reddit post").strip() + f" ({int(time.time())})"
            correction['suggestions'].append("帖子可能重复，已为测试标题添加时间戳")
        
        # 频率限制
        elif any(kw in error_lower for kw in ['rate limit', '频率', 'wait', '等待']):
            correction['should_retry'] = False
            correction['reason'] = '触发频率限制，不自动重试'
        
        # 权限
        elif any(kw in error_lower for kw in ['permission', '权限', 'banned']):
            correction['should_retry'] = False
            correction['reason'] = '没有发帖权限'
        
        else:
            correction['should_retry'] = False
            correction['reason'] = '未知错误，不自动修改内容'
        
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
        """提交帖子并用结果验证保持旧调用兼容。"""
        result = self.submit_post_and_verify()
        return result.get('success', False)

    def submit_post_and_verify(
        self,
        subreddit: str = None,
        wait_time: int = 15,
        title: str = None,
        content: str = None,
        target_flair: str = None,
        max_retries: int = 0
    ) -> Dict:
        """
        提交帖子并验证 Reddit 是否真的创建了帖子。

        Args:
            subreddit: 目标 subreddit。为空时从当前 URL 推断。
            wait_time: 最长等待验证时间（秒）
            title: 当前标题，用于失败后重填。
            content: 当前正文，用于失败后重填。
            target_flair: Flair 缺失时用于重新选择。
            max_retries: 错误后最多重试次数。

        Returns:
            Dict: {
                'success': bool,
                'status': 'success' | 'error' | 'unknown',
                'post_url': str | None,
                'error_message': str | None,
                'screenshot_path': str | None,
                'click': Dict
            }
        """
        attempts = []
        current_title = title
        current_content = content

        for attempt in range(max_retries + 1):
            url_before = self.page.url
            subreddit = subreddit or self._infer_subreddit_from_url(url_before)
            print(f"\n🚀 发帖尝试 {attempt + 1}/{max_retries + 1}")

            click_result = self._click_submit_button()
            result = {
                'success': False,
                'status': 'unknown',
                'post_url': None,
                'error_message': None,
                'screenshot_path': None,
                'url_before': url_before,
                'url_after': self.page.url,
                'click': click_result,
                'attempt': attempt + 1,
                'attempts': attempts
            }

            if not click_result.get('success'):
                result['status'] = 'error'
                result['error_message'] = click_result.get('reason', '提交按钮点击失败')
                result['screenshot_path'] = self._save_result_screenshot('reddit_submit_click_failed')
                attempts.append(result)
                return result

            verification = self._wait_for_submission_result(
                url_before=url_before,
                subreddit=subreddit,
                wait_time=wait_time
            )
            verification['click'] = click_result
            verification['attempt'] = attempt + 1
            attempts.append(verification)

            if verification.get('success'):
                verification['attempts'] = attempts
                return verification

            if attempt >= max_retries:
                verification['attempts'] = attempts
                return verification

            popup_analysis = (verification.get('popup') or {}).get('analysis') or {}
            if popup_analysis:
                correction = self._correction_from_popup_analysis(
                    popup_analysis=popup_analysis,
                    title=current_title or '',
                    content=current_content or ''
                )
            else:
                error_message = verification.get('error_message') or ''
                correction = self._analyze_error_and_correct(
                    error_message=error_message,
                    title=current_title or '',
                    content=current_content or ''
                )
            if not correction.get('should_retry'):
                verification['attempts'] = attempts
                verification['retry_blocked_reason'] = correction.get('reason') or '错误不可自动修复'
                return verification

            print("\n🔧 检测到可修复错误，关闭弹窗并修正表单...")
            self._close_submission_popup()

            if correction.get('needs_flair'):
                flair_result = self.select_flair_with_ocr(
                    target_flair=target_flair,
                    max_attempts=2
                )
                if not flair_result.get('success'):
                    verification['attempts'] = attempts
                    verification['retry_blocked_reason'] = f"Flair 重新选择失败: {flair_result.get('error')}"
                    return verification

            current_title = correction.get('corrected_title', current_title)
            current_content = correction.get('corrected_content', current_content)
            self._refill_form(current_title or '', current_content or '')

        return attempts[-1] if attempts else {'success': False, 'error_message': '未执行发帖'}

    def _click_submit_button(self) -> Dict:
        """
        点击 Reddit 提交按钮。

        使用 DOM 路径优先是因为 OCR 坐标可能点中“创建帖子”等非提交文本；
        只有按钮明确可点击时才发出点击。
        """
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
                return {'success': True, 'method': 'reddit-submit-component'}

            for selector in [
                'button[type="submit"]',
                'button:has-text("Post")',
                'button:has-text("发布")',
                'button:has-text("提交")',
                '[data-testid="submit-button"]'
            ]:
                try:
                    button = self.page.locator(selector).first
                    if button.count() > 0 and button.is_visible() and button.is_enabled():
                        button.scroll_into_view_if_needed()
                        button.click(timeout=5000)
                        print(f"   ✅ 提交按钮已点击: {selector}")
                        return {'success': True, 'method': f'locator:{selector}'}
                except Exception as exc:
                    print(f"   ⚠️  提交按钮选择器失败 {selector}: {exc}")

            reason = self._disabled_submit_reason()
            print(f"   ❌ 提交失败: {reason}")
            return {'success': False, 'reason': reason}

        except Exception as e:
            print(f"   ❌ 提交异常: {e}")
            return {'success': False, 'reason': str(e)}

    def _wait_for_submission_result(self, url_before: str, subreddit: str = None, wait_time: int = 15) -> Dict:
        """等待并验证提交结果，禁止把未知状态当作成功。"""
        deadline = time.time() + wait_time
        result = {
            'success': False,
            'status': 'unknown',
            'post_url': None,
            'error_message': None,
            'screenshot_path': None,
            'url_before': url_before,
            'url_after': self.page.url
        }

        while time.time() < deadline:
            current_url = self.page.url
            result['url_after'] = current_url

            if self._is_success_post_url(current_url, subreddit):
                result.update({
                    'success': True,
                    'status': 'success',
                    'post_url': current_url,
                    'screenshot_path': self._save_result_screenshot('reddit_post_success')
                })
                print(f"   ✅ 发帖成功，帖子 URL: {current_url}")
                return result

            popup_result = self.detect_submission_popup_result(wait_time=0, use_ocr=False)
            if popup_result['status'] == 'success':
                result.update({
                    'success': True,
                    'status': 'success',
                    'post_url': current_url,
                    'error_message': None,
                    'popup': popup_result,
                    'screenshot_path': popup_result.get('screenshot_path')
                })
                print(f"   ✅ 弹窗提示发帖成功: {popup_result.get('message')}")
                return result

            if popup_result['status'] == 'error':
                popup_error = (
                    popup_result.get('summary_zh')
                    or popup_result.get('translated_message_zh')
                    or popup_result.get('message')
                )
                result.update({
                    'status': 'error',
                    'error_message': popup_error,
                    'popup': popup_result,
                    'screenshot_path': popup_result.get('screenshot_path')
                })
                print(f"   ❌ 发帖后弹窗错误: {popup_error}")
                return result

            page_errors = self._detect_page_errors()
            if page_errors:
                result.update({
                    'status': 'error',
                    'error_message': '; '.join(page_errors[:3]),
                    'screenshot_path': self._save_result_screenshot('reddit_post_error')
                })
                print(f"   ❌ 检测到 Reddit 错误: {result['error_message']}")
                return result

            time.sleep(1)

        popup_result = self.detect_submission_popup_result(wait_time=0, use_ocr=True)
        if popup_result['status'] in ['success', 'error']:
            result.update({
                'success': popup_result['status'] == 'success',
                'status': popup_result['status'],
                'post_url': self.page.url if popup_result['status'] == 'success' else None,
                'error_message': None if popup_result['status'] == 'success' else (
                    popup_result.get('summary_zh')
                    or popup_result.get('translated_message_zh')
                    or popup_result.get('message')
                ),
                'popup': popup_result,
                'screenshot_path': popup_result.get('screenshot_path')
            })
            return result

        current_url = self.page.url
        result['url_after'] = current_url

        if current_url == url_before or '/submit' in current_url:
            result['status'] = 'error'
            result['error_message'] = '提交后仍停留在提交页面，未观察到帖子 URL'
        else:
            result['status'] = 'unknown'
            result['error_message'] = f'URL 已变化但不是可验证的帖子 URL: {current_url}'

        result['screenshot_path'] = self._save_result_screenshot('reddit_post_unverified')
        print(f"   ❌ 发帖未验证: {result['error_message']}")
        return result

    def _is_success_post_url(self, url: str, subreddit: str = None) -> bool:
        """判断 URL 是否为 Reddit 帖子结果页。"""
        if not url:
            return False

        normalized_url = url.lower()
        if subreddit:
            subreddit_lower = subreddit.replace('r/', '').lower()
            return (
                f"/r/{subreddit_lower}/comments/" in normalized_url
                or f"/r/{subreddit_lower}/posts/" in normalized_url
            )

        return "/comments/" in normalized_url or "/posts/" in normalized_url

    def _infer_subreddit_from_url(self, url: str) -> Optional[str]:
        """从当前 Reddit 提交页 URL 推断 subreddit。"""
        match = re.search(r"/r/([^/]+)/", url or "", flags=re.IGNORECASE)
        return match.group(1) if match else None

    def detect_submission_popup_result(self, wait_time: int = 3, use_ocr: bool = True) -> Dict:
        """
        识别点击发帖后的弹窗或 toast 内容，并判断成功/错误/无弹窗。

        Args:
            wait_time: 识别前等待秒数。
            use_ocr: DOM 文本不足时是否使用截图 OCR。

        Returns:
            Dict: {
                'status': 'success' | 'error' | 'none' | 'unknown',
                'message': str,
                'screenshot_path': str | None,
                'source': 'dom' | 'ocr' | 'none'
            }
        """
        if wait_time:
            time.sleep(wait_time)

        screenshot_path = self._save_result_screenshot('reddit_submission_popup')
        rule_warning = self._read_post_check_modal_dom(expand_details=True)
        if rule_warning:
            message = self._format_post_check_modal_message(rule_warning)
            analysis = self._interpret_submission_message(message, source='dom_post_check_modal')
            result = self._popup_result_from_analysis(
                analysis=analysis,
                message=message,
                screenshot_path=screenshot_path,
                source='dom_post_check_modal',
            )
            result["post_check_modal"] = rule_warning
            return result

        dom_messages = self._read_submission_popup_dom()
        dom_message = '; '.join(dom_messages)
        dom_analysis = None
        if dom_message:
            dom_analysis = self._interpret_submission_message(dom_message, source='dom')
            if dom_analysis.get('status') != 'unknown':
                return self._popup_result_from_analysis(
                    analysis=dom_analysis,
                    message=dom_message,
                    screenshot_path=screenshot_path,
                    source='dom',
                )

        if use_ocr and self.ocr_helper and screenshot_path:
            try:
                ocr_results = self.ocr_helper.recognize_with_position(screenshot_path, lang='chi_sim+eng')
                grouped = self._group_nearby_texts(ocr_results)
                ocr_message = '; '.join(
                    self._normalize_ocr_text(item.get('text', ''))
                    for item in grouped
                    if item.get('confidence', 0) > 35 and item.get('text')
                )
            except Exception as e:
                print(f"   ⚠️  发帖后弹窗 OCR 失败: {e}")
            else:
                if ocr_message:
                    analysis = self._interpret_submission_message(ocr_message, source='ocr')
                    return self._popup_result_from_analysis(
                        analysis=analysis,
                        message=ocr_message,
                        screenshot_path=screenshot_path,
                        source='ocr',
                    )

        if dom_message:
            return self._popup_result_from_analysis(
                analysis=dom_analysis or self._interpret_submission_message(dom_message, source='dom'),
                message=dom_message,
                screenshot_path=screenshot_path,
                source='dom',
            )

        return {
            'status': 'none',
            'message': '',
            'screenshot_path': screenshot_path,
            'source': 'none'
        }

    def _read_post_check_modal_dom(self, expand_details: bool = True) -> Optional[Dict[str, Any]]:
        """Read Reddit's post-check rule warning modal as structured DOM data."""
        try:
            return self.page.evaluate(
                """
                (expandDetails) => {
                    const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                    const candidates = Array.from(document.querySelectorAll(
                        '#post-check-modal, [role="dialog"], faceplate-modal, rpl-modal-card'
                    ));
                    const modal = candidates.find((node) => {
                        const visible = Boolean(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
                        const text = normalize(node.innerText || node.textContent || '');
                        return visible && (
                            text.includes('你的帖子可能违反') ||
                            text.includes('may violate') ||
                            text.includes('Submit without editing') ||
                            text.includes('Edit Post')
                        );
                    });
                    if (!modal) return null;

                    const detailsNodes = Array.from(modal.querySelectorAll('details'));
                    if (expandDetails) {
                        for (const details of detailsNodes) {
                            details.open = true;
                            const summary = details.querySelector('summary');
                            if (summary) summary.setAttribute('aria-expanded', 'true');
                        }
                    }

                    const title = normalize(
                        modal.querySelector('h1, h2, h3, [slot="title"]')?.innerText ||
                        modal.querySelector('h1, h2, h3, [slot="title"]')?.textContent ||
                        ''
                    );
                    const rules = detailsNodes.map((details) => {
                        const summary = details.querySelector('summary');
                        const summaryText = normalize(summary?.innerText || summary?.textContent || '');
                        const content = details.querySelector(
                            '[faceplate-auto-height-animator-content], [id^="rule-"], .md, p'
                        );
                        let description = normalize(content?.innerText || content?.textContent || '');
                        if (!description) {
                            description = normalize(details.textContent || '').replace(summaryText, '').trim();
                        }
                        return {
                            title: summaryText,
                            description,
                            open: Boolean(details.open),
                            aria_expanded: summary?.getAttribute('aria-expanded') || ''
                        };
                    }).filter((rule) => rule.title);
                    const buttons = Array.from(modal.querySelectorAll('button'))
                        .map((button) => normalize(button.innerText || button.textContent || button.getAttribute('aria-label') || ''))
                        .filter(Boolean);
                    return {
                        type: 'reddit_post_check_rule_warning',
                        title,
                        full_text: normalize(modal.innerText || modal.textContent || ''),
                        rules,
                        buttons,
                        has_edit_post: buttons.some((text) => text.toLowerCase().includes('edit post') || text.includes('编辑')),
                        has_submit_without_editing: buttons.some((text) => text.toLowerCase().includes('submit without editing')),
                    };
                }
                """,
                expand_details,
            )
        except Exception as exc:
            print(f"   ⚠️  Reddit post-check 弹窗 DOM 读取失败: {exc}")
            return None

    def _format_post_check_modal_message(self, modal: Dict[str, Any]) -> str:
        """Format structured post-check modal data for LLM interpretation."""
        lines = [
            f"Reddit post-check modal: {modal.get('title') or ''}".strip(),
        ]
        for rule in modal.get("rules") or []:
            title = rule.get("title") or ""
            description = rule.get("description") or ""
            lines.append(f"- {title}: {description}".strip())
        buttons = ", ".join(str(item) for item in modal.get("buttons") or [])
        if buttons:
            lines.append(f"Available actions: {buttons}")
        return "\n".join(line for line in lines if line)

    def _popup_result_from_analysis(
        self,
        *,
        analysis: Dict,
        message: str,
        screenshot_path: str,
        source: str,
    ) -> Dict:
        """Shape LLM popup analysis into the existing submission result contract."""
        return {
            'status': analysis.get('status', 'unknown'),
            'message': message,
            'translated_message_zh': analysis.get('translated_message_zh'),
            'summary_zh': analysis.get('summary_zh'),
            'category': analysis.get('category'),
            'should_retry': analysis.get('should_retry'),
            'needs_flair': analysis.get('needs_flair'),
            'recommended_action': analysis.get('recommended_action'),
            'llm_trace_id': analysis.get('trace_id'),
            'analysis': analysis,
            'screenshot_path': screenshot_path,
            'source': source,
        }

    def _read_submission_popup_dom(self) -> List[str]:
        """读取 Reddit 弹窗、toast、alert 的 DOM 文本。"""
        try:
            return self.page.evaluate("""
                () => {
                    const selectors = [
                        '[role="dialog"]',
                        '[role="alert"]',
                        '[aria-live="assertive"]',
                        '[aria-live="polite"]',
                        '[faceplate-validity="invalid"]',
                        '[slot*="error" i]',
                        'faceplate-form-helper-text',
                        'shreddit-composer-error',
                        'shreddit-toast',
                        'reddit-toast',
                        '.toast',
                        '.error',
                        '.text-error',
                        '[class*="toast"]',
                        '[class*="error"]',
                        '[class*="invalid"]',
                        '[data-testid*="error" i]'
                    ];
                    const texts = [];
                    for (const selector of selectors) {
                        for (const node of document.querySelectorAll(selector)) {
                            const visible = !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
                            if (!visible) continue;
                            const text = (node.innerText || node.textContent || '').trim();
                            if (text) texts.push(text);
                        }
                    }
                    return [...new Set(texts)].slice(0, 8);
                }
            """)
        except Exception as e:
            print(f"   ⚠️  读取发帖弹窗 DOM 失败: {e}")
            return []

    def _interpret_submission_message(self, message: str, source: str) -> Dict:
        """Interpret popup text with LLM by default; legacy keyword mode is explicit."""
        if self.enable_llm_popup_interpreter:
            interpreter = self._get_popup_interpreter()
            return interpreter.interpret(
                message=message,
                subreddit=self._infer_subreddit_from_url(self.page.url),
                source=source,
            )

        status = self._classify_submission_message(message)
        return {
            'status': status,
            'language': 'unknown',
            'translated_message_zh': message,
            'summary_zh': message,
            'category': 'unknown',
            'should_retry': status == 'error',
            'needs_flair': 'flair' in (message or '').lower() or '标记' in (message or ''),
            'recommended_action': 'manual_review' if status == 'error' else 'none',
            'confidence': 0.0,
            'reason': 'legacy keyword classifier explicitly enabled',
        }

    def _get_popup_interpreter(self):
        """Create the LLM popup interpreter lazily so normal page setup is cheap."""
        if self.llm_popup_interpreter is None:
            from Agent.reddit_popup_llm_interpreter import RedditPopupLLMInterpreter

            self.llm_popup_interpreter = RedditPopupLLMInterpreter()
        return self.llm_popup_interpreter

    def _classify_submission_message(self, message: str) -> str:
        """根据弹窗文本判断发帖成功或错误。"""
        text = (message or '').lower()
        if not text:
            return 'none'

        error_keywords = [
            'error', 'failed', 'failure', 'required', 'invalid', 'try again',
            'something went wrong', 'not allowed', 'rate limit', 'karma',
            'must be', 'too short', 'too long', 'duplicate', 'similar',
            '错误', '失败', '必填', '无效', '限制', '重复', '太短', '太长'
        ]
        success_keywords = [
            'posted', 'submitted', 'success', 'created', 'your post',
            '发布成功', '提交成功', '已发布', '已提交', '创建成功'
        ]

        if any(keyword in text for keyword in error_keywords):
            return 'error'
        if any(keyword in text for keyword in success_keywords):
            return 'success'
        return 'unknown'

    def _close_submission_popup(self):
        """关闭发帖后的错误/成功弹窗。"""
        for selector in [
            '[role="dialog"] button[aria-label="Close"]',
            'button[aria-label="Close"]',
            'button:has-text("Close")',
            'button:has-text("Got it")',
            'button:has-text("OK")',
            'button:has-text("Okay")',
            'button:has-text("确定")',
            'button:has-text("关闭")'
        ]:
            try:
                button = self.page.locator(selector).first
                if button.count() > 0 and button.is_visible():
                    button.click(timeout=3000)
                    time.sleep(0.5)
                    return
            except Exception:
                continue

        try:
            self.page.keyboard.press('Escape')
            time.sleep(0.5)
        except Exception:
            pass

    def _detect_page_errors(self) -> List[str]:
        """读取页面中的常见错误提示。"""
        try:
            return self.page.evaluate("""
                () => {
                    const bodyText = document.body?.innerText || '';
                    const lowerText = bodyText.toLowerCase();
                    const keywords = [
                        'error', 'failed', 'required', 'try again', 'something went wrong',
                        'removed', 'not allowed', 'rate limit', 'karma', 'must be',
                        '错误', '失败', '必填', '限制', '请稍后'
                    ];
                    const matches = [];
                    for (const keyword of keywords) {
                        if (lowerText.includes(keyword)) matches.push(keyword);
                    }

                    const alertTexts = Array.from(document.querySelectorAll(
                        '[role="alert"], [aria-live="assertive"], [faceplate-validity="invalid"], [slot*="error" i], faceplate-form-helper-text, shreddit-composer-error, .error, .text-error, [class*="error"], [class*="invalid"], [data-testid*="error" i]'
                    ))
                        .map((node) => (node.innerText || node.textContent || '').trim())
                        .filter(Boolean)
                        .slice(0, 5);

                    return [...new Set([...alertTexts, ...matches])];
                }
            """)
        except Exception as e:
            print(f"   ⚠️  错误检测失败: {e}")
            return []

    def _disabled_submit_reason(self) -> str:
        """读取提交按钮禁用状态，帮助定位未发帖原因。"""
        try:
            return self.page.evaluate("""
                () => {
                    const submitBtn = document.querySelector('r-post-form-submit-button#submit-post-button');
                    if (!submitBtn) return '未找到 Reddit 提交按钮';
                    if (submitBtn.hasAttribute('disabled')) return 'Reddit 提交按钮仍处于禁用状态';
                    return '提交按钮存在但无法点击';
                }
            """)
        except Exception:
            return '无法读取提交按钮状态'

    def _save_result_screenshot(self, prefix: str) -> Optional[str]:
        """保存提交结果截图作为物理证据。"""
        try:
            screenshot_path = self.screenshot_dir / f"{prefix}_{int(time.time())}.png"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"   📸 结果截图: {screenshot_path}")
            return str(screenshot_path)
        except Exception as e:
            print(f"   ⚠️  结果截图保存失败: {e}")
            return None


# 使用示例
if __name__ == "__main__":
    print("Reddit Visual Recognizer - PaddleOCR + Airtest")
    print("请通过测试脚本调用此模块")

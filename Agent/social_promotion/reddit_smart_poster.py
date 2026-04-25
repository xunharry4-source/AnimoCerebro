#!/usr/bin/env python3
"""
Reddit 智能发帖入口。

文件用途:
    作为 Reddit 发帖流程的入口，负责把社区规则、内容填写、Flair 选择、
    提交和真实成功验证串成一个可审计的发帖尝试。

主要职责:
    - 根据社区规则准备发帖内容
    - 打开 Reddit 发帖页并填写标题/正文
    - 调用视觉识别器选择 Flair 和提交帖子
    - 只在拿到 Reddit permalink 且主动打开验证后返回成功

不负责:
    - 不管理 Reddit 账号登录和密码
    - 不绕过 CAPTCHA、风控、平台限制或社区限制
    - 不在只有点击指令、URL 变化或弹窗文字时宣称发帖成功
"""

import time
import asyncio
import json
import logging
import inspect
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional, Any

# Configure logging
logger = logging.getLogger(__name__)

try:
    from ..reddit_advanced_helper import RedditAdvancedHelper
except ImportError:
    # Fallback for different execution contexts
    try:
        from Agent.reddit_advanced_helper import RedditAdvancedHelper
    except ImportError:
        logger.warning("Could not import RedditAdvancedHelper, some features may be disabled")
        RedditAdvancedHelper = None


class RedditSmartPoster:
    """Reddit 智能发帖助手"""

    def __init__(self, page, rules_manager=None):
        self.page = page
        self.rules_manager = rules_manager
        self.attempt_history = []
        # 初始化高级助手
        if RedditAdvancedHelper:
            self.advanced_helper = RedditAdvancedHelper(page)
        else:
            self.advanced_helper = None

    def _is_async_page(self) -> bool:
        """判断当前 page 是否来自 Playwright async_api。"""
        goto = getattr(self.page, "goto", None)
        return inspect.iscoroutinefunction(goto)

    def _new_trace_id(self, platform: str) -> str:
        """为每次真实发帖尝试生成审计 trace_id。"""
        return f"{platform}-{int(time.time())}-{uuid.uuid4().hex[:8]}"

    def _failure_result(self, *, trace_id: str, subreddit: str, title: str,
                        status: str, error_message: str, code: str,
                        attempt: int = 0, **extra: Any) -> Dict[str, Any]:
        """统一失败结果，禁止用 None/空 dict 冒充可解释状态。"""
        result = {
            "success": False,
            "platform": "reddit",
            "trace_id": trace_id,
            "subreddit": subreddit,
            "title": title,
            "attempt": attempt,
            "status": status,
            "code": code,
            "post_url": None,
            "error_message": error_message,
            "verified_at": None,
            "verification_source": None,
        }
        result.update(extra)
        return result

    def _success_result(self, *, trace_id: str, subreddit: str, title: str,
                        post_url: str, attempt: int, submission_result: Dict[str, Any],
                        active_evidence: Dict[str, Any]) -> Dict[str, Any]:
        """统一成功结果，必须绑定 Reddit permalink 和主动验证证据。"""
        return {
            "success": True,
            "platform": "reddit",
            "trace_id": trace_id,
            "subreddit": subreddit,
            "title": title,
            "attempt": attempt,
            "status": "success",
            "code": "reddit_post_actively_verified",
            "post_url": post_url,
            "error_message": None,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "verification_source": "active_browser_permalink_open",
            "submission_result": submission_result,
            "active_evidence": active_evidence,
            "screenshot_path": submission_result.get("screenshot_path"),
        }

    async def post_with_retry(self, subreddit: str, max_retries: int = 3) -> bool:
        """
        带重试的发帖功能（使用自动生成的内容）

        Args:
            subreddit: 社区名称
            max_retries: 最大重试次数

        Returns:
            bool: 是否成功
        """
        print("\n" + "="*80)
        print(f"  🤖 Reddit 智能发帖 (r/{subreddit})")
        print(f"  🔄 最多重试 {max_retries} 次")
        print("="*80)

        # 步骤 1: 检查并获取社区规则
        print(f"\n📋 步骤 1: 检查 r/{subreddit} 社区规则...")
        rules = await self._ensure_community_rules(subreddit)

        if not rules:
            print(f"   ❌ 无法获取 r/{subreddit} 的社区规则")
            return False

        print(f"   ✅ 已加载 {len(rules.rules)} 条社区规则")

        # 步骤 2: 基于规则生成初始内容
        print(f"\n📝 步骤 2: 基于社区规则生成合规内容...")
        initial_content = self._generate_compliant_content(rules, attempt=1)
        print(f"   ✅ 已生成合规内容")

        # 步骤 3: 重试循环
        for attempt in range(1, max_retries + 1):
            print(f"\n尝试 {attempt}/{max_retries}...")

            try:
                success = await self._try_post(subreddit, attempt, rules)

                if success:
                    print(f"\n✅ 第 {attempt} 次尝试成功!")
                    return True
                else:
                    print(f"\n⚠️  第 {attempt} 次尝试失败")
                    if attempt < max_retries:
                        await asyncio.sleep(3)
            except Exception as e:
                print(f"\n❌ 第 {attempt} 次尝试出错: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(3)

        return False

    def post_custom_content(self, subreddit: str, title: str, content: str,
                            flair: str = None, max_retries: int = 3):
        """
        发布自定义内容，保持旧调用兼容。

        同步 Playwright page 会直接执行并返回 bool；异步 Playwright page 会返回
        coroutine，调用方必须 await。同步路径不再返回 coroutine，避免旧脚本把
        未执行的 coroutine 当成 truthy 成功。
        """
        if self._is_async_page():
            return self._post_custom_content_async(subreddit, title, content, flair, max_retries)

        result = self.post_custom_content_with_evidence(
            subreddit=subreddit,
            title=title,
            content=content,
            flair=flair,
            max_retries=max_retries,
        )
        return bool(result.get("success"))

    def post_custom_content_with_evidence(self, subreddit: str, title: str, content: str,
                                          flair: str = None, max_retries: int = 3):
        """
        发布自定义内容并返回真实验证证据。

        成功必须同时满足：
        - RedditVisualRecognizer 返回 success
        - result.post_url 是目标 subreddit 的 Reddit 帖子 permalink
        - 主动打开该 permalink 后能在页面正文中看到期望标题
        """
        if self._is_async_page():
            return self._post_custom_content_with_evidence_async(
                subreddit=subreddit,
                title=title,
                content=content,
                flair=flair,
                max_retries=max_retries,
            )
        return self._post_custom_content_with_evidence_sync(
            subreddit=subreddit,
            title=title,
            content=content,
            flair=flair,
            max_retries=max_retries,
        )

    async def _post_custom_content_async(self, subreddit: str, title: str, content: str,
                                         flair: str = None, max_retries: int = 3) -> bool:
        result = await self._post_custom_content_with_evidence_async(
            subreddit=subreddit,
            title=title,
            content=content,
            flair=flair,
            max_retries=max_retries,
        )
        return bool(result.get("success"))

    async def _post_custom_content_with_evidence_async(self, subreddit: str, title: str, content: str,
                                                       flair: str = None, max_retries: int = 3) -> Dict[str, Any]:
        """异步 Playwright 版本的结构化真实验证入口。"""
        print(f"\n📝 发布自定义内容到 r/{subreddit}")
        trace_id = self._new_trace_id("reddit")
        last_result = self._failure_result(
            trace_id=trace_id,
            subreddit=subreddit,
            title=title,
            status="not_started",
            error_message="发帖流程未开始",
            code="reddit_post_not_started",
        )

        # 规则下载失败不能伪装成功，但不阻断用户提供内容的真实提交尝试。
        await self._ensure_community_rules(subreddit)

        for attempt in range(1, max_retries + 1):
            print(f"\n尝试 {attempt}/{max_retries}...")
            try:
                last_result = await self._try_post_custom_with_evidence_async(
                    subreddit=subreddit,
                    title=title,
                    content=content,
                    flair=flair,
                    attempt=attempt,
                    trace_id=trace_id,
                )
                if last_result.get("success"):
                    return last_result
                if attempt < max_retries:
                    await asyncio.sleep(3)
            except Exception as e:
                last_result = self._failure_result(
                    trace_id=trace_id,
                    subreddit=subreddit,
                    title=title,
                    status="error",
                    error_message=str(e),
                    code="reddit_post_attempt_exception",
                    attempt=attempt,
                )
                print(f"❌ 尝试出错: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(3)

        return last_result

    def _post_custom_content_with_evidence_sync(self, subreddit: str, title: str, content: str,
                                                flair: str = None, max_retries: int = 3) -> Dict[str, Any]:
        """同步 Playwright 版本的结构化真实验证入口。"""
        print(f"\n📝 发布自定义内容到 r/{subreddit}")
        trace_id = self._new_trace_id("reddit")
        last_result = self._failure_result(
            trace_id=trace_id,
            subreddit=subreddit,
            title=title,
            status="not_started",
            error_message="发帖流程未开始",
            code="reddit_post_not_started",
        )

        for attempt in range(1, max_retries + 1):
            print(f"\n尝试 {attempt}/{max_retries}...")
            try:
                last_result = self._try_post_custom_with_evidence_sync(
                    subreddit=subreddit,
                    title=title,
                    content=content,
                    flair=flair,
                    attempt=attempt,
                    trace_id=trace_id,
                )
                if last_result.get("success"):
                    return last_result
                if attempt < max_retries:
                    time.sleep(3)
            except Exception as e:
                last_result = self._failure_result(
                    trace_id=trace_id,
                    subreddit=subreddit,
                    title=title,
                    status="error",
                    error_message=str(e),
                    code="reddit_post_attempt_exception",
                    attempt=attempt,
                )
                print(f"❌ 尝试出错: {e}")
                if attempt < max_retries:
                    time.sleep(3)

        return last_result

    async def _try_post(self, subreddit: str, attempt: int, rules) -> bool:
        """单次发帖尝试，仅从结构化真实验证结果派生 bool。"""
        content_strategy = self._generate_compliant_content(rules, attempt)
        result = await self._try_post_custom_with_evidence_async(
            subreddit=subreddit,
            title=content_strategy.get("title", ""),
            content=content_strategy.get("content", ""),
            flair=None,
            attempt=attempt,
            trace_id=self._new_trace_id("reddit"),
        )
        return bool(result.get("success"))

    async def _ensure_community_rules(self, subreddit: str):
        """确保社区规则存在"""
        print(f"   🔍 检查本地缓存...")
        cached_rules = self.rules_manager.get_community_rules(subreddit, auto_download=False) if self.rules_manager else None

        if cached_rules and not cached_rules.is_expired(max_age_days=7):
            return cached_rules

        print(f"\n   🌐 正在下载 r/{subreddit} 社区规则...")
        downloaded_rules = await self._download_community_rules_from_web(subreddit)

        if downloaded_rules and self.rules_manager:
            self.rules_manager.save_rule_to_cache(downloaded_rules)
            return downloaded_rules

        return cached_rules

    async def _download_community_rules_from_web(self, subreddit: str):
        """从网页抓取社区规则"""
        try:
            from Agent.social_promotion.community_rules_manager import CommunityRule
            rules_url = f"https://www.reddit.com/r/{subreddit}/about/rules"
            await self.page.goto(rules_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            rules = []
            rule_rows = await self.page.locator('tr').all()
            for row in rule_rows:
                try:
                    cells = await row.locator('td, th').all()
                    if len(cells) >= 2:
                        title = (await cells[0].text_content()).strip()
                        description = (await cells[1].text_content()).strip()
                        if title and len(title) > 5:
                            rules.append({"title": title[:200], "description": description[:500]})
                except: continue

            if not rules:
                rule_elements = await self.page.locator('.rule-row, .md-container li, .CommunityRules__rule').all()
                for elem in rule_elements:
                    try:
                        text = (await elem.text_content()).strip()
                        if text and len(text) > 10:
                            rules.append({"title": text[:200], "description": text[:500]})
                    except: continue

            if not rules:
                page_text = await self.page.text_content('body')
                # ... (rest of the logic)

            return CommunityRule(subreddit=subreddit, rules=rules, source="scraped") if rules else None
        except Exception as e:
            return None

    def _generate_compliant_content(self, rules, attempt: int = 1) -> Dict:
        """
        基于社区规则生成合规内容

        Args:
            rules: CommunityRule 对象
            attempt: 尝试次数

        Returns:
            Dict: 包含 title 和 content 的字典
        """
        # 分析规则中的禁止事项
        prohibited_items = self._analyze_prohibited_items(rules)

        print(f"   🔍 分析规则限制...")
        if prohibited_items:
            print(f"   ⚠️  检测到以下限制:")
            for item in prohibited_items[:5]:
                print(f"      - {item}")

        # 根据尝试次数和规则生成内容
        if attempt == 1:
            # 第一次：标准测试内容（严格遵守规则）
            return self._generate_standard_content(rules, prohibited_items)
        elif attempt == 2:
            # 第二次：更保守的内容
            return self._generate_conservative_content(rules, prohibited_items)
        else:
            # 第三次及以后：最小化内容
            return self._generate_minimal_content(rules, prohibited_items)

    def _analyze_prohibited_items(self, rules) -> List[str]:
        """
        分析规则中的禁止事项

        Returns:
            List[str]: 禁止事项列表
        """
        prohibited = []

        # 常见禁止关键词
        prohibition_keywords = [
            ("self-promotion", ["self-promotion", "self promotion", "自我推广", "自己的作品"]),
            ("external_links", ["external link", "外部链接", "no links", "禁止链接"]),
            ("low_effort", ["low effort", "低质量", "minimal effort"]),
            ("repost", ["repost", "重复发布", "duplicate"]),
            ("spam", ["spam", "广告", "promotion", "推广"]),
            ("nsfw", ["nsfw", "adult", "成人内容"]),
            ("personal_info", ["personal info", "个人信息", "doxxing"]),
            ("harassment", ["harassment", "骚扰", "hate speech"]),
        ]

        rule_texts = ' '.join([r.get('title', '') + ' ' + r.get('description', '')
                              for r in rules.rules]).lower()

        for category, keywords in prohibition_keywords:
            for keyword in keywords:
                if keyword.lower() in rule_texts:
                    prohibited.append(category)
                    break

        return prohibited

    def _generate_standard_content(self, rules, prohibited_items) -> Dict:
        """生成标准测试内容"""
        title = f"Test Post - Automation Verification #{int(time.time())}"
        content = """Hi everyone,

This is an automated test to verify browser automation capabilities.

No action needed. This post will be deleted after testing.

Thanks!"""

        # 如果禁止自我推广，添加说明
        if "self-promotion" in prohibited_items:
            content += "\n\nNote: This is NOT self-promotion. It's a technical test."

        # 如果禁止外部链接，确保没有链接
        if "external_links" in prohibited_items:
            content = content.replace("http", "")

        return {
            "title": title,
            "content": content,
            "strategy": "standard"
        }

    def _generate_conservative_content(self, rules, prohibited_items) -> Dict:
        """生成保守内容"""
        subreddit_name = "this community"

        title = f"Question about best practices in {subreddit_name}"
        content = """Hi all,

I'm interested in learning about best practices here. Could experienced members share their insights?

What are some common mistakes newcomers should avoid?

Thanks in advance for your help!"""

        # 如果禁止低质量内容，增加更多细节
        if "low_effort" in prohibited_items:
            content += """\n\nI've been reading through the community guidelines and want to make sure I understand them correctly."""

        return {
            "title": title,
            "content": content,
            "strategy": "conservative"
        }

    def _generate_minimal_content(self, rules, prohibited_items) -> Dict:
        """生成最小化内容"""
        title = "Quick question"
        content = "Does anyone have experience with this?"

        return {
            "title": title,
            "content": content,
            "strategy": "minimal"
        }

    async def shadow_click(self, selector: str, text_hint: str) -> bool:
        """
        在 shreddit-composer 的 Shadow DOM 中寻找并点击按钮

        Args:
            selector: 内部标签名，如 'button'
            text_hint: 按钮包含的文本或 aria-label 关键字

        Returns:
            bool: 是否成功点击
        """
        try:
            result = await self.page.evaluate(f"""
                () => {{
                    const composer = document.querySelector('shreddit-composer');
                    if (!composer || !composer.shadowRoot) return false;

                    const buttons = Array.from(composer.shadowRoot.querySelectorAll('{selector}'));
                    const target = buttons.find(b => {{
                        const content = (b.textContent + b.getAttribute('aria-label') + b.className).toLowerCase();
                        return content.includes('{text_hint.lower()}');
                    }});

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
            import traceback
            traceback.print_exc()
            return False

    async def _fill_form(self, content_strategy: Dict) -> bool:
        """填写发帖表单 (使用先进的 Shadow DOM 穿透和备选方案)"""
        title = content_strategy.get("title", "")
        content = content_strategy.get("content", "")
        strategy = content_strategy.get("strategy", "unknown")

        print(f"\n✍️  填写表单 (策略: {strategy})...")

        try:
            # 1. 确保在正确的标签页 (Text)
            print("   🔍 切换到 Text 标签...")
            try:
                # 尝试多个选择器
                tab_selectors = [
                    'button:has-text("Text")',
                    'faceplate-tab[aria-label*="Text"]',
                    'shreddit-composer >>> button:has-text("Text")'
                ]
                for sel in tab_selectors:
                    tab = self.page.locator(sel).first
                    if await tab.count() > 0:
                        await tab.click()
                        await asyncio.sleep(1)
                        break
            except Exception as e:
                print(f"   ⚠️  切换标签失败 (可能已在正确位置): {e}")

            # 2. 填写标题
            print(f"   ✍️  填写标题: {title[:50]}...")
            title_filled = False
            title_selectors = [
                'input[name="title"]',
                'input[placeholder*="Title"]',
                'textarea[name="title"]',
                'shreddit-composer >>> input[name="title"]',
                '#post-title'
            ]

            for selector in title_selectors:
                try:
                    elem = self.page.locator(selector).first
                    if await elem.count() > 0 and await elem.is_visible():
                        await elem.fill(title)
                        title_filled = True
                        break
                except: continue

            if not title_filled:
                # 尝试 JS 注入 (Shadow DOM)
                title_filled = await self.page.evaluate(f"""
                    (val) => {{
                        const composer = document.querySelector('shreddit-composer');
                        const root = composer ? composer.shadowRoot : document;
                        const input = root.querySelector('input[name="title"], input[placeholder*="Title"]');
                        if (input) {{
                            input.value = val;
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                        return false;
                    }}
                """, title)

            if not title_filled:
                print("   ❌ 无法找到标题输入框")
                return False

            # 3. 填写内容
            print(f"   ✍️  填写内容 ({len(content)} 字符)...")
            content_filled = False
            content_selectors = [
                'textarea[name="text"]',
                'div[role="textbox"]',
                'shreddit-composer >>> textarea[name="text"]',
                'shreddit-composer >>> div[role="textbox"]'
            ]

            for selector in content_selectors:
                try:
                    elem = self.page.locator(selector).first
                    if await elem.count() > 0 and await elem.is_visible():
                        await elem.fill(content)
                        content_filled = True
                        break
                except: continue

            if not content_filled:
                # 尝试 JS 注入 (Shadow DOM)
                content_filled = await self.page.evaluate(f"""
                    (val) => {{
                        const composer = document.querySelector('shreddit-composer');
                        const root = composer ? composer.shadowRoot : document;
                        const area = root.querySelector('textarea[name="text"], div[role="textbox"], [contenteditable="true"]');
                        if (area) {{
                            if (area.tagName === 'DIV') area.innerText = val;
                            else area.value = val;
                            area.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            area.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return true;
                        }}
                        return false;
                    }}
                """, content)

            if not content_filled:
                print("   ❌ 无法找到内容输入框")
                return False

            print("   ✅ 表单填写完成")
            return True

        except Exception as e:
            print(f"   ❌ 表单填写严重错误: {e}")
            return False

    async def _select_flair(self):
        """选择 Flair（标记）"""
        print("\n🏷️  尝试选择 Flair...")

        try:
            flair_button = self.page.locator('button:has-text("Flair"), button:has-text("标记"), [data-testid="flair-picker"]').first

            if await flair_button.count() > 0:
                print("   ✓ 找到 Flair 按钮")
                await flair_button.click()
                await asyncio.sleep(2)

                # 选择合适的 Flair
                flair_options = await self.page.locator('[role="dialog"] button, .flair-option').all()
                if len(flair_options) > 0:
                    # 优先选择安全的 Flair
                    safe_keywords = ['discussion', 'question', 'help', 'meta', 'general']
                    selected = False

                    for option in flair_options[:10]:
                        try:
                            flair_text = (await option.text_content()).lower()
                            if any(kw in flair_text for kw in safe_keywords):
                                await option.click()
                                print(f"   ✓ 已选择 Flair: {(await option.text_content())[:50]}")
                                selected = True
                                break
                        except:
                            continue

                    if not selected:
                        # 选择第一个
                        await flair_options[0].click()
                        print(f"   ✓ 已选择第一个 Flair")

                    await asyncio.sleep(2)
                else:
                    print("   ⚠️  未找到 Flair 选项")
            else:
                print("   ⚠️  该社区可能不需要 Flair")

        except Exception as e:
            print(f"   ⚠️  Flair 选择失败: {e}")

    async def _submit_post(self, subreddit: str) -> bool:
        """旧提交入口已禁用，避免 URL 粗略判断伪装成真实成功。"""
        print(f"   ❌ 旧提交入口已禁用: r/{subreddit} 必须使用 post_custom_content_with_evidence")
        return False

    async def _check_errors(self) -> Dict:
        """检查页面上的错误提示"""
        errors = { "has_error": False, "error_messages": [], "error_type": None }
        try:
            page_content = (await self.page.text_content('body')).lower()
            error_keywords = {
                "RULE_VIOLATION": ["rule", "规则", "violation", "违反"],
                "QUALITY_ISSUE": ["quality", "质量"],
                "SPAM_DETECTION": ["spam", "广告"]
            }
            for etype, kws in error_keywords.items():
                for kw in kws:
                    if kw in page_content:
                        errors.update({"has_error": True, "error_type": etype})
                        break
                if errors["has_error"]: break

            error_elements = await self.page.locator('.error, .Alert').all()
            for elem in error_elements[:3]:
                msg = (await elem.text_content()).strip()
                if msg: errors["error_messages"].append(msg)
        except: pass
        return errors

    async def _analyze_and_prepare_correction(self, attempt: int, subreddit: str, rules):
        """分析失败原因并准备修正"""
        errors = await self._check_errors()
        self.attempt_history.append({
            "attempt": attempt,
            "errors": errors,
            "timestamp": time.time()
        })

    def _check_content_compliance(self, title: str, content: str, rules) -> List[str]:
        """
        检查内容是否符合社区规则

        Args:
            title: 帖子标题
            content: 帖子内容
            rules: CommunityRule 对象

        Returns:
            List[str]: 违规列表
        """
        violations = []

        # 合并所有规则文本
        rule_texts = ' '.join([r.get('title', '') + ' ' + r.get('description', '')
                              for r in rules.rules]).lower()

        full_content = (title + ' ' + content).lower()

        # 检查自我推广
        if 'self-promotion' in rule_texts or 'no self promo' in rule_texts:
            promo_indicators = ['my project', 'check out', 'visit my', 'github.com', 'follow me']
            for indicator in promo_indicators:
                if indicator in full_content:
                    violations.append(f"可能违反自我推广规则: 包含 '{indicator}'")
                    break

        # 检查外部链接
        if 'no links' in rule_texts or 'external link' in rule_texts or 'no url' in rule_texts:
            if 'http' in full_content or 'www.' in full_content:
                violations.append("包含外部链接，可能违反规则")

        # 检查低质量内容
        if 'low effort' in rule_texts or 'minimal effort' in rule_texts:
            if len(content) < 100:
                violations.append("内容过短，可能被视为低质量")

        # 检查重复发帖
        if 'no repost' in rule_texts or 'duplicate' in rule_texts:
            # 这里可以添加更复杂的检测逻辑
            pass

        return violations

    def _should_select_flair(self, requirement: Dict[str, Any]) -> bool:
        """只有检测到 Flair 必选时才允许进入选择流程。"""
        return bool(requirement.get("required") is True)

    def _detect_flair_requirement_sync(self) -> Dict[str, Any]:
        """
        检测当前 Reddit 发帖页是否强制 Flair。

        该检查只用于决定是否打开 Flair 弹窗；检测不到强制要求时默认不选择，
        后续提交按钮和 Reddit 结果仍会 fail-closed。
        """
        try:
            result = self.page.evaluate(
                """
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
                            for (const attr of ['aria-label', 'title', 'placeholder', 'data-testid']) {
                                const value = element.getAttribute(attr);
                                if (value) parts.push(value);
                            }
                        }
                        if (element.shadowRoot) visit(element.shadowRoot, depth + 1);
                        for (const child of element.childNodes || []) visit(child, depth + 1);
                    };
                    visit(document);

                    const text = parts.join(' ').replace(/\\s+/g, ' ').toLowerCase();
                    const explicitRequired = [
                        'flair is required',
                        'post flair is required',
                        'requires flair',
                        'required flair',
                        'must contain post flair',
                        'please add flair',
                        '请选择标记',
                        '必须选择标记',
                        '需要选择标记',
                        '帖子标记为必填',
                        '标记是必填',
                        '必须添加标记'
                    ].some((needle) => text.includes(needle));

                    const hasFlairControl = [
                        'add flair',
                        'select flair',
                        '添加标记',
                        '选择标记'
                    ].some((needle) => text.includes(needle));

                    const submitComponent = document.querySelector('r-post-form-submit-button#submit-post-button');
                    const shadowButton = submitComponent?.shadowRoot?.querySelector('button');
                    const submitDisabled = Boolean(
                        submitComponent?.hasAttribute('disabled') ||
                        shadowButton?.disabled ||
                        document.querySelector('button[type="submit"][disabled]')
                    );
                    const titleValue = document.querySelector('textarea[name="title"], input[name="title"]')?.value || '';
                    const hasTitle = titleValue.trim().length > 0;
                    const hasBody = text.length > 0;

                    const disabledByLikelyFlair = (
                        submitDisabled &&
                        hasFlairControl &&
                        hasTitle &&
                        hasBody &&
                        ['flair', '标记'].some((needle) => text.includes(needle))
                    );

                    return {
                        required: Boolean(explicitRequired || disabledByLikelyFlair),
                        reason: explicitRequired ? 'explicit_required_text' :
                            (disabledByLikelyFlair ? 'submit_disabled_with_flair_control' : 'no_required_signal'),
                        submit_disabled: submitDisabled,
                        has_flair_control: hasFlairControl,
                    };
                }
                """
            )
            if isinstance(result, dict):
                return result
        except Exception as exc:
            print(f"   ⚠️  Flair 必选检测失败: {exc}")
        return {
            "required": False,
            "reason": "detection_failed_default_skip",
            "submit_disabled": None,
            "has_flair_control": None,
        }

    async def _detect_flair_requirement_async(self) -> Dict[str, Any]:
        """异步版 Flair 必选检测。"""
        try:
            result = await self.page.evaluate(
                """
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
                            for (const attr of ['aria-label', 'title', 'placeholder', 'data-testid']) {
                                const value = element.getAttribute(attr);
                                if (value) parts.push(value);
                            }
                        }
                        if (element.shadowRoot) visit(element.shadowRoot, depth + 1);
                        for (const child of element.childNodes || []) visit(child, depth + 1);
                    };
                    visit(document);
                    const text = parts.join(' ').replace(/\\s+/g, ' ').toLowerCase();
                    const explicitRequired = [
                        'flair is required',
                        'post flair is required',
                        'requires flair',
                        'required flair',
                        'must contain post flair',
                        'please add flair',
                        '请选择标记',
                        '必须选择标记',
                        '需要选择标记',
                        '帖子标记为必填',
                        '标记是必填',
                        '必须添加标记'
                    ].some((needle) => text.includes(needle));
                    const hasFlairControl = [
                        'add flair',
                        'select flair',
                        '添加标记',
                        '选择标记'
                    ].some((needle) => text.includes(needle));
                    const submitComponent = document.querySelector('r-post-form-submit-button#submit-post-button');
                    const shadowButton = submitComponent?.shadowRoot?.querySelector('button');
                    const submitDisabled = Boolean(
                        submitComponent?.hasAttribute('disabled') ||
                        shadowButton?.disabled ||
                        document.querySelector('button[type="submit"][disabled]')
                    );
                    const titleValue = document.querySelector('textarea[name="title"], input[name="title"]')?.value || '';
                    const hasTitle = titleValue.trim().length > 0;
                    const hasBody = text.length > 0;
                    const disabledByLikelyFlair = (
                        submitDisabled &&
                        hasFlairControl &&
                        hasTitle &&
                        hasBody &&
                        ['flair', '标记'].some((needle) => text.includes(needle))
                    );
                    return {
                        required: Boolean(explicitRequired || disabledByLikelyFlair),
                        reason: explicitRequired ? 'explicit_required_text' :
                            (disabledByLikelyFlair ? 'submit_disabled_with_flair_control' : 'no_required_signal'),
                        submit_disabled: submitDisabled,
                        has_flair_control: hasFlairControl,
                    };
                }
                """
            )
            if isinstance(result, dict):
                return result
        except Exception as exc:
            print(f"   ⚠️  Flair 必选检测失败: {exc}")
        return {
            "required": False,
            "reason": "detection_failed_default_skip",
            "submit_disabled": None,
            "has_flair_control": None,
        }

    def _try_post_custom_with_evidence_sync(self, subreddit: str, title: str, content: str,
                                            flair: str, attempt: int, trace_id: str) -> Dict[str, Any]:
        """同步 Playwright 发帖尝试，成功必须通过 permalink 主动验证。"""
        print(f"\n🌐 访问 r/{subreddit} 提交页面...")
        self.page.goto(
            f"https://www.reddit.com/r/{subreddit}/submit",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        self._wait_for_timeout_sync(3000)

        if not self._fill_form_sync(title=title, content=content):
            return self._failure_result(
                trace_id=trace_id,
                subreddit=subreddit,
                title=title,
                status="error",
                code="reddit_form_fill_failed",
                error_message="无法填写 Reddit 标题或正文",
                attempt=attempt,
                screenshot_path=self._save_sync_screenshot("reddit_form_fill_failed", trace_id),
            )

        try:
            from Agent.reddit_visual_recognizer import RedditVisualRecognizer
        except Exception as exc:
            return self._failure_result(
                trace_id=trace_id,
                subreddit=subreddit,
                title=title,
                status="error",
                code="reddit_visual_recognizer_import_failed",
                error_message=f"无法加载 RedditVisualRecognizer: {exc}",
                attempt=attempt,
            )

        recognizer = RedditVisualRecognizer(self.page)
        flair_requirement = self._detect_flair_requirement_sync()
        selected_flair = None

        if self._should_select_flair(flair_requirement):
            print(f"\n🏷️  Flair 为必选，开始选择 ({flair_requirement.get('reason')})...")
            flair_result = recognizer.select_flair_with_ocr(
                target_flair=flair,
                max_attempts=2,
            )
            if not flair_result.get("success"):
                return self._failure_result(
                    trace_id=trace_id,
                    subreddit=subreddit,
                    title=title,
                    status="error",
                    code="reddit_flair_selection_failed",
                    error_message=f"Flair 为必选，但未能真实添加目标 Flair: {flair or '自动候选'}",
                    attempt=attempt,
                    flair_requirement=flair_requirement,
                    flair_result=flair_result,
                    screenshot_path=self._save_sync_screenshot("reddit_flair_selection_failed", trace_id),
                )
            selected_flair = flair_result.get("selected_text") or flair or "auto_selected_required_flair"
        else:
            print(f"   ✅ Flair 非必选，跳过选择 ({flair_requirement.get('reason')})")

        print("\n🖱️  提交并等待 Reddit 结果...")
        submission_result = recognizer.submit_post_and_verify(
            subreddit=subreddit,
            wait_time=20,
            title=title,
            content=content,
            target_flair=selected_flair,
            max_retries=0,
        )
        submission_result["trace_id"] = trace_id
        submission_result["subreddit"] = subreddit
        submission_result["title"] = title
        submission_result["flair_requirement"] = flair_requirement
        submission_result["selected_flair"] = selected_flair

        if not submission_result.get("success"):
            recent_evidence = self._recover_recent_post_permalink_sync(
                subreddit=subreddit,
                title=title,
            )
            if recent_evidence.get("success"):
                submission_result["success"] = True
                submission_result["status"] = "success"
                submission_result["post_url"] = recent_evidence["post_url"]
                submission_result["recovered_via"] = "recent_post_permalink_lookup"
                submission_result["recent_lookup"] = recent_evidence
                return self._success_result(
                    trace_id=trace_id,
                    subreddit=subreddit,
                    title=title,
                    post_url=recent_evidence["post_url"],
                    attempt=attempt,
                    submission_result=submission_result,
                    active_evidence=recent_evidence["active_evidence"],
                )
            return self._failure_result(
                trace_id=trace_id,
                subreddit=subreddit,
                title=title,
                status=submission_result.get("status") or "failed",
                code="reddit_submission_not_verified",
                error_message=submission_result.get("error_message") or "Reddit 提交未被验证为成功",
                attempt=attempt,
                submission_result=submission_result,
                screenshot_path=submission_result.get("screenshot_path"),
            )

        post_url = submission_result.get("post_url")
        if not self._is_reddit_post_url(post_url, subreddit):
            return self._failure_result(
                trace_id=trace_id,
                subreddit=subreddit,
                title=title,
                status="error",
                code="reddit_success_without_permalink",
                error_message=f"提交结果声称成功但没有目标社区 permalink: {post_url}",
                attempt=attempt,
                submission_result=submission_result,
                screenshot_path=submission_result.get("screenshot_path"),
            )

        active_evidence = self._active_verify_reddit_permalink_sync(
            post_url=post_url,
            subreddit=subreddit,
            title=title,
        )
        return self._success_result(
            trace_id=trace_id,
            subreddit=subreddit,
            title=title,
            post_url=post_url,
            attempt=attempt,
            submission_result=submission_result,
            active_evidence=active_evidence,
        )

    def _fill_form_sync(self, *, title: str, content: str) -> bool:
        """同步填写 Reddit 表单，找不到关键输入框时 fail-closed。"""
        print(f"\n✍️  填写表单: {title[:50]}...")
        try:
            title_input = self.page.locator('textarea[name="title"], input[name="title"]').first
            if title_input.count() <= 0:
                print("   ❌ 未找到标题输入框")
                return False
            title_input.fill(title)

            composer = self.page.locator("shreddit-composer").first
            if composer.count() > 0:
                composer.click()
                self._wait_for_timeout_sync(500)
                self.page.keyboard.press("Control+a")
                self.page.keyboard.press("Delete")
                self._wait_for_timeout_sync(300)
                self.page.keyboard.type(content, delay=20)
                print("   ✅ 表单填写完成")
                return True

            text_input = self.page.locator(
                'textarea[name="text"], div[role="textbox"], div[contenteditable="true"]'
            ).first
            if text_input.count() <= 0:
                print("   ❌ 未找到正文输入框")
                return False
            text_input.fill(content)
            print("   ✅ 表单填写完成")
            return True
        except Exception as exc:
            print(f"   ❌ 表单填写失败: {exc}")
            return False

    def _active_verify_reddit_permalink_sync(self, *, post_url: str, subreddit: str, title: str) -> Dict[str, Any]:
        """主动打开 Reddit permalink 并验证页面正文包含标题。"""
        try:
            from Agent.posting_workflows.active_post_verifier import ActivePostVerifier
        except Exception as exc:
            raise RuntimeError(f"主动验证器不可用: {exc}") from exc

        context = SimpleNamespace(require_page=lambda node: self.page)
        state = SimpleNamespace(
            status="success",
            post_url=post_url,
            subreddit=subreddit,
            title=title,
        )
        return ActivePostVerifier().verify(
            context=context,
            platform="reddit",
            state=state,
            node="reddit_smart_poster_active_verify",
        )

    def _recover_recent_post_permalink_sync(self, *, subreddit: str, title: str) -> Dict[str, Any]:
        """
        Reddit 提交后有时跳到社区页而不是帖子页；主动从最新帖子页找精确标题。

        找不到 permalink 时返回失败，不把社区页跳转当作成功。
        """
        try:
            recent_url = f"https://www.reddit.com/r/{subreddit}/new/"
            print(f"   🔎 未拿到 permalink，打开最新帖子页主动查找: {recent_url}")
            self.page.goto(recent_url, wait_until="domcontentloaded", timeout=30000)
            self._wait_for_timeout_sync(5000)
            post_url = self.page.evaluate(
                """
                (expectedTitle) => {
                    const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                    const expected = normalize(expectedTitle);
                    const absolutize = (href) => {
                        if (!href) return null;
                        try { return new URL(href, location.href).href; } catch { return null; }
                    };
                    const posts = Array.from(document.querySelectorAll('shreddit-post, article, [data-testid="post-container"]'));
                    for (const post of posts) {
                        const text = normalize(post.innerText || post.textContent || '');
                        if (!text.includes(expected)) continue;
                        const attrHref = post.getAttribute('permalink') || post.getAttribute('content-href');
                        const attrUrl = absolutize(attrHref);
                        if (attrUrl) return attrUrl;
                        const link = Array.from(post.querySelectorAll('a[href]'))
                            .find((anchor) => /\\/comments\\//.test(anchor.getAttribute('href') || ''));
                        const linkUrl = absolutize(link?.getAttribute('href'));
                        if (linkUrl) return linkUrl;
                    }
                    return '';
                }
                """,
                title,
            )
            if not self._is_reddit_post_url(post_url, subreddit):
                return {
                    "success": False,
                    "error": "最新帖子页未找到目标标题的 Reddit permalink",
                    "post_url": post_url,
                }
            active_evidence = self._active_verify_reddit_permalink_sync(
                post_url=post_url,
                subreddit=subreddit,
                title=title,
            )
            return {
                "success": True,
                "post_url": post_url,
                "verification_source": "recent_post_permalink_lookup",
                "active_evidence": active_evidence,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "post_url": None,
            }

    async def _active_verify_reddit_permalink_async(self, *, post_url: str,
                                                    subreddit: str, title: str) -> Dict[str, Any]:
        """异步打开 Reddit permalink 并验证页面正文包含标题。"""
        if not self._is_reddit_post_url(post_url, subreddit):
            raise RuntimeError(f"不是目标社区 Reddit permalink: {post_url}")
        response = await self.page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        observed_url = self.page.url
        if not self._is_reddit_post_url(observed_url, subreddit):
            raise RuntimeError(f"主动验证跳转后不在帖子 permalink: {observed_url}")
        body_text = await self.page.locator("body").inner_text(timeout=8000)
        if title.strip().lower() not in " ".join(body_text.lower().split()):
            raise RuntimeError("主动验证未在 permalink 页面找到期望标题")
        status = getattr(response, "status", None)
        return {
            "verification_source": "active_browser_permalink_open",
            "post_url": post_url,
            "observed_url": observed_url,
            "response_status": int(status) if isinstance(status, int) else None,
            "expected_text": title[:160],
            "body_snippet": body_text[:500],
            "content_match": True,
        }

    def _is_reddit_post_url(self, post_url: Optional[str], subreddit: str) -> bool:
        """用统一验证门检查 Reddit permalink 形态。"""
        try:
            from Agent.posting_workflows.verification_gate import is_platform_post_url
        except Exception:
            return False
        return is_platform_post_url("reddit", post_url, subreddit=subreddit)

    def _save_sync_screenshot(self, prefix: str, trace_id: str) -> Optional[str]:
        """保存同步 Playwright 截图，失败时返回 None 而不伪造成证据。"""
        try:
            screenshot = Path("screenshots") / f"{prefix}_{trace_id}.png"
            screenshot.parent.mkdir(exist_ok=True)
            self.page.screenshot(path=str(screenshot), full_page=True)
            return str(screenshot)
        except Exception as exc:
            print(f"   ⚠️  截图失败: {exc}")
            return None

    def _wait_for_timeout_sync(self, milliseconds: int) -> None:
        """兼容 Playwright sync page 和普通 time.sleep。"""
        waiter = getattr(self.page, "wait_for_timeout", None)
        if callable(waiter):
            waiter(milliseconds)
        else:
            time.sleep(milliseconds / 1000)

    async def _open_flair_dialog_async(self) -> bool:
        """异步打开 Flair 弹窗，供必选 Flair 路径使用。"""
        for selector in [
            'button:has-text("Add flair")',
            'button:has-text("Flair")',
            'button:has-text("添加标记")',
            'button:has-text("标记")',
            '[aria-label*="flair" i]',
            '[data-testid*="flair" i]',
        ]:
            try:
                button = self.page.locator(selector).first
                if await button.count() > 0 and await button.is_visible():
                    await button.scroll_into_view_if_needed()
                    await button.click(timeout=5000)
                    await asyncio.sleep(1)
                    if await self._is_flair_dialog_open_async():
                        return True
            except Exception as exc:
                print(f"   ⚠️  打开 Flair 弹窗失败 {selector}: {exc}")

        if self.advanced_helper:
            try:
                await self.advanced_helper.force_click_shadow_element(
                    'shreddit-composer',
                    "b => (b.textContent || '').toLowerCase().includes('flair') || (b.textContent || '').includes('标记')",
                )
                await asyncio.sleep(1)
                return await self._is_flair_dialog_open_async()
            except Exception as exc:
                print(f"   ⚠️  Shadow DOM 打开 Flair 弹窗失败: {exc}")
        return False

    async def _is_flair_dialog_open_async(self) -> bool:
        """异步检查 Flair 弹窗是否打开。"""
        try:
            return bool(await self.page.evaluate(
                """
                () => Boolean(
                    document.querySelector('[role="dialog"], shreddit-post-flair-modal, reddit-post-flair-modal')
                )
                """
            ))
        except Exception:
            return False

    async def _select_required_flair_async(self, target_flair: Optional[str]) -> Dict[str, Any]:
        """异步选择必选 Flair；非必选路径不会调用该方法。"""
        if not await self._open_flair_dialog_async():
            return {"success": False, "error": "无法打开 Flair 弹窗"}

        try:
            result = await self.page.evaluate(
                """
                (targetFlair) => {
                    const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                    const lower = (value) => normalize(value).toLowerCase();
                    const target = lower(targetFlair || '');
                    const preferred = ['discussion', '讨论', 'question', '问题', 'general', 'other', '其他'];
                    const dialog = document.querySelector('[role="dialog"], shreddit-post-flair-modal, reddit-post-flair-modal') || document.body;
                    const rows = Array.from(dialog.querySelectorAll('shreddit-post-flair-row, [role="radio"], [role="option"], label, li, div'))
                        .map((node) => ({ node, text: normalize(node.innerText || node.textContent || '') }))
                        .filter((item) => item.text.length >= 2 && !['add', 'apply', 'cancel', '添加', '取消'].includes(lower(item.text)));

                    if (!rows.length) return { success: false, error: '未找到 Flair 候选项' };

                    const scored = rows.map((item, index) => {
                        const text = lower(item.text);
                        let score = 0;
                        if (target && text === target) score += 100;
                        else if (target && (text.includes(target) || target.includes(text))) score += 80;
                        for (const keyword of preferred) {
                            if (text.includes(keyword)) score += 20;
                        }
                        score -= index * 0.01;
                        return { ...item, score };
                    }).sort((a, b) => b.score - a.score);

                    const selected = scored[0];
                    const clickable = selected.node.querySelector?.('[role="switch"], button, input[type="checkbox"], input[type="radio"], faceplate-radio-input') || selected.node;
                    clickable.click();

                    const buttons = Array.from(dialog.querySelectorAll('button')).concat(Array.from(document.querySelectorAll('button')));
                    const apply = buttons.find((button) => {
                        const text = lower(button.innerText || button.textContent || button.getAttribute('aria-label'));
                        return ['apply', 'add', 'done', 'save', '添加', '确认', '确定', '完成', '保存'].some((needle) => text.includes(needle));
                    });
                    if (apply) apply.click();
                    return { success: true, selected_text: selected.text, match_score: selected.score };
                }
                """,
                target_flair,
            )
            await asyncio.sleep(1)
            if isinstance(result, dict):
                return result
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        return {"success": False, "error": "Flair 选择返回了无效结果"}

    async def _try_post_custom(self, subreddit: str, title: str, content: str,
                               flair: str, attempt: int) -> bool:
        """旧内部 bool 入口，仅从结构化证据派生。"""
        result = await self._try_post_custom_with_evidence_async(
            subreddit=subreddit,
            title=title,
            content=content,
            flair=flair,
            attempt=attempt,
            trace_id=self._new_trace_id("reddit"),
        )
        return bool(result.get("success"))

    async def _try_post_custom_with_evidence_async(self, subreddit: str, title: str, content: str,
                                                   flair: str, attempt: int,
                                                   trace_id: str) -> Dict[str, Any]:
        """尝试发布自定义内容"""
        print(f"\n🌐 访问 r/{subreddit} 提交页面...")
        await self.page.goto(f"https://www.reddit.com/r/{subreddit}/submit",
                      wait_until="domcontentloaded", timeout=60000)

        # 步骤 1: 填写内容 (尝试新老版本)
        content_strategy = {"title": title, "content": content, "strategy": "custom"}
        if not await self._fill_form(content_strategy):
            # 备选方案: 强制注入
            print("   ⚠️  常规填写失败，尝试强制注入...")
            await self.page.evaluate(f"""
                (t, c) => {{
                    const composer = document.querySelector('shreddit-composer');
                    const root = composer ? composer.shadowRoot : document;
                    const ti = root.querySelector('input[name="title"]');
                    const co = root.querySelector('textarea[name="text"], div[role="textbox"]');
                    if (ti) ti.value = t;
                    if (co) {{
                        if (co.tagName === 'DIV') co.innerText = c;
                        else co.value = c;
                    }}
                }}
            """, title, content)

        # 步骤 2: 只有 Flair 必选时才选择
        flair_requirement = await self._detect_flair_requirement_async()
        selected_flair = None
        if self._should_select_flair(flair_requirement):
            print(f"\n🏷️  Flair 为必选，开始选择 ({flair_requirement.get('reason')})...")
            flair_result = await self._select_required_flair_async(flair)
            if not flair_result.get("success"):
                return self._failure_result(
                    trace_id=trace_id,
                    subreddit=subreddit,
                    title=title,
                    status="error",
                    code="reddit_flair_selection_failed",
                    error_message=f"Flair 为必选，但未能真实添加目标 Flair: {flair or '自动候选'}",
                    attempt=attempt,
                    flair_requirement=flair_requirement,
                    flair_result=flair_result,
                )
            selected_flair = flair_result.get("selected_text") or flair or "auto_selected_required_flair"
            print(f"   ✅ 已选择必选 Flair: {selected_flair}")
        else:
            print(f"   ✅ Flair 非必选，跳过选择 ({flair_requirement.get('reason')})")

        # 提交帖子
        print("\n🚀 提交帖子...")

        # 等待一下确保页面稳定（Flair对话框关闭后）
        print("   ⏳ 等待页面稳定...")
        await asyncio.sleep(3)

        # 步骤 C：使用高级助手轮询并点击 Post 按钮
        print("   🔍 轮询 Post 按钮状态...")
        if not self.advanced_helper:
            return self._failure_result(
                trace_id=trace_id,
                subreddit=subreddit,
                title=title,
                status="error",
                code="reddit_advanced_helper_unavailable",
                error_message="RedditAdvancedHelper 不可用，无法提交帖子",
                attempt=attempt,
                flair_requirement=flair_requirement,
            )
        button_state = await self.advanced_helper.poll_post_button_state(max_attempts=10, interval=1)

        if not button_state.get('found'):
            print(f"   ❌ 未找到 Post 按钮")
            return self._failure_result(
                trace_id=trace_id,
                subreddit=subreddit,
                title=title,
                status="error",
                code="reddit_submit_button_missing",
                error_message="未找到 Post 按钮",
                attempt=attempt,
                flair_requirement=flair_requirement,
            )

        if button_state.get('disabled'):
            print(f"   ⚠️  Post 按钮仍处于禁用状态")
            return self._failure_result(
                trace_id=trace_id,
                subreddit=subreddit,
                title=title,
                status="error",
                code="reddit_submit_button_disabled",
                error_message="Post 按钮仍处于禁用状态，未提交",
                attempt=attempt,
                flair_requirement=flair_requirement,
                button_state=button_state,
            )

        print("   ✅ Post 按钮已就绪，准备提交...")

        # 尝试提交
        post_result = await self.advanced_helper.try_submit_post()

        if not post_result.get('success'):
            print(f"   ❌ 提交失败: {post_result.get('reason')}")
            return self._failure_result(
                trace_id=trace_id,
                subreddit=subreddit,
                title=title,
                status="error",
                code="reddit_submit_click_failed",
                error_message=post_result.get("reason") or "提交按钮点击失败",
                attempt=attempt,
                flair_requirement=flair_requirement,
                post_result=post_result,
            )

        print(f"   🚀 发帖指令已发出 (方法: {post_result.get('method')})")
        print("\n⏳ 等待发布结果...")
        await asyncio.sleep(15)

        screenshot_path = Path(f"screenshots/reddit_after_submit_{trace_id}.png")
        screenshot_path.parent.mkdir(exist_ok=True)
        await self.page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"   📸 截图已保存: {screenshot_path}")

        current_url = self.page.url
        print(f"   当前 URL: {current_url}")

        submission_result = {
            "success": self._is_reddit_post_url(current_url, subreddit),
            "status": "success" if self._is_reddit_post_url(current_url, subreddit) else "unknown",
            "post_url": current_url if self._is_reddit_post_url(current_url, subreddit) else None,
            "error_message": None if self._is_reddit_post_url(current_url, subreddit) else "提交后未观察到目标社区 Reddit permalink",
            "screenshot_path": str(screenshot_path),
            "click": post_result,
            "trace_id": trace_id,
            "subreddit": subreddit,
            "title": title,
            "flair_requirement": flair_requirement,
            "selected_flair": selected_flair,
        }

        if not submission_result["success"]:
            return self._failure_result(
                trace_id=trace_id,
                subreddit=subreddit,
                title=title,
                status="unknown",
                code="reddit_submission_not_verified",
                error_message=submission_result["error_message"],
                attempt=attempt,
                submission_result=submission_result,
                screenshot_path=str(screenshot_path),
            )

        active_evidence = await self._active_verify_reddit_permalink_async(
            post_url=current_url,
            subreddit=subreddit,
            title=title,
        )
        return self._success_result(
            trace_id=trace_id,
            subreddit=subreddit,
            title=title,
            post_url=current_url,
            attempt=attempt,
            submission_result=submission_result,
            active_evidence=active_evidence,
        )

    def _display_key_rules(self, rules):
        """显示关键规则"""
        print("\n📋 关键规则摘要:")
        for i, rule in enumerate(rules.rules[:5], 1):
            title = rule.get('title', '')[:80]
            desc = rule.get('description', '')[:100]
            print(f"   {i}. {title}")
            if desc and desc != title:
                print(f"      {desc}")


# 使用示例
if __name__ == "__main__":
    print("Reddit Smart Poster Module")
    print("此模块需要与 test_social_media_automation.py 集成使用")

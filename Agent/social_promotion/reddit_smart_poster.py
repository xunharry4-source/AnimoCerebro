#!/usr/bin/env python3
"""
Reddit 智能发帖助手 - 带反复纠错功能

功能：
1. 自动检测社区规则
2. 智能内容优化
3. 多次重试机制
4. 错误检测和修正
5. Flair 自动选择
"""

import time
from pathlib import Path
from typing import Dict, List, Optional

from .reddit_advanced_helper import RedditAdvancedHelper


class RedditSmartPoster:
    """Reddit 智能发帖助手"""
    
    def __init__(self, page, rules_manager):
        self.page = page
        self.rules_manager = rules_manager
        self.attempt_history = []
        # 初始化高级助手
        self.advanced_helper = RedditAdvancedHelper(page)
        
    def post_with_retry(self, subreddit: str, max_retries: int = 3) -> bool:
        """
        带重试的发帖功能（使用自动生成的内容）
        
        流程：
        1. 检查社区规则是否存在
        2. 不存在则自动下载
        3. 基于规则生成合规内容
        4. 多次重试发帖
        
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
        rules = self._ensure_community_rules(subreddit)
        
        if not rules:
            print(f"   ❌ 无法获取 r/{subreddit} 的社区规则")
            print(f"   💡 建议: 手动访问 https://www.reddit.com/r/{subreddit}/about/rules 查看规则")
            return False
        
        print(f"   ✅ 已加载 {len(rules.rules)} 条社区规则")
        self._display_key_rules(rules)
        
        # 步骤 2: 基于规则生成初始内容
        print(f"\n📝 步骤 2: 基于社区规则生成合规内容...")
        initial_content = self._generate_compliant_content(rules, attempt=1)
        print(f"   ✅ 已生成合规内容")
        
        # 步骤 3: 重试循环
        for attempt in range(1, max_retries + 1):
            print(f"\n{'='*80}")
            print(f"  🔄 尝试 {attempt}/{max_retries}")
            print(f"{'='*80}")
            
            try:
                success = self._try_post(subreddit, attempt, rules)
                
                if success:
                    print(f"\n✅ 第 {attempt} 次尝试成功!")
                    return True
                else:
                    print(f"\n⚠️  第 {attempt} 次尝试失败")
                    
                    if attempt < max_retries:
                        print(f"\n🔧 分析失败原因并准备修正...")
                        self._analyze_and_prepare_correction(attempt, subreddit, rules)
                        time.sleep(3)
                    else:
                        print(f"\n❌ 已达到最大重试次数 ({max_retries})")
                        
            except Exception as e:
                print(f"\n❌ 第 {attempt} 次尝试出错: {e}")
                import traceback
                traceback.print_exc()
                
                if attempt < max_retries:
                    print(f"\n🔧 准备第 {attempt + 1} 次重试...")
                    time.sleep(3)
        
        return False
    
    def post_custom_content(self, subreddit: str, title: str, content: str, 
                           flair: str = None, max_retries: int = 3) -> bool:
        """
        发布自定义内容（用于 AnimoCerebro 宣传等）
        
        Args:
            subreddit: 社区名称
            title: 帖子标题
            content: 帖子内容
            flair: Flair 名称（可选）
            max_retries: 最大重试次数
            
        Returns:
            bool: 是否成功
        """
        print("\n" + "="*80)
        print(f"  📝 发布自定义内容到 r/{subreddit}")
        print(f"  🔄 最多重试 {max_retries} 次")
        print("="*80)
        
        # 步骤 1: 检查并获取社区规则
        print(f"\n📋 步骤 1: 检查 r/{subreddit} 社区规则...")
        rules = self._ensure_community_rules(subreddit)
        
        if not rules:
            print(f"   ⚠️  无法获取规则，将直接发帖")
        else:
            print(f"   ✅ 已加载 {len(rules.rules)} 条社区规则")
            
            # 验证内容是否符合规则
            violations = self._check_content_compliance(title, content, rules)
            if violations:
                print(f"   ⚠️  检测到潜在违规:")
                for v in violations:
                    print(f"      - {v}")
                print(f"   💡 建议修改内容以避免被移除")
        
        # 步骤 2: 重试循环
        for attempt in range(1, max_retries + 1):
            print(f"\n{'='*80}")
            print(f"  🔄 尝试 {attempt}/{max_retries}")
            print(f"{'='*80}")
            
            try:
                success = self._try_post_custom(subreddit, title, content, flair, attempt)
                
                if success:
                    print(f"\n✅ 第 {attempt} 次尝试成功!")
                    return True
                else:
                    print(f"\n⚠️  第 {attempt} 次尝试失败")
                    
                    if attempt < max_retries:
                        print(f"\n🔧 准备第 {attempt + 1} 次重试...")
                        time.sleep(3)
                    else:
                        print(f"\n❌ 已达到最大重试次数 ({max_retries})")
                        
            except Exception as e:
                print(f"\n❌ 第 {attempt} 次尝试出错: {e}")
                import traceback
                traceback.print_exc()
                
                if attempt < max_retries:
                    print(f"\n🔧 准备第 {attempt + 1} 次重试...")
                    time.sleep(3)
        
        return False
    
    def _try_post(self, subreddit: str, attempt: int, rules) -> bool:
        """单次发帖尝试"""
        
        # 访问提交页面
        print(f"\n🌐 访问 r/{subreddit} 提交页面...")
        self.page.goto(f"https://www.reddit.com/r/{subreddit}/submit", 
                      wait_until="domcontentloaded", timeout=60000)
        
        # 基于规则生成当前尝试的内容
        content_strategy = self._generate_compliant_content(rules, attempt)
        print(f"   ✓ 使用策略: {content_strategy['strategy']}")
        
        # 填写表单
        if not self._fill_form(content_strategy):
            print("   ❌ 表单填写失败")
            return False
        
        # 选择 Flair
        self._select_flair()
        
        # 提交帖子
        return self._submit_post(subreddit)
    
    def _ensure_community_rules(self, subreddit: str):
        """
        确保社区规则存在，不存在则下载
        
        Args:
            subreddit: 社区名称
            
        Returns:
            CommunityRule 对象或 None
        """
        # 步骤 1: 检查本地缓存
        print(f"   🔍 检查本地缓存...")
        cached_rules = self.rules_manager.get_community_rules(subreddit, auto_download=False)
        
        if cached_rules and not cached_rules.is_expired(max_age_days=7):
            print(f"   ✅ 使用缓存的规则 (更新于: {cached_rules.last_updated.strftime('%Y-%m-%d')})")
            return cached_rules
        
        # 步骤 2: 缓存不存在或已过期，需要下载
        if cached_rules:
            print(f"   ⚠️  缓存已过期，需要更新")
        else:
            print(f"   ⚠️  本地无缓存，需要下载")
        
        # 步骤 3: 尝试从网页抓取规则
        print(f"\n   🌐 正在下载 r/{subreddit} 社区规则...")
        downloaded_rules = self._download_community_rules_from_web(subreddit)
        
        if downloaded_rules:
            print(f"   ✅ 成功下载 {len(downloaded_rules.rules)} 条规则")
            
            # 保存到本地缓存（每个社区单独保存）
            self.rules_manager.save_rule_to_cache(downloaded_rules)
            cache_file = self.rules_manager._get_cache_file_path(subreddit)
            print(f"   💾 规则已保存到: {cache_file}")
            
            return downloaded_rules
        
        # 步骤 4: 如果网页抓取失败，尝试使用 API
        print(f"   ⚠️  网页抓取失败，尝试使用 Reddit API...")
        api_rules = self.rules_manager.download_community_rules(subreddit)
        
        if api_rules:
            print(f"   ✅ 通过 API 获取 {len(api_rules.rules)} 条规则")
            self.rules_manager.save_rule_to_cache(api_rules)
            return api_rules
        
        # 步骤 5: 所有方法都失败，返回过期的缓存（如果有）
        if cached_rules:
            print(f"   ⚠️  使用过期的缓存规则作为降级方案")
            return cached_rules
        
        print(f"   ❌ 无法获取社区规则")
        return None
    
    def _download_community_rules_from_web(self, subreddit: str):
        """
        从网页抓取社区规则
        
        Args:
            subreddit: 社区名称
            
        Returns:
            CommunityRule 对象或 None
        """
        try:
            from Agent.social_promotion.community_rules_manager import CommunityRule
            
            # 访问规则页面
            rules_url = f"https://www.reddit.com/r/{subreddit}/about/rules"
            print(f"      访问: {rules_url}")
            
            self.page.goto(rules_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # 提取规则
            rules = []
            
            # 方法 1: 查找规则表格
            rule_rows = self.page.locator('tr').all()
            for row in rule_rows:
                try:
                    cells = row.locator('td, th').all()
                    if len(cells) >= 2:
                        title = cells[0].text_content().strip()
                        description = cells[1].text_content().strip()
                        
                        if title and len(title) > 5:
                            rules.append({
                                "title": title[:200],
                                "description": description[:500]
                            })
                except:
                    continue
            
            # 方法 2: 如果没找到，尝试其他选择器
            if len(rules) == 0:
                rule_elements = self.page.locator('.rule-row, .md-container li, .CommunityRules__rule').all()
                for elem in rule_elements:
                    try:
                        text = elem.text_content().strip()
                        if text and len(text) > 10:
                            rules.append({
                                "title": text[:200],
                                "description": text[:500]
                            })
                    except:
                        continue
            
            # 方法 3: 从页面文本中提取
            if len(rules) == 0:
                print(f"      ⚠️  尝试从页面文本提取规则...")
                page_text = self.page.text_content('body')
                lines = page_text.split('\n')
                
                current_rule = None
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 检测规则标题（通常以数字开头或包含 "rule"）
                    if (line[0].isdigit() and '.' in line[:5]) or 'rule' in line.lower():
                        if current_rule:
                            rules.append(current_rule)
                        current_rule = {
                            "title": line[:200],
                            "description": ""
                        }
                    elif current_rule and len(line) > 20:
                        current_rule["description"] += line + " "
                
                if current_rule:
                    rules.append(current_rule)
            
            if len(rules) > 0:
                # 清理重复和空规则
                cleaned_rules = []
                seen_titles = set()
                
                for rule in rules:
                    title = rule["title"].strip()
                    if title and title not in seen_titles and len(title) > 5:
                        seen_titles.add(title)
                        cleaned_rules.append(rule)
                
                print(f"      ✅ 提取到 {len(cleaned_rules)} 条规则")
                
                return CommunityRule(
                    subreddit=subreddit,
                    rules=cleaned_rules,
                    source="scraped"
                )
            else:
                print(f"      ⚠️  未能提取到规则")
                return None
                
        except Exception as e:
            print(f"      ❌ 网页抓取失败: {e}")
            import traceback
            traceback.print_exc()
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
        """根据尝试次数和规则获取内容策略"""
        
        if attempt == 1:
            # 第一次：标准测试内容
            return {
                "title": f"Test Post - AnimoCerebro Automation #{int(time.time())}",
                "content": """Hi everyone,

This is an automated test post from AnimoCerebro to verify browser automation capabilities.

No action needed. Thanks!""",
                "strategy": "standard"
            }
        
        elif attempt == 2:
            # 第二次：更保守的内容
            return {
                "title": f"Question about r/{self.page.url.split('/r/')[1].split('/')[0] if '/r/' in self.page.url else 'Python'}",
                "content": """Hi all,

I'm new here and wanted to ask about best practices in this community. 

Could experienced members share their insights?

Thanks in advance!""",
                "strategy": "conservative"
            }
        
        else:
            # 第三次及以后：最小化内容
            return {
                "title": "Quick question",
                "content": "Does anyone have experience with this?",
                "strategy": "minimal"
            }
    
    def shadow_click(self, selector: str, text_hint: str) -> bool:
        """
        在 shreddit-composer 的 Shadow DOM 中寻找并点击按钮
        
        Args:
            selector: 内部标签名，如 'button'
            text_hint: 按钮包含的文本或 aria-label 关键字
        
        Returns:
            bool: 是否成功点击
        """
        try:
            result = self.page.evaluate(f"""
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
    
    def _fill_form(self, content_strategy: Dict) -> bool:
        """填写发帖表单"""
        try:
            # 选择文本帖子类型
            print("\n📝 创建文本帖子...")
            try:
                text_tab = self.page.locator('button:has-text("Text")').first
                if text_tab.count() > 0:
                    text_tab.click()
                    time.sleep(1)
                    print("   ✓ 已选择文本帖子类型")
            except:
                print("   ⚠️  使用默认帖子类型")
            
            # 填写标题
            print(f"\n✍️  填写标题 ({content_strategy['strategy']})...")
            title_input = self.page.locator('input[name="title"], input[placeholder*="Title"]').first
            if title_input.count() > 0:
                title_input.fill(content_strategy["title"])
                print(f"   ✓ 标题: {content_strategy['title'][:60]}")
                time.sleep(1)
            else:
                print("   ❌ 未找到标题输入框")
                return False
            
            # 填写内容
            print("\n✍️  填写内容...")
            content_input = self.page.locator('textarea[name="text"], div[role="textbox"]').first
            if content_input.count() > 0:
                content_input.fill(content_strategy["content"])
                print(f"   ✓ 内容已填写 ({len(content_strategy['content'])} 字符)")
                time.sleep(2)
            else:
                print("   ❌ 未找到内容输入框")
                return False
            
            return True
            
        except Exception as e:
            print(f"   ❌ 表单填写错误: {e}")
            return False
    
    def _select_flair(self):
        """选择 Flair（标记）"""
        print("\n🏷️  尝试选择 Flair...")
        
        try:
            flair_button = self.page.locator('button:has-text("Flair"), button:has-text("标记"), [data-testid="flair-picker"]').first
            
            if flair_button.count() > 0:
                print("   ✓ 找到 Flair 按钮")
                flair_button.click()
                time.sleep(2)
                
                # 选择合适的 Flair
                flair_options = self.page.locator('[role="dialog"] button, .flair-option').all()
                if len(flair_options) > 0:
                    # 优先选择安全的 Flair
                    safe_keywords = ['discussion', 'question', 'help', 'meta', 'general']
                    selected = False
                    
                    for option in flair_options[:10]:
                        try:
                            flair_text = option.text_content().lower()
                            if any(kw in flair_text for kw in safe_keywords):
                                option.click()
                                print(f"   ✓ 已选择 Flair: {option.text_content()[:50]}")
                                selected = True
                                break
                        except:
                            continue
                    
                    if not selected:
                        # 选择第一个
                        flair_options[0].click()
                        print(f"   ✓ 已选择第一个 Flair")
                    
                    time.sleep(2)
                else:
                    print("   ⚠️  未找到 Flair 选项")
            else:
                print("   ⚠️  该社区可能不需要 Flair")
                
        except Exception as e:
            print(f"   ⚠️  Flair 选择失败: {e}")
    
    def _submit_post(self, subreddit: str) -> bool:
        """提交帖子"""
        print("\n🚀 提交帖子...")
        
        # 查找发布按钮
        post_button_selectors = [
            'button[type="submit"]',
            'button:has-text("Post")',
            'button:has-text("发布")',
            '[data-testid="submit-button"]',
        ]
        
        post_button = None
        for selector in post_button_selectors:
            try:
                btn = self.page.locator(selector).first
                if btn.count() > 0 and btn.is_enabled():
                    post_button = btn
                    print(f"   ✓ 找到发布按钮")
                    break
            except:
                continue
        
        if not post_button:
            print("   ❌ 未找到发布按钮")
            return False
        
        # 截图
        screenshot = Path(f"screenshots/reddit_submit_attempt.png")
        screenshot.parent.mkdir(exist_ok=True)
        self.page.screenshot(path=str(screenshot), full_page=True)
        
        # 点击发布
        post_button.click()
        print("   ✓ 已点击发布")
        
        # 等待结果
        print("\n⏳ 等待发布结果...")
        time.sleep(8)
        
        # 检查是否成功
        current_url = self.page.url
        if "comments" in current_url and f"r/" in current_url:
            print("   ✅ 发帖成功!")
            
            # 成功截图
            success_screenshot = Path("screenshots/reddit_post_success.png")
            self.page.screenshot(path=str(success_screenshot), full_page=True)
            print(f"   📸 截图: {success_screenshot}")
            
            return True
        else:
            print(f"   ⚠️  发帖状态未知")
            
            # 检查错误
            errors = self._check_errors()
            if errors["has_error"]:
                print(f"   ❌ 检测到错误: {errors['error_type']}")
                for msg in errors["error_messages"][:3]:
                    print(f"      - {msg[:100]}")
            
            # 截图
            error_screenshot = Path("screenshots/reddit_post_failed.png")
            self.page.screenshot(path=str(error_screenshot), full_page=True)
            
            return False
    
    def _check_errors(self) -> Dict:
        """检查页面上的错误提示"""
        errors = {
            "has_error": False,
            "error_messages": [],
            "error_type": None
        }
        
        try:
            page_content = self.page.text_content('body').lower()
            
            # 常见错误关键词
            error_keywords = {
                "RULE_VIOLATION": ["rule", "规则", "violation", "违反"],
                "QUALITY_ISSUE": ["quality", "质量", "standard", "标准"],
                "AUTOMOD_REMOVAL": ["automod", "auto moderator", "removed by bot"],
                "SPAM_DETECTION": ["spam", "广告", "promotion", "推广"],
                "ACCOUNT_AGE": ["account age", "账号年龄", "karma"],
                "DUPLICATE_POST": ["duplicate", "重复", "already posted"]
            }
            
            for error_type, keywords in error_keywords.items():
                for keyword in keywords:
                    if keyword in page_content:
                        errors["has_error"] = True
                        errors["error_type"] = error_type
                        errors["error_messages"].append(f"检测到 {error_type}: 包含 '{keyword}'")
                        break
                
                if errors["has_error"]:
                    break
            
            # 查找明显的错误元素
            error_elements = self.page.locator('.error, [style*="red"], .text-error, .Alert').all()
            for elem in error_elements[:3]:
                try:
                    msg = elem.text_content().strip()
                    if msg and len(msg) > 10:
                        errors["has_error"] = True
                        errors["error_messages"].append(msg)
                except:
                    pass
            
        except Exception as e:
            print(f"   ⚠️  错误检测失败: {e}")
        
        return errors
    
    def _analyze_and_prepare_correction(self, attempt: int, subreddit: str, rules):
        """分析失败原因并准备修正"""
        print(f"\n🔍 分析第 {attempt} 次失败...")
        
        # 检查错误
        errors = self._check_errors()
        
        if errors["has_error"]:
            print(f"   错误类型: {errors['error_type']}")
            print(f"   错误信息:")
            for msg in errors["error_messages"][:3]:
                print(f"      - {msg[:100]}")
            
            # 根据错误类型给出建议
            if errors["error_type"] == "RULE_VIOLATION":
                print("\n💡 建议: 下次尝试将严格遵守社区规则")
                print("   - 移除所有外部链接")
                print("   - 避免自我推广")
                print("   - 使用更中性的语言")
                
            elif errors["error_type"] == "QUALITY_ISSUE":
                print("\n💡 建议: 提高帖子质量")
                print("   - 增加更多细节")
                print("   - 提出具体问题")
                print("   - 展示努力和研究")
                
            elif errors["error_type"] == "ACCOUNT_AGE":
                print("\n💡 建议: 账号限制")
                print("   - 需要更长的账号历史")
                print("   - 需要更多的 Karma")
                print("   - 考虑使用其他社区测试")
                
            elif errors["error_type"] == "SPAM_DETECTION":
                print("\n💡 建议: 避免被识别为垃圾内容")
                print("   - 不要重复发帖")
                print("   - 避免促销性语言")
                print("   - 增加有价值的讨论")
        else:
            print("   ⚠️  未检测到明确错误")
            print("   💡 建议: 尝试更简单的内容")
        
        # 记录尝试历史
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
    
    def _try_post_custom(self, subreddit: str, title: str, content: str, 
                        flair: str, attempt: int) -> bool:
        """
        尝试发布自定义内容
        
        Args:
            subreddit: 社区名称
            title: 帖子标题
            content: 帖子内容
            flair: Flair 名称
            attempt: 尝试次数
            
        Returns:
            bool: 是否成功
        """
        # 访问提交页面
        print(f"\n🌐 访问 r/{subreddit} 提交页面...")
        self.page.goto(f"https://www.reddit.com/r/{subreddit}/submit", 
                      wait_until="domcontentloaded", timeout=60000)
        
        # 填写表单
        try:
            # 选择文本帖子类型
            print("\n📝 创建文本帖子...")
            try:
                text_tab = self.page.locator('button:has-text("Text")').first
                if text_tab.count() > 0:
                    text_tab.click()
                    time.sleep(1)
                    print("   ✓ 已选择文本帖子类型")
            except:
                print("   ⚠️  使用默认帖子类型")
            
            # 填写标题
            print(f"\n✍️  填写标题...")
            
            # 等待页面加载
            time.sleep(3)
            
            # 尝试多个选择器（包括 Shadow DOM）
            title_filled = False
            
            # 方法 1: 尝试直接查找并填写
            title_selectors = [
                'input[name="title"]',
                'input[placeholder*="Title"]',
                'input[aria-label*="Title"]',
                'textarea[name="title"]',
                '#post-title',
                '[data-testid="post-title"]',
                'shreddit-composer input',
            ]
            
            for selector in title_selectors:
                try:
                    elem = self.page.locator(selector).first
                    if elem.count() > 0 and elem.is_visible():
                        print(f"   ✓ 找到标题输入框: {selector}")
                        elem.fill(title)
                        print(f"   ✓ 标题已填写: {title[:60]}...")
                        title_filled = True
                        time.sleep(1)
                        break
                except:
                    continue
            
            # 方法 2: 如果没找到，尝试通过 JavaScript 在 Shadow DOM 中查找
            if not title_filled:
                print("   ⚠️  尝试在 Shadow DOM 中查找...")
                try:
                    result = self.page.evaluate("""
                        (titleText) => {
                            const composer = document.querySelector('shreddit-composer');
                            if (composer && composer.shadowRoot) {
                                const titleInput = composer.shadowRoot.querySelector('input[placeholder*="Title"], input[name="title"]');
                                if (titleInput) {
                                    titleInput.value = titleText;
                                    titleInput.dispatchEvent(new Event('input', { bubbles: true }));
                                    titleInput.dispatchEvent(new Event('change', { bubbles: true }));
                                    return 'success';
                                }
                            }
                            return 'not_found';
                        }
                    """, title)
                    
                    if result == 'success':
                        print("   ✓ 通过 Shadow DOM 填写标题")
                        title_filled = True
                    else:
                        print("   ❌ Shadow DOM 中也未找到标题输入框")
                except Exception as e:
                    print(f"   ⚠️  Shadow DOM 查找失败: {e}")
            
            # 方法 3: 如果还是没找到，使用键盘模拟输入
            if not title_filled:
                print("   ⚠️  尝试使用键盘模拟输入...")
                try:
                    # 点击页面主体，确保焦点正确
                    self.page.click('body')
                    time.sleep(1)
                    
                    # 使用 Tab 键导航到标题字段
                    self.page.keyboard.press('Tab')
                    time.sleep(0.5)
                    
                    # 输入标题
                    self.page.keyboard.type(title, delay=50)
                    print("   ✓ 通过键盘模拟填写标题")
                    title_filled = True
                except Exception as e:
                    print(f"   ❌ 键盘模拟失败: {e}")
            
            # 检查是否成功填写
            if not title_filled:
                print("   ❌ 未找到标题输入框")
                print("   💡 可能的原因:")
                print("      1. 页面还未完全加载")
                print("      2. Reddit 更新了界面")
                print("      3. 需要先点击'Create Post'按钮")
                
                # 截图调试
                screenshot_path = Path("screenshots/reddit_title_not_found.png")
                screenshot_path.parent.mkdir(exist_ok=True)
                self.page.screenshot(path=str(screenshot_path))
                print(f"   📸 截图已保存: {screenshot_path}")
                return False
            
            # 填写内容
            print("\n✍️  填写内容...")
            
            content_filled = False
            
            # 方法 1: 尝试直接查找并填写
            content_selectors = [
                'textarea[name="text"]',
                'div[role="textbox"]',
                'textarea[placeholder*="Text"]',
                '#post-text',
                '[data-testid="post-body"]',
                'shreddit-composer textarea',
            ]
            
            for selector in content_selectors:
                try:
                    elem = self.page.locator(selector).first
                    if elem.count() > 0 and elem.is_visible():
                        print(f"   ✓ 找到内容输入框: {selector}")
                        elem.fill(content)
                        print(f"   ✓ 内容已填写 ({len(content)} 字符)")
                        content_filled = True
                        time.sleep(2)
                        break
                except:
                    continue
            
            # 方法 2: 如果没找到，尝试通过 JavaScript 在 Shadow DOM 中查找
            if not content_filled:
                print("   ⚠️  尝试在 Shadow DOM 中查找内容框...")
                try:
                    result = self.page.evaluate("""
                        (contentText) => {
                            const composer = document.querySelector('shreddit-composer');
                            if (composer && composer.shadowRoot) {
                                // 查找内容输入框（可能是 textarea 或 div）
                                let contentInput = composer.shadowRoot.querySelector('textarea[name="text"], div[role="textbox"]');
                                
                                if (!contentInput) {
                                    // 尝试查找所有可编辑元素
                                    const allInputs = composer.shadowRoot.querySelectorAll('textarea, div[contenteditable="true"], div[role="textbox"]');
                                    if (allInputs.length > 0) {
                                        contentInput = allInputs[0];
                                    }
                                }
                                
                                if (contentInput) {
                                    if (contentInput.tagName === 'TEXTAREA') {
                                        contentInput.value = contentText;
                                    } else {
                                        contentInput.innerText = contentText;
                                    }
                                    contentInput.dispatchEvent(new Event('input', { bubbles: true }));
                                    contentInput.dispatchEvent(new Event('change', { bubbles: true }));
                                    return 'success';
                                }
                            }
                            return 'not_found';
                        }
                    """, content)
                    
                    if result == 'success':
                        print("   ✓ 通过 Shadow DOM 填写内容")
                        content_filled = True
                    else:
                        print("   ❌ Shadow DOM 中也未找到内容输入框")
                except Exception as e:
                    print(f"   ⚠️  Shadow DOM 查找失败: {e}")
            
            # 方法 3: 使用键盘模拟
            if not content_filled:
                print("   ⚠️  尝试使用键盘模拟填写内容...")
                try:
                    # 先点击内容区域确保焦点正确
                    # 尝试点击可能的内容区域
                    content_areas = [
                        'textarea[name="text"]',
                        'div[role="textbox"]',
                        'shreddit-composer',
                        '[data-testid="post-body"]',
                    ]
                    
                    clicked = False
                    for area_selector in content_areas:
                        try:
                            area = self.page.locator(area_selector).first
                            if area.count() > 0 and area.is_visible():
                                area.click()
                                print(f"   ✓ 点击内容区域: {area_selector}")
                                clicked = True
                                time.sleep(0.5)
                                break
                        except:
                            continue
                    
                    if not clicked:
                        print("   ⚠️  未找到可点击的内容区域，直接输入")
                    
                    # 输入内容（限制长度以避免超时）
                    content_preview = content[:500] if len(content) > 500 else content
                    self.page.keyboard.type(content_preview, delay=30)
                    print(f"   ✓ 通过键盘模拟填写内容 ({len(content_preview)} 字符)")
                    content_filled = True
                    
                    # 等待一下确保内容已输入
                    time.sleep(1)
                except Exception as e:
                    print(f"   ❌ 键盘模拟失败: {e}")
            
            if not content_filled:
                print("   ❌ 未找到内容输入框")
                return False
            
        except Exception as e:
            print(f"   ❌ 表单填写错误: {e}")
            return False
        
        # 选择 Flair（如果提供）
        if flair:
            print(f"\n🏷️  尝试选择 Flair: {flair}")
            try:
                # 使用高级助手获取所有 Flair 选项
                flairs = self.advanced_helper.get_all_flair_options()
                
                if flairs:
                    print(f"   🔍 找到 {len(flairs)} 个 Flair 选项")
                    
                    # 查找匹配的 Flair
                    selected = False
                    for flair_opt in flairs:
                        print(f"      - {flair_opt['text']}")
                        if flair.lower() in flair_opt['text'].lower():
                            # 重新打开对话框并选择
                            self.advanced_helper.force_click_shadow_element(
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
                                        return span && span.textContent.includes('{flair}');
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
                            print(f"   ✅ 已选择 Flair: {flair_opt['text']}")
                            selected = True
                            break
                    
                    if not selected:
                        print(f"   ⚠️  未找到匹配的 Flair: {flair}")
                else:
                    print(f"   ⚠️  未获取到 Flair 选项，跳过")
            
            except Exception as e:
                print(f"   ⚠️  Flair 选择失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 提交帖子
        print("\n🚀 提交帖子...")
        
        # 等待一下确保页面稳定（Flair对话框关闭后）
        print("   ⏳ 等待页面稳定...")
        time.sleep(3)
        
        # 步骤 C：使用高级助手轮询并点击 Post 按钮
        print("   🔍 轮询 Post 按钮状态...")
        button_state = self.advanced_helper.poll_post_button_state(max_attempts=10, interval=1)
        
        if not button_state.get('found'):
            print(f"   ❌ 未找到 Post 按钮")
            return False
        
        if button_state.get('disabled'):
            print(f"   ⚠️  Post 按钮仍处于禁用状态")
            return False
        
        print("   ✅ Post 按钮已就绪，准备提交...")
        
        # 尝试提交
        post_result = self.advanced_helper.try_submit_post()
        
        if post_result.get('success'):
            print(f"   🚀 发帖指令已发出 (方法: {post_result.get('method')})")
            print("\n⏳ 等待发布结果...")
            time.sleep(10)  # 增加等待时间
            
            # 截图
            screenshot_path = Path(f"screenshots/reddit_after_submit.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"   📸 截图已保存: {screenshot_path}")
            
            # 检查是否成功
            current_url = self.page.url
            print(f"   当前 URL: {current_url}")
            
            if f"/r/{subreddit}/comments/" in current_url or "/posts/" in current_url:
                print("✅ 帖子发布成功！")
                return True
            else:
                print(f"⚠️  发布状态未知")
                return False
        else:
            print(f"   ❌ 提交失败: {post_result.get('reason')}")
            return False
    
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

"""
Community Rules Manager - 社区规则管理器

文件用途:
    管理 Reddit 等社交平台的社区规则，支持：
    - 本地缓存社区规则
    - 自动下载缺失的规则
    - 规则过期检查和更新
    - 发帖前规则验证

主要职责:
    - 加载和保存社区规则到本地文件系统
    - 通过 Reddit API 或网页抓取获取最新规则
    - 检查帖子内容是否符合社区规则
    - 提供规则建议和修正方案

不负责:
    - 不替代人工审核最终决定
    - 不保证 100% 符合所有社区规则（规则可能随时变化）
    - 不处理需要特殊权限的私有社区
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class CommunityRule:
    """社区规则模型"""

    def __init__(
        self,
        subreddit: str,
        rules: List[Dict[str, Any]],
        last_updated: Optional[datetime] = None,
        source: str = "manual"
    ):
        self.subreddit = subreddit
        self.rules = rules  # 规则列表，每个规则包含 title, description, violation_examples
        self.last_updated = last_updated or datetime.now(timezone.utc)
        self.source = source  # "manual", "api", "scraped"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subreddit": self.subreddit,
            "rules": self.rules,
            "last_updated": self.last_updated.isoformat(),
            "source": self.source,
            "rule_count": len(self.rules)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CommunityRule':
        return cls(
            subreddit=data["subreddit"],
            rules=data["rules"],
            last_updated=datetime.fromisoformat(data["last_updated"]),
            source=data.get("source", "manual")
        )

    def is_expired(self, max_age_days: int = 7) -> bool:
        """检查规则是否过期"""
        age = datetime.now(timezone.utc) - self.last_updated
        return age > timedelta(days=max_age_days)

    def get_rule_text_list(self) -> List[str]:
        """获取规则文本列表（用于 LLM prompt）"""
        return [f"{i+1}. {rule.get('title', '')}: {rule.get('description', '')}"
                for i, rule in enumerate(self.rules)]


class CommunityRulesManager:
    """
    社区规则管理器

    功能：
    - 本地缓存 Reddit 社区规则
    - 自动下载缺失或过期的规则
    - 发帖前验证内容是否符合规则
    """

    def __init__(self, cache_dir: Optional[str] = None):
        # 缓存目录
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # 默认缓存目录：Agent/community_rules_cache/
            script_dir = Path(__file__).parent
            self.cache_dir = script_dir / "community_rules_cache"

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 内存缓存
        self.rules_cache: Dict[str, CommunityRule] = {}

        # 规则过期时间（天）
        self.rule_max_age_days = 7

        # 加载已缓存的规则
        self._load_cached_rules()

        logger.info(f"✅ CommunityRulesManager initialized (cache: {self.cache_dir})")

    def _load_cached_rules(self):
        """从本地文件系统加载已缓存的规则"""
        for json_file in self.cache_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    rule = CommunityRule.from_dict(data)
                    self.rules_cache[rule.subreddit] = rule
                    logger.debug(f"Loaded cached rules for r/{rule.subreddit}")
            except Exception as e:
                logger.warning(f"Failed to load cached rules from {json_file}: {e}")

        logger.info(f"Loaded {len(self.rules_cache)} cached community rules")

    def _get_cache_file_path(self, subreddit: str) -> Path:
        """获取社区规则的缓存文件路径"""
        # 清理 subreddit 名称（移除 r/ 前缀）
        clean_name = subreddit.replace("r/", "").replace("/", "_")
        return self.cache_dir / f"{clean_name}.json"

    def save_rule_to_cache(self, rule: CommunityRule):
        """保存规则到本地缓存"""
        cache_file = self._get_cache_file_path(rule.subreddit)

        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(rule.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"💾 Saved rules for r/{rule.subreddit} to {cache_file}")
        except Exception as e:
            logger.error(f"Failed to save rules for r/{rule.subreddit}: {e}")

    def get_community_rules(self, subreddit: str, auto_download: bool = True) -> Optional[CommunityRule]:
        """
        获取社区规则

        Args:
            subreddit: 社区名称（如 "MachineLearning" 或 "r/MachineLearning"）
            auto_download: 如果规则不存在或过期，是否自动下载

        Returns:
            CommunityRule 对象，如果无法获取则返回 None
        """
        # 清理 subreddit 名称
        clean_subreddit = subreddit.replace("r/", "")

        # 检查内存缓存
        if clean_subreddit in self.rules_cache:
            rule = self.rules_cache[clean_subreddit]

            # 检查是否过期
            if not rule.is_expired(self.rule_max_age_days):
                logger.debug(f"Using cached rules for r/{clean_subreddit}")
                return rule
            else:
                logger.info(f"Rules for r/{clean_subreddit} expired, will refresh")

        # 如果需要自动下载
        if auto_download:
            logger.info(f"Downloading rules for r/{clean_subreddit}...")
            rule = self.download_community_rules(clean_subreddit)

            if rule:
                return rule

        # 即使过期也返回缓存的规则（作为降级方案）
        if clean_subreddit in self.rules_cache:
            logger.warning(f"Returning expired rules for r/{clean_subreddit}")
            return self.rules_cache[clean_subreddit]

        return None

    def download_community_rules(self, subreddit: str) -> Optional[CommunityRule]:
        """
        下载社区规则

        方法优先级：
        1. Reddit API（需要认证）
        2. 网页抓取（无需认证，但可能被限流）
        3. 使用默认规则模板（fallback）

        Args:
            subreddit: 社区名称

        Returns:
            CommunityRule 对象，如果失败则返回 None
        """
        clean_subreddit = subreddit.replace("r/", "")

        # 尝试方法 1: Reddit API
        rule = self._download_via_reddit_api(clean_subreddit)
        if rule:
            logger.info(f"✅ Downloaded rules for r/{clean_subreddit} via Reddit API")
            self.rules_cache[clean_subreddit] = rule
            self.save_rule_to_cache(rule)
            return rule

        # 尝试方法 2: 网页抓取
        rule = self._download_via_web_scraping(clean_subreddit)
        if rule:
            logger.info(f"✅ Downloaded rules for r/{clean_subreddit} via web scraping")
            self.rules_cache[clean_subreddit] = rule
            self.save_rule_to_cache(rule)
            return rule

        # Fallback: 使用默认规则模板
        logger.warning(f"⚠️  Using default rules template for r/{clean_subreddit}")
        rule = self._create_default_rules(clean_subreddit)
        self.rules_cache[clean_subreddit] = rule
        self.save_rule_to_cache(rule)
        return rule

    def _download_via_reddit_api(self, subreddit: str) -> Optional[CommunityRule]:
        """
        通过 Reddit API 下载规则（需要 OAuth 认证）

        注意：此方法需要有效的 Reddit API 凭证
        """
        # TODO: 实现 Reddit API 调用
        # 需要：
        # 1. Reddit API credentials (client_id, client_secret)
        # 2. OAuth token
        # 3. 调用 GET /r/{subreddit}/about/rules

        logger.debug(f"Reddit API method not yet implemented for r/{subreddit}")
        return None

    def _download_via_web_scraping(self, subreddit: str) -> Optional[CommunityRule]:
        """
        通过网页抓取获取社区规则

        使用 Playwright 访问 Reddit 社区规则页面并提取规则
        """
        try:
            # 检查 Playwright 是否可用
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                logger.warning("Playwright not available for web scraping")
                return None

            rules_url = f"https://www.reddit.com/r/{subreddit}/about/rules"

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (compatible; CommunityRulesBot/1.0)"
                )
                page = context.new_page()

                # 访问规则页面
                page.goto(rules_url, wait_until="networkidle", timeout=10000)

                # 等待规则加载
                page.wait_for_selector(".rule", timeout=5000)

                # 提取规则
                rules_data = []
                rule_elements = page.query_selector_all(".rule")

                for rule_elem in rule_elements:
                    title_elem = rule_elem.query_selector(".rule-title")
                    desc_elem = rule_elem.query_selector(".rule-description")

                    if title_elem:
                        rule_info = {
                            "title": title_elem.inner_text().strip(),
                            "description": desc_elem.inner_text().strip() if desc_elem else "",
                            "violation_examples": []
                        }
                        rules_data.append(rule_info)

                browser.close()

                if rules_data:
                    return CommunityRule(
                        subreddit=subreddit,
                        rules=rules_data,
                        last_updated=datetime.now(timezone.utc),
                        source="scraped"
                    )

        except Exception as e:
            logger.error(f"Web scraping failed for r/{subreddit}: {e}")

        return None

    def _create_default_rules(self, subreddit: str) -> CommunityRule:
        """
        创建默认规则模板（fallback）

        基于常见 Reddit 社区规则的通用模板
        """
        default_rules = [
            {
                "title": "Be respectful and civil",
                "description": "Treat all users with respect. No personal attacks, harassment, or hate speech.",
                "violation_examples": ["Insulting other users", "Threats", "Discriminatory language"]
            },
            {
                "title": "No spam or excessive self-promotion",
                "description": "Limit self-promotion to appropriate contexts. Follow the 10:1 rule (10 non-promotional posts for every 1 promotional post).",
                "violation_examples": ["Repeatedly posting same content", "Only posting your own content", "Vote manipulation"]
            },
            {
                "title": "Follow Reddit's content policy",
                "description": "All content must comply with Reddit's site-wide rules and content policy.",
                "violation_examples": ["Illegal content", "Non-consensual intimate media", "Impersonation"]
            },
            {
                "title": "Use appropriate post flair",
                "description": "Tag your posts with relevant flairs to help organize content.",
                "violation_examples": ["Missing flair", "Incorrect flair"]
            },
            {
                "title": "No low-effort content",
                "description": "Posts should contribute meaningfully to the community discussion.",
                "violation_examples": ["One-word titles", "Meme without context", "Obvious reposts"]
            }
        ]

        return CommunityRule(
            subreddit=subreddit,
            rules=default_rules,
            last_updated=datetime.now(timezone.utc),
            source="default_template"
        )

    def validate_post_against_rules(
        self,
        subreddit: str,
        title: str,
        content: str,
        post_type: str = "text"
    ) -> Dict[str, Any]:
        """
        验证帖子是否符合社区规则

        Args:
            subreddit: 社区名称
            title: 帖子标题
            content: 帖子内容
            post_type: 帖子类型（text, link, image）

        Returns:
            验证结果字典
        """
        # 获取社区规则
        rules = self.get_community_rules(subreddit, auto_download=True)

        if not rules:
            return {
                "valid": False,
                "error": f"Could not retrieve rules for r/{subreddit}",
                "violations": [],
                "suggestions": ["Try posting to a different community"]
            }

        violations = []
        suggestions = []

        # 检查自推广（如果有相关规则）
        self_promo_keywords = ["check out", "my project", "i built", "try my", "sign up"]
        content_lower = f"{title} {content}".lower()

        for keyword in self_promo_keywords:
            if keyword in content_lower:
                violations.append({
                    "rule": "No excessive self-promotion",
                    "reason": f"Content contains self-promotional language: '{keyword}'",
                    "severity": "warning"
                })
                suggestions.append(
                    "Rephrase to focus on value to community rather than promotion"
                )
                break

        # 检查标题长度
        if len(title) > 300:
            violations.append({
                "rule": "Title length limit",
                "reason": f"Title is {len(title)} characters (max 300)",
                "severity": "error"
            })
            suggestions.append("Shorten title to under 300 characters")

        # 检查内容是否为空
        if not content.strip():
            violations.append({
                "rule": "Content requirement",
                "reason": "Post content is empty",
                "severity": "error"
            })
            suggestions.append("Add meaningful content to your post")

        # 使用 LLM 进行更智能的规则检查（如果可用）
        llm_violations = self._check_with_llm(rules, title, content)
        violations.extend(llm_violations)

        is_valid = len([v for v in violations if v["severity"] == "error"]) == 0

        return {
            "valid": is_valid,
            "subreddit": subreddit,
            "rules_checked": len(rules.rules),
            "violations": violations,
            "suggestions": suggestions,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def _check_with_llm(self, rules: CommunityRule, title: str, content: str) -> List[Dict[str, Any]]:
        """
        使用 LLM 检查帖子是否符合社区规则

        这是一个更智能的检查方法，可以理解规则的语义
        """
        try:
            from zentex.llm import get_llm_service
            from zentex.foundation.specs.model_provider import ModelProviderCallerContext
            import uuid

            llm_service = get_llm_service()

            rule_texts = "\n".join(rules.get_rule_text_list())

            prompt = f"""
请检查以下帖子是否符合 r/{rules.subreddit} 的社区规则。

社区规则：
{rule_texts}

帖子标题：{title}
帖子内容：{content[:1000]}

请分析：
1. 是否违反了任何规则？
2. 如果有违反，具体是哪条规则？
3. 如何修改才能符合规则？

输出 JSON 格式：
{{
    "violations": [
        {{
            "rule": "规则名称",
            "reason": "违反原因",
            "severity": "error" 或 "warning"
        }}
    ],
    "suggestions": ["修改建议1", "修改建议2"]
}}

如果没有违反，返回空数组。
"""

            caller_context = ModelProviderCallerContext(
                source_module="community_rules_manager",
                invocation_phase="rule_validation",
                trace_id=f"rule-check:{uuid.uuid4().hex[:8]}"
            )

            result = llm_service.generate_json(
                prompt=prompt,
                context={"subreddit": rules.subreddit},
                caller_context=caller_context,
                source_module="community_rules_manager",
                invocation_phase="rule_validation",
            )

            return result.output.get("violations", [])

        except Exception as e:
            logger.debug(f"LLM rule check failed: {e}")
            return []

    def list_cached_rules(self) -> List[Dict[str, Any]]:
        """列出所有已缓存的规则"""
        return [
            {
                "subreddit": rule.subreddit,
                "rule_count": len(rule.rules),
                "last_updated": rule.last_updated.isoformat(),
                "source": rule.source,
                "is_expired": rule.is_expired(self.rule_max_age_days)
            }
            for rule in self.rules_cache.values()
        ]

    def clear_expired_rules(self) -> int:
        """清除过期的规则缓存"""
        expired = [
            name for name, rule in self.rules_cache.items()
            if rule.is_expired(self.rule_max_age_days)
        ]

        for name in expired:
            del self.rules_cache[name]
            cache_file = self._get_cache_file_path(name)
            if cache_file.exists():
                cache_file.unlink()

        logger.info(f"Cleared {len(expired)} expired rules from cache")
        return len(expired)

    def clear_all_rules(self):
        """清除所有规则缓存"""
        self.rules_cache.clear()
        for json_file in self.cache_dir.glob("*.json"):
            json_file.unlink()
        logger.info("Cleared all cached rules")

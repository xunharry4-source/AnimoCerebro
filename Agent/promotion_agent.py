"""
Promotion Agent - 社交媒体宣传自动化代理

文件用途:
    提供自动化的社交媒体宣传能力，支持在X(Twitter)和Reddit平台自动发帖，
    制定宣传计划，追踪宣传效果，并根据不同社区规则优化内容。

主要职责:
    - 制定和管理每日/每周/每月宣传计划
    - 自动在X平台发布宣传内容
    - 自动在Reddit不同subreddit发布符合社区规则的内容
    - 根据平台特性智能优化宣传文案
    - 追踪和分析宣传效果（点赞、评论、转发等）
    - 提供宣传数据分析和报告

不负责:
    - 不处理付费广告投放
    - 不管理用户账号安全（如密码修改、两步验证等）
    - 不生成原始创意内容（需要用户提供基础素材）
    - 不违反各平台的API使用条款和社区规范
"""

import logging
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class Platform(Enum):
    """支持的社交平台"""
    X = "x"  # Twitter
    REDDIT = "reddit"


class PostStatus(Enum):
    """帖子状态"""
    PENDING = "pending"  # 待发布
    SCHEDULED = "scheduled"  # 已调度
    PUBLISHED = "published"  # 已发布
    FAILED = "failed"  # 发布失败
    OPTIMIZED = "optimized"  # 已优化


class ReviewStatus(Enum):
    """审核状态"""
    PENDING_REVIEW = "pending_review"  # 待审核
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"  # 已拒绝
    NEEDS_REVISION = "needs_revision"  # 需要修改
    AUTO_APPROVED = "auto_approved"  # 自动批准（低风险）


class PromotionPlan:
    """宣传计划模型"""

    def __init__(self, plan_id: str, title: str, description: str,
                 platforms: List[Platform], start_date: datetime,
                 end_date: datetime, target_audience: str = "",
                 goals: List[str] = None, budget: float = 0.0):
        self.plan_id = plan_id
        self.title = title
        self.description = description
        self.platforms = platforms
        self.start_date = start_date
        self.end_date = end_date
        self.target_audience = target_audience
        self.goals = goals or []
        self.budget = budget
        self.posts: List[Dict[str, Any]] = []
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.status = "active"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "title": self.title,
            "description": self.description,
            "platforms": [p.value for p in self.platforms],
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "target_audience": self.target_audience,
            "goals": self.goals,
            "budget": self.budget,
            "posts_count": len(self.posts),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class RedditCommunityRule:
    """Reddit社区规则"""

    def __init__(self, subreddit: str, rules: List[str],
                 post_types: List[str], max_title_length: int = 300,
                 max_body_length: int = 40000, requires_flair: bool = False,
                 allowed_flairs: List[str] = None, min_karma: int = 0,
                 min_account_age_days: int = 0):
        self.subreddit = subreddit
        self.rules = rules
        self.post_types = post_types  # ["link", "text", "image"]
        self.max_title_length = max_title_length
        self.max_body_length = max_body_length
        self.requires_flair = requires_flair
        self.allowed_flairs = allowed_flairs or []
        self.min_karma = min_karma
        self.min_account_age_days = min_account_age_days

    def validate_post(self, title: str, body: str = "",
                      post_type: str = "text") -> Dict[str, Any]:
        """验证帖子是否符合社区规则"""
        violations = []

        if len(title) > self.max_title_length:
            violations.append(
                f"Title too long: {len(title)} > {self.max_title_length}"
            )

        if body and len(body) > self.max_body_length:
            violations.append(
                f"Body too long: {len(body)} > {self.max_body_length}"
            )

        if post_type not in self.post_types:
            violations.append(
                f"Post type '{post_type}' not allowed. "
                f"Allowed: {self.post_types}"
            )

        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "subreddit": self.subreddit
        }


class ContentOptimizer:
    """内容优化器 - 根据平台特性优化宣传文案"""

    def __init__(self):
        self.x_max_length = 280
        self.reddit_title_max = 300
        self.hashtag_db = {
            "tech": ["#Tech", "#Innovation", "#AI", "#Technology"],
            "startup": ["#Startup", "#Entrepreneur", "#Business"],
            "product": ["#Product", "#Launch", "#NewProduct"],
            "general": ["#Promotion", "#Announcement"]
        }

    def optimize_for_x(self, content: str, category: str = "general",
                       include_hashtags: bool = True) -> str:
        """为X平台优化内容"""
        optimized = content.strip()

        # 截断到合适长度
        if include_hashtags:
            hashtags = " ".join(self.hashtag_db.get(category,
                                                     self.hashtag_db["general"]))
            max_content_length = self.x_max_length - len(hashtags) - 2
        else:
            max_content_length = self.x_max_length
            hashtags = ""

        if len(optimized) > max_content_length:
            optimized = optimized[:max_content_length - 3] + "..."

        if include_hashtags and hashtags:
            optimized = f"{optimized} {hashtags}"

        return optimized

    def optimize_for_reddit(self, title: str, body: str,
                            subreddit: str = "") -> Dict[str, str]:
        """为Reddit优化内容"""
        optimized_title = title.strip()
        optimized_body = body.strip()

        # Reddit标题优化
        if len(optimized_title) > self.reddit_title_max:
            optimized_title = optimized_title[:self.reddit_title_max - 3] + "..."

        # 确保标题不以特殊字符开头（某些subreddit禁止）
        optimized_title = optimized_title.lstrip("!@#$%^&*")

        # Reddit正文优化 - 添加适当的格式
        if optimized_body and not optimized_body.startswith("#"):
            # 如果没有markdown标题，添加一个
            lines = optimized_body.split("\n")
            if lines and not lines[0].startswith("#"):
                optimized_body = f"## {lines[0]}\n" + "\n".join(lines[1:])

        return {
            "title": optimized_title,
            "body": optimized_body
        }

    def generate_variations(self, base_content: str,
                            count: int = 3) -> List[str]:
        """生成内容变体用于A/B测试"""
        variations = [base_content]

        # 简单的变体生成策略
        prefixes = [
            "Exciting news! ",
            "Check this out: ",
            "Just launched: ",
            "Introducing: ",
            "Now available: "
        ]

        for i in range(1, count):
            prefix = prefixes[i % len(prefixes)]
            variation = prefix + base_content
            if len(variation) <= self.x_max_length:
                variations.append(variation)
            else:
                variations.append(base_content)

        return variations


class PromotionAgent:
    """
    宣传Agent - 自动化社交媒体宣传

    功能:
    - 创建和管理宣传计划
    - 自动在X和Reddit发帖
    - 内容优化和适配
    - 结果追踪和分析
    """

    def __init__(self, config_path: Optional[str] = None):
        self.agent_id = "agent-promotion"
        self.name = "Promotion Agent"
        self.status = "active"
        self.created_at = datetime.now(timezone.utc)

        # 配置
        self.config = self._load_config(config_path)

        # 组件
        self.content_optimizer = ContentOptimizer()

        # 数据存储
        self.plans: Dict[str, PromotionPlan] = {}
        self.posts: Dict[str, Dict[str, Any]] = {}
        self.community_rules: Dict[str, RedditCommunityRule] = {}
        self.analytics: Dict[str, Any] = {}
        
        # 人工干预和审计链
        self.audit_log: List[Dict[str, Any]] = []  # 审计日志
        self.review_queue: Dict[str, Dict[str, Any]] = {}  # 审核队列
        self.intervention_history: Dict[str, List[Dict[str, Any]]] = {}  # 干预历史
        
        # 浏览器自动化（可选）
        self.browser_manager = None
        self.use_browser_automation = False

        # 初始化默认社区规则
        self._init_default_community_rules()

        logger.info("✅ Promotion Agent initialized")

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "x_api": {
                "api_key": os.getenv("X_API_KEY", ""),
                "api_secret": os.getenv("X_API_SECRET", ""),
                "access_token": os.getenv("X_ACCESS_TOKEN", ""),
                "access_token_secret": os.getenv("X_ACCESS_TOKEN_SECRET", ""),
                "bearer_token": os.getenv("X_BEARER_TOKEN", "")
            },
            "reddit_api": {
                "client_id": os.getenv("REDDIT_CLIENT_ID", ""),
                "client_secret": os.getenv("REDDIT_CLIENT_SECRET", ""),
                "user_agent": os.getenv("REDDIT_USER_AGENT",
                                        "PromotionAgent/1.0"),
                "username": os.getenv("REDDIT_USERNAME", ""),
                "password": os.getenv("REDDIT_PASSWORD", "")
            },
            "posting_schedule": {
                "max_posts_per_day": 10,
                "min_interval_minutes": 30,
                "preferred_hours": [9, 12, 15, 18, 21]
            },
            "content_optimization": {
                "auto_optimize": True,
                "enable_hashtags": True,
                "enable_variations": True
            }
        }

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    # 合并配置
                    for key in user_config:
                        if isinstance(user_config[key], dict):
                            default_config[key].update(user_config[key])
                        else:
                            default_config[key] = user_config[key]
                logger.info(f"✅ Loaded config from {config_path}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load config: {e}, using defaults")

        return default_config

    def _init_default_community_rules(self):
        """初始化默认的Reddit社区规则"""
        # 这些是示例规则，实际使用时需要根据具体subreddit更新
        default_rules = [
            RedditCommunityRule(
                subreddit="technology",
                rules=["No spam", "Relevant content only", "No self-promotion without context"],
                post_types=["link", "text"],
                max_title_length=300,
                requires_flair=True,
                allowed_flairs=["News", "Discussion", "Question"],
                min_karma=10,
                min_account_age_days=7
            ),
            RedditCommunityRule(
                subreddit="programming",
                rules=["Programming related only", "No low-effort posts"],
                post_types=["link", "text"],
                max_title_length=300,
                requires_flair=True,
                allowed_flairs=["Project", "Article", "Tutorial"],
                min_karma=50,
                min_account_age_days=30
            ),
            RedditCommunityRule(
                subreddit="startups",
                rules=["Startup related content", "Show HN on weekends only"],
                post_types=["link", "text"],
                max_title_length=300,
                requires_flair=False,
                min_karma=20,
                min_account_age_days=14
            )
        ]

        for rule in default_rules:
            self.community_rules[rule.subreddit] = rule

    def create_promotion_plan(self, title: str, description: str,
                              platforms: List[str],
                              start_date: Optional[str] = None,
                              end_date: Optional[str] = None,
                              target_audience: str = "",
                              goals: List[str] = None,
                              budget: float = 0.0) -> Dict[str, Any]:
        """
        创建宣传计划

        Args:
            title: 计划标题
            description: 计划描述
            platforms: 目标平台列表 ["x", "reddit"]
            start_date: 开始日期 (ISO format string)
            end_date: 结束日期 (ISO format string)
            target_audience: 目标受众描述
            goals: 宣传目标列表
            budget: 预算

        Returns:
            创建的 план信息
        """
        plan_id = f"plan_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # 解析日期
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_dt = datetime.now(timezone.utc)

        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_dt = start_dt + timedelta(days=7)  # 默认7天

        # 转换平台字符串为枚举
        platform_enums = []
        for p in platforms:
            if p.lower() == "x" or p.lower() == "twitter":
                platform_enums.append(Platform.X)
            elif p.lower() == "reddit":
                platform_enums.append(Platform.REDDIT)

        plan = PromotionPlan(
            plan_id=plan_id,
            title=title,
            description=description,
            platforms=platform_enums,
            start_date=start_dt,
            end_date=end_dt,
            target_audience=target_audience,
            goals=goals or [],
            budget=budget
        )

        self.plans[plan_id] = plan

        logger.info(f"✅ Created promotion plan: {plan_id}")

        return {
            "success": True,
            "plan": plan.to_dict(),
            "message": "Promotion plan created successfully"
        }

    def schedule_post(self, plan_id: str, platform: str,
                      content: str, scheduled_time: Optional[str] = None,
                      subreddit: Optional[str] = None,
                      title: Optional[str] = None,
                      media_urls: List[str] = None) -> Dict[str, Any]:
        """
        调度帖子发布

        Args:
            plan_id: 宣传计划ID
            platform: 平台 ("x" 或 "reddit")
            content: 帖子内容
            scheduled_time: 调度时间 (ISO format)
            subreddit: Reddit子版块（仅Reddit）
            title: 帖子标题（仅Reddit）
            media_urls: 媒体URL列表

        Returns:
            调度结果
        """
        if plan_id not in self.plans:
            return {
                "success": False,
                "error": f"Plan {plan_id} not found"
            }

        post_id = f"post_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"

        # 内容优化
        optimized_content = content
        if self.config["content_optimization"]["auto_optimize"]:
            if platform.lower() in ["x", "twitter"]:
                optimized_content = self.content_optimizer.optimize_for_x(
                    content, category="tech"
                )
            elif platform.lower() == "reddit" and title:
                optimized = self.content_optimizer.optimize_for_reddit(
                    title, content, subreddit or ""
                )
                title = optimized["title"]
                optimized_content = optimized["body"]

        # 验证Reddit社区规则
        if platform.lower() == "reddit" and subreddit:
            if subreddit in self.community_rules:
                rule = self.community_rules[subreddit]
                validation = rule.validate_post(
                    title or "", optimized_content, "text"
                )
                if not validation["valid"]:
                    return {
                        "success": False,
                        "error": f"Post violates {subreddit} rules",
                        "violations": validation["violations"]
                    }

        post_data = {
            "post_id": post_id,
            "plan_id": plan_id,
            "platform": platform,
            "content": optimized_content,
            "original_content": content,
            "title": title,
            "subreddit": subreddit,
            "media_urls": media_urls or [],
            "scheduled_time": scheduled_time or datetime.now(timezone.utc).isoformat(),
            "status": PostStatus.SCHEDULED.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "published_at": None,
            "metrics": {
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "views": 0
            }
        }

        self.posts[post_id] = post_data
        self.plans[plan_id].posts.append(post_data)

        logger.info(f"✅ Scheduled post: {post_id} for {platform}")

        return {
            "success": True,
            "post_id": post_id,
            "post": post_data,
            "message": "Post scheduled successfully"
        }

    def publish_post(self, post_id: str) -> Dict[str, Any]:
        """
        发布帖子（模拟，实际需要API集成）

        Args:
            post_id: 帖子ID

        Returns:
            发布结果
        """
        if post_id not in self.posts:
            return {
                "success": False,
                "error": f"Post {post_id} not found"
            }

        post = self.posts[post_id]
        platform = post["platform"]

        try:
            if platform.lower() in ["x", "twitter"]:
                result = self._publish_to_x(post)
            elif platform.lower() == "reddit":
                result = self._publish_to_reddit(post)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported platform: {platform}"
                }

            if result["success"]:
                post["status"] = PostStatus.PUBLISHED.value
                post["published_at"] = datetime.now(timezone.utc).isoformat()
                post["platform_post_id"] = result.get("platform_post_id")
                post["platform_url"] = result.get("platform_url")

                logger.info(f"✅ Published post {post_id} to {platform}")
            else:
                post["status"] = PostStatus.FAILED.value
                post["error"] = result.get("error")

                logger.error(f"❌ Failed to publish post {post_id}: {result.get('error')}")

            return result

        except Exception as e:
            post["status"] = PostStatus.FAILED.value
            post["error"] = str(e)

            return {
                "success": False,
                "error": str(e)
            }

    def _publish_to_x(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """
        发布到X平台

        NOTE: 这是模拟实现，实际需要集成Twitter API v2
        需要安装: pip install tweepy
        """
        # TODO: 实现真实的Twitter API集成
        # 示例代码结构:
        # import tweepy
        # client = tweepy.Client(
        #     bearer_token=self.config["x_api"]["bearer_token"],
        #     consumer_key=self.config["x_api"]["api_key"],
        #     consumer_secret=self.config["x_api"]["api_secret"],
        #     access_token=self.config["x_api"]["access_token"],
        #     access_token_secret=self.config["x_api"]["access_token_secret"]
        # )
        # response = client.create_tweet(text=post["content"])

        logger.warning("⚠️ X publishing is in simulation mode")

        return {
            "success": True,
            "platform_post_id": f"x_sim_{post['post_id']}",
            "platform_url": f"https://twitter.com/simulated/{post['post_id']}",
            "message": "Post published to X (simulation)"
        }

    def _publish_to_reddit(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """
        发布到Reddit

        NOTE: 这是模拟实现，实际需要集成Reddit API
        需要安装: pip install praw
        """
        # TODO: 实现真实的Reddit API集成
        # 示例代码结构:
        # import praw
        # reddit = praw.Reddit(
        #     client_id=self.config["reddit_api"]["client_id"],
        #     client_secret=self.config["reddit_api"]["client_secret"],
        #     user_agent=self.config["reddit_api"]["user_agent"],
        #     username=self.config["reddit_api"]["username"],
        #     password=self.config["reddit_api"]["password"]
        # )
        # subreddit = reddit.subreddit(post["subreddit"])
        # submission = subreddit.submit(
        #     title=post["title"],
        #     selftext=post["content"]
        # )

        logger.warning("⚠️ Reddit publishing is in simulation mode")

        return {
            "success": True,
            "platform_post_id": f"reddit_sim_{post['post_id']}",
            "platform_url": f"https://reddit.com/r/{post['subreddit']}/comments/simulated",
            "message": f"Post published to r/{post['subreddit']} (simulation)"
        }

    def execute_daily_plan(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        执行每日宣传计划

        Args:
            date: 执行日期 (ISO format)，默认为今天

        Returns:
            执行结果摘要
        """
        if date:
            target_date = datetime.fromisoformat(date.replace('Z', '+00:00')).date()
        else:
            target_date = datetime.now(timezone.utc).date()

        results = {
            "date": target_date.isoformat(),
            "total_posts": 0,
            "successful": 0,
            "failed": 0,
            "posts": []
        }

        # 查找今天应该发布的帖子
        for post_id, post in self.posts.items():
            if post["status"] == PostStatus.SCHEDULED.value:
                scheduled_time = datetime.fromisoformat(
                    post["scheduled_time"].replace('Z', '+00:00')
                )

                if scheduled_time.date() == target_date:
                    results["total_posts"] += 1
                    publish_result = self.publish_post(post_id)
                    results["posts"].append({
                        "post_id": post_id,
                        "result": publish_result
                    })

                    if publish_result["success"]:
                        results["successful"] += 1
                    else:
                        results["failed"] += 1

        logger.info(
            f"✅ Daily plan executed: {results['successful']}/{results['total_posts']} successful"
        )

        return results

    def get_promotion_results(self, plan_id: Optional[str] = None,
                               platform: Optional[str] = None,
                               start_date: Optional[str] = None,
                               end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取宣传结果

        Args:
            plan_id: 过滤特定计划
            platform: 过滤特定平台
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            宣传结果统计
        """
        filtered_posts = []

        for post_id, post in self.posts.items():
            # 应用过滤器
            if plan_id and post["plan_id"] != plan_id:
                continue
            if platform and post["platform"] != platform:
                continue

            filtered_posts.append(post)

        # 计算统计数据
        total_posts = len(filtered_posts)
        published = sum(1 for p in filtered_posts
                       if p["status"] == PostStatus.PUBLISHED.value)
        failed = sum(1 for p in filtered_posts
                    if p["status"] == PostStatus.FAILED.value)
        scheduled = sum(1 for p in filtered_posts
                       if p["status"] == PostStatus.SCHEDULED.value)

        total_metrics = {
            "likes": sum(p["metrics"]["likes"] for p in filtered_posts),
            "comments": sum(p["metrics"]["comments"] for p in filtered_posts),
            "shares": sum(p["metrics"]["shares"] for p in filtered_posts),
            "views": sum(p["metrics"]["views"] for p in filtered_posts)
        }

        # 按平台分组统计
        platform_stats = {}
        for post in filtered_posts:
            plat = post["platform"]
            if plat not in platform_stats:
                platform_stats[plat] = {
                    "total": 0,
                    "published": 0,
                    "failed": 0,
                    "metrics": {"likes": 0, "comments": 0, "shares": 0, "views": 0}
                }
            platform_stats[plat]["total"] += 1
            if post["status"] == PostStatus.PUBLISHED.value:
                platform_stats[plat]["published"] += 1
            elif post["status"] == PostStatus.FAILED.value:
                platform_stats[plat]["failed"] += 1

            for key in platform_stats[plat]["metrics"]:
                platform_stats[plat]["metrics"][key] += post["metrics"][key]

        return {
            "success": True,
            "summary": {
                "total_posts": total_posts,
                "published": published,
                "failed": failed,
                "scheduled": scheduled,
                "total_metrics": total_metrics
            },
            "platform_stats": platform_stats,
            "posts": filtered_posts
        }

    def update_post_metrics(self, post_id: str, metrics: Dict[str, int]) -> Dict[str, Any]:
        """
        更新帖子指标（通常由定时任务调用以获取最新数据）

        Args:
            post_id: 帖子ID
            metrics: 指标数据 {"likes": 10, "comments": 5, ...}

        Returns:
            更新结果
        """
        if post_id not in self.posts:
            return {
                "success": False,
                "error": f"Post {post_id} not found"
            }

        self.posts[post_id]["metrics"].update(metrics)
        self.posts[post_id]["last_metrics_update"] = datetime.now(timezone.utc).isoformat()

        return {
            "success": True,
            "post_id": post_id,
            "metrics": self.posts[post_id]["metrics"]
        }

    def add_community_rule(self, subreddit: str, rules: Dict[str, Any]) -> Dict[str, Any]:
        """
        添加或更新Reddit社区规则

        Args:
            subreddit: 子版块名称
            rules: 规则配置

        Returns:
            操作结果
        """
        community_rule = RedditCommunityRule(
            subreddit=subreddit,
            rules=rules.get("rules", []),
            post_types=rules.get("post_types", ["text", "link"]),
            max_title_length=rules.get("max_title_length", 300),
            max_body_length=rules.get("max_body_length", 40000),
            requires_flair=rules.get("requires_flair", False),
            allowed_flairs=rules.get("allowed_flairs", []),
            min_karma=rules.get("min_karma", 0),
            min_account_age_days=rules.get("min_account_age_days", 0)
        )

        self.community_rules[subreddit] = community_rule

        return {
            "success": True,
            "subreddit": subreddit,
            "message": f"Community rules for r/{subreddit} updated"
        }

    def generate_content_variations(self, content: str, count: int = 3) -> Dict[str, Any]:
        """
        生成内容变体用于A/B测试

        Args:
            content: 基础内容
            count: 变体数量

        Returns:
            内容变体列表
        """
        variations = self.content_optimizer.generate_variations(content, count)

        return {
            "success": True,
            "variations": variations,
            "count": len(variations)
        }

    def get_plan_status(self, plan_id: str) -> Dict[str, Any]:
        """
        获取宣传计划状态

        Args:
            plan_id: 计划ID

        Returns:
            计划详细信息
        """
        if plan_id not in self.plans:
            return {
                "success": False,
                "error": f"Plan {plan_id} not found"
            }

        plan = self.plans[plan_id]

        # 计算计划级别的统计
        plan_posts = [p for p in self.posts.values() if p["plan_id"] == plan_id]
        published = sum(1 for p in plan_posts if p["status"] == PostStatus.PUBLISHED.value)
        failed = sum(1 for p in plan_posts if p["status"] == PostStatus.FAILED.value)
        scheduled = sum(1 for p in plan_posts if p["status"] == PostStatus.SCHEDULED.value)

        return {
            "success": True,
            "plan": plan.to_dict(),
            "statistics": {
                "total_posts": len(plan_posts),
                "published": published,
                "failed": failed,
                "scheduled": scheduled
            }
        }

    def _add_audit_log(self, action: str, post_id: str, user_id: str,
                       details: Dict[str, Any], trace_id: Optional[str] = None):
        """
        添加审计日志（带trace_id和原因字段）

        Args:
            action: 操作类型 (review, approve, reject, modify, etc.)
            post_id: 帖子ID
            user_id: 操作用户ID
            details: 详细信息
            trace_id: 追踪ID
        """
        import uuid
        audit_entry = {
            "audit_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "post_id": post_id,
            "user_id": user_id,
            "trace_id": trace_id or str(uuid.uuid4()),
            "details": details,
            "reason": details.get("reason", "")
        }
        self.audit_log.append(audit_entry)

        # 同时记录到帖子的干预历史
        if post_id not in self.intervention_history:
            self.intervention_history[post_id] = []
        self.intervention_history[post_id].append(audit_entry)

        logger.info(f"📋 Audit log added: {action} by {user_id} for post {post_id}")

    def submit_for_review(self, post_id: str, reviewer_id: Optional[str] = None,
                          auto_review: bool = False) -> Dict[str, Any]:
        """
        提交帖子进行审核

        Args:
            post_id: 帖子ID
            reviewer_id: 审核人ID（可选）
            auto_review: 是否自动审核（低风险内容）

        Returns:
            审核提交结果
        """
        if post_id not in self.posts:
            return {
                "success": False,
                "error": f"Post {post_id} not found"
            }

        post = self.posts[post_id]

        # 确定审核状态
        if auto_review:
            review_status = ReviewStatus.AUTO_APPROVED.value
            decision = "Auto-approved (low risk)"
        else:
            review_status = ReviewStatus.PENDING_REVIEW.value
            decision = "Pending manual review"

        # 创建审核队列条目
        review_entry = {
            "post_id": post_id,
            "plan_id": post["plan_id"],
            "platform": post["platform"],
            "content": post["content"],
            "title": post.get("title"),
            "subreddit": post.get("subreddit"),
            "review_status": review_status,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "reviewer_id": reviewer_id,
            "decision": decision,
            "reviewed_at": None,
            "review_notes": ""
        }

        self.review_queue[post_id] = review_entry

        # 更新帖子状态
        post["review_status"] = review_status

        # 记录审计日志
        self._add_audit_log(
            action="submit_for_review",
            post_id=post_id,
            user_id=reviewer_id or "system",
            details={
                "auto_review": auto_review,
                "reason": "Submitted for human review" if not auto_review else "Auto-review passed"
            }
        )

        logger.info(f"✅ Post {post_id} submitted for review: {review_status}")

        return {
            "success": True,
            "post_id": post_id,
            "review_status": review_status,
            "review_entry": review_entry,
            "message": f"Post submitted for review: {decision}"
        }

    def review_post(self, post_id: str, reviewer_id: str,
                    decision: str, notes: str = "",
                    modified_content: Optional[str] = None,
                    modified_title: Optional[str] = None) -> Dict[str, Any]:
        """
        人工审核帖子

        Args:
            post_id: 帖子ID
            reviewer_id: 审核人ID
            decision: 审核决定 ("approved", "rejected", "needs_revision")
            notes: 审核备注
            modified_content: 修改后的内容（可选）
            modified_title: 修改后的标题（可选）

        Returns:
            审核结果
        """
        if post_id not in self.review_queue:
            return {
                "success": False,
                "error": f"No review entry found for post {post_id}"
            }

        review_entry = self.review_queue[post_id]

        # 验证决定
        valid_decisions = ["approved", "rejected", "needs_revision"]
        if decision not in valid_decisions:
            return {
                "success": False,
                "error": f"Invalid decision. Must be one of: {valid_decisions}"
            }

        # 更新审核状态
        review_status_map = {
            "approved": ReviewStatus.APPROVED.value,
            "rejected": ReviewStatus.REJECTED.value,
            "needs_revision": ReviewStatus.NEEDS_REVISION.value
        }

        review_entry["review_status"] = review_status_map[decision]
        review_entry["reviewer_id"] = reviewer_id
        review_entry["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        review_entry["review_notes"] = notes
        review_entry["decision"] = decision

        # 如果有修改，应用修改
        modifications = {}
        if modified_content is not None:
            self.posts[post_id]["content"] = modified_content
            self.posts[post_id]["original_content"] = self.posts[post_id].get(
                "original_content", self.posts[post_id]["content"]
            )
            modifications["content_modified"] = True

        if modified_title is not None and "title" in self.posts[post_id]:
            self.posts[post_id]["title"] = modified_title
            modifications["title_modified"] = True

        # 根据决定更新帖子状态
        if decision == "approved":
            self.posts[post_id]["status"] = PostStatus.SCHEDULED.value
            self.posts[post_id]["approved_by"] = reviewer_id
            self.posts[post_id]["approved_at"] = datetime.now(timezone.utc).isoformat()
        elif decision == "rejected":
            self.posts[post_id]["status"] = PostStatus.FAILED.value
            self.posts[post_id]["rejection_reason"] = notes
        elif decision == "needs_revision":
            self.posts[post_id]["status"] = PostStatus.PENDING.value
            self.posts[post_id]["revision_needed"] = True

        # 记录审计日志
        self._add_audit_log(
            action=f"review_{decision}",
            post_id=post_id,
            user_id=reviewer_id,
            details={
                "decision": decision,
                "notes": notes,
                "modifications": modifications,
                "reason": f"Manual review by {reviewer_id}: {notes}"
            }
        )

        logger.info(f"✅ Post {post_id} reviewed by {reviewer_id}: {decision}")

        return {
            "success": True,
            "post_id": post_id,
            "review_status": review_entry["review_status"],
            "decision": decision,
            "modifications": modifications,
            "message": f"Post {decision} by {reviewer_id}"
        }

    def modify_post_content(self, post_id: str, user_id: str,
                             new_content: str, new_title: Optional[str] = None,
                             reason: str = "") -> Dict[str, Any]:
        """
        人工修改帖子内容

        Args:
            post_id: 帖子ID
            user_id: 修改人ID
            new_content: 新内容
            new_title: 新标题（可选，仅Reddit）
            reason: 修改原因

        Returns:
            修改结果
        """
        if post_id not in self.posts:
            return {
                "success": False,
                "error": f"Post {post_id} not found"
            }

        post = self.posts[post_id]

        # 保存原始内容
        if "original_content" not in post:
            post["original_content"] = post["content"]
        if "original_title" not in post and post.get("title"):
            post["original_title"] = post["title"]

        # 应用修改
        old_content = post["content"]
        post["content"] = new_content

        title_changed = False
        if new_title is not None and "title" in post:
            old_title = post["title"]
            post["title"] = new_title
            title_changed = True

        # 记录修改历史
        modification_record = {
            "modified_at": datetime.now(timezone.utc).isoformat(),
            "modified_by": user_id,
            "old_content": old_content,
            "new_content": new_content,
            "old_title": post.get("original_title"),
            "new_title": new_title if title_changed else None,
            "reason": reason
        }

        if "modification_history" not in post:
            post["modification_history"] = []
        post["modification_history"].append(modification_record)

        # 标记需要重新审核
        post["status"] = PostStatus.PENDING.value
        post["requires_re_review"] = True

        # 记录审计日志
        self._add_audit_log(
            action="manual_modification",
            post_id=post_id,
            user_id=user_id,
            details={
                "content_changed": old_content != new_content,
                "title_changed": title_changed,
                "reason": reason or f"Manual intervention by {user_id}"
            }
        )

        logger.info(f"✏️ Post {post_id} modified by {user_id}")

        return {
            "success": True,
            "post_id": post_id,
            "modifications": {
                "content_changed": old_content != new_content,
                "title_changed": title_changed
            },
            "requires_re_review": True,
            "message": f"Post modified by {user_id}, requires re-review"
        }

    def get_review_queue(self, status_filter: Optional[str] = None,
                         platform_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        获取审核队列

        Args:
            status_filter: 状态过滤 ("pending_review", "approved", "rejected", etc.)
            platform_filter: 平台过滤 ("x", "reddit")

        Returns:
            审核队列列表
        """
        filtered_queue = []

        for post_id, entry in self.review_queue.items():
            # 应用过滤器
            if status_filter and entry["review_status"] != status_filter:
                continue
            if platform_filter and entry["platform"] != platform_filter:
                continue

            filtered_queue.append(entry)

        # 统计
        stats = {
            "total": len(filtered_queue),
            "pending": sum(1 for e in filtered_queue
                          if e["review_status"] == ReviewStatus.PENDING_REVIEW.value),
            "approved": sum(1 for e in filtered_queue
                           if e["review_status"] == ReviewStatus.APPROVED.value),
            "rejected": sum(1 for e in filtered_queue
                           if e["review_status"] == ReviewStatus.REJECTED.value),
            "needs_revision": sum(1 for e in filtered_queue
                                  if e["review_status"] == ReviewStatus.NEEDS_REVISION.value)
        }

        return {
            "success": True,
            "queue": filtered_queue,
            "statistics": stats
        }

    def get_audit_log(self, post_id: Optional[str] = None,
                      user_id: Optional[str] = None,
                      action_filter: Optional[str] = None,
                      limit: int = 100) -> Dict[str, Any]:
        """
        获取审计日志

        Args:
            post_id: 过滤特定帖子
            user_id: 过滤特定用户
            action_filter: 过滤操作类型
            limit: 返回数量限制

        Returns:
            审计日志列表
        """
        filtered_logs = self.audit_log.copy()

        # 应用过滤器
        if post_id:
            filtered_logs = [log for log in filtered_logs
                            if log["post_id"] == post_id]
        if user_id:
            filtered_logs = [log for log in filtered_logs
                            if log["user_id"] == user_id]
        if action_filter:
            filtered_logs = [log for log in filtered_logs
                            if log["action"] == action_filter]

        # 按时间倒序排列
        filtered_logs.sort(key=lambda x: x["timestamp"], reverse=True)

        # 限制数量
        filtered_logs = filtered_logs[:limit]

        return {
            "success": True,
            "audit_log": filtered_logs,
            "total_entries": len(filtered_logs)
        }

    def bulk_approve_posts(self, post_ids: List[str], reviewer_id: str,
                           notes: str = "") -> Dict[str, Any]:
        """
        批量批准帖子

        Args:
            post_ids: 帖子ID列表
            reviewer_id: 审核人ID
            notes: 审核备注

        Returns:
            批量审核结果
        """
        results = {
            "success": True,
            "total": len(post_ids),
            "approved": 0,
            "failed": 0,
            "details": []
        }

        for post_id in post_ids:
            result = self.review_post(
                post_id=post_id,
                reviewer_id=reviewer_id,
                decision="approved",
                notes=notes
            )

            if result["success"]:
                results["approved"] += 1
            else:
                results["failed"] += 1

            results["details"].append({
                "post_id": post_id,
                "result": result
            })

        # 记录批量操作审计日志
        self._add_audit_log(
            action="bulk_approve",
            post_id=",".join(post_ids),
            user_id=reviewer_id,
            details={
                "total": len(post_ids),
                "approved": results["approved"],
                "failed": results["failed"],
                "reason": f"Bulk approval by {reviewer_id}: {notes}"
            }
        )

        logger.info(f"✅ Bulk approved: {results['approved']}/{results['total']} posts")

        return results

    def get_intervention_summary(self, post_id: str) -> Dict[str, Any]:
        """
        获取帖子的人工干预摘要

        Args:
            post_id: 帖子ID

        Returns:
            干预摘要
        """
        if post_id not in self.posts:
            return {
                "success": False,
                "error": f"Post {post_id} not found"
            }

        post = self.posts[post_id]
        interventions = self.intervention_history.get(post_id, [])

        summary = {
            "post_id": post_id,
            "current_status": post["status"],
            "review_status": post.get("review_status", "not_reviewed"),
            "total_interventions": len(interventions),
            "interventions": interventions,
            "modification_count": len(post.get("modification_history", [])),
            "approved_by": post.get("approved_by"),
            "approved_at": post.get("approved_at"),
            "rejection_reason": post.get("rejection_reason")
        }

        return {
            "success": True,
            "summary": summary
        }

    def get_info(self) -> Dict[str, Any]:
        """获取Agent信息"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "capabilities": [
                "create_promotion_plan",
                "schedule_post",
                "publish_post",
                "execute_daily_plan",
                "get_promotion_results",
                "optimize_content",
                "manage_community_rules",
                "generate_content_variations",
                "submit_for_review",
                "review_post",
                "modify_post_content",
                "get_review_queue",
                "get_audit_log",
                "bulk_approve_posts",
                "get_intervention_summary"
            ],
            "supported_platforms": ["x", "reddit"],
            "total_plans": len(self.plans),
            "total_posts": len(self.posts),
            "pending_reviews": sum(1 for r in self.review_queue.values()
                                   if r["review_status"] == ReviewStatus.PENDING_REVIEW.value),
            "total_audit_entries": len(self.audit_log),
            "created_at": self.created_at.isoformat()
        }

    def enable_browser_automation(self, headless: bool = False,
                                   slow_mo: int = 500) -> Dict[str, Any]:
        """
        启用浏览器自动化（基于Playwright）

        Args:
            headless: 是否无头模式（False显示浏览器窗口，便于人工协助）
            slow_mo: 操作延迟毫秒数

        Returns:
            启用结果
        """
        try:
            from Agent.browser_automation import BrowserAutomationManager

            self.browser_manager = BrowserAutomationManager(
                headless=headless,
                slow_mo=slow_mo
            )
            self.browser_manager.start_browser()
            self.use_browser_automation = True

            logger.info("✅ Browser automation enabled")

            return {
                "success": True,
                "message": "Browser automation enabled",
                "headless": headless
            }

        except ImportError as e:
            logger.error(f"❌ Playwright not available: {e}")
            return {
                "success": False,
                "error": "Playwright not installed. Install with: pip install playwright && playwright install"
            }
        except Exception as e:
            logger.error(f"❌ Failed to enable browser automation: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def disable_browser_automation(self) -> Dict[str, Any]:
        """禁用浏览器自动化"""
        if self.browser_manager:
            try:
                self.browser_manager.stop_browser()
                self.browser_manager = None
                self.use_browser_automation = False

                logger.info("✅ Browser automation disabled")

                return {
                    "success": True,
                    "message": "Browser automation disabled"
                }
            except Exception as e:
                logger.error(f"Error disabling browser automation: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }
        else:
            return {
                "success": True,
                "message": "Browser automation was not enabled"
            }

    def login_to_platform(self, platform: str, username: str,
                          password: str) -> Dict[str, Any]:
        """
        登录到指定平台

        Args:
            platform: 平台名称 ("x" 或 "reddit")
            username: 用户名
            password: 密码

        Returns:
            登录结果
        """
        if not self.use_browser_automation or not self.browser_manager:
            return {
                "success": False,
                "error": "Browser automation not enabled. Call enable_browser_automation() first."
            }

        try:
            if platform.lower() == "x":
                result = self.browser_manager.login_to_x(username, password)
            elif platform.lower() == "reddit":
                result = self.browser_manager.login_to_reddit(username, password)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported platform: {platform}"
                }

            # 记录审计日志
            self._add_audit_log(
                action="login",
                post_id="",
                user_id=username,
                details={
                    "platform": platform,
                    "success": result.get("success", False),
                    "reason": f"Login to {platform}"
                }
            )

            return result

        except Exception as e:
            logger.error(f"Login error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def publish_post_with_browser(self, post_id: str) -> Dict[str, Any]:
        """
        使用浏览器发布帖子（支持人工协助处理机器人验证）

        Args:
            post_id: 帖子ID

        Returns:
            发布结果
        """
        if not self.use_browser_automation or not self.browser_manager:
            return {
                "success": False,
                "error": "Browser automation not enabled"
            }

        if post_id not in self.posts:
            return {
                "success": False,
                "error": f"Post {post_id} not found"
            }

        post = self.posts[post_id]
        platform = post["platform"]

        try:
            logger.info(f"🚀 Publishing post {post_id} via browser to {platform}")

            if platform.lower() == "x":
                result = self.browser_manager.post_to_x(
                    content=post["content"],
                    media_files=post.get("media_urls", [])
                )

            elif platform.lower() == "reddit":
                result = self.browser_manager.post_to_reddit(
                    subreddit=post.get("subreddit", ""),
                    title=post.get("title", ""),
                    content=post["content"],
                    post_type="text"
                )
            else:
                return {
                    "success": False,
                    "error": f"Unsupported platform: {platform}"
                }

            if result["success"]:
                post["status"] = PostStatus.PUBLISHED.value
                post["published_at"] = datetime.now(timezone.utc).isoformat()
                post["platform_post_id"] = result.get("url", "")
                post["platform_url"] = result.get("url", "")
                post["publish_method"] = "browser_automation"

                logger.info(f"✅ Post {post_id} published successfully via browser")
            else:
                post["status"] = PostStatus.FAILED.value
                post["error"] = result.get("error")

                logger.error(f"❌ Failed to publish post {post_id}: {result.get('error')}")

            # 记录审计日志
            self._add_audit_log(
                action="publish_via_browser",
                post_id=post_id,
                user_id="system",
                details={
                    "platform": platform,
                    "success": result.get("success", False),
                    "url": result.get("url"),
                    "error": result.get("error"),
                    "reason": f"Browser automation publishing to {platform}"
                }
            )

            return result

        except Exception as e:
            post["status"] = PostStatus.FAILED.value
            post["error"] = str(e)

            logger.error(f"Browser publishing error: {e}")

            return {
                "success": False,
                "error": str(e)
            }

    def save_browser_session(self, session_name: str) -> Dict[str, Any]:
        """
        保存浏览器会话

        Args:
            session_name: 会话名称

        Returns:
            保存结果
        """
        if not self.use_browser_automation or not self.browser_manager:
            return {
                "success": False,
                "error": "Browser automation not enabled"
            }

        try:
            session_file = self.browser_manager.save_session(session_name)

            return {
                "success": True,
                "session_file": session_file,
                "message": f"Session saved to {session_file}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def load_browser_session(self, session_name: str) -> Dict[str, Any]:
        """
        加载浏览器会话

        Args:
            session_name: 会话名称

        Returns:
            加载结果
        """
        if not self.use_browser_automation or not self.browser_manager:
            return {
                "success": False,
                "error": "Browser automation not enabled"
            }

        try:
            success = self.browser_manager.load_session(session_name)

            return {
                "success": success,
                "message": f"Session '{session_name}' loaded" if success
                           else f"Session '{session_name}' not found"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def take_browser_screenshot(self, filename: str = None) -> Dict[str, Any]:
        """
        截取浏览器屏幕截图

        Args:
            filename: 文件名（可选）

        Returns:
            截图结果
        """
        if not self.use_browser_automation or not self.browser_manager:
            return {
                "success": False,
                "error": "Browser automation not enabled"
            }

        try:
            screenshot_path = self.browser_manager.take_screenshot(filename)

            return {
                "success": True,
                "screenshot_path": screenshot_path,
                "message": f"Screenshot saved to {screenshot_path}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# 全局实例
promotion_agent = PromotionAgent()

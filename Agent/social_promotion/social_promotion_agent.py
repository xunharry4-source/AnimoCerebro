"""
社交媒体宣传 Agent
通过浏览器自动化在 X (Twitter) 和 Reddit 上自动发帖宣传
能够制定宣传计划、查看宣传结果，并根据不同社区要求发布不同内容
使用 Playwright 进行浏览器自动化操作
"""
import json
import random
import time
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path
import logging
from dataclasses import dataclass, asdict

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PostContent:
    """帖子内容"""
    title: str = ""
    content: str = ""
    media_files: List[str] = None
    tags: List[str] = None
    link: str = ""
    
    def __post_init__(self):
        if self.media_files is None:
            self.media_files = []
        if self.tags is None:
            self.tags = []


@dataclass
class CommunityRequirement:
    """社区要求"""
    name: str
    max_title_length: int = 300
    max_content_length: int = 10000
    required_tags: List[str] = None
    forbidden_words: List[str] = None
    posting_frequency_limit: str = "once per day"
    content_type: str = "any"
    special_rules: str = ""
    
    def __post_init__(self):
        if self.required_tags is None:
            self.required_tags = []
        if self.forbidden_words is None:
            self.forbidden_words = []


class BrowserAutomationManager:
    """浏览器自动化管理器"""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.is_initialized = False
        
    async def initialize(self, headless: bool = True):
        """初始化浏览器"""
        try:
            from playwright.async_api import async_playwright
            
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            self.page = await self.context.new_page()
            self.is_initialized = True
            logger.info("Browser automation initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            return False
    
    async def close(self):
        """关闭浏览器"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.is_initialized = False
            logger.info("Browser automation closed")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")
    
    async def take_screenshot(self, filepath: str):
        """截图"""
        if self.page and self.is_initialized:
            await self.page.screenshot(path=filepath)
            logger.info(f"Screenshot saved to {filepath}")


class SocialMediaPromotionAgent:
    """社交媒体宣传 Agent，通过浏览器自动化在 X 和 Reddit 发帖"""
    
    def __init__(self):
        self.agent_id = "agent-social-promotion"
        self.name = "Social Media Promotion Agent"
        self.status = "active"
        self.capabilities = [
            "create_promotion_plan",
            "post_to_x",
            "post_to_reddit",
            "get_promotion_results",
            "analyze_community_requirements",
            "schedule_posts",
            "login_to_platforms",
            "validate_content"
        ]
        self.created_at = datetime.now(timezone.utc)
        
        # 浏览器自动化管理器
        self.browser_manager = BrowserAutomationManager()
        
        # 用户账户信息
        self.x_credentials = {"username": "", "password": ""}
        self.reddit_credentials = {"username": "", "password": ""}
        
        # 存储宣传计划和结果
        self.promotion_plans = {}
        self.post_results = []
        
        # 社区要求数据库
        self.community_requirements = self._load_community_requirements()
        
        # 数据存储路径
        self.data_dir = Path(__file__).parent.parent / "testdata" / "promotion_data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
    def _load_community_requirements(self) -> Dict[str, CommunityRequirement]:
        """加载社区要求"""
        requirements = {
            "technology": CommunityRequirement(
                name="technology",
                max_title_length=300,
                max_content_length=10000,
                required_tags=["tech", "innovation"],
                forbidden_words=["spam", "scam"],
                posting_frequency_limit="3 posts per day",
                content_type="informative",
                special_rules="Must provide value, no self-promotion without context"
            ),
            "science": CommunityRequirement(
                name="science",
                max_title_length=300,
                max_content_length=15000,
                required_tags=["science", "research"],
                forbidden_words=["fake", "pseudoscience"],
                posting_frequency_limit="2 posts per day",
                content_type="educational",
                special_rules="Must cite sources, be scientifically accurate"
            ),
            "programming": CommunityRequirement(
                name="programming",
                max_title_length=300,
                max_content_length=10000,
                required_tags=["code", "programming"],
                forbidden_words=["hire", "job"],
                posting_frequency_limit="5 posts per day",
                content_type="technical",
                special_rules="Share code snippets, ask specific questions"
            ),
            "general": CommunityRequirement(
                name="general",
                max_title_length=300,
                max_content_length=10000,
                required_tags=[],
                forbidden_words=["hate", "harassment"],
                posting_frequency_limit="10 posts per day",
                content_type="any",
                special_rules="Be respectful, follow Reddit rules"
            )
        }
        return requirements
    
    def save_data(self):
        """保存数据到文件"""
        try:
            # 保存宣传计划
            plans_file = self.data_dir / "promotion_plans.json"
            plans_data = {}
            for plan_id, plan in self.promotion_plans.items():
                plan_copy = plan.copy() if isinstance(plan, dict) else asdict(plan)
                if isinstance(plan_copy.get("created_at"), datetime):
                    plan_copy["created_at"] = plan_copy["created_at"].isoformat()
                if isinstance(plan_copy.get("start_date"), datetime):
                    plan_copy["start_date"] = plan_copy["start_date"].isoformat()
                if plan_copy.get("end_date") and isinstance(plan_copy["end_date"], datetime):
                    plan_copy["end_date"] = plan_copy["end_date"].isoformat()
                plans_data[plan_id] = plan_copy
            with open(plans_file, 'w', encoding='utf-8') as f:
                json.dump(plans_data, f, ensure_ascii=False, indent=2)
            
            # 保存发帖结果
            results_file = self.data_dir / "post_results.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(self.post_results, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"Data saved to {self.data_dir}")
        except Exception as e:
            logger.error(f"Failed to save data: {e}")
    
    def load_data(self):
        """从文件加载数据"""
        try:
            # 加载宣传计划
            plans_file = self.data_dir / "promotion_plans.json"
            if plans_file.exists():
                with open(plans_file, 'r', encoding='utf-8') as f:
                    plans_data = json.load(f)
                    self.promotion_plans = plans_data
            
            # 加载发帖结果
            results_file = self.data_dir / "post_results.json"
            if results_file.exists():
                with open(results_file, 'r', encoding='utf-8') as f:
                    self.post_results = json.load(f)
            
            logger.info(f"Data loaded from {self.data_dir}")
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
    
    async def initialize_browser(self, headless: bool = True):
        """初始化浏览器"""
        return await self.browser_manager.initialize(headless=headless)
    
    async def close_browser(self):
        """关闭浏览器"""
        await self.browser_manager.close()
    
    async def login_to_x(self, username: str, password: str) -> Dict[str, Any]:
        """登录 X (Twitter)"""
        try:
            if not self.browser_manager.is_initialized:
                await self.initialize_browser()
            
            page = self.browser_manager.page
            
            # 导航到登录页面
            await page.goto("https://twitter.com/i/flow/login", wait_until="networkidle")
            await asyncio.sleep(2)
            
            # 输入用户名
            username_input = await page.query_selector('input[autocomplete="username"]')
            if username_input:
                await username_input.fill(username)
                await asyncio.sleep(1)
                
                # 点击下一步
                next_button = await page.query_selector('div[role="button"]:has-text("Next")')
                if next_button:
                    await next_button.click()
                    await asyncio.sleep(2)
            
            # 输入密码
            password_input = await page.query_selector('input[type="password"]')
            if password_input:
                await password_input.fill(password)
                await asyncio.sleep(1)
                
                # 点击登录
                login_button = await page.query_selector('div[role="button"]:has-text("Log in")')
                if login_button:
                    await login_button.click()
                    await asyncio.sleep(3)
            
            # 检查是否登录成功
            current_url = page.url
            if "home" in current_url or "timeline" in current_url:
                self.x_credentials = {"username": username, "password": password}
                logger.info("Successfully logged in to X")
                return {"success": True, "message": "Logged in to X successfully"}
            else:
                logger.warning("Login to X may have failed")
                return {"success": False, "message": "Login to X failed"}
                
        except Exception as e:
            logger.error(f"Failed to login to X: {e}")
            return {"success": False, "error": str(e)}
    
    async def login_to_reddit(self, username: str, password: str) -> Dict[str, Any]:
        """登录 Reddit"""
        try:
            if not self.browser_manager.is_initialized:
                await self.initialize_browser()
            
            page = self.browser_manager.page
            
            # 导航到登录页面
            await page.goto("https://www.reddit.com/login", wait_until="networkidle")
            await asyncio.sleep(2)
            
            # 输入用户名
            username_input = await page.query_selector('input[name="username"]')
            if username_input:
                await username_input.fill(username)
                await asyncio.sleep(1)
            
            # 输入密码
            password_input = await page.query_selector('input[name="password"]')
            if password_input:
                await password_input.fill(password)
                await asyncio.sleep(1)
            
            # 点击登录按钮
            login_button = await page.query_selector('button[type="submit"]')
            if login_button:
                await login_button.click()
                await asyncio.sleep(3)
            
            # 检查是否登录成功
            current_url = page.url
            if "reddit.com" in current_url and "login" not in current_url:
                self.reddit_credentials = {"username": username, "password": password}
                logger.info("Successfully logged in to Reddit")
                return {"success": True, "message": "Logged in to Reddit successfully"}
            else:
                logger.warning("Login to Reddit may have failed")
                return {"success": False, "message": "Login to Reddit failed"}
                
        except Exception as e:
            logger.error(f"Failed to login to Reddit: {e}")
            return {"success": False, "error": str(e)}
    
    def create_promotion_plan(self, 
                             campaign_name: str,
                             platforms: List[str],
                             target_communities: List[str],
                             content_templates: List[Dict[str, str]],
                             start_date: Optional[datetime] = None,
                             end_date: Optional[datetime] = None,
                             frequency: str = "daily",
                             budget: Optional[float] = None) -> Dict[str, Any]:
        """创建宣传计划"""
        try:
            if not start_date:
                start_date = datetime.now(timezone.utc)
            
            plan_id = f"plan_{int(time.time())}"
            
            plan = {
                "plan_id": plan_id,
                "campaign_name": campaign_name,
                "platforms": platforms,
                "target_communities": target_communities,
                "content_templates": content_templates,
                "start_date": start_date,
                "end_date": end_date,
                "frequency": frequency,
                "budget": budget,
                "status": "created",
                "created_at": datetime.now(timezone.utc),
                "posts_scheduled": 0,
                "posts_published": 0,
                "posts_failed": 0,
                "engagement_metrics": {
                    "likes": 0,
                    "shares": 0,
                    "comments": 0,
                    "clicks": 0,
                    "upvotes": 0,
                    "downvotes": 0
                }
            }
            
            self.promotion_plans[plan_id] = plan
            self.save_data()
            
            return {
                "success": True,
                "plan_id": plan_id,
                "message": f"Promotion plan '{campaign_name}' created successfully",
                "plan": plan
            }
        except Exception as e:
            logger.error(f"Failed to create promotion plan: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def analyze_community_requirements(self, community: str) -> Dict[str, Any]:
        """分析特定社区的要求"""
        requirements = self.community_requirements.get(community, self.community_requirements["general"])
        
        return {
            "success": True,
            "community": community,
            "requirements": asdict(requirements),
            "recommendations": self._generate_content_recommendations(requirements)
        }
    
    def _generate_content_recommendations(self, requirements: CommunityRequirement) -> List[str]:
        """根据社区要求生成内容建议"""
        recommendations = []
        
        if requirements.content_type == "informative":
            recommendations.append("Focus on providing valuable information")
            recommendations.append("Include relevant statistics or data")
        elif requirements.content_type == "educational":
            recommendations.append("Explain concepts clearly")
            recommendations.append("Provide sources and references")
        elif requirements.content_type == "technical":
            recommendations.append("Include code examples or technical details")
            recommendations.append("Be specific about the problem or solution")
        else:
            recommendations.append("Create engaging and relevant content")
        
        if requirements.required_tags:
            recommendations.append(f"Include required tags: {', '.join(requirements.required_tags)}")
        
        if requirements.forbidden_words:
            recommendations.append(f"Avoid these words: {', '.join(requirements.forbidden_words)}")
        
        recommendations.append(f"Keep title under {requirements.max_title_length} characters")
        recommendations.append(f"Keep content under {requirements.max_content_length} characters")
        recommendations.append(f"Posting limit: {requirements.posting_frequency_limit}")
        recommendations.append(f"Special rules: {requirements.special_rules}")
        
        return recommendations
    
    def validate_content_for_community(self, content: PostContent, community: str) -> Dict[str, Any]:
        """验证内容是否符合社区要求"""
        requirements = self.community_requirements.get(community, self.community_requirements["general"])
        
        issues = []
        
        # 检查标题长度
        if content.title and len(content.title) > requirements.max_title_length:
            issues.append(f"Title exceeds {requirements.max_title_length} character limit")
        
        # 检查内容长度
        if len(content.content) > requirements.max_content_length:
            issues.append(f"Content exceeds {requirements.max_content_length} character limit")
        
        # 检查必需标签
        missing_tags = [tag for tag in requirements.required_tags if tag.lower() not in content.content.lower()]
        if missing_tags:
            issues.append(f"Missing required tags: {', '.join(missing_tags)}")
        
        # 检查禁用词
        found_forbidden = [word for word in requirements.forbidden_words if word.lower() in content.content.lower()]
        if found_forbidden:
            issues.append(f"Contains forbidden words: {', '.join(found_forbidden)}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "community": community,
            "requirements": asdict(requirements)
        }
    
    async def post_to_x(self, content: PostContent, plan_id: Optional[str] = None) -> Dict[str, Any]:
        """在 X (Twitter) 上发帖"""
        try:
            if not self.browser_manager.is_initialized:
                await self.initialize_browser()
            
            page = self.browser_manager.page
            
            # 验证内容
            validation = self.validate_content_for_community(content, "general")
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": f"Content validation failed: {'; '.join(validation['issues'])}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            # 导航到发推页面
            await page.goto("https://twitter.com/compose/tweet", wait_until="networkidle")
            await asyncio.sleep(2)
            
            # 输入推文内容
            textarea = await page.query_selector('div[role="textbox"]')
            if textarea:
                await textarea.fill(content.content)
                await asyncio.sleep(1)
            
            # 如果有媒体文件，上传
            if content.media_files:
                for media_file in content.media_files:
                    file_input = await page.query_selector('input[type="file"]')
                    if file_input:
                        await file_input.set_input_files(media_file)
                        await asyncio.sleep(2)
            
            # 点击发布按钮
            post_button = await page.query_selector('div[role="button"]:has-text("Post")')
            if post_button:
                await post_button.click()
                await asyncio.sleep(3)
            
            # 记录结果
            post_result = {
                "platform": "x",
                "content": content.content,
                "media_files": content.media_files,
                "posted_at": datetime.now(timezone.utc).isoformat(),
                "post_id": f"x_post_{int(time.time())}",
                "status": "published",
                "plan_id": plan_id,
                "engagement": {
                    "likes": 0,
                    "retweets": 0,
                    "replies": 0,
                    "impressions": 0
                }
            }
            
            self.post_results.append(post_result)
            
            # 更新计划统计
            if plan_id and plan_id in self.promotion_plans:
                self.promotion_plans[plan_id]["posts_published"] += 1
                self.promotion_plans[plan_id]["status"] = "active"
            
            self.save_data()
            
            return {
                "success": True,
                "post_result": post_result,
                "message": "Post published to X successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to post to X: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def post_to_reddit(self, title: str, content: str, subreddit: str, 
                           flair: Optional[str] = None, 
                           plan_id: Optional[str] = None) -> Dict[str, Any]:
        """在 Reddit 上发帖"""
        try:
            if not self.browser_manager.is_initialized:
                await self.initialize_browser()
            
            page = self.browser_manager.page
            
            # 创建 PostContent 对象用于验证
            post_content = PostContent(title=title, content=content)
            
            # 验证内容是否符合社区要求
            validation = self.validate_content_for_community(post_content, subreddit)
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": f"Content validation failed for r/{subreddit}: {'; '.join(validation['issues'])}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            # 导航到 subreddit 发帖页面
            await page.goto(f"https://www.reddit.com/r/{subreddit}/submit", wait_until="networkidle")
            await asyncio.sleep(2)
            
            # 选择帖子类型（文本帖子）
            text_post_button = await page.query_selector('button:has-text("Text")')
            if text_post_button:
                await text_post_button.click()
                await asyncio.sleep(1)
            
            # 输入标题
            title_input = await page.query_selector('input[name="title"]')
            if title_input:
                await title_input.fill(title)
                await asyncio.sleep(1)
            
            # 输入内容
            content_input = await page.query_selector('textarea[name="text"]')
            if content_input:
                await content_input.fill(content)
                await asyncio.sleep(1)
            
            # 选择 flair（如果提供）
            if flair:
                flair_button = await page.query_selector('button:has-text("Flair")')
                if flair_button:
                    await flair_button.click()
                    await asyncio.sleep(1)
                    
                    # 选择指定的 flair
                    flair_option = await page.query_selector(f'div:has-text("{flair}")')
                    if flair_option:
                        await flair_option.click()
                        await asyncio.sleep(1)
            
            # 点击发布按钮
            post_button = await page.query_selector('button[type="submit"]')
            if post_button:
                await post_button.click()
                await asyncio.sleep(3)
            
            # 记录结果
            post_result = {
                "platform": "reddit",
                "title": title,
                "content": content,
                "subreddit": subreddit,
                "flair": flair,
                "posted_at": datetime.now(timezone.utc).isoformat(),
                "post_id": f"reddit_post_{int(time.time())}",
                "status": "published",
                "plan_id": plan_id,
                "engagement": {
                    "upvotes": 0,
                    "downvotes": 0,
                    "comments": 0,
                    "awards": 0
                }
            }
            
            self.post_results.append(post_result)
            
            # 更新计划统计
            if plan_id and plan_id in self.promotion_plans:
                self.promotion_plans[plan_id]["posts_published"] += 1
                self.promotion_plans[plan_id]["status"] = "active"
            
            self.save_data()
            
            return {
                "success": True,
                "post_result": post_result,
                "message": f"Post published to r/{subreddit} successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to post to Reddit: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def schedule_posts(self, plan_id: str, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """安排帖子发布（立即执行或定时执行）"""
        try:
            if plan_id not in self.promotion_plans:
                return {
                    "success": False,
                    "error": f"Plan {plan_id} not found",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            scheduled_count = 0
            failed_count = 0
            
            for post in posts:
                platform = post.get("platform")
                schedule_time = post.get("schedule_time")
                
                # 如果指定了发布时间，检查是否到达
                if schedule_time:
                    if isinstance(schedule_time, str):
                        schedule_time = datetime.fromisoformat(schedule_time.replace('Z', '+00:00'))
                    
                    if schedule_time > datetime.now(timezone.utc):
                        # 还未到发布时间，跳过
                        continue
                
                try:
                    if platform == "x":
                        content = PostContent(
                            content=post.get("content", ""),
                            media_files=post.get("media_files", [])
                        )
                        result = await self.post_to_x(content, plan_id)
                    elif platform == "reddit":
                        result = await self.post_to_reddit(
                            post.get("title", ""),
                            post.get("content", ""),
                            post.get("subreddit", "general"),
                            post.get("flair"),
                            plan_id
                        )
                    else:
                        continue
                    
                    if result["success"]:
                        scheduled_count += 1
                    else:
                        failed_count += 1
                        
                except Exception as e:
                    logger.error(f"Failed to schedule post: {e}")
                    failed_count += 1
            
            # 更新计划状态
            self.promotion_plans[plan_id]["posts_scheduled"] += scheduled_count
            self.promotion_plans[plan_id]["posts_failed"] += failed_count
            
            if scheduled_count > 0:
                self.promotion_plans[plan_id]["status"] = "active"
            
            self.save_data()
            
            return {
                "success": True,
                "scheduled_count": scheduled_count,
                "failed_count": failed_count,
                "message": f"Scheduled {scheduled_count} posts for plan {plan_id} ({failed_count} failed)"
            }
            
        except Exception as e:
            logger.error(f"Failed to schedule posts: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def get_promotion_results(self, plan_id: Optional[str] = None, 
                             platform: Optional[str] = None,
                             date_range: Optional[tuple] = None) -> Dict[str, Any]:
        """获取宣传结果"""
        try:
            results = self.post_results.copy()
            
            # 按计划ID过滤
            if plan_id:
                results = [r for r in results if r.get("plan_id") == plan_id]
            
            # 按平台过滤
            if platform:
                results = [r for r in results if r.get("platform") == platform]
            
            # 按日期范围过滤
            if date_range:
                start_date, end_date = date_range
                filtered_results = []
                for result in results:
                    posted_at = result.get("posted_at")
                    if posted_at:
                        post_date = datetime.fromisoformat(posted_at.replace('Z', '+00:00'))
                        if start_date <= post_date <= end_date:
                            filtered_results.append(result)
                results = filtered_results
            
            # 计算统计数据
            total_posts = len(results)
            successful_posts = len([r for r in results if r.get("status") == "published"])
            failed_posts = len([r for r in results if r.get("status") == "failed"])
            
            # 计算参与度指标
            total_engagement = {
                "likes": sum(r.get("engagement", {}).get("likes", 0) for r in results),
                "shares": sum(r.get("engagement", {}).get("retweets", 0) + r.get("engagement", {}).get("shares", 0) for r in results),
                "comments": sum(r.get("engagement", {}).get("replies", 0) + r.get("engagement", {}).get("comments", 0) for r in results),
                "upvotes": sum(r.get("engagement", {}).get("upvotes", 0) for r in results),
            }
            
            return {
                "success": True,
                "total_posts": total_posts,
                "successful_posts": successful_posts,
                "failed_posts": failed_posts,
                "results": results,
                "engagement_metrics": total_engagement,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get promotion results: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def get_plan_details(self, plan_id: str) -> Dict[str, Any]:
        """获取计划详情"""
        try:
            if plan_id not in self.promotion_plans:
                return {
                    "success": False,
                    "error": f"Plan {plan_id} not found"
                }
            
            plan = self.promotion_plans[plan_id]
            
            # 获取该计划的所有帖子
            plan_posts = [r for r in self.post_results if r.get("plan_id") == plan_id]
            
            return {
                "success": True,
                "plan": plan,
                "posts": plan_posts,
                "total_posts": len(plan_posts),
                "published_posts": len([p for p in plan_posts if p.get("status") == "published"]),
                "failed_posts": len([p for p in plan_posts if p.get("status") == "failed"])
            }
            
        except Exception as e:
            logger.error(f"Failed to get plan details: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_info(self) -> Dict[str, Any]:
        """获取 Agent 信息"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "capabilities": self.capabilities,
            "total_plans": len(self.promotion_plans),
            "total_posts": len(self.post_results),
            "browser_initialized": self.browser_manager.is_initialized,
            "created_at": self.created_at.isoformat()
        }


# 全局实例
social_promotion_agent = SocialMediaPromotionAgent()

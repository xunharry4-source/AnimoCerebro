"""
Self-Promotion Agent - 基于 LLM 的智能社交媒体推广系统

文件用途:
    提供自动化的 AnimoCerebro 项目推广能力，通过 LLM 分析项目特点，
    生成针对 Reddit 和 X 平台的周度推广计划，并通过浏览器自动化执行发布。

主要职责:
    - 使用 LLM 分析 AnimoCerebro 项目特点和目标受众
    - 生成每周推广计划（7天详细内容安排）
    - 根据平台特性智能优化帖子内容
    - 通过浏览器自动化发布到 Reddit 和 X
    - 检测并请求人工协助处理 CAPTCHA
    - 识别 Reddit 发帖失败原因并自动修正内容
    - 支持人类中途指定推广内容
    - 记录完整的审计日志和追踪效果

不负责:
    - 不处理付费广告投放
    - 不管理用户账号安全
    - 不违反各平台的 API 使用条款和社区规范
    - 不替代人类的最终审核决策
"""

import logging
import json
import os
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum

# 导入社区规则管理器
try:
    from Agent.community_rules_manager import CommunityRulesManager
    RULES_MANAGER_AVAILABLE = True
except ImportError:
    logger.warning("CommunityRulesManager not available")
    RULES_MANAGER_AVAILABLE = False

logger = logging.getLogger(__name__)

# 导入 Zentex LLM 服务
try:
    from zentex.llm import get_llm_service
    from zentex.foundation.specs.model_provider import ModelProviderCallerContext
    LLM_AVAILABLE = True
except ImportError:
    logger.warning("Zentex LLM service not available, using mock mode")
    LLM_AVAILABLE = False

# 导入浏览器自动化模块
try:
    from Agent.browser_automation import BrowserAutomationManager
    BROWSER_AVAILABLE = True
except ImportError:
    logger.warning("Browser automation not available")
    BROWSER_AVAILABLE = False


class Platform(Enum):
    """支持的社交平台"""
    X = "x"
    REDDIT = "reddit"


class PostStatus(Enum):
    """帖子状态"""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"
    REVOKED = "revoked"


@dataclass
class DailySchedule:
    """每日推广计划"""
    day: int  # 1-7
    date: str
    platform: str  # "x" or "reddit"
    subreddit: Optional[str] = None  # e.g., "r/MachineLearning"
    post_type: str = "discussion"  # "discussion", "showcase", "tutorial"
    title: Optional[str] = None  # For Reddit
    content: str = ""
    hashtags: List[str] = field(default_factory=list)  # For X
    suggested_time_utc: str = "14:00"
    rationale: str = ""
    status: str = "pending"
    post_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            "date": self.date,
            "platform": self.platform,
            "subreddit": self.subreddit,
            "post_type": self.post_type,
            "title": self.title,
            "content": self.content,
            "hashtags": self.hashtags,
            "suggested_time_utc": self.suggested_time_utc,
            "rationale": self.rationale,
            "status": self.status,
            "post_id": self.post_id
        }


@dataclass
class WeeklyPlan:
    """周度推广计划"""
    plan_id: str
    title: str
    description: str
    week_start: datetime
    week_end: datetime
    daily_schedules: List[DailySchedule] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "draft"  # "draft", "approved", "executing", "completed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "title": self.title,
            "description": self.description,
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
            "daily_schedules": [ds.to_dict() for ds in self.daily_schedules],
            "created_at": self.created_at.isoformat(),
            "status": self.status
        }


class WeeklyPlanGenerator:
    """
    周计划生成器 - 使用 LLM 生成7天的详细推广计划

    输入:
        - 项目信息（从 README.zh.md 提取）
        - 目标受众描述
        - 推广目标（增加知名度、吸引贡献者等）
        - 目标社区列表（Reddit subreddits, X hashtags）

    输出:
        WeeklyPlan 对象，包含7天的详细安排
    """

    def __init__(self, llm_service=None):
        self.llm_service = llm_service

    def generate_weekly_plan(
        self,
        project_info: Dict[str, Any],
        target_audience: str,
        goals: List[str],
        target_communities: List[str],
        week_start: datetime
    ) -> WeeklyPlan:
        """
        生成一周的推广计划

        Args:
            project_info: 项目信息字典（名称、描述、技术栈、特色功能等）
            target_audience: 目标受众描述
            goals: 推广目标列表
            target_communities: 目标社区列表（如 r/MachineLearning, #AI）
            week_start: 周起始日期

        Returns:
            WeeklyPlan 对象
        """
        if not LLM_AVAILABLE or self.llm_service is None:
            raise RuntimeError("LLM MANDATORY: ModelProvider not available for weekly plan generation")

        # 1. 构建 LLM Prompt
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            project_info, target_audience, goals, target_communities, week_start
        )

        # 2. 调用 LLM 生成计划
        trace_id = f"weekly-plan:{uuid.uuid4().hex[:8]}"
        caller_context = ModelProviderCallerContext(
            source_module="self_promotion_agent",
            invocation_phase="weekly_plan_generation",
            trace_id=trace_id
        )

        try:
            llm_call_result = self.llm_service.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context={
                    "project_name": project_info.get("name"),
                    "week_start": week_start.isoformat(),
                },
                caller_context=caller_context,
                source_module="self_promotion_agent",
                invocation_phase="weekly_plan_generation",
            )
            # Extract JSON output from LLMGatewayCall object
            raw_plan = llm_call_result.output if hasattr(llm_call_result, 'output') else llm_call_result
        except Exception as exc:
            logger.error(f"LLM call failed for weekly plan generation: {exc}")
            raise  # Fail-Closed: 不允许静默降级

        # 3. 验证和解析结果
        plan = self._validate_and_parse(raw_plan, week_start, trace_id)

        return plan

    def _build_system_prompt(self) -> str:
        return """你是一个专业的开源项目推广专家，专注于 AI/ML 领域的技术社区营销。

你的任务是为一周（7天）制定详细的社交媒体推广计划，目标平台是 Reddit 和 X (Twitter)。

要求：
1. 每天安排 1 个帖子，交替使用 Reddit 和 X 平台
2. 内容要有变化，避免重复，覆盖项目的不同方面
3. Reddit 帖子要符合各 subreddit 的规则，避免自推广嫌疑
4. X 帖子要在 280 字符以内，包含相关 hashtag
5. 考虑不同时区的最佳发布时间
6. 内容要真实、有价值，不要过度营销

输出格式必须是严格的 JSON：
{
    "plan_title": "本周推广主题",
    "daily_schedules": [
        {
            "day": 1,
            "date": "2026-04-20",
            "platform": "reddit",
            "subreddit": "r/MachineLearning",
            "post_type": "discussion",
            "title": "帖子标题",
            "content": "帖子正文",
            "suggested_time_utc": "14:00",
            "rationale": "为什么选择这个时间和内容"
        }
    ]
}

注意：
- 对于 X 平台，不需要 subreddit 和 title 字段，但需要 hashtags 数组
- 对于 Reddit 平台，必须有 subreddit 和 title 字段
- 确保内容多样性和专业性"""

    def _build_user_prompt(
        self,
        project_info: Dict[str, Any],
        target_audience: str,
        goals: List[str],
        target_communities: List[str],
        week_start: datetime
    ) -> str:
        project_name = project_info.get("name", "AnimoCerebro")
        description = project_info.get("description", "")
        tech_stack = ", ".join(project_info.get("tech_stack", []))
        features = "\n".join(f"- {f}" for f in project_info.get("features", []))

        return f"""请为以下项目制定一周的推广计划：

项目名称：{project_name}
项目描述：{description}
技术栈：{tech_stack}

核心功能：
{features}

目标受众：{target_audience}

推广目标：
{chr(10).join(f"- {goal}" for goal in goals)}

目标社区：
{chr(10).join(f"- {comm}" for comm in target_communities)}

周起始日期：{week_start.strftime('%Y-%m-%d')}

请生成一个7天的详细推广计划，确保内容专业、有价值且符合各平台规范。"""

    def _validate_and_parse(
        self,
        raw_plan: Dict[str, Any],
        week_start: datetime,
        trace_id: str
    ) -> WeeklyPlan:
        """验证并解析 LLM 返回的计划"""
        try:
            # 验证基本结构
            if "plan_title" not in raw_plan or "daily_schedules" not in raw_plan:
                raise ValueError("Invalid plan structure: missing plan_title or daily_schedules")

            daily_schedules = []
            for day_data in raw_plan["daily_schedules"]:
                schedule = DailySchedule(
                    day=day_data["day"],
                    date=day_data["date"],
                    platform=day_data["platform"],
                    subreddit=day_data.get("subreddit"),
                    post_type=day_data.get("post_type", "discussion"),
                    title=day_data.get("title"),
                    content=day_data.get("content", ""),
                    hashtags=day_data.get("hashtags", []),
                    suggested_time_utc=day_data.get("suggested_time_utc", "14:00"),
                    rationale=day_data.get("rationale", ""),
                    status="pending"
                )
                daily_schedules.append(schedule)

            plan = WeeklyPlan(
                plan_id=f"plan-{uuid.uuid4().hex[:8]}",
                title=raw_plan["plan_title"],
                description=f"Weekly promotion plan starting {week_start.strftime('%Y-%m-%d')}",
                week_start=week_start,
                week_end=week_start + timedelta(days=6),
                daily_schedules=daily_schedules,
                created_at=datetime.now(timezone.utc),
                status="draft"
            )

            logger.info(f"✅ Weekly plan generated: {plan.plan_id} with {len(daily_schedules)} days")
            return plan

        except Exception as e:
            logger.error(f"Failed to validate and parse plan: {e}")
            raise


class ContentStrategyEngine:
    """
    内容策略引擎 - 使用 LLM 优化和修复帖子内容

    职责：
        - 根据平台特性优化内容（X 的字符限制、Reddit 的 Markdown 格式）
        - 当 Reddit 发帖失败时，分析错误原因并生成修正版本
        - 确保内容符合社区规则
        - 生成内容的多个变体用于 A/B 测试
    """

    def __init__(self, llm_service=None):
        self.llm_service = llm_service

    async def optimize_for_platform(
        self,
        content: str,
        platform: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """根据平台特性优化内容"""
        if platform == "x":
            return await self._optimize_for_x(content, context)
        elif platform == "reddit":
            return await self._optimize_for_reddit(content, context)
        else:
            return {"success": False, "error": f"Unsupported platform: {platform}"}

    async def fix_reddit_post_error(
        self,
        original_content: Dict[str, Any],
        error_message: str,
        subreddit_rules: List[str]
    ) -> Dict[str, Any]:
        """
        分析 Reddit 发帖失败原因并生成修正版本

        Args:
            original_content: 原始帖子内容（title, body）
            error_message: Reddit 返回的错误信息
            subreddit_rules: 社区规则列表

        Returns:
            修正后的内容和建议
        """
        if not LLM_AVAILABLE or self.llm_service is None:
            return {
                "success": False,
                "error": "LLM service not available for error recovery",
                "suggestion": "请人工检查并手动修改内容"
            }

        # 1. 使用 LLM 分析错误原因
        analysis_prompt = f"""
Reddit 发帖失败，请分析原因并提供修正方案。

原始标题: {original_content.get('title', '')}
原始内容: {original_content.get('body', '')[:500]}...
错误信息: {error_message}
社区规则: {', '.join(subreddit_rules)}

请分析：
1. 违反了哪条规则？
2. 如何修改才能符合规则？
3. 提供修正后的标题和内容

输出 JSON 格式：
{{
    "analysis": "错误原因分析",
    "fixed_title": "修正后的标题",
    "fixed_body": "修正后的内容",
    "success": true
}}
"""

        trace_id = f"fix-reddit-error:{uuid.uuid4().hex[:8]}"
        caller_context = ModelProviderCallerContext(
            source_module="self_promotion_agent",
            invocation_phase="error_recovery",
            trace_id=trace_id
        )

        try:
            result = self.llm_service.generate_json(
                prompt=analysis_prompt,
                context={"error_type": "reddit_post_rejection"},
                caller_context=caller_context,
                source_module="self_promotion_agent",
                invocation_phase="error_recovery",
            )

            # 2. 验证修正方案
            fixed_content = self._validate_fix(result)

            logger.info(f"✅ Reddit post error fixed successfully (trace: {trace_id})")
            return fixed_content

        except Exception as exc:
            logger.error(f"Failed to fix Reddit post error: {exc}")
            return {
                "success": False,
                "error": f"Error recovery failed: {str(exc)}",
                "suggestion": "请人工检查并手动修改内容"
            }

    async def _optimize_for_x(self, content: str, context: Dict) -> Dict:
        """优化 X 平台内容"""
        max_length = 280
        optimized = content.strip()

        # 截断到 280 字符
        if len(optimized) > max_length:
            optimized = optimized[:max_length - 3] + "..."

        # 添加 hashtag（如果上下文提供）
        hashtags = context.get("hashtags", [])
        if hashtags:
            hashtag_str = " ".join(hashtags[:3])  # 最多3个 hashtag
            if len(optimized) + len(hashtag_str) + 1 <= max_length:
                optimized = f"{optimized} {hashtag_str}"

        return {
            "success": True,
            "content": optimized,
            "length": len(optimized)
        }

    async def _optimize_for_reddit(self, content: Dict, context: Dict) -> Dict:
        """优化 Reddit 内容"""
        title = content.get("title", "").strip()
        body = content.get("body", "").strip()

        # 确保标题不以特殊字符开头
        title = title.lstrip("!@#$%^&*")

        # 添加 Markdown 格式
        if body and not body.startswith("#"):
            lines = body.split("\n")
            if lines and not lines[0].startswith("#"):
                body = f"## {lines[0]}\n" + "\n".join(lines[1:])

        return {
            "success": True,
            "title": title,
            "body": body
        }

    def _validate_fix(self, result: Dict) -> Dict:
        """验证修正结果"""
        if result.get("success") and "fixed_title" in result and "fixed_body" in result:
            return {
                "success": True,
                "title": result["fixed_title"],
                "body": result["fixed_body"],
                "analysis": result.get("analysis", "")
            }
        else:
            return {
                "success": False,
                "error": "Invalid fix result structure",
                "suggestion": "请人工检查并手动修改内容"
            }


class SelfPromotionAgent:
    """
    自我推广 Agent - 基于 LLM 的智能社交媒体推广系统
    """

    def __init__(self, config_path: Optional[str] = None):
        # 基础属性
        self.agent_id = "agent-self-promotion"
        self.name = "Self-Promotion Agent"
        self.status = "active"
        self.capabilities = [
            "generate_weekly_plan",
            "create_post",
            "execute_promotion",
            "human_intervention",
            "error_recovery"
        ]
        self.created_at = datetime.now(timezone.utc)

        # LLM 服务（自动使用 config/provider_tools.yml 中的 default_provider）
        # 当前默认提供商: openai_compat (http://localhost:8317/v1)
        # 可通过修改配置文件或设置 ZENTEX_DEFAULT_PROVIDER 环境变量更改
        if LLM_AVAILABLE:
            self.llm_service = get_llm_service()
        else:
            self.llm_service = None
            logger.warning("LLM service not available, agent will run in limited mode")

        # 组件组合
        self.weekly_planner = WeeklyPlanGenerator(self.llm_service)
        self.content_engine = ContentStrategyEngine(self.llm_service)

        # 社区规则管理器（自动下载和缓存 Reddit 社区规则）
        if RULES_MANAGER_AVAILABLE:
            self.rules_manager = CommunityRulesManager()
        else:
            self.rules_manager = None
            logger.warning("CommunityRulesManager not available")

        # 浏览器自动化（有头模式，便于人工协助）
        if BROWSER_AVAILABLE:
            try:
                self.browser_manager = BrowserAutomationManager(headless=False, slow_mo=500)
            except ImportError as e:
                logger.warning(f"Browser automation initialization failed: {e}")
                self.browser_manager = None
        else:
            self.browser_manager = None
            logger.warning("Browser automation not available")

        # 数据存储
        self.weekly_plans: Dict[str, WeeklyPlan] = {}
        self.posts: Dict[str, Dict[str, Any]] = {}
        self.human_requests: List[Dict[str, Any]] = []  # 人类中途指定的推广内容

        # 审计和监控
        self.audit_log: List[Dict[str, Any]] = []
        self.error_history: Dict[str, List[Dict[str, Any]]] = {}

        # 配置
        self.config = self._load_config(config_path)

        logger.info(f"✅ Self-Promotion Agent initialized: {self.agent_id}")

    def get_info(self) -> Dict[str, Any]:
        """获取 Agent 信息"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "capabilities": self.capabilities,
            "created_at": self.created_at.isoformat(),
            "llm_available": LLM_AVAILABLE,
            "browser_available": BROWSER_AVAILABLE
        }

    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "auto_approve_plans": False,
            "max_posts_per_day": 2,
            "captcha_timeout_minutes": 10,
            "retry_on_failure": True,
            "max_retries": 3
        }

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
                logger.info(f"Loaded config from {config_path}")
            except Exception as e:
                logger.error(f"Failed to load config: {e}")

        return default_config

    def _add_audit_log(self, action: str, details: Dict[str, Any]):
        """
        添加审计日志（符合 Zentex 红线要求）

        必须记录的事件：
        - 周计划生成
        - 帖子发布（成功/失败）
        - 人工干预请求
        - 错误修复尝试
        - LLM 调用（带 trace_id）
        """
        audit_entry = {
            "audit_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "trace_id": details.get("trace_id", str(uuid.uuid4())),
            "details": details,
            "reason": details.get("reason", f"Automated action: {action}")
        }

        self.audit_log.append(audit_entry)
        logger.debug(f"Audit log added: {action}")

    def generate_weekly_plan(
        self,
        project_info: Dict[str, Any],
        target_audience: str = "AI/ML developers",
        goals: List[str] = None,
        target_communities: List[str] = None,
        week_start: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        生成周度推广计划

        Args:
            project_info: 项目信息
            target_audience: 目标受众
            goals: 推广目标
            target_communities: 目标社区
            week_start: 周起始日期

        Returns:
            生成结果
        """
        try:
            if goals is None:
                goals = ["increase awareness", "attract contributors"]
            if target_communities is None:
                target_communities = ["r/MachineLearning", "r/artificial"]
            if week_start is None:
                week_start = datetime.now(timezone.utc)

            plan = self.weekly_planner.generate_weekly_plan(
                project_info=project_info,
                target_audience=target_audience,
                goals=goals,
                target_communities=target_communities,
                week_start=week_start
            )

            # 保存计划
            self.weekly_plans[plan.plan_id] = plan

            # 记录审计日志
            self._add_audit_log(
                action="generate_weekly_plan",
                details={
                    "plan_id": plan.plan_id,
                    "week_start": week_start.isoformat(),
                    "days_count": len(plan.daily_schedules),
                    "trace_id": f"weekly-plan:{uuid.uuid4().hex[:8]}"
                }
            )

            return {
                "success": True,
                "plan_id": plan.plan_id,
                "plan": plan.to_dict(),
                "message": "Weekly plan generated successfully"
            }

        except Exception as e:
            logger.error(f"Failed to generate weekly plan: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def submit_human_request(
        self,
        content: str,
        platform: str = "both",
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """
        提交人类中途指定的推广内容

        Args:
            content: 推广内容
            platform: 目标平台（x, reddit, both）
            priority: 优先级（low, normal, high）

        Returns:
            提交结果
        """
        request = {
            "request_id": str(uuid.uuid4()),
            "content": content,
            "platform": platform,
            "priority": priority,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending"
        }

        self.human_requests.append(request)

        # 记录审计日志
        self._add_audit_log(
            action="human_intervention_request",
            details={
                "request_id": request["request_id"],
                "content_preview": content[:100],
                "platform": platform,
                "priority": priority
            }
        )

        logger.info(f"✅ Human request submitted: {request['request_id']}")

        return {
            "success": True,
            "request_id": request["request_id"],
            "message": "Human request submitted successfully"
        }

    def get_weekly_plan(self, plan_id: str) -> Dict[str, Any]:
        """获取周计划详情"""
        if plan_id not in self.weekly_plans:
            return {
                "success": False,
                "error": f"Plan {plan_id} not found"
            }

        plan = self.weekly_plans[plan_id]
        return {
            "success": True,
            "plan": plan.to_dict()
        }

    def get_audit_log(
        self,
        action_filter: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """获取审计日志"""
        filtered_logs = self.audit_log.copy()

        if action_filter:
            filtered_logs = [log for log in filtered_logs if log["action"] == action_filter]

        # 按时间倒序排列
        filtered_logs.sort(key=lambda x: x["timestamp"], reverse=True)

        return {
            "success": True,
            "audit_log": filtered_logs[:limit],
            "total_count": len(filtered_logs)
        }

    def track_promotion_results(self, plan_id: str) -> Dict[str, Any]:
        """
        追踪推广效果

        指标：
        - 发布成功率
        - 错误率和修复成功率
        - 人类干预频率
        """
        plan = self.weekly_plans.get(plan_id)
        if not plan:
            return {"success": False, "error": f"Plan {plan_id} not found"}

        results = {
            "plan_id": plan_id,
            "total_posts": len(plan.daily_schedules),
            "published": sum(1 for ds in plan.daily_schedules if ds.status == "published"),
            "failed": sum(1 for ds in plan.daily_schedules if ds.status == "failed"),
            "pending": sum(1 for ds in plan.daily_schedules if ds.status == "pending"),
            "human_interventions": len([
                req for req in self.human_requests
                if req.get("plan_id") == plan_id
            ])
        }

        # 计算错误率
        if results["total_posts"] > 0:
            results["error_rate"] = results["failed"] / results["total_posts"]
        else:
            results["error_rate"] = 0.0

        return {
            "success": True,
            "results": results
        }

    def get_community_rules(self, subreddit: str, auto_download: bool = True) -> Dict[str, Any]:
        """
        获取社区规则

        Args:
            subreddit: 社区名称（如 "MachineLearning"）
            auto_download: 如果规则不存在，是否自动下载

        Returns:
            规则信息字典
        """
        if not self.rules_manager:
            return {
                "success": False,
                "error": "CommunityRulesManager not available"
            }

        try:
            rule = self.rules_manager.get_community_rules(subreddit, auto_download=auto_download)

            if rule:
                return {
                    "success": True,
                    "subreddit": rule.subreddit,
                    "rules": rule.to_dict(),
                    "message": f"Rules for r/{subreddit} retrieved successfully"
                }
            else:
                return {
                    "success": False,
                    "error": f"Could not retrieve rules for r/{subreddit}"
                }

        except Exception as e:
            logger.error(f"Failed to get community rules: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def validate_post_against_rules(
        self,
        subreddit: str,
        title: str,
        content: str
    ) -> Dict[str, Any]:
        """
        验证帖子是否符合社区规则

        Args:
            subreddit: 社区名称
            title: 帖子标题
            content: 帖子内容

        Returns:
            验证结果
        """
        if not self.rules_manager:
            return {
                "success": False,
                "error": "CommunityRulesManager not available"
            }

        try:
            result = self.rules_manager.validate_post_against_rules(
                subreddit=subreddit,
                title=title,
                content=content
            )

            # 记录审计日志
            self._add_audit_log(
                action="validate_post_rules",
                details={
                    "subreddit": subreddit,
                    "valid": result["valid"],
                    "violations_count": len(result.get("violations", []))
                }
            )

            return {
                "success": True,
                "validation": result
            }

        except Exception as e:
            logger.error(f"Failed to validate post against rules: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def list_cached_rules(self) -> Dict[str, Any]:
        """列出所有已缓存的社区规则"""
        if not self.rules_manager:
            return {
                "success": False,
                "error": "CommunityRulesManager not available"
            }

        try:
            rules_list = self.rules_manager.list_cached_rules()
            return {
                "success": True,
                "cached_rules": rules_list,
                "total_count": len(rules_list)
            }
        except Exception as e:
            logger.error(f"Failed to list cached rules: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def clear_expired_rules(self) -> Dict[str, Any]:
        """清除过期的规则缓存"""
        if not self.rules_manager:
            return {
                "success": False,
                "error": "CommunityRulesManager not available"
            }

        try:
            cleared_count = self.rules_manager.clear_expired_rules()
            return {
                "success": True,
                "cleared_count": cleared_count,
                "message": f"Cleared {cleared_count} expired rules"
            }
        except Exception as e:
            logger.error(f"Failed to clear expired rules: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# 全局单例实例
self_promotion_agent = SelfPromotionAgent()

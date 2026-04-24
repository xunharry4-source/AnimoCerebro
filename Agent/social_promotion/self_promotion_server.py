"""
Self-Promotion Agent FastAPI Server - Zentex 远程 Agent 服务封装

文件用途:
    将 SelfPromotionAgent 封装为 FastAPI HTTP 服务，实现 Zentex 远程 Agent 标准接口。
    提供 /handshake、/execute、/status 三个端点，供 Zentex AgentCoordinationService 调用。

主要职责:
    - 实现 Zentex 标准的握手协议（/handshake）
    - 实现任务执行端点（/execute）
    - 实现健康检查端点（/status）
    - 处理任务路由和参数验证
    - 统一的错误处理和响应格式化

不负责:
    - 不实现业务逻辑（委托给 SelfPromotionAgent）
    - 不管理用户认证（由 Zentex 协调服务处理）
    - 不持久化数据（由 Agent 内部管理）
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from Agent.self_promotion_agent import self_promotion_agent

logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="Self-Promotion Agent",
    description="Autonomous social media promotion agent for AnimoCerebro",
    version="1.0.0"
)


# --- 数据模型 ---

class HandshakeResponse(BaseModel):
    """握手响应模型"""
    agent_id: str
    version: str
    capabilities: list[Dict[str, str]]
    status: str


class ExecuteRequest(BaseModel):
    """任务执行请求模型"""
    task_id: str
    action: str
    params: Dict[str, Any]


class ExecuteResponse(BaseModel):
    """任务执行响应模型"""
    task_id: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# --- HTTP 端点 ---

@app.get("/status")
async def status():
    """
    健康检查端点

    Returns:
        服务状态信息
    """
    return {
        "status": "online",
        "agent_id": self_promotion_agent.agent_id,
        "uptime": "running",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/handshake", response_model=HandshakeResponse)
async def handshake():
    """
    能力发现和身份验证端点

    Zentex AgentCoordinationService 会调用此端点进行握手，
    验证 Agent 身份并获取其能力列表。

    Returns:
        包含 agent_id、版本、能力和状态的握手响应
    """
    info = self_promotion_agent.get_info()

    return HandshakeResponse(
        agent_id=self_promotion_agent.agent_id,
        version="1.0.0",
        capabilities=[
            {"name": "generate_weekly_plan", "description": "Generate weekly promotion plan using LLM"},
            {"name": "create_post", "description": "Create optimized post content for specific platform"},
            {"name": "execute_promotion", "description": "Execute promotion tasks via browser automation"},
            {"name": "submit_human_request", "description": "Accept human intervention requests"},
            {"name": "get_weekly_plan", "description": "Retrieve generated weekly plan"},
            {"name": "get_audit_log", "description": "Retrieve audit logs"},
            {"name": "track_results", "description": "Track promotion results and metrics"},
            {"name": "get_community_rules", "description": "Get Reddit community rules (auto-download if missing)"},
            {"name": "validate_post_rules", "description": "Validate post against community rules before posting"},
            {"name": "list_cached_rules", "description": "List all cached community rules"},
            {"name": "clear_expired_rules", "description": "Clear expired community rules from cache"}
        ],
        status=info["status"]
    )


@app.post("/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest):
    """
    任务执行端点

    Zentex AgentCoordinationService 通过此端点分发任务到 Agent。
    支持的任务类型：
    - generate_weekly_plan: 生成周度推广计划
    - create_post: 创建优化的帖子内容
    - execute_promotion: 执行推广任务（通过浏览器自动化）
    - submit_human_request: 提交人类干预请求
    - get_weekly_plan: 获取周计划详情
    - get_audit_log: 获取审计日志
    - track_results: 追踪推广效果

    Args:
        request: 包含 task_id、action 和 params 的执行请求

    Returns:
        包含执行结果的响应
    """
    try:
        logger.info(f"Executing task: {request.action} (task_id: {request.task_id})")

        # 路由到对应的处理器
        if request.action == "generate_weekly_plan":
            result = await _handle_generate_weekly_plan(request.params)

        elif request.action == "create_post":
            result = await _handle_create_post(request.params)

        elif request.action == "execute_promotion":
            result = await _handle_execute_promotion(request.params)

        elif request.action == "submit_human_request":
            result = await _handle_human_request(request.params)

        elif request.action == "get_weekly_plan":
            result = await _handle_get_weekly_plan(request.params)

        elif request.action == "get_audit_log":
            result = await _handle_get_audit_log(request.params)

        elif request.action == "track_results":
            result = await _handle_track_results(request.params)

        elif request.action == "get_community_rules":
            result = await _handle_get_community_rules(request.params)

        elif request.action == "validate_post_rules":
            result = await _handle_validate_post_rules(request.params)

        elif request.action == "list_cached_rules":
            result = await _handle_list_cached_rules(request.params)

        elif request.action == "clear_expired_rules":
            result = await _handle_clear_expired_rules(request.params)

        else:
            raise ValueError(f"Unknown action: {request.action}")

        logger.info(f"Task completed: {request.action} (success: {result.get('success', False)})")

        return ExecuteResponse(
            task_id=request.task_id,
            success=True,
            result=result
        )

    except Exception as e:
        logger.error(f"Task execution failed: {request.action} - {str(e)}")
        return ExecuteResponse(
            task_id=request.task_id,
            success=False,
            error=str(e)
        )


# --- 任务处理器 ---

async def _handle_generate_weekly_plan(params: Dict) -> Dict:
    """处理周计划生成任务"""
    project_info = params.get("project_info", {})
    target_audience = params.get("target_audience", "AI/ML developers")
    goals = params.get("goals", ["increase awareness", "attract contributors"])
    target_communities = params.get("target_communities", ["r/MachineLearning", "r/artificial"])

    # 解析 week_start
    week_start_str = params.get("week_start")
    if week_start_str:
        week_start = datetime.fromisoformat(week_start_str)
    else:
        week_start = datetime.now(timezone.utc)

    result = self_promotion_agent.generate_weekly_plan(
        project_info=project_info,
        target_audience=target_audience,
        goals=goals,
        target_communities=target_communities,
        week_start=week_start
    )

    return result


async def _handle_create_post(params: Dict) -> Dict:
    """处理创建帖子任务"""
    # TODO: 实现帖子创建逻辑
    return {
        "success": True,
        "message": "Post creation not yet implemented",
        "note": "This feature will be added in future versions"
    }


async def _handle_execute_promotion(params: Dict) -> Dict:
    """处理执行推广任务"""
    plan_id = params.get("plan_id")
    day = params.get("day", 1)

    if not plan_id:
        raise ValueError("plan_id is required")

    # 获取计划
    plan_result = self_promotion_agent.get_weekly_plan(plan_id)
    if not plan_result["success"]:
        raise ValueError(plan_result.get("error", "Plan not found"))

    plan_data = plan_result["plan"]
    if day < 1 or day > len(plan_data["daily_schedules"]):
        raise ValueError(f"Invalid day: {day}. Plan has {len(plan_data['daily_schedules'])} days")

    schedule = plan_data["daily_schedules"][day - 1]

    # 检查浏览器自动化是否可用
    if not self_promotion_agent.browser_manager:
        return {
            "success": False,
            "error": "Browser automation not available",
            "schedule": schedule,
            "note": "Please ensure Playwright is installed and configured"
        }

    # 初始化浏览器（如果尚未初始化）
    try:
        if not hasattr(self_promotion_agent.browser_manager, 'is_initialized') or \
           not self_promotion_agent.browser_manager.is_initialized:
            await self_promotion_agent.browser_manager.initialize(headless=False)
    except AttributeError:
        # 同步版本的 BrowserAutomationManager
        if not self_promotion_agent.browser_manager.browser:
            self_promotion_agent.browser_manager.start_browser()

    # 根据平台发布
    try:
        if schedule["platform"] == "x":
            result = self_promotion_agent.browser_manager.post_to_x(
                content=schedule["content"]
            )
        elif schedule["platform"] == "reddit":
            subreddit = schedule.get("subreddit", "").replace("r/", "")
            result = self_promotion_agent.browser_manager.post_to_reddit(
                subreddit=subreddit,
                title=schedule.get("title", ""),
                content=schedule["content"],
                post_type=schedule.get("post_type", "text")
            )
        else:
            return {
                "success": False,
                "error": f"Unsupported platform: {schedule['platform']}"
            }

        # 更新帖子状态
        if result.get("success"):
            schedule["status"] = "published"
            schedule["published_at"] = datetime.now(timezone.utc).isoformat()
            schedule["platform_url"] = result.get("url", "")
        else:
            schedule["status"] = "failed"
            schedule["error"] = result.get("error", "Unknown error")

            # 如果是 Reddit 且失败，尝试自动修复
            if schedule["platform"] == "reddit":
                logger.warning(f"Reddit post failed, attempting auto-fix...")
                # TODO: 调用内容策略引擎修复

        return result

    except Exception as e:
        logger.error(f"Failed to execute promotion: {e}")
        schedule["status"] = "failed"
        schedule["error"] = str(e)
        return {
            "success": False,
            "error": str(e),
            "schedule": schedule
        }


async def _handle_human_request(params: Dict) -> Dict:
    """处理人类中途指定的推广内容"""
    content = params.get("content")
    if not content:
        raise ValueError("content is required")

    platform = params.get("platform", "both")
    priority = params.get("priority", "normal")

    result = self_promotion_agent.submit_human_request(
        content=content,
        platform=platform,
        priority=priority
    )

    return result


async def _handle_get_weekly_plan(params: Dict) -> Dict:
    """处理获取周计划任务"""
    plan_id = params.get("plan_id")
    if not plan_id:
        raise ValueError("plan_id is required")

    result = self_promotion_agent.get_weekly_plan(plan_id)
    return result


async def _handle_get_audit_log(params: Dict) -> Dict:
    """处理获取审计日志任务"""
    action_filter = params.get("action_filter")
    limit = params.get("limit", 100)

    result = self_promotion_agent.get_audit_log(
        action_filter=action_filter,
        limit=limit
    )

    return result


async def _handle_track_results(params: Dict) -> Dict:
    """处理追踪推广效果任务"""
    plan_id = params.get("plan_id")
    if not plan_id:
        raise ValueError("plan_id is required")

    result = self_promotion_agent.track_promotion_results(plan_id)
    return result


async def _handle_get_community_rules(params: Dict) -> Dict:
    """处理获取社区规则任务"""
    subreddit = params.get("subreddit")
    if not subreddit:
        raise ValueError("subreddit is required")

    auto_download = params.get("auto_download", True)

    result = self_promotion_agent.get_community_rules(
        subreddit=subreddit,
        auto_download=auto_download
    )
    return result


async def _handle_validate_post_rules(params: Dict) -> Dict:
    """处理验证帖子规则任务"""
    subreddit = params.get("subreddit")
    title = params.get("title", "")
    content = params.get("content", "")

    if not subreddit:
        raise ValueError("subreddit is required")
    if not content:
        raise ValueError("content is required")

    result = self_promotion_agent.validate_post_against_rules(
        subreddit=subreddit,
        title=title,
        content=content
    )
    return result


async def _handle_list_cached_rules(params: Dict) -> Dict:
    """处理列出缓存规则任务"""
    result = self_promotion_agent.list_cached_rules()
    return result


async def _handle_clear_expired_rules(params: Dict) -> Dict:
    """处理清除过期规则任务"""
    result = self_promotion_agent.clear_expired_rules()
    return result


# --- 主入口 ---

if __name__ == "__main__":
    import uvicorn

    logger.info("🚀 Starting Self-Promotion Agent server on port 9004...")

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=9004,
        reload=True,
        ws="websockets-sansio"
    )

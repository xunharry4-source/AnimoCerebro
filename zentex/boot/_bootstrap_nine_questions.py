"""
Nine Questions Bootstrap Module

This module handles initialization of nine questions runtime state
and startup procedures through the plugin service.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, Optional

from zentex.tasks.service import TaskManagementService
from zentex.agents.service import AgentCoordinationService

logger = logging.getLogger(__name__)


def should_autorun_real_startup_nine_questions() -> bool:
    """Check if real startup nine questions should auto-run."""
    flag = str(os.getenv("ZENTEX_AUTORUN_STARTUP_NINE_QUESTIONS", "")).strip().lower()
    return flag in {"1", "true", "yes", "on"}


def should_seed_fake_startup_nine_questions() -> bool:
    """Check if fake startup nine questions should be seeded."""
    flag = str(os.getenv("ZENTEX_SEED_STARTUP_NINE_QUESTIONS", "")).strip().lower()
    return flag in {"1", "true", "yes", "on"} or "pytest" in sys.modules


def build_startup_workspace_snapshot(
    *,
    workspace_root: str,
    cognitive_registry: Any,
    execution_registry: Optional[Any] = None,
    task_service: Optional[Any] = None,
    host_telemetry_plugin: Optional[object] = None,
    mcp_service: Optional[object] = None,
    cli_service: Optional[object] = None,
) -> Dict[str, Any]:
    """
    Build initial workspace snapshot for nine questions startup.
    
    Args:
        workspace_root: Root directory of the workspace
        cognitive_registry: CognitiveToolRegistry instance
        execution_registry: Optional ExecutionDomainRegistry
        task_service: Optional TaskManagementService
        host_telemetry_plugin: Optional host telemetry plugin
        mcp_service: Optional MCP service
        cli_service: Optional CLI service
        
    Returns:
        Workspace snapshot dictionary
    """
    # This is a stub implementation
    # The full implementation should be moved from web_dev.py
    return {
        "workspace_root": workspace_root,
        "environment_summary": "web console startup auto-ran nine questions",
        "timestamp": None,
    }


def seed_nine_question_runtime_state(
    *,
    workspace_snapshot: Dict[str, Any],
    task_service: Optional[Any] = None,
    agent_service: Optional[Any] = None,
) -> None:
    """
    Seed runtime state for nine questions execution.
    
    Args:
        workspace_snapshot: Initial workspace snapshot
        task_service: Optional TaskManagementService
        agent_service: Optional AgentCoordinationService
    """
    logger.info("Seeding nine question runtime state")


async def seed_task_and_agent_runtime_state(
    *,
    task_service: Optional[TaskManagementService] = None,
    agent_service: Optional[AgentCoordinationService] = None,
) -> None:
    """
    Seed runtime state for tasks and agents.
    
    Args:
        task_service: Optional TaskManagementService
        agent_service: Optional AgentCoordinationService
    """
    if task_service is None or agent_service is None:
        logger.info("Skipping task/agent runtime state seed because services are missing")
        return

    agent_service.seed_demo_agents(
        [
            {
                "agent_id": "agent-build",
                "name": "agent-build",
                "agent_name": "Build Bot",
                "version": "1.2.3",
                "function_description": "负责构建、测试与交付前的运行态检查。",
                "endpoint": "http://127.0.0.1:9101",
                "role_tag": "worker",
                "trust_level": "trusted",
                "status": "active",
                "scope": ["build", "ci"],
                "capabilities": [{"capability": "build", "version": "1.0"}],
                "latency_ms": 32.5,
                "success_rate": 0.98,
            },
            {
                "agent_id": "agent-audit",
                "name": "agent-audit",
                "agent_name": "Audit Bot",
                "version": "2.0.1",
                "function_description": "负责 transcript 审计与运行态回放核对。",
                "endpoint": "http://127.0.0.1:9102",
                "role_tag": "auditor",
                "trust_level": "trusted",
                "status": "idle",
                "scope": ["audit", "replay"],
                "capabilities": [{"capability": "audit", "version": "2.0"}],
                "latency_ms": 41.0,
                "success_rate": 0.995,
            },
            {
                "agent_id": "agent-memory",
                "name": "agent-memory",
                "agent_name": "Memory Bot",
                "version": "1.5.0",
                "function_description": "负责记忆整理与任务回执归档。",
                "endpoint": "http://127.0.0.1:9103",
                "role_tag": "support",
                "trust_level": "restricted",
                "status": "busy",
                "scope": ["memory"],
                "capabilities": [{"capability": "memory", "version": "1.5"}],
                "latency_ms": 58.0,
                "success_rate": 0.97,
            },
        ]
    )

    await task_service.seed_demo_tasks(
        [
            {
                "idempotency_key": "seed-task-001",
                "title": "校验九问真实状态绑定",
                "task_type": "system_action",
                "status": "in_progress",
                "progress": 0.55,
                "originator_id": "web-console",
                "target_id": "agent-build",
                "remarks": "正在核对 NineQuestionState 与前端卡片绑定。",
            },
            {
                "idempotency_key": "seed-task-002",
                "title": "审计 Agent 收件箱聚合",
                "task_type": "cognitive_step",
                "status": "todo",
                "progress": 0.0,
                "originator_id": "web-console",
                "target_id": "agent-audit",
                "remarks": "等待检查 receipts 与 inbox 视图。",
            },
            {
                "idempotency_key": "seed-task-003",
                "title": "归档任务执行回执",
                "task_type": "intervention",
                "status": "done",
                "progress": 1.0,
                "originator_id": "web-console",
                "target_id": "agent-memory",
                "remarks": "历史回执已归档。",
            },
        ]
    )


async def auto_run_startup_nine_questions(
    *,
    workspace_snapshot: Dict[str, Any],
    runtime: Optional[Any] = None,
) -> None:
    """
    Auto-run startup nine questions if enabled.
    
    Args:
        workspace_snapshot: Initial workspace snapshot
        runtime: Optional BrainRuntime instance
    """
    if not should_autorun_real_startup_nine_questions():
        logger.info("Startup nine questions auto-run disabled")
        return
    
    logger.info("Auto-running startup nine questions")


def start_cold_start_onboarding_background(
    *,
    workspace_snapshot: Optional[Dict[str, Any]] = None,
    runtime: Optional[Any] = None,
) -> None:
    """
    Start cold-start onboarding procedures in background.
    
    Args:
        workspace_snapshot: Optional workspace snapshot
        runtime: Optional BrainRuntime instance
    """
    logger.info("Starting cold-start onboarding background process")

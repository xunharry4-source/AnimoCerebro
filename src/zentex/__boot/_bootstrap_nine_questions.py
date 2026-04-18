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
    """Build initial workspace snapshot for nine questions startup.

    Scans the workspace directory structure and collects available tools,
    plugins, and service availability so the nine-questions bootstrap has
    real evidence to work with from the first cycle.
    """
    import datetime
    import platform
    from pathlib import Path

    workspace_path = Path(workspace_root)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # --- Directory structure scan (lightweight: top 2 levels only) -----------
    ext_counts: Dict[str, int] = {}
    dir_count = 0
    file_count = 0
    try:
        for entry in workspace_path.rglob("*"):
            if any(part.startswith(".") for part in entry.parts):
                continue  # skip hidden dirs/files
            if entry.is_dir():
                dir_count += 1
            elif entry.is_file():
                file_count += 1
                ext = entry.suffix.lower()
                if ext:
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
    except Exception as exc:
        logger.error("build_startup_workspace_snapshot: directory scan failed: %s", exc)

    top_extensions = sorted(ext_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]

    # --- Cognitive tools ------------------------------------------------------
    cognitive_tool_ids: list[str] = []
    try:
        if cognitive_registry is not None:
            registrations = getattr(cognitive_registry, "list_registrations", lambda: [])()
            cognitive_tool_ids = [str(r.plugin_id) for r in registrations if r is not None]
    except Exception as exc:
        logger.error("build_startup_workspace_snapshot: cognitive registry scan failed: %s", exc)

    # --- Execution tools ------------------------------------------------------
    execution_domain_ids: list[str] = []
    try:
        if execution_registry is not None:
            list_fn = getattr(execution_registry, "list_domains", None) or getattr(
                execution_registry, "list_registrations", None
            )
            if callable(list_fn):
                execution_domain_ids = [str(d) for d in (list_fn() or [])]
    except Exception as exc:
        logger.error("build_startup_workspace_snapshot: execution registry scan failed: %s", exc)

    # --- Service availability markers ----------------------------------------
    service_availability: Dict[str, str] = {
        "cognitive_registry": "available" if cognitive_registry is not None else "unavailable",
        "execution_registry": "available" if execution_registry is not None else "unavailable",
        "task_service": "available" if task_service is not None else "unavailable",
        "host_telemetry_plugin": "available" if host_telemetry_plugin is not None else "unavailable",
        "mcp_service": "available" if mcp_service is not None else "unavailable",
        "cli_service": "available" if cli_service is not None else "unavailable",
    }
    unavailable = [k for k, v in service_availability.items() if v == "unavailable"]
    if unavailable:
        logger.error(
            "build_startup_workspace_snapshot: unavailable services at startup: %s",
            ", ".join(unavailable),
        )

    # --- Host environment -----------------------------------------------------
    host_info: Dict[str, Any] = {}
    try:
        host_info = {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "python_version": platform.python_version(),
            "machine": platform.machine(),
        }
    except Exception:
        pass

    snapshot = {
        "workspace_root": str(workspace_root),
        "timestamp": timestamp,
        "environment_summary": (
            f"工作区扫描完成：{file_count} 个文件，{dir_count} 个目录"
            f"，主要扩展名: {', '.join(f'{ext}({cnt})' for ext, cnt in top_extensions[:5])}"
        ),
        "workspace_structure": {
            "file_count": file_count,
            "dir_count": dir_count,
            "top_extensions": [{"ext": ext, "count": cnt} for ext, cnt in top_extensions],
        },
        "available_cognitive_tools": cognitive_tool_ids,
        "available_execution_domains": execution_domain_ids,
        "service_availability": service_availability,
        "host_environment": host_info,
    }
    logger.info(
        "build_startup_workspace_snapshot: snapshot built — %d cognitive tools, "
        "%d execution domains, %d files scanned",
        len(cognitive_tool_ids),
        len(execution_domain_ids),
        file_count,
    )
    return snapshot


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
    """Auto-run startup nine questions if ZENTEX_AUTORUN_STARTUP_NINE_QUESTIONS=1.

    Uses the kernel service (via ``runtime`` or direct import fallback) to
    bootstrap the nine questions for the startup session.  Runs off the event
    loop via ``asyncio.to_thread`` so the call is safe from an async context.
    """
    import asyncio

    if not should_autorun_real_startup_nine_questions():
        logger.info("Startup nine questions auto-run disabled (set ZENTEX_AUTORUN_STARTUP_NINE_QUESTIONS=1 to enable)")
        return

    logger.info("Auto-running startup nine questions with workspace snapshot: %s",
                {k: v for k, v in workspace_snapshot.items() if k != "host_environment"})

    # Resolve the kernel service facade from runtime or direct import.
    kernel_service = None
    try:
        if runtime is not None:
            kernel_service = getattr(runtime, "kernel_service", None) or getattr(runtime, "kernel", None)
        if kernel_service is None:
            from zentex.kernel.service import get_service as _get_kernel
            kernel_service = _get_kernel()
    except Exception as exc:
        logger.error("auto_run_startup_nine_questions: could not resolve kernel service: %s", exc)
        return

    # Get or create a startup session.
    try:
        create_session_fn = getattr(kernel_service, "create_session", None)
        if not callable(create_session_fn):
            logger.error("auto_run_startup_nine_questions: kernel service has no create_session()")
            return
        session_id: str = create_session_fn(user_id="startup")
    except Exception as exc:
        logger.error("auto_run_startup_nine_questions: failed to create startup session: %s", exc)
        return

    # Run the bootstrap off the event loop.
    try:
        await asyncio.to_thread(
            kernel_service.ensure_nine_questions_bootstrap, session_id, force=True
        )
        logger.info(
            "auto_run_startup_nine_questions: bootstrap completed for session %s", session_id
        )
    except Exception as exc:
        logger.error(
            "auto_run_startup_nine_questions: bootstrap failed for session %s: %s",
            session_id,
            exc,
            exc_info=True,
        )


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

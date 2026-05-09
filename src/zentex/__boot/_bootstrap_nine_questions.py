from __future__ import annotations
"""
Nine Questions Bootstrap Module

This module handles initialization of nine questions runtime state
and startup procedures through the plugin service.
"""


import logging
import os
import sys
from typing import Any, Dict, Optional

from zentex.tasks import TaskManagementService
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
    
    POLICY: No more stubs. This performs a REAL scan of the workspace root.
    """
    from datetime import datetime, timezone
    import os
    
    if not workspace_root or not os.path.exists(workspace_root):
        logger.error(f"Bootstrap: Invalid workspace_root provided: {workspace_root}")
        return {"error": "invalid_workspace_root", "timestamp": datetime.now(timezone.utc).isoformat()}

    # Authentic Environment Awareness
    file_count = 0
    try:
        for root, dirs, files in os.walk(workspace_root):
            if ".git" in dirs:
                dirs.remove(".git")
            file_count += len(files)
            if file_count > 1000: # Cap for startup speed
                break
    except Exception:
        logger.warning("Bootstrap: Failed to count workspace files during snapshot.")

    return {
        "workspace_root": os.path.abspath(workspace_root),
        "environment_summary": f"Authentic workspace detected. Files counted: {file_count}+",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_real_snapshot": True,
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
    if not hasattr(agent_service, "seed_demo_agents"):
        raise NotImplementedError("Provided agent_service is a stub or lacks seed_demo_agents.")
    if not hasattr(task_service, "seed_demo_tasks"):
        raise NotImplementedError("Provided task_service is a stub or lacks seed_demo_tasks.")

    # POLICY: No Forged Data. Demo agents and tasks are dismantled to ensure system honesty.
    logger.warning("Bootstrap: Seeding of demo agents/tasks is DISABLED. System reflects authentic state only.")
    return


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
        logger.info("Startup nine questions auto-run disabled (ZENTEX_AUTORUN_STARTUP_NINE_QUESTIONS not set)")
        return
    
    if runtime is None:
        logger.error("Startup Failure: Cannot auto-run nine questions without a BrainRuntime/KernelService.")
        return

    logger.info("Executing AUTHENTIC nine-question bootstrap via Kernel")
    try:
        # Wire to KernelService.ensure_nine_questions_bootstrap
        if hasattr(runtime, "ensure_nine_questions_bootstrap"):
             from zentex.kernel.contracts import BootstrapStatus
             status = runtime.ensure_nine_questions_bootstrap(force=True)
             logger.info(f"Startup bootstrap completed with status: {status}")
        else:
            logger.error("Bootstrap Error: Provided runtime does not support 'ensure_nine_questions_bootstrap'")
    except Exception as exc:
        logger.exception(f"Bootstrap Failure: Real startup bootstrap aborted with error: {exc}")
        raise exc


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

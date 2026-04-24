from __future__ import annotations

import warnings
# Suppress pkg_resources deprecation warning from jieba
warnings.filterwarnings("ignore", category=UserWarning, module="jieba")

from pathlib import Path
import logging
import os
import asyncio
import traceback

from typing import Any, Dict, List, Optional, Union
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from zentex.plugins.service import WeightPluginAssembler
from zentex.agents.service import AgentCoordinationService
from zentex.common.plugin_registry import AbstractPluginRegistry
from zentex.foundation.specs.model_provider import (
    ModelProviderAuthError,
    ModelProviderConfigError,
    ModelProviderError,
    ModelProviderParseError,
    ModelProviderRateLimitError,
    ModelProviderTimeoutError,
)
from zentex.plugins.contracts import BasePluginSpec, PluginHealthStatus, PluginLifecycleStatus
from zentex.plugins.service import CognitiveToolRegistry
from zentex.tasks.service import TaskManagementService, TaskAutoLoopScheduler
from zentex.memory.service import build_default_episode_graph_adapter, get_memory_service
from zentex.memory.repair_scheduler import MemoryRepairScheduler
from zentex.audit.trace_store import AuditTraceStore
from zentex.upgrade.service import (
    UpgradeAuditStore,
    UpgradeEvidenceService,
    UpgradeExecutionService,
    UpgradeFacade,
    UpgradeManagementStore,
    UpgradeMemoryStore,
    PluginEvolutionRuntime,
    build_default_upgrade_runtime_components,
)
from zentex.web_console.contracts.plugins import ManagedPluginRecord
from zentex.web_console.router import api_router
from zentex.web_console.routers.environment import router as environment_router
from zentex.web_console.routers.learning_async import router as learning_async_router
from zentex.web_console.routers.reflection_async import router as reflection_async_router
from zentex.web_console.routers.supervision import router as supervision_router
from zentex.web_console.services.llm import compute_llm_status
from zentex.plugins.service.utils import build_managed_plugin_record


logger = logging.getLogger(__name__)


LLM_GUARDED_PREFIXES = (
    "/api/web/upgrades",
    "/api/web/nine-questions",
    "/api/web/reflections",
    "/api/reflection",
)


def _build_llm_error_detail(
    *,
    error_code: str,
    user_message: str,
    provider_name: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key_env: Optional[str] = None,
    reason: Optional[str] = None,
    missing_env: list[Optional[str]] = None,
    hint: Optional[str] = None,
    provider_error_type: Optional[str] = None,
    developer_message: Optional[str] = None,
) -> dict[str, object]:
    return {
        "error": "llm_unavailable",
        "error_code": error_code,
        "root_cause_hint": hint
        or "请检查模型 Provider 配置、API Key 环境变量与网关连通性。",
        "user_message": user_message,
        "provider_name": provider_name,
        "api_base": api_base,
        "api_key_env": api_key_env,
        "reason": reason,
        "missing_env": list(missing_env or []),
        "hint": hint,
        "provider_error_type": provider_error_type,
        "developer_message": developer_message,
    }


def _normalize_503_detail(detail: object, request: Request) -> dict[str, object]:
    default_hint = (
        "服务依赖未初始化或启动失败。请检查后端启动日志与 app_data/logs/startup_error.log。"
    )

    if isinstance(detail, dict):
        normalized = dict(detail)
        normalized.setdefault("error", "service_unavailable")
        normalized.setdefault("error_code", "service_unavailable")
        normalized.setdefault("root_cause_hint", normalized.get("hint") or default_hint)
        normalized.setdefault("path", request.url.path)
        return normalized

    message = str(detail) if detail is not None else "Service unavailable"
    return {
        "error": "service_unavailable",
        "error_code": "service_unavailable",
        "root_cause_hint": default_hint,
        "user_message": "当前服务暂时不可用，请稍后重试。",
        "developer_message": message,
        "path": request.url.path,
    }


def _is_active_model_provider_record(record: object) -> bool:
    lifecycle = getattr(record, "lifecycle_status", None)
    if lifecycle is None and isinstance(record, dict):
        lifecycle = record.get("lifecycle_status")
    lifecycle_value = str(getattr(lifecycle, "value", lifecycle) or "").strip().lower()
    if lifecycle_value != PluginLifecycleStatus.ACTIVE.value:
        return False

    feature_code = getattr(record, "feature_code", None)
    if feature_code is None and isinstance(record, dict):
        feature_code = record.get("feature_code")
    feature_code_value = str(feature_code or "").strip().lower()
    if feature_code_value.startswith("model_provider."):
        return True

    plugin = getattr(record, "plugin", None)
    if plugin is None and isinstance(record, dict):
        plugin = record.get("plugin")
    return bool(
        getattr(plugin, "provider_name", None)
        and getattr(plugin, "api_base", None)
        and getattr(plugin, "default_model", None)
    )


def _format_traceback(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def _looks_like_memory_service(candidate: object) -> bool:
    return all(
        hasattr(candidate, attr)
        for attr in (
            "remember",
            "list_managed_records",
            "recall",
            "get_health_snapshot",
        )
    )


def _extract_memory_service(candidate: object) -> Any:
    if _looks_like_memory_service(candidate):
        return candidate
    return None


def _set_app_state_if_present(app: FastAPI, **services: object) -> None:
    for key, value in services.items():
        if value is not None:
            setattr(app.state, key, value)


def _resolve_memory_service(
    *,
    memory_service: Any,
    runtime: Any,
) -> Any:
    resolved = _extract_memory_service(memory_service)
    if resolved is not None:
        return resolved
    runtime_memory_service = getattr(runtime, "memory_service", None) if runtime is not None else None
    resolved = _extract_memory_service(runtime_memory_service)
    if resolved is not None:
        return resolved
    return get_memory_service()


def _resolve_reflection_service(app: FastAPI) -> Any:
    return getattr(app.state, "reflection_service", None)


def _map_llm_exception(exc: ModelProviderError) -> tuple[int, dict[str, object]]:
    if isinstance(exc, ModelProviderAuthError):
        return 401, _build_llm_error_detail(
            error_code="llm_auth_error",
            user_message="大模型认证失败，请检查 API Key 或网关鉴权设置。",
            provider_error_type=exc.__class__.__name__,
            developer_message=str(exc),
        )
    if isinstance(exc, ModelProviderConfigError):
        return 503, _build_llm_error_detail(
            error_code="llm_config_error",
            user_message="大模型配置错误或缺少必要参数，请检查 provider 配置。",
            provider_error_type=exc.__class__.__name__,
            developer_message=str(exc),
        )
    if isinstance(exc, ModelProviderRateLimitError):
        return 429, _build_llm_error_detail(
            error_code="llm_rate_limited",
            user_message="大模型调用被限流，请稍后重试或检查额度。",
            provider_error_type=exc.__class__.__name__,
            developer_message=str(exc),
        )
    if isinstance(exc, ModelProviderTimeoutError):
        return 504, _build_llm_error_detail(
            error_code="llm_timeout",
            user_message="大模型调用超时或网络不可达，请检查网关连通性。",
            provider_error_type=exc.__class__.__name__,
            developer_message=str(exc),
        )
    if isinstance(exc, ModelProviderParseError):
        return 502, _build_llm_error_detail(
            error_code="llm_invalid_response",
            user_message="大模型返回了无效结构，当前推理已被强制阻断。",
            provider_error_type=exc.__class__.__name__,
            developer_message=str(exc),
        )
    return 502, _build_llm_error_detail(
        error_code="llm_remote_error",
        user_message="大模型调用失败，请检查 provider 服务状态。",
        provider_error_type=exc.__class__.__name__,
        developer_message=str(exc),
    )


def create_app(
    *,
    cognitive_tool_registry: Optional[CognitiveToolRegistry] = None,
    plugin_registry: AbstractPluginRegistry[Optional[object]] = None,
    weight_assembler: Optional[WeightPluginAssembler] = None,
    plugin_service: Any = None,  # SystemPluginService instance
    managed_plugin_records: dict[str, ManagedPluginRecord],  # REQUIRED - must be injected from bootstrap
    plugin_feature_catalog: list[PluginFeatureCatalogItem],  # REQUIRED - must be injected from bootstrap
    runtime: Any = None,
    session: Any = None,
    transcript_store: Any = None,
    agent_manager: Any = None,
    agent_coordination_service: Optional[AgentCoordinationService] = None,
    task_service: Optional[TaskManagementService] = None,
    upgrade_management_store: Optional[UpgradeManagementStore] = None,
    plugin_evolution_runtime: Optional[PluginEvolutionRuntime] = None,
    upgrade_audit_store: Optional[UpgradeAuditStore] = None,
    upgrade_memory_store: Optional[UpgradeMemoryStore] = None,
    upgrade_evidence_service: Optional[UpgradeEvidenceService] = None,
    upgrade_execution_service: Optional[UpgradeExecutionService] = None,
    memory_service: Any = None,
    cli_service: Any = None,
    mcp_service: Optional[object] = None,
    execution_registry: Optional[object] = None,
    simulation_engine: Any = None,
    interaction_mind_engine: Any = None,
    consolidation_engine: Any = None,
    reflection_service: Any = None,
    learning_service: Any = None,
    audit_service: Any = None,
) -> FastAPI:
    app = FastAPI(title="Zentex Web Console")
    # ========== Phase 0: Initialize DI Container ==========
    # Initialize WebConsoleContainer for new dependency injection layer
    # This provides access to new Facade contracts (SessionManager, etc.)
    from .di_container import WebConsoleContainer

    # Policy: Failure to initialize DI is catastrophic.
    WebConsoleContainer.initialize()
    logger.info("✓ WebConsoleContainer initialized successfully")

    @app.exception_handler(ModelProviderError)
    async def model_provider_error_handler(request: Request, exc: ModelProviderError):  # type: ignore[no-untyped-def]
        status_code, detail = _map_llm_exception(exc)
        return JSONResponse(status_code=status_code, content={"detail": detail})

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):  # type: ignore[no-untyped-def]
        tb = _format_traceback(exc)
        if exc.status_code == 503:
            detail = _normalize_503_detail(exc.detail, request)
            detail.setdefault("exception_type", type(exc).__name__)
            detail["full_traceback"] = tb
            logger.error(
                "HTTP 503 on %s %s: %s",
                request.method,
                request.url.path,
                detail.get("developer_message") or detail.get("user_message") or detail.get("error"),
            )
            return JSONResponse(
                status_code=503,
                content={"detail": detail},
                headers=exc.headers,
            )

        non503_detail: object
        if isinstance(exc.detail, dict):
            non503_detail = {
                **exc.detail,
                "exception_type": type(exc).__name__,
                "full_traceback": tb,
                "path": request.url.path,
            }
        else:
            non503_detail = {
                "error": "http_exception",
                "error_code": "http_exception",
                "message": str(exc.detail),
                "exception_type": type(exc).__name__,
                "full_traceback": tb,
                "path": request.url.path,
            }

        logger.error(
            "HTTP %s on %s %s: %s",
            exc.status_code,
            request.method,
            request.url.path,
            str(exc.detail),
            exc_info=True,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": non503_detail},
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):  # type: ignore[no-untyped-def]
        tb = _format_traceback(exc)
        logger.exception(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "error": "internal_server_error",
                    "error_code": "internal_server_error",
                    "message": str(exc),
                    "exception_type": type(exc).__name__,
                    "full_traceback": tb,
                    "path": request.url.path,
                }
            },
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _set_app_state_if_present(
        app,
        cognitive_tool_registry=cognitive_tool_registry,
        plugin_registry=plugin_registry,
        weight_assembler=weight_assembler,
        plugin_service=plugin_service,
    )

    # managed_plugin_records and plugin_feature_catalog MUST be provided by caller (fail-closed per Phase 6)
    # No auto-normalization or fallback allowed
    resolved_managed_plugin_records = dict(managed_plugin_records)
    for record in resolved_managed_plugin_records.values():
        plugin = getattr(record, "plugin", None)
        if _is_active_model_provider_record(record):
            app.state.active_model_provider = plugin
            break

    app.state.managed_plugin_records = resolved_managed_plugin_records
    app.state.managed_plugins = list(resolved_managed_plugin_records.values())
    app.state.plugin_feature_catalog = plugin_feature_catalog
    app.state.runtime = None  # Deprecated: Legacy BrainRuntime no longer supported
    resolved_audit_service = audit_service
    if resolved_audit_service is None:
        from zentex.audit.service import get_service as get_audit_service
        resolved_audit_service = get_audit_service()
    app.state.audit_service = resolved_audit_service
        
    # KuzuDB initialization moved to startup event for better performance
    app.state.kuzu_adapter = None 

    resolved_memory_service = _resolve_memory_service(
        memory_service=memory_service,
        runtime=runtime,
    )
    app.state.memory_service = resolved_memory_service
    _set_app_state_if_present(
        app,
        session=session,
        agent_manager=agent_manager,
        agent_coordination_service=agent_coordination_service,
        task_service=task_service,
    )
    if isinstance(upgrade_execution_service, UpgradeExecutionService):
        app.state.upgrade_execution_service = upgrade_execution_service
        app.state.upgrade_management_store = (
            upgrade_management_store
            if isinstance(upgrade_management_store, UpgradeManagementStore)
            else upgrade_execution_service.management_store
        )
        app.state.plugin_evolution_runtime = (
            plugin_evolution_runtime
            if isinstance(plugin_evolution_runtime, PluginEvolutionRuntime)
            else PluginEvolutionRuntime()
        )
        app.state.upgrade_evidence_service = (
            upgrade_evidence_service
            if isinstance(upgrade_evidence_service, UpgradeEvidenceService)
            else upgrade_execution_service.evidence_service
        )
        app.state.upgrade_audit_store = (
            upgrade_audit_store
            if isinstance(upgrade_audit_store, UpgradeAuditStore)
            else app.state.upgrade_evidence_service.audit_store
        )
        app.state.upgrade_memory_store = (
            upgrade_memory_store
            if isinstance(upgrade_memory_store, UpgradeMemoryStore)
            else app.state.upgrade_evidence_service.memory_store
        )
        if getattr(app.state.upgrade_evidence_service, "memory_service", None) is None:
            app.state.upgrade_evidence_service._memory_service = resolved_memory_service  # type: ignore[attr-defined]
    else:
        default_upgrade_components = build_default_upgrade_runtime_components(
            memory_service=resolved_memory_service
        )
        app.state.upgrade_management_store = (
            upgrade_management_store
            if isinstance(upgrade_management_store, UpgradeManagementStore)
            else default_upgrade_components.management_store
        )
        app.state.plugin_evolution_runtime = (
            plugin_evolution_runtime
            if isinstance(plugin_evolution_runtime, PluginEvolutionRuntime)
            else default_upgrade_components.plugin_runtime
        )
        app.state.upgrade_audit_store = (
            upgrade_audit_store
            if isinstance(upgrade_audit_store, UpgradeAuditStore)
            else default_upgrade_components.audit_store
        )
        app.state.upgrade_memory_store = (
            upgrade_memory_store
            if isinstance(upgrade_memory_store, UpgradeMemoryStore)
            else default_upgrade_components.memory_store
        )
        app.state.upgrade_evidence_service = (
            upgrade_evidence_service
            if isinstance(upgrade_evidence_service, UpgradeEvidenceService)
            else default_upgrade_components.evidence_service
        )
        app.state.upgrade_execution_service = UpgradeExecutionService(
            facade=UpgradeFacade(
                memory_service=resolved_memory_service,
            ),
            management_store=app.state.upgrade_management_store,
            plugin_runtime=app.state.plugin_evolution_runtime,
            evidence_service=app.state.upgrade_evidence_service,
        )
    if runtime is not None:
        # Backfill is deferred to a background thread to avoid blocking app
        # startup.  A concurrent background backfill is already started by
        # _bootstrap_runtime.py; _seen_projection_keys prevents duplicate
        # ingestion so running both is safe.
        _backfill_service = resolved_memory_service
        _backfill_entries = resolved_audit_service.list_recent_events()
        def _bg_transcript_backfill() -> None:
            try:
                _backfill_service.backfill_transcript_entries(_backfill_entries)
            except Exception:
                logger.exception("Startup transcript backfill (create_app) failed")
        import threading as _threading
        _threading.Thread(
            target=_bg_transcript_backfill,
            name="app-transcript-backfill",
            daemon=True,
        ).start()
    if isinstance(app.state.upgrade_memory_store, UpgradeMemoryStore):
        _upgrade_service = resolved_memory_service
        _upgrade_records = app.state.upgrade_memory_store.list_records()
        def _bg_upgrade_backfill() -> None:
            try:
                _upgrade_service.backfill_upgrade_memory_records(_upgrade_records)
            except Exception:
                logger.exception("Startup upgrade backfill (create_app) failed")
        import threading as _threading
        _threading.Thread(
            target=_bg_upgrade_backfill,
            name="app-upgrade-backfill",
            daemon=True,
        ).start()
    _set_app_state_if_present(
        app,
        cli_service=cli_service,
        mcp_service=mcp_service,
        execution_registry=execution_registry,
        simulation_engine=simulation_engine,
        interaction_mind_engine=interaction_mind_engine,
        consolidation_engine=consolidation_engine,
        reflection_service=reflection_service,
        learning_service=learning_service,
        audit_service=resolved_audit_service,
    )

    if task_service is not None:
        task_auto_loop_enabled = str(os.getenv("ZENTEX_TASK_AUTO_LOOP_ENABLED", "1")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        task_auto_loop_scheduler = TaskAutoLoopScheduler(
            task_service=task_service,
            interval_seconds=int(os.getenv("ZENTEX_TASK_AUTO_LOOP_INTERVAL_SECONDS", "15")),
            batch_size=int(os.getenv("ZENTEX_TASK_AUTO_LOOP_BATCH_SIZE", "50")),
            enabled=task_auto_loop_enabled,
        )
        app.state.task_auto_loop_scheduler = task_auto_loop_scheduler

        @app.on_event("startup")
        async def _start_task_auto_loop_scheduler() -> None:
            try:
                task_auto_loop_scheduler.start()
            except Exception as exc:
                logger.warning(f"Failed to start task auto loop scheduler: {exc}")

        @app.on_event("startup")
        async def _initialize_heavy_services() -> None:
            """Initialize KuzuDB and Memory Engine in the background."""
            # 1. Initialize KuzuDB
            cluster_mode = os.environ.get("ZENTEX_CLUSTER_MODE", "false").lower() == "true"
            if not cluster_mode:
                logger.info("Initializing KuzuDB graph client...")
                try:
                    kuzu_adapter = build_default_episode_graph_adapter()
                    app.state.kuzu_adapter = kuzu_adapter
                    # Attach to the single MemoryService facade.
                    if hasattr(app.state.memory_service, "bind_episodic_adapter"):
                        app.state.memory_service.bind_episodic_adapter(kuzu_adapter)
                    logger.info("✓ KuzuDB initialized and attached to Memory Service")
                except Exception as exc:
                    logger.warning(
                        "KuzuDB graph client unavailable; continuing without episodic graph adapter: %s",
                        exc,
                    )

            # 2. Trigger Memory Engine background initialization
            if hasattr(app.state.memory_service, "initialize_background"):
                # Run this as a separate task so it doesn't block other startup events
                asyncio.create_task(app.state.memory_service.initialize_background())

        @app.on_event("shutdown")
        async def _stop_task_auto_loop_scheduler() -> None:
            task_auto_loop_scheduler.stop()

    if runtime is not None:
        from zentex.reflection.nine_question_scheduler import NineQuestionReflectionScheduler

        resolved_reflection_service = _resolve_reflection_service(app)
        if resolved_reflection_service is not None:
            scheduler = NineQuestionReflectionScheduler(
                runtime=runtime,
                reflection_service=resolved_reflection_service,
                upgrade_execution_service=getattr(app.state, "upgrade_execution_service", None),
                interval_seconds=3600,
            )
            app.state.nine_question_reflection_scheduler = scheduler

            @app.on_event("startup")
            async def _start_nine_question_reflection_scheduler() -> None:
                try:
                    scheduler.start()
                except Exception as exc:
                    logger.warning(f"Failed to start nine-question reflection scheduler: {exc}")

            @app.on_event("shutdown")
            async def _stop_nine_question_reflection_scheduler() -> None:
                try:
                    scheduler.stop()
                except Exception as exc:
                    logger.warning(f"Failed to stop nine-question reflection scheduler: {exc}")
        else:
            logger.info("Skipping nine-question reflection scheduler: reflection_service not provided")

    memory_service_state = getattr(app.state, "memory_service", None)
    if memory_service_state is not None:
        memory_repair_scheduler = MemoryRepairScheduler(
            memory_service=memory_service_state,
            interval_seconds=int(os.getenv("ZENTEX_MEMORY_REPAIR_INTERVAL_SECONDS", "3600")),
            enabled=str(os.getenv("ZENTEX_MEMORY_REPAIR_ENABLED", "1")).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            },
        )
        app.state.memory_repair_scheduler = memory_repair_scheduler

        @app.on_event("startup")
        async def _start_memory_repair_scheduler() -> None:
            try:
                memory_repair_scheduler.start()
            except Exception as exc:
                logger.warning(f"Failed to start memory repair scheduler: {exc}")

        @app.on_event("shutdown")
        async def _stop_memory_repair_scheduler() -> None:
            try:
                memory_repair_scheduler.stop()
            except Exception as exc:
                logger.warning(f"Failed to stop memory repair scheduler: {exc}")

    # Paths that are LLM-guarded but have specific sub-paths excluded from the guard
    # (operational actions that don't require LLM — cancel, cleanup, etc.)
    LLM_GUARD_EXCEPTIONS = (
        "/api/web/upgrades/llm/execute",
        "/api/web/upgrades/plugins/execute",
    )

    @app.middleware("http")
    async def llm_disable_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Health endpoint is always allowed
        if request.url.path.startswith("/api/web/health"):
            return await call_next(request)

        if request.url.path.startswith("/api/web") and request.method.upper() in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            path = request.url.path
            # Only guard paths in LLM_GUARDED_PREFIXES but exclude specific operational sub-paths
            is_guarded = any(path.startswith(prefix) for prefix in LLM_GUARDED_PREFIXES)
            # For upgrades, only execute endpoints require LLM
            if path.startswith("/api/web/upgrades") and not any(path.startswith(ex) for ex in LLM_GUARD_EXCEPTIONS):
                is_guarded = False
            if not is_guarded:
                return await call_next(request)
            status = compute_llm_status(request)
            if not status.available:
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": _build_llm_error_detail(
                            error_code="llm_missing_credentials"
                            if status.reason == "missing_credentials"
                            else "llm_not_configured",
                            user_message=(
                                "大模型配置错误或 API Key 缺失，请检查设置。"
                                if status.reason == "missing_credentials"
                                else "当前没有可用的大模型 Provider，相关操作已被阻断。"
                            ),
                            provider_name=status.provider_name,
                            api_base=status.api_base,
                            api_key_env=status.api_key_env,
                            reason=status.reason,
                            missing_env=status.missing_env,
                            hint=status.hint,
                        )
                    },
                )
        return await call_next(request)

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict:  # type: ignore[no-untyped-def]
        """Full health check including mandatory service validation.
        
        Standard Redline:
        - Fail-Closed: If core services are uninitialized, the status must reflect
          this as unhealthy rather than a static "ok".
        """
        is_healthy = all([
            hasattr(app.state, "memory_service"),
            hasattr(app.state, "active_model_provider"),
            app.state.kuzu_adapter is not None,
            getattr(app.state, "task_auto_loop_scheduler", None) is not None,
        ])
        
        status = "ok" if is_healthy else "unhealthy"
        return {
            "status": status,
            "service": "Zentex Web Console",
            "details": {
                "memory_engine": "online" if hasattr(app.state, "memory_service") else "offline",
                "model_provider": "online" if hasattr(app.state, "active_model_provider") else "offline",
                "graph_memory": "online" if app.state.kuzu_adapter else "offline",
                "scheduler": "online" if getattr(app.state, "task_auto_loop_scheduler", None) else "offline",
            }
        }

    app.include_router(api_router)
    app.include_router(supervision_router)
    app.include_router(environment_router)
    app.include_router(learning_async_router)
    app.include_router(reflection_async_router)
    return app

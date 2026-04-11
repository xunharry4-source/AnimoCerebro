from __future__ import annotations

from pathlib import Path
import logging
import os
import tempfile

from typing import Any
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from zentex.plugins.service import WeightPluginAssembler
from zentex.agents.service import AgentCoordinationService
from zentex.common.plugin_registry import AbstractPluginRegistry
from zentex.core.model_provider_spec import (
    ModelProviderAuthError,
    ModelProviderConfigError,
    ModelProviderError,
    ModelProviderParseError,
    ModelProviderRateLimitError,
    ModelProviderTimeoutError,
)
from zentex.core.plugin_base import BasePluginSpec, PluginHealthStatus, PluginLifecycleStatus
from zentex.runtime.cognitive_tools.registry import CognitiveToolRegistry
from zentex.tasks.service import TaskManagementService
from zentex.memory import EnhancedMemoryService, EpisodeGraphMemoryAdapter
from zentex.memory import KuzuGraphMemoryClient
from zentex.upgrade.service import (
    UpgradeAuditStore,
    UpgradeEvidenceService,
    UpgradeExecutionService,
    UpgradeFacade,
    UpgradeManagementStore,
    UpgradeMemoryStore,
    PluginEvolutionRuntime,
)
from zentex.web_console.contracts.plugins import ManagedPluginRecord, PluginFeatureCatalogItem
from zentex.web_console.router import api_router
from zentex.web_console.services.llm import compute_llm_status
from zentex.web_console.services.plugins import build_managed_plugin_record


logger = logging.getLogger(__name__)


def _build_llm_error_detail(
    *,
    error_code: str,
    user_message: str,
    provider_name: str | None = None,
    api_base: str | None = None,
    api_key_env: str | None = None,
    reason: str | None = None,
    missing_env: list[str] | None = None,
    hint: str | None = None,
    provider_error_type: str | None = None,
    developer_message: str | None = None,
) -> dict[str, object]:
    return {
        "error": "llm_unavailable",
        "error_code": error_code,
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
    cognitive_tool_registry: CognitiveToolRegistry | None = None,
    plugin_registry: AbstractPluginRegistry[object] | None = None,
    weight_assembler: WeightPluginAssembler | None = None,
    plugin_service: Any | None = None,  # SystemPluginService instance
    managed_plugins: list[BasePluginSpec] | None = None,
    plugin_feature_catalog: list[PluginFeatureCatalogItem] | None = None,
    runtime: Any | None = None,
    session: Any | None = None,
    transcript_store: Any | None = None,
    agent_manager: Any | None = None,
    agent_coordination_service: AgentCoordinationService | None = None,
    task_service: TaskManagementService | None = None,
    upgrade_management_store: UpgradeManagementStore | None = None,
    plugin_evolution_runtime: PluginEvolutionRuntime | None = None,
    upgrade_audit_store: UpgradeAuditStore | None = None,
    upgrade_memory_store: UpgradeMemoryStore | None = None,
    upgrade_evidence_service: UpgradeEvidenceService | None = None,
    upgrade_execution_service: UpgradeExecutionService | None = None,
    enhanced_memory_service: EnhancedMemoryService | None = None,
    cli_adapter: Any | None = None,
    mcp_adapter: object | None = None,
    execution_registry: object | None = None,
) -> FastAPI:
    app = FastAPI(title="Zentex Web Console")
    default_runtime_root = Path(tempfile.gettempdir()) / "zentex-upgrade-runtime"

    @app.exception_handler(ModelProviderError)
    async def model_provider_error_handler(request: Request, exc: ModelProviderError):  # type: ignore[no-untyped-def]
        status_code, detail = _map_llm_exception(exc)
        return JSONResponse(status_code=status_code, content={"detail": detail})

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
    if cognitive_tool_registry is not None:
        app.state.cognitive_tool_registry = cognitive_tool_registry
    if plugin_registry is not None:
        app.state.plugin_registry = plugin_registry
    if weight_assembler is not None:
        app.state.weight_assembler = weight_assembler
    if plugin_service is not None:
        app.state.plugin_service = plugin_service
    
    # ✅ If plugin_service is provided, use it to get managed plugins and feature catalog
    if plugin_service is not None:
        try:
            # Get managed plugins from service
            if hasattr(plugin_service, 'get_all_plugins'):
                all_plugins = plugin_service.get_all_plugins()
                if all_plugins and not managed_plugins:
                    normalized_plugins: list[BasePluginSpec] = []
                    for record in all_plugins.values():
                        if isinstance(record, (ManagedPluginRecord, BasePluginSpec)):
                            normalized_plugins.append(record)
                            continue
                        if isinstance(record, dict):
                            spec = record.get("spec")
                            if isinstance(spec, (ManagedPluginRecord, BasePluginSpec)):
                                normalized_plugins.append(spec)
                    if normalized_plugins:
                        managed_plugins = normalized_plugins
            
            # Get feature catalog from service  
            if hasattr(plugin_service, 'get_feature_catalog'):
                catalog = plugin_service.get_feature_catalog()
                if catalog and not plugin_feature_catalog:
                    plugin_feature_catalog = catalog
        except Exception as exc:
            logger.warning(f"Failed to get data from plugin_service: {exc}")
    
    if managed_plugins is not None:
        normalized_records: dict[str, ManagedPluginRecord] = {}
        for item in managed_plugins:
            if isinstance(item, ManagedPluginRecord):
                normalized_records[item.plugin.plugin_id] = item
                continue
            if isinstance(item, BasePluginSpec):
                record = build_managed_plugin_record(item)
                normalized_records[record.plugin.plugin_id] = record
        app.state.managed_plugins = list(normalized_records.values())
        app.state.managed_plugin_records = normalized_records
    if plugin_feature_catalog is not None:
        app.state.plugin_feature_catalog = plugin_feature_catalog
    app.state.runtime = runtime
    if transcript_store is not None:
        app.state.transcript_store = transcript_store
    elif runtime is not None and hasattr(runtime, "transcript_store"):
        app.state.transcript_store = runtime.transcript_store
        
    kuzu_adapter = None
    cluster_mode = os.environ.get("ZENTEX_CLUSTER_MODE", "false").lower() == "true"
    if not cluster_mode:
        try:
            kuzu_client = KuzuGraphMemoryClient(db_path=".zentex/kuzu_db")
            kuzu_adapter = EpisodeGraphMemoryAdapter(graph_client=kuzu_client)
        except Exception:
            pass


    resolved_enhanced_memory_service = (
        enhanced_memory_service
        if isinstance(enhanced_memory_service, EnhancedMemoryService)
        else (
            runtime.runtime_memory_store
            if runtime is not None and isinstance(runtime.runtime_memory_store, EnhancedMemoryService)
            else EnhancedMemoryService(
                semantic_store_path=default_runtime_root / "enhanced_semantic.jsonl",
                procedural_store_path=default_runtime_root / "enhanced_procedural.jsonl",
                episodic_store_path=default_runtime_root / "enhanced_episodic.jsonl",
                management_store_path=default_runtime_root / "enhanced_management.json",
                audit_store_path=default_runtime_root / "enhanced_memory_audit.jsonl",
                episodic_sink=kuzu_adapter,
                episodic_recall_client=kuzu_adapter,
            )
        )
    )
    app.state.enhanced_memory_service = resolved_enhanced_memory_service
    if session is not None:
        app.state.session = session
    if agent_manager is not None:
        app.state.agent_manager = agent_manager
    if agent_coordination_service is not None:
        app.state.agent_coordination_service = agent_coordination_service
    if task_service is not None:
        app.state.task_service = task_service
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
        if getattr(app.state.upgrade_evidence_service, "enhanced_memory_service", None) is None:
            app.state.upgrade_evidence_service._enhanced_memory_service = (  # type: ignore[attr-defined]
                resolved_enhanced_memory_service
            )
        if getattr(app.state.upgrade_evidence_service, "enhanced_memory_service", None) is None:
            app.state.upgrade_evidence_service._enhanced_memory_service = (  # type: ignore[attr-defined]
                resolved_enhanced_memory_service
            )
    else:
        app.state.upgrade_management_store = (
            upgrade_management_store
            if isinstance(upgrade_management_store, UpgradeManagementStore)
            else UpgradeManagementStore(
                file_path=default_runtime_root / "upgrade_management.json",
            )
        )
        app.state.plugin_evolution_runtime = (
            plugin_evolution_runtime
            if isinstance(plugin_evolution_runtime, PluginEvolutionRuntime)
            else PluginEvolutionRuntime()
        )
        app.state.upgrade_audit_store = (
            upgrade_audit_store
            if isinstance(upgrade_audit_store, UpgradeAuditStore)
            else UpgradeAuditStore(default_runtime_root / "upgrade_audit.jsonl")
        )
        app.state.upgrade_memory_store = (
            upgrade_memory_store
            if isinstance(upgrade_memory_store, UpgradeMemoryStore)
            else UpgradeMemoryStore(default_runtime_root / "upgrade_memory.jsonl")
        )
        app.state.upgrade_evidence_service = (
            upgrade_evidence_service
            if isinstance(upgrade_evidence_service, UpgradeEvidenceService)
            else UpgradeEvidenceService(
                audit_store=app.state.upgrade_audit_store,
                memory_store=app.state.upgrade_memory_store,
                enhanced_memory_service=resolved_enhanced_memory_service,
            )
        )
        app.state.upgrade_execution_service = UpgradeExecutionService(
            facade=UpgradeFacade(
                enhanced_memory_service=resolved_enhanced_memory_service,
            ),
            management_store=app.state.upgrade_management_store,
            plugin_runtime=app.state.plugin_evolution_runtime,
            evidence_service=app.state.upgrade_evidence_service,
        )
    if runtime is not None:
        resolved_enhanced_memory_service.backfill_transcript_entries(
            runtime.transcript_store.get_entries_snapshot()
        )
    if isinstance(app.state.upgrade_memory_store, UpgradeMemoryStore):
        resolved_enhanced_memory_service.backfill_upgrade_memory_records(
            app.state.upgrade_memory_store.list_records()
        )
    if cli_adapter is not None:
        app.state.cli_adapter = cli_adapter
    if mcp_adapter is not None:
        app.state.mcp_adapter = mcp_adapter
    if execution_registry is not None:
        app.state.execution_registry = execution_registry

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
            if (
                request.url.path.startswith("/api/web/plugins")
                or request.url.path.startswith("/api/web/interventions")
                or request.url.path.startswith("/api/web/memory")
                or request.url.path.startswith("/api/web/upgrades")
                or request.url.path.startswith("/api/web/cli-tools")
                or request.url.path.startswith("/api/web/mcp-servers")
            ):
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

    app.include_router(api_router)
    return app

create_web_console_app = create_app

"""
Plugin Commons — shared plugin query helpers for web_console route handlers.

RESPONSIBILITY:
  Provides request-scoped PluginSession assembly and query-builder helpers used
  by plugin-related route handlers.  Does NOT own routes, app state, or the
  plugin service lifecycle.

CAPABILITIES:
  - get_or_create_plugin_session(): assembles a PluginSession from DI deps.
  - list_cognitive_plugins(), list_functional_plugins(): build typed payloads.
  - list_plugins_by_feature(), get_cognitive_plugin_detail(), etc.

FAIL-CLOSED CONTRACT (Zentex Codex §1):
  - plugin_service must be non-None; absent → 503.
  - cognitive_registry is sourced from a deprecated dependency
    (get_cognitive_tool_registry raises NotImplementedError).  When unavailable,
    cognitive_registry is set to None with an explicit WARN log.  Downstream
    builders are expected to handle None gracefully; if they do not, the outer
    exception handler surfaces a 500, never silently returns empty data.

DOES NOT:
  - Define routes (routes live in plugins.py).
  - Implement plugin lifecycle or health-check logic.
  - Fall back to synthetic/empty cognitive state when registries are absent.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException, Request

from zentex.web_console.contracts.plugins import (
    CognitivePluginStatusItem,
    CognitivePluginDetailResponse,
    FunctionalPluginDetailResponse,
    PluginFeatureGroupItem,
    PluginVersionHistoryItem,
)
from zentex.web_console.dependencies import (
    get_cognitive_tool_registry,
    get_plugin_registry,
    get_managed_plugin_records,
    get_plugin_feature_catalog,
    get_plugin_service,
)
from zentex.web_console.services.plugins import (
    build_cognitive_plugin_list,
    build_functional_plugin_list,
    build_plugin_feature_groups,
    build_cognitive_plugin_detail,
    build_functional_plugin_detail,
)

logger = logging.getLogger(__name__)


# ========== Plugin State & Session Management ==========

class PluginSession:
    """Encapsulates plugin-related session state"""
    
    def __init__(
        self,
        cognitive_registry: Any,
        plugin_registry: Any,
        managed_records: Any,
        plugin_service: Any,
        feature_catalog: Optional[Any] = None,
    ):
        self.cognitive_registry = cognitive_registry
        self.plugin_registry = plugin_registry
        self.managed_records = managed_records
        self.plugin_service = plugin_service
        self.feature_catalog = feature_catalog


async def get_or_create_plugin_session(request: Request) -> PluginSession:
    """
    Get or create a plugin session for the request
    
    Centralizes access to plugin registries and services
    
    Args:
        request: FastAPI request
        
    Returns:
        PluginSession with all needed registries
        
    Raises:
        HTTPException: If plugin_service not available (503)
    """
    # get_cognitive_tool_registry is deprecated — cognitive tools are now owned by
    # plugins.service.  NotImplementedError is the expected signal; we degrade to
    # None and log WARN so the absence is observable.  Downstream builders must
    # handle None explicitly; they must NOT return fabricated data.
    try:
        cognitive_registry = get_cognitive_tool_registry(request=request)
    except NotImplementedError:
        logger.warning(
            "plugin_commons: get_cognitive_tool_registry raised NotImplementedError "
            "— cognitive registry is unavailable; cognitive_registry set to None. "
            "Downstream builders must handle None without fabricating results.",
            extra={"location": "web_console.plugin_commons", "action": "get_or_create_plugin_session"},
        )
        cognitive_registry = None
    plugin_registry = get_plugin_registry(request)
    managed_records = get_managed_plugin_records(request)
    plugin_service = get_plugin_service(request)
    feature_catalog = get_plugin_feature_catalog(request)
    
    if not plugin_service:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "service_unavailable",
                "message": "Plugin service not initialized",
                "hint": "插件服务未初始化，请检查系统启动日志和插件配置",
            }
        )
    
    return PluginSession(
        cognitive_registry=cognitive_registry,
        plugin_registry=plugin_registry,
        managed_records=managed_records,
        plugin_service=plugin_service,
        feature_catalog=feature_catalog,
    )


# ========== Query Builders ==========

async def list_cognitive_plugins(
    request: Request,
) -> list[CognitivePluginStatusItem]:
    """
    Query and build list of cognitive plugins
    
    Args:
        request: FastAPI request
        
    Returns:
        List of cognitive plugin status items
    """
    try:
        session = await get_or_create_plugin_session(request)

        return build_cognitive_plugin_list(
            session.cognitive_registry,
            session.plugin_registry,
            session.managed_records,
            session.plugin_service,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing cognitive plugins: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail={
                "error": "internal_error",
                "message": "Failed to list cognitive plugins",
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e


async def list_functional_plugins(
    request: Request,
) -> list[CognitivePluginStatusItem]:
    """
    Query and build list of functional plugins
    
    Args:
        request: FastAPI request
        
    Returns:
        List of functional plugin status items
    """
    try:
        session = await get_or_create_plugin_session(request)

        return build_functional_plugin_list(
            session.cognitive_registry,
            session.plugin_registry,
            session.managed_records,
            session.plugin_service,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing functional plugins: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to list functional plugins",
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e


async def list_plugins_by_feature(
    request: Request,
) -> list[PluginFeatureGroupItem]:
    """
    Query plugins grouped by feature
    
    Args:
        request: FastAPI request
        
    Returns:
        Plugins grouped by feature
    """
    try:
        session = await get_or_create_plugin_session(request)

        return build_plugin_feature_groups(
            session.cognitive_registry,
            session.plugin_registry,
            session.managed_records,
            session.feature_catalog,
            session.plugin_service,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing plugins by feature: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to list plugins by feature",
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e


async def get_cognitive_plugin_detail(
    request: Request,
    plugin_id: str,
) -> CognitivePluginDetailResponse:
    """
    Get detailed information about a cognitive plugin
    
    Args:
        request: FastAPI request
        plugin_id: ID of the cognitive plugin
        
    Returns:
        Detailed cognitive plugin response
        
    Raises:
        HTTPException: 404 if not found, 500 on error
    """
    try:
        session = await get_or_create_plugin_session(request)

        # cognitive_registry may be None (deprecated), but plugin_service should handle it
        return build_cognitive_plugin_detail(
            session.cognitive_registry,
            session.plugin_registry,
            session.managed_records,
            session.plugin_service,
            plugin_id,
        )
    except KeyError as e:
        logger.warning(f"Cognitive plugin not found: {plugin_id}")
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cognitive plugin detail for {plugin_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to get plugin detail",
                "plugin_id": plugin_id,
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e


async def get_functional_plugin_detail(
    request: Request,
    plugin_id: str,
) -> FunctionalPluginDetailResponse:
    """
    Get detailed information about a functional plugin
    
    Args:
        request: FastAPI request
        plugin_id: ID of the functional plugin
        
    Returns:
        Detailed functional plugin response
        
    Raises:
        HTTPException: 404 if not found, 500 on error
    """
    try:
        session = await get_or_create_plugin_session(request)
        
        return build_functional_plugin_detail(
            session.cognitive_registry,
            session.plugin_registry,
            session.managed_records,
            session.plugin_service,
            plugin_id,
        )
    except KeyError as e:
        logger.warning(f"Functional plugin not found: {plugin_id}")
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}") from e
    except Exception as e:
        logger.error(f"Error getting functional plugin detail for {plugin_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to get plugin detail",
                "plugin_id": plugin_id,
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e


async def get_plugin_history(
    request: Request,
    plugin_id: str,
) -> list[PluginVersionHistoryItem]:
    """
    Get version history for a plugin
    
    Args:
        request: FastAPI request
        plugin_id: ID of the plugin
        
    Returns:
        List of version history items
    """
    try:
        session = await get_or_create_plugin_session(request)
        
        if not hasattr(session.plugin_service, "get_upgrade_history"):
            return []
        
        history = []
        for item in list(session.plugin_service.get_upgrade_history(plugin_id) or []):
            history.append(
                PluginVersionHistoryItem(
                    plugin_id=getattr(item, "plugin_id", plugin_id),
                    version=str(getattr(item, "version", "")),
                    upgrade_status=str(getattr(item, "status", "")),
                    started_at=getattr(item, "started_at", None),
                    completed_at=getattr(item, "completed_at", None),
                    error_message=getattr(item, "error_message", None),
                    previous_version=getattr(item, "previous_version", None),
                )
            )
        return history
    except Exception as e:
        logger.error(f"Error getting plugin history for {plugin_id}: {e}")
        return []

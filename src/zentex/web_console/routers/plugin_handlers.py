"""Plugin Handlers - Plugin-Specific Operations

Handles bind, unbind, test, force-enable/disable, and delete operations for plugins.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request

from zentex.web_console.contracts.plugins import (
    CognitivePluginStatusItem,
    CognitivePluginDetailResponse,
    ForceEnablePluginResponse,
    PluginTestResponse,
    PluginRelationActionRequest,
    PluginActionRequest,
)
from zentex.web_console.routers.plugin_commons import (
    get_or_create_plugin_session,
    get_cognitive_plugin_detail,
)
from zentex.web_console.services.plugins import (
    build_force_enable_response,
    force_enable_managed_plugin,
    force_disable_managed_plugin,
    run_managed_plugin_test,
)

logger = logging.getLogger(__name__)


# ========== Plugin Relationship Operations ==========

async def bind_functional_to_cognitive(
    request: Request,
    cognitive_plugin_id: str,
    functional_plugin_id: str,
    payload: PluginRelationActionRequest,
) -> CognitivePluginDetailResponse:
    """
    Bind a functional plugin to a cognitive plugin
    
    Args:
        request: FastAPI request
        cognitive_plugin_id: ID of cognitive plugin
        functional_plugin_id: ID of functional plugin
        payload: Binding configuration (role, priority, fallback)
        
    Returns:
        Updated cognitive plugin detail
        
    Raises:
        HTTPException: On bind failure or plugin not found
    """
    try:
        session = await get_or_create_plugin_session(request)
        
        # Perform the binding
        session.plugin_service.bind_cognitive_functional(
            cognitive_plugin_id=cognitive_plugin_id,
            functional_plugin_id=functional_plugin_id,
            role=payload.role,
            priority=payload.priority,
            fallback_id=payload.fallback_id,
        )
        
        logger.info(
            f"Bound {functional_plugin_id} to {cognitive_plugin_id} "
            f"with role={payload.role}"
        )
        
        # Return updated detail
        return await get_cognitive_plugin_detail(request, cognitive_plugin_id)
        
    except KeyError as e:
        logger.warning(f"Plugin not found during bind: {e}")
        raise HTTPException(status_code=404, detail=f"Plugin not found: {e}") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error binding plugins: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to bind plugins",
                "cognitive_plugin_id": cognitive_plugin_id,
                "functional_plugin_id": functional_plugin_id,
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e


async def unbind_functional_from_cognitive(
    request: Request,
    cognitive_plugin_id: str,
    functional_plugin_id: str,
    payload: PluginRelationActionRequest,
) -> CognitivePluginDetailResponse:
    """
    Unbind a functional plugin from a cognitive plugin
    
    Args:
        request: FastAPI request
        cognitive_plugin_id: ID of cognitive plugin
        functional_plugin_id: ID of functional plugin
        payload: Additional context (ignored, kept for API compatibility)
        
    Returns:
        Updated cognitive plugin detail
        
    Raises:
        HTTPException: On unbind failure or plugin not found
    """
    try:
        session = await get_or_create_plugin_session(request)
        
        # Perform the unbinding
        session.plugin_service.unbind_cognitive_functional(
            cognitive_plugin_id,
            functional_plugin_id,
        )
        
        logger.info(f"Unbound {functional_plugin_id} from {cognitive_plugin_id}")
        
        # Return updated detail
        return await get_cognitive_plugin_detail(request, cognitive_plugin_id)
        
    except KeyError as e:
        logger.warning(f"Plugin not found during unbind: {e}")
        raise HTTPException(status_code=404, detail=f"Plugin not found: {e}") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unbinding plugins: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to unbind plugins",
                "cognitive_plugin_id": cognitive_plugin_id,
                "functional_plugin_id": functional_plugin_id,
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e


# ========== Plugin Testing & Execution ==========

async def test_functional_plugin(
    request: Request,
    cognitive_plugin_id: str,
    functional_plugin_id: str,
    payload: PluginTestRequest,
) -> PluginTestResponse:
    """
    Test a functional plugin in the context of a cognitive plugin
    
    Args:
        request: FastAPI request
        cognitive_plugin_id: ID of cognitive plugin context
        functional_plugin_id: ID of functional plugin to test
        payload: Test input/mock data
        
    Returns:
        Test execution result
        
    Raises:
        HTTPException: On test failure or plugin not found
    """
    try:
        session = await get_or_create_plugin_session(request)
        
        # Run the test through plugin service
        result = run_managed_plugin_test(
            plugin_service=session.plugin_service,
            plugin_id=functional_plugin_id,
            test_payload=payload.model_dump() if payload else {},
        )
        
        logger.info(
            f"Tested {functional_plugin_id} in context of {cognitive_plugin_id}: "
            f"status={result.get('status', 'unknown')}"
        )
        
        return PluginTestResponse(
            plugin_id=functional_plugin_id,
            ok=result.get("status", "passed") == "passed",
            details=result,
        )
        
    except KeyError as e:
        logger.warning(f"Plugin not found during test: {e}")
        raise HTTPException(status_code=404, detail=f"Plugin not found: {e}") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing plugin: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Plugin test failed",
                "plugin_id": functional_plugin_id,
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e


async def test_plugin(
    request: Request,
    plugin_id: str,
    payload: PluginTestRequest,
) -> PluginTestResponse:
    """
    Test a plugin directly
    
    Args:
        request: FastAPI request
        plugin_id: ID of plugin to test
        payload: Test input/mock data
        
    Returns:
        Test execution result
        
    Raises:
        HTTPException: On test failure or plugin not found
    """
    try:
        session = await get_or_create_plugin_session(request)
        
        # Run the test through plugin service
        result = run_managed_plugin_test(
            plugin_service=session.plugin_service,
            plugin_id=plugin_id,
            test_payload=payload.model_dump() if payload else {},
        )

        ok = result.get("status", "failed") == "passed"
        logger.info(f"Tested {plugin_id}: ok={ok}")

        return PluginTestResponse(
            plugin_id=plugin_id,
            ok=ok,
            details=result,
        )
        
    except KeyError as e:
        logger.warning(f"Plugin not found during test: {e}")
        raise HTTPException(status_code=404, detail=f"Plugin not found: {e}") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing plugin: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Plugin test failed",
                "plugin_id": plugin_id,
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e


# ========== Plugin State Management ==========

async def force_enable_plugin(
    request: Request,
    plugin_id: str,
    payload: PluginActionRequest,
) -> ForceEnablePluginResponse:
    """
    Force enable a plugin (bypass normal activation rules)
    
    Args:
        request: FastAPI request
        plugin_id: ID of plugin to enable
        payload: Action context
        
    Returns:
        Force enable response with status
        
    Raises:
        HTTPException: On operation failure
    """
    try:
        session = await get_or_create_plugin_session(request)
        
        # Check if plugin can be forced enabled
        try:
            detail = await get_cognitive_plugin_detail(request, plugin_id)
            if not detail.can_force_enable:
                raise HTTPException(
                    status_code=400,
                    detail=f"Plugin {plugin_id} cannot be force enabled"
                )
        except HTTPException:
            raise
        
        # Perform force enable
        force_enable_managed_plugin(
            plugin_service=session.plugin_service,
            plugin_id=plugin_id,
        )
        
        logger.info(f"Force enabled plugin: {plugin_id}")
        
        return build_force_enable_response(
            plugin_service=session.plugin_service,
            plugin_id=plugin_id,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error force enabling plugin {plugin_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to force enable plugin",
                "plugin_id": plugin_id,
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e


async def force_disable_plugin(
    request: Request,
    plugin_id: str,
) -> CognitivePluginStatusItem:
    """
    Force disable a plugin (stop execution immediately)
    
    Args:
        request: FastAPI request
        plugin_id: ID of plugin to disable
        
    Returns:
        Updated plugin status
        
    Raises:
        HTTPException: On operation failure
    """
    try:
        session = await get_or_create_plugin_session(request)
        
        # Check if plugin can be force disabled
        try:
            detail = await get_cognitive_plugin_detail(request, plugin_id)
            if not detail.can_force_disable:
                raise HTTPException(
                    status_code=400,
                    detail=f"Plugin {plugin_id} cannot be force disabled"
                )
        except HTTPException:
            raise
        
        # Perform force disable
        force_disable_managed_plugin(
            plugin_service=session.plugin_service,
            plugin_id=plugin_id,
        )
        
        logger.info(f"Force disabled plugin: {plugin_id}")
        
        # Return updated status
        return await get_cognitive_plugin_detail(request, plugin_id)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error force disabling plugin {plugin_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to force disable plugin",
                "plugin_id": plugin_id,
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e


async def delete_plugin(
    request: Request,
    plugin_id: str,
) -> dict[str, Any]:
    """
    Delete a plugin (remove from system)
    
    Args:
        request: FastAPI request
        plugin_id: ID of plugin to delete
        
    Returns:
        Deletion confirmation
        
    Raises:
        HTTPException: If plugin cannot be deleted
    """
    try:
        session = await get_or_create_plugin_session(request)
        
        # Check if plugin can be deleted
        try:
            detail = await get_cognitive_plugin_detail(request, plugin_id)
            if not detail.can_delete:
                raise HTTPException(
                    status_code=400,
                    detail=f"Plugin {plugin_id} cannot be deleted"
                )
        except HTTPException:
            raise
        
        # Perform deletion
        if hasattr(session.plugin_service, "delete_plugin"):
            session.plugin_service.delete_plugin(plugin_id)
        else:
            logger.warning(f"Plugin service does not support delete operation for {plugin_id}")
            raise HTTPException(
                status_code=501,
                detail="Delete operation not supported"
            )
        
        logger.info(f"Deleted plugin: {plugin_id}")
        
        return {
            "status": "deleted",
            "plugin_id": plugin_id,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting plugin {plugin_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to delete plugin",
                "plugin_id": plugin_id,
                "exception_type": type(e).__name__,
                "exception_message": str(e),
            }
        ) from e

"""Plugin Routes v2 - Refactored with Facade-First Design

⚠️  MODULARIZATION CONSTRAINT - MAX 200 LINES
════════════════════════════════════════════════════════════════════
This module MUST NOT exceed 200 lines. All business logic extracted to:
  - plugin_commons.py: Shared plugin queries
  - plugin_handlers.py: Plugin-specific operations

This file contains ONLY route definitions that delegate to services.
════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from typing import Any, List

from fastapi import APIRouter, Request
from pydantic import BaseModel

from zentex.web_console.contracts.plugins import (
    CognitivePluginStatusItem,
    CognitivePluginDetailResponse,
    ForceEnablePluginResponse,
    PluginActionRequest,
    PluginRelationActionRequest,
    PluginFeatureGroupItem,
    FunctionalPluginDetailResponse,
    PluginVersionHistoryItem,
    PluginTestRequest,
    PluginTestResponse,
)

# Import service layer
from .plugin_commons import (
    list_cognitive_plugins,
    list_functional_plugins,
    list_plugins_by_feature,
    get_cognitive_plugin_detail,
    get_functional_plugin_detail,
    get_plugin_history,
)
from .plugin_handlers import (
    bind_functional_to_cognitive,
    unbind_functional_from_cognitive,
    test_functional_plugin,
    test_plugin,
    force_enable_plugin,
    force_disable_plugin,
    delete_plugin,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ========== Plugin List Endpoints ==========

@router.get("/plugins/cognitive", response_model=List[CognitivePluginStatusItem])
async def list_cognitive(request: Request):
    """List all cognitive plugins"""
    return await list_cognitive_plugins(request)


@router.get("/plugins/functional", response_model=List[CognitivePluginStatusItem])
async def list_functional(request: Request):
    """List all functional plugins"""
    return await list_functional_plugins(request)


@router.get("/plugins", response_model=List[PluginFeatureGroupItem])
async def list_by_feature(request: Request):
    """List plugins grouped by feature"""
    return await list_plugins_by_feature(request)


# ========== Plugin Detail Endpoints ==========

@router.get("/plugins/cognitive/{plugin_id}", response_model=CognitivePluginDetailResponse)
async def get_cognitive_detail(plugin_id: str, request: Request):
    """Get cognitive plugin detail"""
    return await get_cognitive_plugin_detail(request, plugin_id)


@router.get("/plugins/functional/{plugin_id}", response_model=FunctionalPluginDetailResponse)
async def get_functional_detail(plugin_id: str, request: Request):
    """Get functional plugin detail"""
    return await get_functional_plugin_detail(request, plugin_id)


@router.get("/plugins/{plugin_id}/history", response_model=List[PluginVersionHistoryItem])
async def get_history(plugin_id: str, request: Request):
    """Get plugin version history"""
    return await get_plugin_history(request, plugin_id)


# ========== Plugin Relationship Operations ==========

@router.post(
    "/plugins/cognitive/{plugin_id}/functional/{functional_id}/bind",
    response_model=CognitivePluginDetailResponse,
)
async def bind_plugin(
    plugin_id: str,
    functional_id: str,
    payload: PluginRelationActionRequest,
    request: Request,
):
    """Bind functional plugin to cognitive plugin"""
    return await bind_functional_to_cognitive(request, plugin_id, functional_id, payload)


@router.delete(
    "/plugins/cognitive/{plugin_id}/functional/{functional_id}/bind",
    response_model=CognitivePluginDetailResponse,
)
async def unbind_plugin(
    plugin_id: str,
    functional_id: str,
    payload: PluginRelationActionRequest,
    request: Request,
):
    """Unbind functional plugin from cognitive plugin"""
    return await unbind_functional_from_cognitive(request, plugin_id, functional_id, payload)


# ========== Plugin Testing Operations ==========

@router.post(
    "/plugins/cognitive/{plugin_id}/functional/{functional_id}/test",
    response_model=PluginTestResponse,
)
async def test_functional(
    plugin_id: str,
    functional_id: str,
    payload: PluginTestRequest,
    request: Request,
):
    """Test functional plugin in cognitive context"""
    return await test_functional_plugin(request, plugin_id, functional_id, payload)


@router.post("/plugins/{plugin_id}/test", response_model=PluginTestResponse)
async def test_plugin_endpoint(
    plugin_id: str,
    payload: PluginTestRequest,
    request: Request,
):
    """Test a plugin directly"""
    return await test_plugin(request, plugin_id, payload)


# ========== Plugin State Management Operations ==========

@router.post("/plugins/{plugin_id}/force-enable", response_model=ForceEnablePluginResponse)
async def enable_plugin(
    plugin_id: str,
    payload: PluginActionRequest,
    request: Request,
):
    """Force enable a plugin"""
    return await force_enable_plugin(request, plugin_id, payload)


@router.post("/plugins/{plugin_id}/force-disable", response_model=CognitivePluginStatusItem)
async def disable_plugin(
    plugin_id: str,
    request: Request,
):
    """Force disable a plugin"""
    return await force_disable_plugin(request, plugin_id)


@router.delete("/plugins/{plugin_id}")
async def delete_plugin_endpoint(
    plugin_id: str,
    request: Request,
):
    """Delete a plugin"""
    return await delete_plugin(request, plugin_id)

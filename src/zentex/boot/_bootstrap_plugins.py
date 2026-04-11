"""
Plugin Service Bootstrap Module

This module handles initialization of the plugin service through SystemPluginService.
All plugin instantiation MUST go through the service, not direct factory imports.

Key Principle:
  - NEVER import plugin factories directly
  - ALWAYS use SystemPluginService.bootstrap() for initialization
  - Bootstrap functions only instantiate plugins through the service
"""

from __future__ import annotations

import logging
from typing import List

from zentex.plugins.service import SystemPluginService

logger = logging.getLogger(__name__)


def seed_plugin_service(db_path: str = ".zentex/plugins.db") -> SystemPluginService:
    """
    Bootstrap the SystemPluginService and load all plugins.
    
    This is the ONLY way to initialize plugins in the system.
    
    Args:
        db_path: Path to SQLite database for plugin metadata
        
    Returns:
        Initialized SystemPluginService with all plugins bootstrapped
        
    Example:
        service = seed_plugin_service()
        plugins = service.query_plugins(status="active")
    """
    service = SystemPluginService(db_path=db_path)
    
    # Bootstrap loads all plugins from boot_exports
    service.bootstrap()
    
    logger.info(f"✅ Plugin service bootstrapped with {len(service.list_plugin_instances())} plugins")
    return service


def seed_managed_plugins() -> List[object]:
    """
    Get all managed plugins from the service.
    
    This replaces the old _seed_managed_plugins() function in web_dev.py
    which was directly instantiating plugins without going through the service.
    
    Returns:
        List of all instantiated plugin objects from the service
    """
    service = seed_plugin_service()
    
    plugins = service.list_plugin_instances()
    
    logger.info(f"Seeded {len(plugins)} managed plugins")
    return plugins


def seed_plugin_feature_catalog() -> List[object]:
    """
    Get the plugin feature catalog from the service.
    
    Returns:
        List of PluginFeatureCatalogItem objects describing available plugins
    """
    service = seed_plugin_service()
    
    # Query all active plugins and compile catalog items
    catalog = []
    for plugin in service.list_plugin_instances():
        plugin_id = getattr(plugin, "plugin_id", None)
        if not plugin_id:
            continue
        # Each plugin should have feature_code and other metadata
        if hasattr(plugin, "feature_code"):
            catalog.append({
                "feature_code": plugin.feature_code,
                "plugin_id": plugin_id,
                "version": getattr(plugin, "version", "1.0.0"),
                "description": f"Plugin: {plugin_id}",
            })
    
    logger.info(f"Created feature catalog with {len(catalog)} items")
    return catalog

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

from dataclasses import dataclass
import logging
from typing import Dict, List

from zentex.plugins.contracts import ManagedPluginRecord, PluginFeatureCatalogItem
from zentex.plugins.service import SystemPluginService
from zentex.plugins.service.utils import build_managed_plugin_record

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PluginRuntimeBundle:
    """Single-source plugin runtime view for one startup flow."""

    plugin_service: SystemPluginService
    managed_plugins: List[object]
    managed_plugin_records: Dict[str, ManagedPluginRecord]
    plugin_feature_catalog: List[PluginFeatureCatalogItem]


def _is_real_plugin_instance(plugin: object) -> bool:
    plugin_id = str(getattr(plugin, "plugin_id", "") or "").strip()
    return bool(plugin_id)


def _build_plugin_feature_catalog_from_plugins(
    managed_plugins: List[object],
) -> List[PluginFeatureCatalogItem]:
    catalog: List[PluginFeatureCatalogItem] = []
    seen_feature_codes: set[str] = set()
    for plugin in managed_plugins:
        if not _is_real_plugin_instance(plugin):
            continue
        feature_code = str(getattr(plugin, "feature_code", "") or "").strip()
        if not feature_code or feature_code in seen_feature_codes:
            continue
        seen_feature_codes.add(feature_code)
        catalog.append(
            PluginFeatureCatalogItem(
                feature_code=feature_code,
                display_name=str(
                    getattr(plugin, "display_name", "")
                    or getattr(plugin, "plugin_id", feature_code)
                ),
                plugin_kind=str(getattr(plugin, "plugin_kind", lambda: "unknown")() or "unknown"),
                supports_multiple_plugins=bool(
                    getattr(plugin, "supports_multiple_plugins", False)
                ),
            )
        )
    logger.info("Created feature catalog with %s items", len(catalog))
    return catalog


def build_managed_plugin_records_from_plugins(
    managed_plugins: List[object],
) -> Dict[str, ManagedPluginRecord]:
    """Build managed plugin records from the real runtime plugin instances."""
    managed_records: Dict[str, ManagedPluginRecord] = {}
    for plugin in managed_plugins:
        if not _is_real_plugin_instance(plugin):
            logger.debug("Skipping non-plugin runtime object: %r", plugin)
            continue
        plugin_id = str(getattr(plugin, "plugin_id", "") or "").strip()
        if not plugin_id:
            continue
        try:
            managed_records[plugin_id] = build_managed_plugin_record(plugin)
        except Exception as exc:
            logger.warning("Failed to build managed record for plugin %s: %s", plugin_id, exc)
    logger.info("[Bootstrap] Built %s managed plugin records", len(managed_records))
    return managed_records


def seed_plugin_runtime_bundle(
    db_path: str = ".zentex/plugins.db",
) -> PluginRuntimeBundle:
    """Create the single plugin runtime bundle used by one startup flow."""
    plugin_service = SystemPluginService(db_path=db_path)
    plugin_service.bootstrap()
    plugin_service.activate_all_cognitive(reason="system startup - activate all cognitive plugins")
    plugin_service.activate_all_functional(reason="system startup - activate all functional plugins")

    logger.info(
        "[Bootstrap] Plugin service bootstrapped with %s plugins",
        len(plugin_service.list_plugin_instances()),
    )
    managed_plugins = [
        plugin
        for plugin in plugin_service.list_plugin_instances()
        if _is_real_plugin_instance(plugin)
    ]
    managed_plugin_records = build_managed_plugin_records_from_plugins(managed_plugins)
    try:
        plugin_feature_catalog = list(plugin_service.get_feature_catalog() or [])
    except Exception as exc:
        logger.warning(
            "[Bootstrap] Failed to load feature catalog from plugin service, falling back to managed plugins: %s",
            exc,
        )
        plugin_feature_catalog = _build_plugin_feature_catalog_from_plugins(managed_plugins)
    return PluginRuntimeBundle(
        plugin_service=plugin_service,
        managed_plugins=managed_plugins,
        managed_plugin_records=managed_plugin_records,
        plugin_feature_catalog=plugin_feature_catalog,
    )

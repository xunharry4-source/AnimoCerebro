from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Type

from zentex.plugins.models import BasePluginSpec, PluginLayer

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Internal helper for implementation-time plugin discovery metadata.

    This class is not the public plugin API. Runtime callers must use
    `zentex.plugins.service.SystemPluginService`.
    """

    def __init__(self, plugins_root: str | Path, asset_store: Any | None = None) -> None:
        self.plugins_root = Path(plugins_root)
        self.asset_store = asset_store
        self._discovered_specs: Dict[str, Type[BasePluginSpec]] = {}

    def discover_all(self) -> Dict[str, Type[BasePluginSpec]]:
        """
        Scan the plugins directory and load all valid PluginSpec classes.
        """
        self._discovered_specs.clear()
        
        for _, name, is_pkg in pkgutil.walk_packages([str(self.plugins_root)], prefix="plugins."):
            if is_pkg:
                continue
            try:
                module = importlib.import_module(name)
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BasePluginSpec) and obj is not BasePluginSpec and not inspect.isabstract(obj):
                        self._discovered_specs[obj.__name__] = obj
            except Exception as e:
                logger.warning(f"Failed to load plugin module {name}: {e}")

        return self._discovered_specs

    def sync_to_db(self, discovered_instances: Iterable[BasePluginSpec]) -> None:
        """
        Synchronize the list of discovered plugin instances with the database.

        The storage adapter is optional because the current service bootstrap
        path owns persistence. This helper is kept only for narrow internal use.
        """
        if self.asset_store is None:
            logger.info("PluginManager.sync_to_db skipped: no storage adapter configured")
            return

        for plugin in discovered_instances:
            category = "cognitive" if plugin.plugin_layer == PluginLayer.LOGICAL_COGNITIVE else "functional"
            registration = {
                "source_kind": "physical_discovery",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            self.asset_store.upsert_plugin(
                category=category,
                plugin_id=plugin.plugin_id,
                spec_dict=plugin.model_dump(),
                registration_dict=registration
            )
            logger.info(f"Synced plugin {plugin.plugin_id} ({category}) to database.")

from datetime import datetime, timezone

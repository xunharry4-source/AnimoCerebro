from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path
from typing import Dict, List, Type, Any

from zentex.plugins.models import BasePluginSpec, PluginLayer
from zentex.plugins.storage import PluginStorage

logger = logging.getLogger(__name__)

class PluginManager:
    """
    Discovery and Registration Engine for Zentex Plugins.
    
    Responsibilities:
    - Recursively scan `src/plugins` for plugin specifications.
    - Classify plugins into Cognitive and Functional layers.
    - Sync discovered plugins with the persistence layer (SQLite).
    """

    def __init__(self, plugins_root: str | Path, asset_store: AssetDatabaseStore) -> None:
        self.plugins_root = Path(plugins_root)
        self.asset_store = asset_store
        self._discovered_specs: Dict[str, Type[BasePluginSpec]] = {}

    def discover_all(self) -> Dict[str, Type[BasePluginSpec]]:
        """
        Scan the plugins directory and load all valid PluginSpec classes.
        """
        self._discovered_specs.clear()
        
        # Add plugins root to path if not present (simplified for this repo structure)
        # Note: In a production system, we'd use a more robust loader
        
        # Traverse src/plugins
        for _, name, is_pkg in pkgutil.walk_packages([str(self.plugins_root)], prefix="plugins."):
            try:
                module = importlib.import_module(name)
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BasePluginSpec) and obj is not BasePluginSpec and not inspect.isabstract(obj):
                        # Use a temporary instance to extract metadata if needed, 
                        # or use class methods defined in BasePluginSpec
                        plugin_id = getattr(obj, "default_plugin_id", None) # Some specs might have this
                        if not plugin_id:
                            # Try to instantiate a candidate spec to get metadata 
                            # (Note: Requires careful handling if __init__ has side effects)
                            pass
                        
                        # Store by class name or id if available
                        self._discovered_specs[obj.__name__] = obj
            except Exception as e:
                logger.warning(f"Failed to load plugin module {name}: {e}")

        return self._discovered_specs

    def sync_to_db(self, discovered_instances: List[BasePluginSpec]) -> None:
        """
        Synchronize the list of discovered plugin instances with the database.
        
        Only adds new plugins (as CANDIDATE) or updates existing ones.
        Does not automatically activate them.
        """
        for plugin in discovered_instances:
            category = "cognitive" if plugin.plugin_layer == PluginLayer.LOGICAL_COGNITIVE else "functional"
            
            # Upsert into system_plugins
            # We use a default registration dict for first-time discovery
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

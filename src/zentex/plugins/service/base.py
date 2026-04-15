"""
Base Plugin Service: Initialization and Bootstrap

Handles:
- Plugin service initialization
- Factory loading
- Bootstrap process
- Plugin instantiation
- Category determination
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.storage import PluginStorage
from zentex.plugins.manager import PluginManager
from zentex.plugins.plugin_ids import iter_plugin_id_aliases
from zentex.common.plugin_ids import NINE_QUESTION_Q1

logger = logging.getLogger(__name__)


def _plugins_root() -> Path:
    return Path(__file__).resolve().parents[3] / "plugins"


def _discover_plugin_unit_directories() -> list[Path]:
    root = _plugins_root()
    discovered: list[Path] = []
    for metadata_path in root.glob("**/plugin.json"):
        plugin_dir = metadata_path.parent
        if (plugin_dir / "startup.py").exists() and (plugin_dir / "register.py").exists():
            discovered.append(plugin_dir)
    return sorted(discovered)


def _load_module_from_file(module_name: str, file_path: Path):
    import sys

    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec_module so that @dataclass (and any
    # other decorator that does sys.modules[cls.__module__].__dict__) can resolve
    # the module during class-body execution.  Python 3.12 dataclasses.KW_ONLY
    # detection triggers exactly this lookup.  Without the registration the call
    # returns None and raises AttributeError: 'NoneType' object has no attribute
    # '__dict__'.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _read_plugin_metadata(plugin_dir: Path) -> dict[str, str] | None:
    metadata_path = plugin_dir / "plugin.json"
    if not metadata_path.exists():
        return None
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("[Plugins] Invalid JSON in %s", metadata_path)
        return None
    plugin_id = str(payload.get("plugin_id") or "").strip()
    if not plugin_id:
        logger.warning("[Plugins] Missing plugin_id in %s", metadata_path)
        return None
    return {
        "plugin_id": plugin_id,
        "name": str(payload.get("name") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "dir": str(plugin_dir),
    }

def _select_implementation_file(plugin_dir: Path) -> Path:
    preferred = plugin_dir / f"{plugin_dir.name}_plugin.py"
    if preferred.exists():
        return preferred

    candidates = sorted(
        path
        for path in plugin_dir.glob("*_plugin.py")
        if "_patch_" not in path.name and not path.name.endswith("_patch_plugin.py")
    )
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(f"No plugin implementation file found in {plugin_dir}")
    raise RuntimeError(
        f"Ambiguous plugin implementation in {plugin_dir}: {[path.name for path in candidates]}"
    )


def _build_dynamic_factory(plugin_dir: Path, plugin_id: str) -> Callable:
    implementation_file = _select_implementation_file(plugin_dir)

    def _factory():
        module_name = f"zentex_dynamic_plugin_{plugin_id.replace('-', '_')}"
        module = _load_module_from_file(module_name, implementation_file)
        build_functions = [
            getattr(module, name)
            for name in dir(module)
            if name.startswith("build_") and callable(getattr(module, name))
        ]
        if not build_functions:
            raise RuntimeError(
                f"No build_* factory found for plugin_id={plugin_id} in {implementation_file}"
            )
        if len(build_functions) > 1:
            exact_name = f"build_{plugin_dir.name}_plugin"
            for candidate in build_functions:
                if candidate.__name__ == exact_name:
                    return candidate()
        if len(build_functions) > 1:
            raise RuntimeError(
                f"Ambiguous build_* factories for plugin_id={plugin_id} in {implementation_file}"
            )
        return build_functions[0]()

    return _factory


def _get_plugin_factories() -> Dict[str, Callable]:
    factories: Dict[str, Callable] = {}
    for plugin_dir in _discover_plugin_unit_directories():
        metadata = _read_plugin_metadata(plugin_dir)
        if metadata is None:
            continue
        plugin_id = metadata["plugin_id"]
        factories[plugin_id] = _build_dynamic_factory(plugin_dir, plugin_id)
    return factories


class BasePluginService:
    """
    Base service providing initialization and bootstrap for plugin system.
    
    Responsibilities:
    - Manage storage and registry
    - Initialize service state
    - Load plugin factories
    - Bootstrap plugins on startup
    - Determine plugin categories
    """
    
    @classmethod
    def _get_plugin_catalog_config(cls) -> Dict[str, Dict[str, str]]:
        """Load plugin metadata from discovered plugin unit directories."""
        try:
            catalog: Dict[str, Dict[str, str]] = {}
            for plugin_dir in _discover_plugin_unit_directories():
                metadata = _read_plugin_metadata(plugin_dir)
                if metadata is None:
                    continue
                catalog[metadata["plugin_id"]] = {
                    "name": metadata["name"],
                    "description": metadata["description"],
                    "dir": metadata["dir"],
                }

            logger.info("[Plugins] Loaded plugin metadata for %s plugins", len(catalog))
            return catalog
        except Exception as exc:
            logger.warning(f"[Plugins] Failed to load catalog config: {exc}")
            return {}

    def __init__(
        self, 
        db_path: str,
        manager: Optional[PluginManager] = None, 
    ) -> None:
        """
        Initialize the plugin service.
        
        Args:
            db_path: Path to SQLite database
            manager: Optional PluginManager reference
        """
        self._storage = PluginStorage(db_path)
        self.manager = manager
        
        # In-memory registry: plugin_id -> actual plugin instance
        self._plugin_instances: Dict[str, Any] = {}
        
        # Spec cache for quick lookup: plugin_id -> spec dict
        self._plugin_specs: Dict[str, Dict[str, Any]] = {}
        
        # Execution records: plugin_id -> execution stats
        self._execution_stats: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _get_factories(cls) -> Dict[str, Callable]:
        """Get plugin factories from the current plugin-unit directories."""
        return _get_plugin_factories()

    def _index_plugin_runtime_state(
        self,
        plugin_id: str,
        *,
        instance: Any | None = None,
        spec_dict: Dict[str, Any] | None = None,
        execution_stats: Dict[str, Any] | None = None,
    ) -> None:
        for alias in iter_plugin_id_aliases(plugin_id):
            if instance is not None:
                self._plugin_instances[alias] = instance
            if spec_dict is not None:
                self._plugin_specs[alias] = spec_dict
            if execution_stats is not None:
                self._execution_stats[alias] = execution_stats

    def bootstrap(self) -> None:
        """
        Register built-in plugin metadata and rebuild runtime indexes.

        Bootstrap is intentionally non-executing:
        - no plugin instantiation
        - no plugin activation
        - no bulk lifecycle transition
        """
        logger.info("[Plugins] Starting metadata bootstrap...")

        registration_summary = self.register_discovered_plugins()
        runtime_summary = self.rehydrate_registered_plugins()
        relation_summary = self.ensure_default_relationships()

        logger.info(
            "[Plugins] Bootstrap complete. discovered_registered=%s records=%s instantiated=%s default_relations_added=%s",
            registration_summary["registered_count"],
            runtime_summary["record_count"],
            runtime_summary["instantiated_count"],
            relation_summary["created_count"],
        )

    def rehydrate_registered_plugins(self) -> Dict[str, int]:
        """
        Load already-registered plugin metadata from database into runtime memory.

        This method never instantiates plugin runtime objects. Runtime instances
        are created only during explicit activation.
        """
        records = self._storage.list_plugins()
        self._plugin_specs.clear()
        self._execution_stats.clear()
        self._plugin_instances.clear()

        for record in records:
            plugin_id = record["plugin_id"]
            try:
                spec_dict = json.loads(record["spec_json"])
                self._plugin_specs[plugin_id] = spec_dict
                        
                # Initialize execution stats
                if plugin_id not in self._execution_stats:
                    self._execution_stats[plugin_id] = {
                        'usage_count': record.get('usage_count', 0),
                        'failure_count': record.get('failure_count', 0),
                        'last_executed_at': None,
                    }
                self._index_plugin_runtime_state(
                    plugin_id,
                    instance=None,
                    spec_dict=self._plugin_specs.get(plugin_id),
                    execution_stats=self._execution_stats.get(plugin_id),
                )
                    
            except Exception as exc:
                logger.error(f"[Plugins] Failed to load {plugin_id}: {exc}")

        return {
            "record_count": len(records),
            "active_count": sum(
                1
                for record in records
                if str(record.get("lifecycle_status") or "").strip().lower()
                == PluginLifecycleStatus.ACTIVE.value
            ),
            "instantiated_count": 0,
        }

    def register_discovered_plugins(self) -> Dict[str, int]:
        """
        Discover built-in plugin units and register missing plugins to storage.

        This is a write operation owned by the plugins module itself. Callers
        that only need a service handle must not use this API implicitly.
        """
        return self._load_and_instantiate_plugins()

    def ensure_default_relationships(self) -> Dict[str, int]:
        """
        Ensure built-in default plugin relations exist.

        This is a write operation owned by the plugins module itself.
        """
        return self._seed_default_relationships()

    def _load_and_instantiate_plugins(self) -> Dict[str, int]:
        """
        Register all built-in plugins to the database without eagerly
        instantiating runtime objects.
        """
        registered = {r['plugin_id'] for r in self._storage.list_plugins()}
        catalog = self._get_plugin_catalog_config()
        registered_count = 0

        for plugin_id in self._get_factories().keys():
            if plugin_id in registered:
                continue  # Already registered, skip
            
            try:
                logger.info(f"[Plugins] Registering discovered plugin: {plugin_id}")
                category = self._determine_category(plugin_id)
                catalog_item = catalog.get(plugin_id, {})
                configured_name = str(catalog_item.get("name", "")).strip()
                configured_description = str(catalog_item.get("description", "")).strip()

                spec_dict = {
                    'plugin_id': plugin_id,
                    'version': '1.0.0',
                    'lifecycle_status': PluginLifecycleStatus.CANDIDATE.value,
                    'operational_status': 'enabled',
                    'category': category,
                    'behavior_key': None,
                    'feature_code': plugin_id,
                    'display_name': configured_name or plugin_id,
                    'description': configured_description,
                }
                
                # ✅ 关键修复：只在插件不存在时才注册，避免重复 upsert
                existing = self._storage.get_plugin(plugin_id)
                if existing:
                    logger.debug(f"[Plugins] Plugin {plugin_id} already exists (ID={existing.get('id')}), skipping")
                    continue
                
                # Register in database
                registration = {
                    'source_kind': 'built_in',
                    'created_at': datetime.now(timezone.utc).isoformat(),
                }
                
                self._storage.upsert_plugin(
                    category=category,
                    plugin_id=plugin_id,
                    spec_dict=spec_dict,
                    registration_dict=registration
                )
                
                self._plugin_specs[plugin_id] = spec_dict
                self._index_plugin_runtime_state(
                    plugin_id,
                    instance=None,
                    spec_dict=spec_dict,
                )
                registered_count += 1
                
            except Exception as e:
                logger.error(f"[Plugins] Failed to register {plugin_id}: {e}"); import traceback; traceback.print_exc()

        return {
            "registered_count": registered_count,
            "known_factory_count": len(self._get_factories()),
        }

    def _seed_default_relationships(self) -> Dict[str, int]:
        q1_cognitive_id = NINE_QUESTION_Q1
        q1_functional_bindings = [
            ("sensory_webhook", "primary", 1),
            ("sensory_injection_sanitizer", "primary", 2),
            ("sensory_environment", "primary", 3),
            ("sensory_telemetry", "support", 4),
        ]

        if not self._storage.get_plugin(q1_cognitive_id):
            return {"created_count": 0}

        created_count = 0
        for functional_plugin_id, role, priority in q1_functional_bindings:
            if not self._storage.get_plugin(functional_plugin_id):
                continue
            if self._storage.get_relation(q1_cognitive_id, functional_plugin_id):
                continue
            self._storage.create_relation(
                cognitive_plugin_id=q1_cognitive_id,
                functional_plugin_id=functional_plugin_id,
                role=role,
                priority=priority,
            )
            created_count += 1

        return {"created_count": created_count}

    def _determine_category(self, plugin_id: str) -> str:
        """
        Determine plugin category from its ID.
        
        Args:
            plugin_id: The plugin identifier
            
        Returns:
            Category string ('cognitive', 'functional', 'sensory', etc.)
        """
        if 'execution' in plugin_id:
            return 'functional'
        elif 'oracle' in plugin_id:
            return 'functional'
        elif any(x in plugin_id for x in ['cognitive', 'q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8', 'q9', 'memory', 'reflection']):
            return 'cognitive'
        elif 'sensory' in plugin_id or 'telemetry' in plugin_id:
            return 'sensory'
        elif 'simulation' in plugin_id:
            return 'simulation'
        elif 'weight' in plugin_id:
            return 'governance'
        elif 'model_provider' in plugin_id:
            return 'llm'
        else:
            return 'functional'

from __future__ import annotations

"""Unified startup entry for plugin unit discovery and factory resolution.

Allowed plugin unit paths:
- src/plugins/<plugin>
- src/plugins/<group>/<plugin>

Disallowed:
- src/plugins/<plugin>/<plugin>

Each plugin unit must contain:
- startup.py
- plugin.json
- register.py
- README.md
"""

import importlib.util
import logging
from pathlib import Path
from typing import Callable, Dict, List, Tuple


logger = logging.getLogger(__name__)

PluginFactory = Callable[..., object]
REQUIRED_PLUGIN_UNIT_FILES = ("startup.py", "plugin.json", "register.py", "README.md")
ALLOWED_GROUP_DIRS = (
    "cognitive",
    "execution",
    "memory",
    "model_providers",
    "oracle",
    "nine_questions",
    "reflection",
    "sensory",
    "simulation",
    "tasks",
    "weights",
)


def _plugins_root() -> Path:
    return Path(__file__).resolve().parent


def _is_plugin_unit_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    return all((path / name).exists() for name in REQUIRED_PLUGIN_UNIT_FILES)


def _group_dir_has_sibling_code(group_dir: Path) -> bool:
    """Return True if group dir contains direct Python code files.

    Policy:
    - Group dir (e.g. src/plugins/cognitive) is a pure container.
    - If direct .py files exist under group dir (except __init__.py),
      group sub-plugin registration is blocked.
    """
    for child in group_dir.iterdir():
        if not child.is_file():
            continue
        if child.suffix != ".py":
            continue
        if child.name == "__init__.py":
            continue
        return True
    return False


def _discover_plugin_unit_directories_with_policy() -> Tuple[List[Path], bool]:
    """Discover plugin dirs and report whether policy blocked any group."""
    root = _plugins_root()
    discovered: List[Path] = []
    policy_blocked_group = False

    # Depth-1: src/plugins/<plugin>
    for path in root.iterdir():
        if not path.is_dir() or path.name.startswith("__"):
            continue
        if _is_plugin_unit_dir(path):
            discovered.append(path)

    # Depth-2: src/plugins/<group>/<plugin>
    for group_name in ALLOWED_GROUP_DIRS:
        group_dir = root / group_name
        if not group_dir.exists() or not group_dir.is_dir():
            continue

        if _group_dir_has_sibling_code(group_dir):
            policy_blocked_group = True
            logger.warning(
                "[Plugins] Policy blocked group '%s': sibling .py code files found under %s. "
                "Sub-plugins in this group will not be registered.",
                group_name,
                group_dir,
            )
            continue

        for path in group_dir.iterdir():
            if not path.is_dir() or path.name.startswith("__"):
                continue
            if _is_plugin_unit_dir(path):
                discovered.append(path)

    return discovered, policy_blocked_group


def discover_plugin_unit_directories() -> List[Path]:
    """Discover plugin units under allowed depth rules.

    Returns plugin directories from:
    1) src/plugins/<plugin>
    2) src/plugins/<group>/<plugin>

    Only known group directories are traversed for depth-2 discovery to avoid
    treating src/plugins/<plugin>/<plugin> as valid plugin placement.
    """
    discovered, _ = _discover_plugin_unit_directories_with_policy()
    return discovered


def _load_module_from_file(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_registry_factories(factory_catalog: Dict[str, PluginFactory]) -> Dict[str, PluginFactory]:
    """Resolve factories through discovered plugin unit startup entries.

    Args:
        factory_catalog: Base factory map keyed by plugin_id.

    Returns:
        Resolved factory map from plugin unit `startup.py` entries.
        Falls back to `factory_catalog` when no valid plugin units are found.
    """
    plugin_dirs, policy_blocked_group = _discover_plugin_unit_directories_with_policy()
    if not plugin_dirs:
        if policy_blocked_group:
            logger.error(
                "[Plugins] No plugin units discovered because policy blocked one or more groups. "
                "Returning empty factory map by policy."
            )
            return {}
        return dict(factory_catalog)

    resolved: Dict[str, PluginFactory] = {}
    root = _plugins_root()

    for plugin_dir in plugin_dirs:
        startup_path = plugin_dir / "startup.py"
        module_name = "plugins_unit_" + "_".join(plugin_dir.relative_to(root).parts) + "_startup"
        
        # Policy: Any failure to load/execute a plugin is fatal (Fail-Closed).
        module = _load_module_from_file(module_name, startup_path)
        startup = getattr(module, "startup", None)
        if not callable(startup):
            raise RuntimeError(f"[Plugins] Critical failure: startup() not callable in plugin {startup_path}")

        plugin_id, factory = startup(factory_catalog)
        if isinstance(plugin_id, str) and callable(factory):
            resolved[plugin_id] = factory
        else:
            raise RuntimeError(f"[Plugins] Critical failure: Invalid startup() return values in {startup_path}")

    if resolved:
        return resolved

    if policy_blocked_group:
        logger.error(
            "[Plugins] All resolved plugin factories were blocked/invalid under policy. "
            "Returning empty factory map by policy."
        )
        return {}

    return dict(factory_catalog)


def get_unified_plugin_factories(factory_catalog: Dict[str, PluginFactory]) -> Dict[str, PluginFactory]:
    """Return plugin-unit resolved factory map."""
    return resolve_registry_factories(factory_catalog)


def bootstrap_plugins(db_path: str):
    """Create and bootstrap SystemPluginService with plugin unit discovery."""
    from zentex.plugins.service import SystemPluginService

    service = SystemPluginService(db_path=db_path)
    service.bootstrap()
    return service


__all__ = [
    "PluginFactory",
    "REQUIRED_PLUGIN_UNIT_FILES",
    "ALLOWED_GROUP_DIRS",
    "discover_plugin_unit_directories",
    "resolve_registry_factories",
    "get_unified_plugin_factories",
    "bootstrap_plugins",
]

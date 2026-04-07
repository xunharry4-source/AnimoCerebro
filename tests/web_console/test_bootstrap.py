from __future__ import annotations

import importlib
import asyncio
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def test_dev_server_import_raises_structured_error_when_dependency_missing() -> None:
    errors = importlib.import_module("zentex.web_console.errors")
    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "pydantic" or name.startswith("pydantic."):
            raise ModuleNotFoundError("No module named 'pydantic'")
        return original_import(name, globals, locals, fromlist, level)

    for module_name in [
        "zentex.web_console.dev_server",
        "plugins.execution.base_executor_chain",
        "zentex.core.execution_spec",
    ]:
        sys.modules.pop(module_name, None)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(errors.InitializationError, match="缺少依赖模块 `pydantic`"):
            importlib.import_module("zentex.web_console.dev_server")


def test_build_dev_server_app_raises_initialization_error_on_mcp_timeout() -> None:
    module = importlib.import_module("zentex.web_console.dev_server")
    errors = importlib.import_module("zentex.web_console.errors")

    with patch.object(module, "_seed_mcp_adapter", side_effect=TimeoutError("mcp transport disconnected")):
        with pytest.raises(errors.InitializationError, match="运行时装配未就绪"):
            module.build_dev_server_app()


def test_build_dev_server_app_raises_config_error_without_model_provider() -> None:
    module = importlib.import_module("zentex.web_console.dev_server")
    errors = importlib.import_module("zentex.web_console.errors")

    with patch.object(module, "_seed_managed_plugins", return_value=[]):
        with pytest.raises(errors.ConfigError, match="未找到可用的 model_provider 插件"):
            module.build_dev_server_app()


def test_build_dev_server_app_succeeds_inside_running_event_loop() -> None:
    module = importlib.import_module("zentex.web_console.dev_server")

    async def _run() -> None:
        app = module.build_dev_server_app()
        assert getattr(app, "state", None) is not None

    asyncio.run(_run())

from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.web_console.cli import main
from zentex.web_console.errors import InitializationError


def test_cli_check_startup_returns_nonzero_on_initialization_error(capsys) -> None:
    with patch("zentex.web_console.cli.validate_web_console_startup", side_effect=InitializationError("missing deps")):
        code = main(["check-startup"])

    captured = capsys.readouterr()
    assert code == 1
    assert "missing deps" in captured.err


def test_cli_check_startup_returns_zero_on_success() -> None:
    with patch("zentex.web_console.cli.validate_web_console_startup", return_value=None):
        code = main(["check-startup"])

    assert code == 0


def test_cli_check_startup_rejects_legacy_ws_runtime_with_websockets_16(monkeypatch) -> None:
    monkeypatch.setenv("ZENTEX_WS_IMPLEMENTATION", "auto")
    with patch("importlib.metadata.version", return_value="16.0"):
        with patch("zentex.web_console.cli.validate_web_console_startup", side_effect=InitializationError(
            "Web 控制台启动失败：当前 websockets>=16，禁止继续使用 legacy/auto WebSocket 实现；请使用 `websockets-sansio`。"
        )):
            code = main(["check-startup"])

    assert code == 1

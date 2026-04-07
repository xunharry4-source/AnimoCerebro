from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import pytest


pytest.importorskip("websockets")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(base_url: str, timeout_seconds: float = 20.0) -> None:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/web/overview", timeout=1.0) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.2)
    raise AssertionError("timed out waiting for uvicorn test server readiness")


@pytest.mark.integration
def test_events_stream_repeated_idle_connect_disconnect_with_real_uvicorn(tmp_path: Path) -> None:
    import websockets

    port = _find_free_port()
    log_path = tmp_path / "uvicorn-events-stream.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    env["ZENTEX_WS_IMPLEMENTATION"] = "websockets-sansio"

    with log_path.open("w+", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                str(PROJECT_ROOT / ".venv" / "bin" / "python"),
                "-m",
                "uvicorn",
                "zentex.web_console.dev_server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--ws",
                "websockets-sansio",
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

        try:
            _wait_until_ready(f"http://127.0.0.1:{port}")

            async def _exercise() -> list[dict[str, object]]:
                results: list[dict[str, object]] = []
                uri = f"ws://127.0.0.1:{port}/api/web/events/stream"
                for index, idle in enumerate((1.0, 1.0, 1.0, 6.0, 6.0, 1.0, 1.0, 1.0), start=1):
                    try:
                        async with websockets.connect(uri, ping_interval=5, ping_timeout=5):
                            await asyncio.sleep(idle)
                        results.append({"index": index, "idle": idle, "status": "closed_cleanly"})
                    except Exception as exc:  # pragma: no cover - assertion below reports details
                        results.append({"index": index, "idle": idle, "status": f"{type(exc).__name__}: {exc}"})
                    await asyncio.sleep(0.2)
                return results

            results = asyncio.run(_exercise())
            assert all(item["status"] == "closed_cleanly" for item in results), json.dumps(results, ensure_ascii=False)

            time.sleep(2.0)
            log_file.flush()
            log_text = log_path.read_text(encoding="utf-8")
            assert "keepalive ping failed" not in log_text
            assert "socket.send() raised exception." not in log_text
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

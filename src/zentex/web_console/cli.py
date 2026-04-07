from __future__ import annotations
from typing import List


import argparse
import importlib
import os
import sys
from importlib import metadata

from zentex.web_console.errors import InitializationError


def validate_websocket_runtime() -> None:
    requested = str(os.getenv("ZENTEX_WS_IMPLEMENTATION", "websockets-sansio")).strip() or "websockets-sansio"

    try:
        websockets_version = metadata.version("websockets")
    except metadata.PackageNotFoundError as exc:
        raise InitializationError("Web 控制台启动失败：缺少依赖模块 `websockets`。") from exc

    major_text = websockets_version.split(".", 1)[0]
    try:
        websockets_major = int(major_text)
    except ValueError:
        websockets_major = 0

    if requested in {"auto", "websockets"} and websockets_major >= 16:
        raise InitializationError(
            "Web 控制台启动失败：当前 websockets>=16，禁止继续使用 legacy/auto WebSocket 实现；"
            "请使用 `websockets-sansio`。"
        )

    if requested == "websockets-sansio":
        try:
            importlib.import_module("uvicorn.protocols.websockets.websockets_sansio_impl")
        except Exception as exc:
            raise InitializationError(
                "Web 控制台启动失败：`websockets-sansio` 运行时不可用，请检查 uvicorn/websockets 安装。"
            ) from exc


def validate_web_console_startup() -> None:
    validate_websocket_runtime()
    from zentex.web_console.dev_server import build_dev_server_app

    build_dev_server_app()


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zentex-web-console")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check-startup", help="Validate web console startup dependencies and runtime assembly")

    args = parser.parse_args(argv)

    if args.command == "check-startup":
        try:
            validate_web_console_startup()
        except InitializationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

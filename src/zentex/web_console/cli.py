from __future__ import annotations
from typing import List


import argparse
import importlib
import os
import sys
from importlib import metadata
from pathlib import Path

from zentex.web_console.errors import InitializationError
from zentex.web_console.verification import (
    SmokeImportResult,
    render_verification_report_markdown,
    scan_legacy_runtime_imports,
    smoke_import_module,
)


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
    from zentex.boot.web_dev import build_dev_server_app

    build_dev_server_app()


def run_migration_verification(
    *,
    root: Path | None = None,
    modules: list[str] | None = None,
) -> tuple[list[object], list[SmokeImportResult], str]:
    scan_root = root or Path("src/zentex/web_console")
    smoke_modules = modules or ["zentex.web_console.router", "zentex.web_console.app"]
    scan_findings = scan_legacy_runtime_imports(scan_root)
    smoke_results = [smoke_import_module(module_name) for module_name in smoke_modules]
    report = render_verification_report_markdown(
        scan_findings=scan_findings,
        smoke_results=smoke_results,
    )
    return scan_findings, smoke_results, report


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zentex-web-console")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check-startup", help="Validate web console startup dependencies and runtime assembly")
    subparsers.add_parser("verify-migration", help="Scan for legacy runtime imports and smoke-import web_console modules")

    args = parser.parse_args(argv)

    if args.command == "check-startup":
        try:
            validate_web_console_startup()
        except InitializationError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    if args.command == "verify-migration":
        scan_findings, smoke_results, report = run_migration_verification()
        print(report)
        has_smoke_failures = any(not result.ok for result in smoke_results)
        return 1 if scan_findings or has_smoke_failures else 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from typing import Any


def normalize_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def normalize_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def infer_host_runtime_type(physical_host_state: dict[str, Any]) -> tuple[str, str]:
    platform_text = str(physical_host_state.get("platform") or "").lower()
    hostname = str(physical_host_state.get("hostname") or "").lower()
    cwd_text = str(physical_host_state.get("cwd") or "").lower()

    server_markers = [
        "linux",
        "ubuntu",
        "debian",
        "centos",
        "red hat",
        "alpine",
        "server",
        "prod",
        "staging",
        "k8s",
        "kubernetes",
        "container",
    ]
    desktop_markers = [
        "darwin",
        "macos",
        "windows",
        "desktop",
        "laptop",
        "notebook",
    ]

    server_hits = sum(1 for token in server_markers if token in platform_text or token in hostname or token in cwd_text)
    desktop_hits = sum(1 for token in desktop_markers if token in platform_text or token in hostname)

    if server_hits >= 2 and server_hits >= desktop_hits:
        return "服务器", "平台/主机名特征更接近服务端运行环境"
    if desktop_hits >= 1 and desktop_hits > server_hits:
        return "普通电脑", "平台特征更接近个人电脑（桌面或笔记本）"
    if "darwin" in platform_text or "macos" in platform_text:
        return "普通电脑", "检测到 macOS 运行环境"
    if "windows" in platform_text:
        return "普通电脑", "检测到 Windows 运行环境"
    if "linux" in platform_text:
        return "服务器", "检测到 Linux 运行环境（默认按服务器场景判定）"
    return "未知", "宿主机特征不足，无法稳定区分服务器或普通电脑"

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
from typing import Any

from pydantic import Field

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.plugin_family import HostTelemetryPluginSpec


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify_memory_pressure(used_ratio: float | None) -> str:
    if used_ratio is None:
        return "unknown"
    if used_ratio >= 0.9:
        return "critical"
    if used_ratio >= 0.8:
        return "high"
    if used_ratio >= 0.65:
        return "medium"
    return "normal"


def _read_linux_memory_ratio() -> float | None:
    meminfo: dict[str, float] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if ":" not in line:
                    continue
                key, raw_value = line.split(":", 1)
                amount = raw_value.strip().split()[0]
                parsed = _safe_float(amount)
                if parsed is not None:
                    meminfo[key.strip()] = parsed * 1024.0
    except OSError:
        return None

    total = meminfo.get("MemTotal")
    available = meminfo.get("MemAvailable")
    if total is None or available is None or total <= 0:
        return None
    used_ratio = 1.0 - (available / total)
    return max(0.0, min(1.0, used_ratio))


def _read_darwin_memory_ratio() -> float | None:
    try:
        total_raw = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
        total = _safe_float(total_raw)
        vm_stat = subprocess.check_output(["vm_stat"], text=True)
    except (OSError, subprocess.SubprocessError):
        return None

    if total is None or total <= 0:
        return None

    page_size = 4096.0
    lines = vm_stat.splitlines()
    if lines:
        header = lines[0]
        marker = "page size of "
        if marker in header:
            raw_size = header.split(marker, 1)[1].split(" bytes", 1)[0]
            parsed = _safe_float(raw_size)
            if parsed is not None:
                page_size = parsed

    counters: dict[str, float] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parsed = _safe_float(raw_value.replace(".", "").strip())
        if parsed is not None:
            counters[key.strip()] = parsed

    available_pages = (
        counters.get("Pages free", 0.0)
        + counters.get("Pages inactive", 0.0)
        + counters.get("Pages speculative", 0.0)
    )
    available = available_pages * page_size
    used_ratio = 1.0 - (available / total)
    return max(0.0, min(1.0, used_ratio))


def _read_memory_pressure() -> str:
    used_ratio: float | None = None
    if sys.platform.startswith("linux"):
        used_ratio = _read_linux_memory_ratio()
    elif sys.platform == "darwin":
        used_ratio = _read_darwin_memory_ratio()
    return _classify_memory_pressure(used_ratio)


def _has_non_loopback_interface_psutil() -> tuple[bool, bool] | None:
    try:
        import psutil  # type: ignore
    except Exception:
        return None

    configured = False
    active = False
    try:
        interface_addrs = psutil.net_if_addrs()
        interface_stats = psutil.net_if_stats()
    except Exception:
        return None

    for name, addresses in interface_addrs.items():
        normalized_name = name.lower()
        if normalized_name in {"lo", "lo0"}:
            continue
        has_real_address = False
        for address in addresses:
            family_name = getattr(address.family, "name", "")
            addr = str(getattr(address, "address", "") or "")
            if family_name == "AF_INET" and not addr.startswith("127."):
                has_real_address = True
            if family_name == "AF_INET6" and addr not in {"::1", ""}:
                has_real_address = True
        if not has_real_address:
            continue
        configured = True
        stats = interface_stats.get(name)
        if stats is not None and bool(getattr(stats, "isup", False)):
            active = True
    return configured, active


def _has_non_loopback_interface_fallback() -> tuple[bool, bool]:
    try:
        output = subprocess.check_output(["ifconfig"], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False, False

    configured = False
    active = False
    current_name = ""
    current_has_real_address = False
    current_active = False

    def _flush() -> None:
        nonlocal configured, active, current_has_real_address, current_active
        if current_name.lower() in {"lo", "lo0"}:
            return
        if current_has_real_address:
            configured = True
            if current_active:
                active = True

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if line and not line.startswith("\t") and ":" in line:
            _flush()
            current_name = line.split(":", 1)[0].strip()
            current_has_real_address = False
            current_active = "status: active" in line.lower()
            continue
        stripped = line.strip()
        if stripped.startswith("inet "):
            addr = stripped.split()[1]
            if not addr.startswith("127."):
                current_has_real_address = True
        if stripped.startswith("inet6 "):
            addr = stripped.split()[1]
            if addr != "::1":
                current_has_real_address = True
        if stripped.lower() == "status: active":
            current_active = True
    _flush()
    return configured, active


def _read_network_health() -> str:
    result = _has_non_loopback_interface_psutil()
    if result is None:
        result = _has_non_loopback_interface_fallback()
    configured, active = result
    if active:
        return "healthy"
    if configured:
        return "degraded"
    return "offline"


class HostTelemetryPlugin(HostTelemetryPluginSpec):
    purpose: str = Field(
        default="Collect read-only local host telemetry for Q1 environment evidence."
    )

    def capture_host_state(self, context: dict[str, Any]) -> dict[str, Any]:
        workspace_root = str(
            context.get("workspace_root")
            or context.get("cwd")
            or os.getcwd()
        )
        return {
            "cwd": workspace_root,
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "memory_pressure": _read_memory_pressure(),
            "network_health": _read_network_health(),
        }


def build_default_host_telemetry_plugin(
    *,
    plugin_id: str = "host-telemetry-local",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> HostTelemetryPlugin:
    return HostTelemetryPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="host.telemetry",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["host_telemetry_capture_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )

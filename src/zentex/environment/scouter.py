from __future__ import annotations

"""
Environment Scouter / 环境侦察器

Implements physical host state sampling for CPU, memory, disk, and network resources.
Provides debounced, smoothed output with proper failure handling.

实现 CPU、内存、磁盘和网络资源的物理宿主状态采样。
提供去抖、平滑输出和适当的故障处理。
"""

import logging
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

from zentex.environment.models import (
    HealthStatus,
    MemoryPressureLevel,
    NetworkHealthStatus,
    PhysicalHostState,
)


def _safe_float(value: Optional[str]) -> Optional[float]:
    """Safely convert string to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify_memory_pressure(used_ratio: Optional[float]) -> MemoryPressureLevel:
    """Classify memory pressure based on usage ratio."""
    if used_ratio is None:
        return MemoryPressureLevel.UNKNOWN
    if used_ratio >= 0.9:
        return MemoryPressureLevel.CRITICAL
    if used_ratio >= 0.8:
        return MemoryPressureLevel.HIGH
    if used_ratio >= 0.65:
        return MemoryPressureLevel.MEDIUM
    return MemoryPressureLevel.NORMAL


def _read_linux_memory_info() -> tuple[Optional[float], Optional[int], Optional[int]]:
    """Read memory information from /proc/meminfo on Linux."""
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
                    meminfo[key.strip()] = parsed * 1024.0  # Convert kB to bytes
    except OSError:
        return None, None, None
    
    total = meminfo.get("MemTotal")
    available = meminfo.get("MemAvailable")
    
    if total is None or available is None or total <= 0:
        return None, None, None
    
    used_ratio = 1.0 - (available / total)
    return max(0.0, min(1.0, used_ratio)), int(total), int(available)


def _read_darwin_memory_info() -> tuple[Optional[float], Optional[int], Optional[int]]:
    """Read memory information on macOS using sysctl and vm_stat."""
    try:
        total_raw = subprocess.check_output(
            ["sysctl", "-n", "hw.memsize"], encoding="utf-8", errors="replace"
        ).strip()
        total = _safe_float(total_raw)
        vm_stat = subprocess.check_output(["vm_stat"], encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None, None, None
    
    if total is None or total <= 0:
        return None, None, None
    
    # Parse page size from vm_stat output
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
    
    # Parse page counters
    counters: dict[str, float] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parsed = _safe_float(raw_value.replace(".", "").strip())
        if parsed is not None:
            counters[key.strip()] = parsed
    
    # Calculate available memory
    available_pages = (
        counters.get("Pages free", 0.0)
        + counters.get("Pages inactive", 0.0)
        + counters.get("Pages speculative", 0.0)
    )
    available = available_pages * page_size
    used_ratio = 1.0 - (available / total)
    
    return max(0.0, min(1.0, used_ratio)), int(total), int(available)


def _read_memory_info() -> tuple[Optional[float], Optional[int], Optional[int]]:
    """Read memory information based on platform."""
    if sys.platform.startswith("linux"):
        return _read_linux_memory_info()
    elif sys.platform == "darwin":
        return _read_darwin_memory_info()
    else:
        # Unsupported platform
        return None, None, None


def _has_non_loopback_interface_psutil() -> tuple[bool, Optional[bool]]:
    """Check for non-loopback network interfaces using psutil."""
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
    """Fallback method to check network interfaces using ifconfig."""
    try:
        output = subprocess.check_output(
            ["ifconfig"], encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL
        )
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


def _read_network_health() -> tuple[NetworkHealthStatus, bool, bool]:
    """Read network health status."""
    result = _has_non_loopback_interface_psutil()
    if result is None:
        result = _has_non_loopback_interface_fallback()
    
    configured, active = result
    
    if active:
        return NetworkHealthStatus.HEALTHY, configured, active
    elif configured:
        return NetworkHealthStatus.DEGRADED, configured, active
    else:
        return NetworkHealthStatus.OFFLINE, configured, active


def _assess_overall_health(
    memory_pressure: MemoryPressureLevel,
    network_health: NetworkHealthStatus,
    cpu_load: Optional[float],
    disk_usage: Optional[float],
) -> HealthStatus:
    """Assess overall host health based on individual metrics."""
    # Critical conditions
    if (
        memory_pressure == MemoryPressureLevel.CRITICAL
        or network_health == NetworkHealthStatus.OFFLINE
    ):
        return HealthStatus.CRITICAL
    
    # Degraded conditions
    if (
        memory_pressure in (MemoryPressureLevel.HIGH, MemoryPressureLevel.MEDIUM)
        or network_health == NetworkHealthStatus.DEGRADED
        or (cpu_load is not None and cpu_load > 90)
        or (disk_usage is not None and disk_usage > 90)
    ):
        return HealthStatus.DEGRADED
    
    # Unknown if we couldn't get basic info
    if memory_pressure == MemoryPressureLevel.UNKNOWN:
        return HealthStatus.UNKNOWN
    
    return HealthStatus.HEALTHY


class EnvironmentScouter:
    """
    Environment scouter for sampling physical host state.
    
    环境侦察器，用于采样物理宿主状态。
    
    Periodically samples CPU, memory, disk, and network metrics to provide
    a comprehensive view of the host's resource utilization and health.
    Implements debouncing and smoothing to prevent rapid state oscillations.
    
    定期采样 CPU、内存、磁盘和网络指标，提供主机资源利用率和健康状况的
    全面视图。实现去抖和平滑以防止状态快速振荡。
    """
    
    def __init__(
        self,
        *,
        debounce_window_seconds: float = 5.0,
        sampling_source: str = "local_host",
    ) -> None:
        """
        Initialize the EnvironmentScouter.
        
        Args:
            debounce_window_seconds: Minimum time between state changes to prevent flapping
            sampling_source: Identifier for the sampling source
        """
        self.debounce_window_seconds = debounce_window_seconds
        self.sampling_source = sampling_source
        
        self._lock = Lock()
        self._last_state: Optional[PhysicalHostState] = None
        self._last_change_time: Optional[datetime] = None
    
    def sample_host_state(self) -> PhysicalHostState:
        """
        Sample current physical host state.
        
        采样当前物理宿主状态。
        
        Returns:
            PhysicalHostState: Current host state with all available metrics
            
        Rules:
            - Sampling failures must output unknown/degraded, never healthy defaults
            - Network interfaces that exist but are unreachable must not be marked healthy
            - High-frequency sampling must be debounced to avoid mode switching errors
        """
        # Collect memory metrics
        memory_ratio, memory_total, memory_available = _read_memory_info()
        memory_pressure = _classify_memory_pressure(memory_ratio)
        
        # Collect network metrics
        network_health, net_configured, net_active = _read_network_health()
        
        # Collect CPU metrics (basic implementation)
        cpu_load = self._read_cpu_load()
        cpu_count = self._get_cpu_count()
        
        # Collect disk metrics
        disk_usage, disk_free = self._read_disk_usage()
        
        # Assess overall health
        overall_health = _assess_overall_health(
            memory_pressure, network_health, cpu_load, disk_usage
        )
        
        # Generate warnings
        warnings = self._generate_warnings(
            memory_pressure, network_health, cpu_load, disk_usage
        )
        
        # Build state object
        current_state = PhysicalHostState(
            hostname=socket.gethostname(),
            platform=platform.platform(),
            python_version=platform.python_version(),
            memory_pressure=memory_pressure,
            memory_used_ratio=memory_ratio,
            memory_total_bytes=memory_total,
            memory_available_bytes=memory_available,
            cpu_load_percent=cpu_load,
            cpu_count=cpu_count,
            disk_usage_percent=disk_usage,
            disk_free_bytes=disk_free,
            network_health=network_health,
            network_interfaces_configured=net_configured,
            network_interfaces_active=net_active,
            overall_health=overall_health,
            warnings=warnings,
            sampling_source=self.sampling_source,
        )
        
        # Apply debouncing
        debounced_state = self._apply_debounce(current_state)
        
        return debounced_state
    
    def _read_cpu_load(self) -> Optional[float]:
        """Read CPU load percentage."""
        try:
            if sys.platform.startswith("linux"):
                # Read from /proc/loadavg
                with open("/proc/loadavg", "r") as f:
                    load_avg = f.read().strip().split()[0]
                    load = _safe_float(load_avg)
                    if load is not None and self._get_cpu_count():
                        # Convert to percentage (approximate)
                        return min(100.0, (load / self._get_cpu_count()) * 100)
            elif sys.platform == "darwin":
                # Use top command on macOS
                output = subprocess.check_output(
                    ["top", "-l", "1", "-s", "0"], encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL
                )
                for line in output.splitlines():
                    if "CPU usage" in line:
                        # Parse CPU usage percentage
                        parts = line.split(":")
                        if len(parts) > 1:
                            usage_str = parts[1].strip().split("%")[0]
                            return _safe_float(usage_str)
        except Exception:
            logger.debug("Failed to sample CPU usage via top output", exc_info=True)
        
        return None
    
    def _get_cpu_count(self) -> Optional[int]:
        """Get number of CPU cores."""
        try:
            return os.cpu_count()
        except Exception:
            return None
    
    def _read_disk_usage(self) -> tuple[Optional[float], Optional[int]]:
        """Read disk usage percentage and free space."""
        try:
            statvfs = os.statvfs("/")
            total = statvfs.f_frsize * statvfs.f_blocks
            free = statvfs.f_frsize * statvfs.f_bavail
            used_ratio = ((total - free) / total * 100) if total > 0 else None
            return used_ratio, free
        except Exception:
            return None, None
    
    def _generate_warnings(
        self,
        memory_pressure: MemoryPressureLevel,
        network_health: NetworkHealthStatus,
        cpu_load: Optional[float],
        disk_usage: Optional[float],
    ) -> list[str]:
        """Generate warning messages based on metrics."""
        warnings = []
        
        if memory_pressure == MemoryPressureLevel.CRITICAL:
            warnings.append("CRITICAL: Memory usage above 90%")
        elif memory_pressure == MemoryPressureLevel.HIGH:
            warnings.append("WARNING: Memory usage above 80%")
        
        if network_health == NetworkHealthStatus.OFFLINE:
            warnings.append("CRITICAL: No network connectivity")
        elif network_health == NetworkHealthStatus.DEGRADED:
            warnings.append("WARNING: Network interfaces configured but inactive")
        
        if cpu_load is not None and cpu_load > 90:
            warnings.append(f"WARNING: High CPU load: {cpu_load:.1f}%")
        
        if disk_usage is not None and disk_usage > 90:
            warnings.append(f"WARNING: High disk usage: {disk_usage:.1f}%")
        
        return warnings
    
    def _apply_debounce(self, new_state: PhysicalHostState) -> PhysicalHostState:
        """
        Apply debouncing to prevent rapid state oscillations.
        
        应用去抖以防止状态快速振荡。
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            
            # If no previous state, accept new state
            if self._last_state is None:
                self._last_state = new_state
                self._last_change_time = now
                return new_state
            
            # Check if significant change occurred
            significant_change = self._is_significant_change(
                self._last_state, new_state
            )
            
            if not significant_change:
                # Return last state if within debounce window
                return self._last_state
            
            # Check debounce window
            if self._last_change_time is not None:
                time_since_change = (now - self._last_change_time).total_seconds()
                if time_since_change < self.debounce_window_seconds:
                    # Within debounce window, return last state
                    return self._last_state
            
            # Accept new state
            self._last_state = new_state
            self._last_change_time = now
            return new_state
    
    def _is_significant_change(
        self, old_state: PhysicalHostState, new_state: PhysicalHostState
    ) -> bool:
        """Determine if the state change is significant enough to update."""
        # Check for category changes
        if old_state.memory_pressure != new_state.memory_pressure:
            return True
        if old_state.network_health != new_state.network_health:
            return True
        if old_state.overall_health != new_state.overall_health:
            return True
        
        # Check for significant numeric changes (>10% difference)
        if old_state.cpu_load_percent is not None and new_state.cpu_load_percent is not None:
            if abs(old_state.cpu_load_percent - new_state.cpu_load_percent) > 10:
                return True
        
        if old_state.disk_usage_percent is not None and new_state.disk_usage_percent is not None:
            if abs(old_state.disk_usage_percent - new_state.disk_usage_percent) > 10:
                return True
        
        return False
    
    def get_last_state(self) -> Optional[PhysicalHostState]:
        """Get the last sampled state without triggering a new sample."""
        with self._lock:
            return self._last_state

from __future__ import annotations

from zentex.environment.models import (
    HealthStatus,
    MemoryPressureLevel,
    NetworkHealthStatus,
    PhysicalHostState,
)
from zentex.environment.sampling_audit import audit_host_sampling_defaults
from zentex.environment.scouter import EnvironmentScouter, _assess_overall_health


def test_environment_host_sampling_audit_rejects_fake_zero_defaults() -> None:
    """查询：Host sampling 审计必须证明 unavailable metrics 不用 0 伪装。"""

    report = audit_host_sampling_defaults()

    assert report.audit_status == "passed"
    assert len(report.checked_model_fields) == 10
    by_field = {item.field_name: item for item in report.checked_model_fields}
    for field_name in (
        "memory_used_ratio",
        "memory_total_bytes",
        "memory_available_bytes",
        "cpu_load_percent",
        "cpu_count",
        "disk_usage_percent",
        "disk_free_bytes",
    ):
        assert by_field[field_name].expected_unavailable_value is None
        assert by_field[field_name].actual_model_default is None

    assert by_field["memory_pressure"].actual_model_default == MemoryPressureLevel.UNKNOWN
    assert by_field["network_health"].actual_model_default == NetworkHealthStatus.UNKNOWN
    assert by_field["overall_health"].actual_model_default == HealthStatus.UNKNOWN

    constructor_sources = {
        item.constructor_keyword: item.source_expression
        for item in report.checked_constructor_keywords
    }
    assert constructor_sources == {
        "memory_used_ratio": "memory_ratio",
        "memory_total_bytes": "memory_total",
        "memory_available_bytes": "memory_available",
        "cpu_load_percent": "cpu_load",
        "cpu_count": "cpu_count",
        "disk_usage_percent": "disk_usage",
        "disk_free_bytes": "disk_free",
    }
    assert set(report.checked_failure_functions) == {
        "_read_linux_memory_info",
        "_read_darwin_memory_info",
        "_read_memory_info",
        "_read_cpu_load",
        "_get_cpu_count",
        "_read_disk_usage",
    }


def test_environment_real_host_sample_uses_none_or_real_metric_values() -> None:
    """查询：真实采样结果必须是 None/UNKNOWN 或真实范围值，不能靠 0 兜底。"""

    scouter = EnvironmentScouter(debounce_window_seconds=0.0, sampling_source="phase_i_real_test")
    state = scouter.sample_host_state()
    queried = scouter.get_last_state()

    assert queried is not None
    assert queried == state
    assert state.hostname.strip()
    assert state.platform.strip()
    assert state.python_version.strip()
    assert state.sampling_source == "phase_i_real_test"
    assert state.cpu_load_percent is None or state.cpu_load_percent >= 0.0
    assert state.cpu_count is None or state.cpu_count >= 1
    assert state.memory_used_ratio is None or 0.0 <= state.memory_used_ratio <= 1.0
    assert state.memory_total_bytes is None or state.memory_total_bytes > 0
    assert state.memory_available_bytes is None or state.memory_available_bytes >= 0
    assert state.disk_usage_percent is None or 0.0 <= state.disk_usage_percent <= 100.0
    assert state.disk_free_bytes is None or state.disk_free_bytes >= 0
    assert state.memory_pressure in set(MemoryPressureLevel)
    assert state.network_health in set(NetworkHealthStatus)
    assert state.overall_health in set(HealthStatus)
    if state.memory_pressure == MemoryPressureLevel.UNKNOWN:
        assert state.overall_health == HealthStatus.UNKNOWN
        assert state.memory_used_ratio is None


def test_environment_unavailable_metrics_are_unknown_not_healthy_zero() -> None:
    """边界：采样指标不可用时业务状态必须 UNKNOWN，不得构造 healthy + zero。"""

    state = PhysicalHostState(
        hostname="phase-i-host",
        platform="phase-i-platform",
        python_version="3.x",
        memory_pressure=MemoryPressureLevel.UNKNOWN,
        memory_used_ratio=None,
        memory_total_bytes=None,
        memory_available_bytes=None,
        cpu_load_percent=None,
        cpu_count=None,
        disk_usage_percent=None,
        disk_free_bytes=None,
        network_health=NetworkHealthStatus.UNKNOWN,
        overall_health=HealthStatus.UNKNOWN,
        sampling_source="phase_i_unavailable_metric_test",
    )

    assert state.memory_used_ratio is None
    assert state.cpu_load_percent is None
    assert state.cpu_count is None
    assert state.disk_usage_percent is None
    assert state.overall_health == HealthStatus.UNKNOWN
    assert not state.is_degraded()
    assert (
        _assess_overall_health(
            MemoryPressureLevel.UNKNOWN,
            NetworkHealthStatus.UNKNOWN,
            None,
            None,
        )
        == HealthStatus.UNKNOWN
    )

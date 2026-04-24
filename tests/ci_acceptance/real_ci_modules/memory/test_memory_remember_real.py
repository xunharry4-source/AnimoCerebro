from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_remember_real(real_ci_runtime) -> None:
    """功能：验证 remember 真实写入。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(
        title=f"mem-{suffix}",
        summary=f"sum-{suffix}",
        content=f"content-{suffix}",
        layer="semantic",
        source="tests.ci_acceptance",
        trace_id=f"trace-{suffix}",
        tags=["q1", suffix],
    )
    assert rec.memory_id

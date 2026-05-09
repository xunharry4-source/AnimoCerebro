from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_recall_real(real_ci_runtime) -> None:
    """功能：验证 recall 查询结果必须命中新写入记忆。"""
    suffix = unique_suffix()
    rec = real_ci_runtime.memory_service.remember(
        title=f"recall-{suffix}",
        content=f"recall-content-{suffix}",
        source="tests",
        tags=["q1", suffix],
    )
    hits = real_ci_runtime.memory_service.recall(suffix, limit=20)
    assert isinstance(hits, list)
    assert any(getattr(item, "memory_id", "") == rec.memory_id for item in hits), "召回结果未命中新写入记录"

from __future__ import annotations


def test_memory_backfill_transcript_entries_real(real_ci_runtime) -> None:
    """功能：验证 backfill_transcript_entries 可调用。"""
    before = real_ci_runtime.memory_service.list_projection_failures()
    real_ci_runtime.memory_service.backfill_transcript_entries([])
    after = real_ci_runtime.memory_service.list_projection_failures()
    assert after == before, "空 backfill_transcript_entries 不应改变 projection_failures"

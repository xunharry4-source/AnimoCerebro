from __future__ import annotations

import time

from zentex.memory.consolidation.stats_pipeline import compute_pattern_scores, refs_to_dataframe


def test_memory_consolidation_pattern_scores_real() -> None:
    """功能：验证巩固评分不再使用硬编码时间跨度和复用值。"""
    now_ts = time.time()
    refs = [
        {
            "ref_id": "r1",
            "created_at_ts": now_ts - 86400 * 5,
            "reuse_value": 0.8,
            "tags": ["decision"],
            "outcome_type": "success",
        },
        {
            "ref_id": "r2",
            "created_at_ts": now_ts - 86400 * 60,
            "reuse_value": 0.8,
            "tags": ["decision"],
            "outcome_type": "failure",
        },
    ]
    df = refs_to_dataframe(refs, now_ts=now_ts)
    scores = compute_pattern_scores(df)
    assert scores, "expected at least one pattern score"
    assert scores[0].time_span_seconds != 3600
    assert scores[0].cross_context_reuse != 0.5
    assert 0.0 <= scores[0].stability_score <= 1.0

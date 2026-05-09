from __future__ import annotations

from zentex.memory.consolidation.semantic_clusterer import SemanticClusteringPlugin

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_semantic_clusterer_real(real_ci_runtime) -> None:
    """功能：验证语义聚类插件可对真实插入的记忆片段生成聚类候选。"""
    suffix = unique_suffix()
    rec1 = real_ci_runtime.memory_service.remember(
        title=f"decision-loss-{suffix}",
        content=f"decision failure caused resource waste {suffix}",
        summary=f"decision failure caused resource waste {suffix}",
        source="tests",
        tags=["decision", suffix],
    )
    rec2 = real_ci_runtime.memory_service.remember(
        title=f"decision-cost-{suffix}",
        content=f"decision failure caused cost waste {suffix}",
        summary=f"decision failure caused cost waste {suffix}",
        source="tests",
        tags=["decision", suffix],
    )
    rec3 = real_ci_runtime.memory_service.remember(
        title=f"toolchain-success-{suffix}",
        content=f"toolchain success stable pipeline {suffix}",
        summary=f"toolchain success stable pipeline {suffix}",
        source="tests",
        tags=["tooling", suffix],
    )

    refs = [
        {
            "ref_id": rec1.memory_id,
            "title": rec1.title,
            "summary": rec1.summary,
            "reuse_value": 0.8,
            "created_at_ts": rec1.created_at.timestamp(),
            "tags": list(rec1.tags or []),
            "outcome_type": "failure",
        },
        {
            "ref_id": rec2.memory_id,
            "title": rec2.title,
            "summary": rec2.summary,
            "reuse_value": 0.75,
            "created_at_ts": rec2.created_at.timestamp(),
            "tags": list(rec2.tags or []),
            "outcome_type": "failure",
        },
        {
            "ref_id": rec3.memory_id,
            "title": rec3.title,
            "summary": rec3.summary,
            "reuse_value": 0.9,
            "created_at_ts": rec3.created_at.timestamp(),
            "tags": list(rec3.tags or []),
            "outcome_type": "success",
        },
    ]

    plugin = SemanticClusteringPlugin()
    output = plugin.analyze_memory(context={"input_memory_refs": refs}, noise_rules=[])
    assert output.plugin_id == "semantic_clusterer"
    assert output.promotion_candidates, "expected at least one semantic cluster promotion candidate"
    assert output.pattern_scores, "expected pattern scores from semantic clustering"
    assert all(score.stability_score != 0.8 for score in output.pattern_scores)


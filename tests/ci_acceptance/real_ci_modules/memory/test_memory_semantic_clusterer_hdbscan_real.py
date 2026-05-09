from __future__ import annotations

from zentex.memory.consolidation.semantic_clusterer import SemanticClusteringPlugin

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_semantic_clusterer_hdbscan_real(real_ci_runtime) -> None:
    """功能：验证真实安装 hdbscan 后，语义聚类可强制走 HDBSCAN 路径。"""
    suffix = unique_suffix()
    inserted = []
    for title, summary, tags, reuse_value, outcome_type in [
        (
            f"decision-loss-{suffix}",
            f"decision failure caused resource waste in planning alpha {suffix}",
            ["decision", "failure", suffix],
            0.82,
            "failure",
        ),
        (
            f"decision-cost-{suffix}",
            f"decision failure caused resource waste in planning beta {suffix}",
            ["decision", "failure", suffix],
            0.79,
            "failure",
        ),
        (
            f"decision-overrun-{suffix}",
            f"decision failure caused resource waste in planning gamma {suffix}",
            ["decision", "failure", suffix],
            0.77,
            "failure",
        ),
        (
            f"decision-delay-{suffix}",
            f"decision failure caused resource waste in planning delta {suffix}",
            ["decision", "failure", suffix],
            0.75,
            "failure",
        ),
        (
            f"decision-rework-{suffix}",
            f"decision failure caused resource waste in planning epsilon {suffix}",
            ["decision", "failure", suffix],
            0.73,
            "failure",
        ),
        (
            f"decision-scope-{suffix}",
            f"decision failure caused resource waste in planning zeta {suffix}",
            ["decision", "failure", suffix],
            0.71,
            "failure",
        ),
        (
            f"tooling-stable-{suffix}",
            f"toolchain configuration remained stable after rollout one {suffix}",
            ["tooling", suffix],
            0.91,
            "success",
        ),
        (
            f"tooling-repeat-{suffix}",
            f"toolchain configuration remained stable after rollout two {suffix}",
            ["tooling", suffix],
            0.89,
            "success",
        ),
    ]:
        inserted.append(
            (
                real_ci_runtime.memory_service.remember(
                    title=title,
                    content=summary,
                    summary=summary,
                    source="tests",
                    tags=tags,
                ),
                reuse_value,
                outcome_type,
            )
        )

    refs = [
        {
            "ref_id": record.memory_id,
            "title": record.title,
            "summary": record.summary,
            "reuse_value": reuse_value,
            "created_at_ts": record.created_at.timestamp(),
            "tags": list(record.tags or []),
            "outcome_type": outcome_type,
        }
        for record, reuse_value, outcome_type in inserted
    ]

    plugin = SemanticClusteringPlugin(
        cluster_backend="hdbscan",
        min_cluster_size=2,
        min_samples=1,
    )
    output = plugin.analyze_memory(context={"input_memory_refs": refs}, noise_rules=[])

    assert plugin.last_backend_used == "hdbscan"
    assert output.plugin_id == "semantic_clusterer"
    assert output.promotion_candidates, "expected at least one HDBSCAN cluster promotion candidate"
    assert output.pattern_scores, "expected pattern scores from HDBSCAN clustering"
    assert all(score.stability_score != 0.8 for score in output.pattern_scores)

from __future__ import annotations

"""
Q1 (我在哪) evidence building and extraction.

Contains functions for building Q1 preprocessed evidence from context snapshots
and extracting Q1 inference results from tool outputs.
"""

from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from zentex.web_console.contracts.nine_questions import (
    Q1StructureTreeRow,
    Q1CandidateGroupDetail,
    Q1RiskFileDetail,
    Q1LongTextEvidence,
    Q1PreprocessedEvidence,
    Q1PhysicalAndEnvironmentEvidence,
    Q1WorkspaceStructureEvidence,
    Q1WorkspaceContentSamplingEvidence,
    Q1WorkspaceSampleSummary,
    WorkspaceDomainInferenceView,
    Q1LLMUpgradeView,
)

from .helpers import _coerce_string_list, _normalize_health_status


def _build_directory_tree_rows(structure_dict: dict[str, object], top_level_dirs: list[str]) -> list[Q1StructureTreeRow]:
    """Build directory tree rows from structure analysis."""
    raw_nodes = structure_dict.get("directory_tree") or structure_dict.get("directory_hierarchy") or structure_dict.get("directories")
    rows: list[Q1StructureTreeRow] = []

    if isinstance(raw_nodes, list):
        for index, node in enumerate(raw_nodes):
            if not isinstance(node, dict):
                continue
            path = str(node.get("path") or node.get("name") or node.get("label") or "").strip()
            if not path:
                continue
            label = str(node.get("label") or Path(path).name or path)
            depth = node.get("depth")
            if not isinstance(depth, int):
                depth = max(path.count("/") - 1, 0)
            file_count = node.get("file_count")
            rows.append(
                Q1StructureTreeRow(
                    row_id=f"dir-{index}",
                    path=path,
                    label=label,
                    depth=depth,
                    kind=str(node.get("kind") or "directory"),
                    file_count=file_count if isinstance(file_count, int) else None,
                    summary=str(node.get("summary")).strip() if node.get("summary") else None,
                )
            )

    if rows:
        return rows

    return [
        Q1StructureTreeRow(
            row_id=f"dir-top-{index}",
            path=directory,
            label=directory,
            depth=0,
            kind="directory",
        )
        for index, directory in enumerate(top_level_dirs)
    ]


def _build_candidate_group_details(structure_dict: dict[str, object], candidate_groups: list[str]) -> list[Q1CandidateGroupDetail]:
    """Build candidate group details from structure analysis."""
    raw_groups = structure_dict.get("candidate_group_details") or structure_dict.get("candidate_groups_detailed")
    details: list[Q1CandidateGroupDetail] = []

    if isinstance(raw_groups, list):
        for index, group in enumerate(raw_groups):
            if isinstance(group, dict):
                label = str(group.get("label") or group.get("name") or "").strip()
                if not label:
                    continue
                file_count = group.get("file_count")
                details.append(
                    Q1CandidateGroupDetail(
                        group_id=f"group-{index}",
                        label=label,
                        file_count=file_count if isinstance(file_count, int) else None,
                        summary=str(group.get("summary")).strip() if group.get("summary") else None,
                    )
                )
            elif str(group).strip():
                details.append(Q1CandidateGroupDetail(group_id=f"group-{index}", label=str(group).strip()))

    if details:
        return details

    return [
        Q1CandidateGroupDetail(group_id=f"group-fallback-{index}", label=group)
        for index, group in enumerate(candidate_groups)
    ]


def _build_risk_file_details(structure_dict: dict[str, object], obvious_risk_files: list[str]) -> list[Q1RiskFileDetail]:
    """Build risk file details from structure analysis."""
    raw_risks = structure_dict.get("obvious_risk_file_details") or structure_dict.get("risk_file_details")
    details: list[Q1RiskFileDetail] = []

    if isinstance(raw_risks, list):
        for risk in raw_risks:
            if isinstance(risk, dict):
                path = str(risk.get("path") or risk.get("file") or "").strip()
                if not path:
                    continue
                details.append(
                    Q1RiskFileDetail(
                        path=path,
                        severity=str(risk.get("severity")).strip() if risk.get("severity") else None,
                        reason=str(risk.get("reason")).strip() if risk.get("reason") else None,
                    )
                )
            elif str(risk).strip():
                details.append(Q1RiskFileDetail(path=str(risk).strip()))

    if details:
        return details

    return [Q1RiskFileDetail(path=path) for path in obvious_risk_files]


def _build_long_text_evidence(
    sampled_items: list[dict[str, object]],
    anomalies: list[str],
) -> list[Q1LongTextEvidence]:
    """Build long text evidence blocks from sampled items and anomalies."""
    blocks: list[Q1LongTextEvidence] = []
    sample_text_keys = [
        ("title", "标题"),
        ("header", "表头"),
        ("summary", "摘要"),
        ("snippet", "样本行"),
        ("excerpt", "文档前段"),
        ("first_lines", "文件前段"),
    ]

    for sample_index, sample in enumerate(sampled_items):
        sample_path = str(sample.get("path") or sample.get("file") or "").strip() or None
        base_label = sample_path or f"sample-{sample_index + 1}"
        for field_name, field_label in sample_text_keys:
            text = sample.get(field_name)
            if not isinstance(text, str) or not text.strip():
                continue
            blocks.append(
                Q1LongTextEvidence(
                    evidence_id=f"sample-{sample_index}-{field_name}",
                    label=f"{base_label} · {field_label}",
                    kind=field_name,
                    source="workspace_content_sampler",
                    path=sample_path,
                    text=text.strip(),
                )
            )

    for index, snippet in enumerate(anomalies):
        if not isinstance(snippet, str) or not snippet.strip():
            continue
        blocks.append(
            Q1LongTextEvidence(
                evidence_id=f"anomaly-{index}",
                label=f"日志异常片段 #{index + 1}",
                kind="log_anomaly",
                source="workspace_content_sampler",
                text=snippet.strip(),
            )
        )

    return blocks


def _build_q1_preprocessed_evidence(context_snapshot: dict[str, object]) -> Q1PreprocessedEvidence:
    """Build Q1 preprocessed evidence from context snapshot."""
    structure = context_snapshot.get("workspace_structure_analysis", {})
    samples = context_snapshot.get("workspace_content_samples", {})
    environment_event = context_snapshot.get("environment_event", {})
    physical_host_state = context_snapshot.get("physical_host_state", {})

    structure_dict = structure if isinstance(structure, dict) else {}
    samples_dict = samples if isinstance(samples, dict) else {}
    environment_dict = environment_event if isinstance(environment_event, dict) else {}
    host_dict = physical_host_state if isinstance(physical_host_state, dict) else {}

    sampled_items_raw = samples_dict.get("sampled_file_summaries") or samples_dict.get("file_samples") or []
    sampled_items: list[dict[str, object]] = []
    if isinstance(sampled_items_raw, list):
        sampled_items = [item for item in sampled_items_raw if isinstance(item, dict)]

    anomalies = samples_dict.get("log_anomaly_snippets") or samples_dict.get("anomalies") or []
    anomaly_list = [str(item).strip() for item in anomalies if isinstance(item, str) and item.strip()] if isinstance(anomalies, list) else []

    top_level_dirs = _coerce_string_list(structure_dict.get("top_level_dirs"))
    candidate_groups = _coerce_string_list(structure_dict.get("candidate_groups"))
    obvious_risk_files = _coerce_string_list(structure_dict.get("obvious_risk_files") or structure_dict.get("risk_files"))
    suffix_distribution = structure_dict.get("suffix_distribution") or structure_dict.get("extension_distribution") or {}
    keyword_distribution = (
        structure_dict.get("high_frequency_filename_keywords") or structure_dict.get("keyword_frequencies") or {}
    )
    file_total_count = structure_dict.get("file_total_count") or structure_dict.get("file_count")

    environment_summary = []
    for key in ("cwd", "hostname", "platform", "python_version"):
        value = host_dict.get(key)
        if value:
            environment_summary.append(f"{key}={value}")
    for key in ("kind", "summary"):
        value = environment_dict.get(key)
        if value:
            environment_summary.append(f"environment_{key}={value}")

    sampled_summaries = [Q1WorkspaceSampleSummary.model_validate(sample) for sample in sampled_items]
    long_text_evidence = _build_long_text_evidence(sampled_items, anomaly_list)

    return Q1PreprocessedEvidence(
        physical_and_environment=Q1PhysicalAndEnvironmentEvidence(
            environment_event=environment_dict,
            physical_host_state=host_dict,
            memory_pressure=str(host_dict.get("memory_pressure")) if host_dict.get("memory_pressure") is not None else None,
            network_health=str(host_dict.get("network_health")) if host_dict.get("network_health") is not None else None,
            memory_pressure_status=_normalize_health_status(host_dict.get("memory_pressure")),
            network_health_status=_normalize_health_status(host_dict.get("network_health")),
            environment_summary=environment_summary,
        ),
        workspace_structure=Q1WorkspaceStructureEvidence(
            directory_hierarchy_summary=str(structure_dict.get("directory_hierarchy_summary")).strip()
            if structure_dict.get("directory_hierarchy_summary")
            else None,
            top_level_dirs=top_level_dirs,
            file_total_count=file_total_count if isinstance(file_total_count, int) else None,
            suffix_distribution={
                str(key): int(value)
                for key, value in suffix_distribution.items()
                if str(key).strip() and isinstance(value, int)
            }
            if isinstance(suffix_distribution, dict)
            else {},
            high_frequency_filename_keywords={
                str(key): int(value)
                for key, value in keyword_distribution.items()
                if str(key).strip() and isinstance(value, int)
            }
            if isinstance(keyword_distribution, dict)
            else {},
            candidate_groups=candidate_groups,
            obvious_risk_files=obvious_risk_files,
            directory_tree_rows=_build_directory_tree_rows(structure_dict, top_level_dirs),
            candidate_group_details=_build_candidate_group_details(structure_dict, candidate_groups),
            obvious_risk_file_details=_build_risk_file_details(structure_dict, obvious_risk_files),
            analyzer_snapshot=structure_dict,
        ),
        workspace_content_sampling=Q1WorkspaceContentSamplingEvidence(
            sampled_file_summaries=sampled_summaries,
            log_anomaly_snippets=anomaly_list,
            long_text_evidence=long_text_evidence,
            sample_count=len(sampled_summaries),
            anomaly_count=len(anomaly_list),
            sampler_snapshot=samples_dict,
        ),
    )


def _extract_q1_inference_result(result_payload: object) -> Optional[WorkspaceDomainInferenceView]:
    """Extract Q1 inference result from tool output payload."""
    if not isinstance(result_payload, dict):
        return None

    # Extraction handles both flat results (traces) and nested results (snapshots)
    data = result_payload.get("workspace_domain_inference") or result_payload
    if not isinstance(data, dict):
        return None

    ordered_keys = [
        "primary_domain",
        "secondary_domains",
        "confidence",
        "reasoning_summary",
        "uncertainties",
        "suggested_first_step",
        "host_runtime_type",
        "host_runtime_reason",
    ]
    required_keys = ordered_keys[:6]
    if not set(required_keys).issubset(data.keys()):
        return None

    raw_dict = {key: data.get(key) for key in ordered_keys}
    # Coerce uncertainties to List[str] — LLM may return list of dicts
    raw_uncertainties = raw_dict.get("uncertainties")
    if isinstance(raw_uncertainties, list):
        raw_dict["uncertainties"] = [
            item if isinstance(item, str)
            else str(item.get("description") or item.get("text") or item)
            for item in raw_uncertainties
        ]
    return WorkspaceDomainInferenceView.model_validate(raw_dict)


def _extract_q1_llm_upgrade(context_payload: object) -> Optional[Q1LLMUpgradeView]:
    """Extract Q1 LLM upgrade information from context payload."""
    if not isinstance(context_payload, dict):
        return None
    upgrade_payload = context_payload.get("q1_llm_upgrade")
    if not isinstance(upgrade_payload, dict):
        return None
    return Q1LLMUpgradeView.model_validate(upgrade_payload)


def _extract_q1_preprocessed_evidence(context_payload: object) -> Optional[Q1PreprocessedEvidence]:
    """Extract Q1 preprocessed evidence from context payload if available."""
    if not isinstance(context_payload, dict):
        return None
    if not any(
        key in context_payload
        for key in ("workspace_structure_analysis", "workspace_content_samples", "environment_event", "physical_host_state")
    ):
        return None
    return _build_q1_preprocessed_evidence(context_payload)

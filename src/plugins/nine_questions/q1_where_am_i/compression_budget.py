from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from plugins.nine_questions.q1_where_am_i.utils import estimate_token_count, one_line


@dataclass(frozen=True)
class LocalCompressionBudget:
    """
    Local compression guardrail.

    Absolute red line:
    - This class compresses *structured summaries only*.
    - The plugin must never read raw file bodies.
    """

    max_evidence_tokens: int = 900
    max_stats_tokens: int = 600
    max_uncertainty_tokens: int = 400

    def compress(
        self,
        *,
        structure: Dict[str, Any],
        samples: Dict[str, Any],
        environment_event: Dict[str, Any],
        physical_host_state: Dict[str, Any],
    ) -> Dict[str, str]:
        evidence_lines: List[str] = []
        stats_lines: List[str] = []
        uncertainty_lines: List[str] = []

        hierarchy = structure.get("directory_hierarchy_summary")
        if hierarchy is not None:
            evidence_lines.append(f"- directory_hierarchy_summary: {one_line(hierarchy, 260)}")

        risk_files = structure.get("obvious_risk_files") or structure.get("risk_files")
        if isinstance(risk_files, list) and risk_files:
            evidence_lines.append(f"- obvious_risk_files(sample): {one_line(risk_files[:12], 260)}")

        sampled = samples.get("sampled_file_summaries") or samples.get("file_samples") or []
        if isinstance(sampled, list) and sampled:
            for item in sampled[:10]:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or item.get("file") or "unknown")
                headline = item.get("title") or item.get("header") or item.get("summary") or ""
                snippet = item.get("snippet") or item.get("excerpt") or item.get("first_lines") or ""
                evidence_lines.append(
                    f"- sample:{path} | {one_line(headline, 140)} | {one_line(snippet, 180)}"
                )

        anomalies = samples.get("log_anomaly_snippets") or samples.get("anomalies") or []
        if isinstance(anomalies, list) and anomalies:
            for item in anomalies[:6]:
                evidence_lines.append(f"- log_anomaly: {one_line(item, 220)}")

        file_count = structure.get("file_total_count") or structure.get("file_count")
        if file_count is not None:
            stats_lines.append(f"- file_total_count: {file_count}")

        suffix_dist = structure.get("suffix_distribution") or structure.get("extension_distribution") or {}
        if isinstance(suffix_dist, dict) and suffix_dist:
            top_suffixes = sorted(
                ((str(k), int(v)) for k, v in suffix_dist.items()),
                key=lambda item: item[1],
                reverse=True,
            )[:12]
            stats_lines.append(f"- suffix_distribution(top): {top_suffixes}")

        keyword_freq = structure.get("high_frequency_filename_keywords") or structure.get("keyword_frequencies") or {}
        if isinstance(keyword_freq, dict) and keyword_freq:
            top_keywords = sorted(
                ((str(k), int(v)) for k, v in keyword_freq.items()),
                key=lambda item: item[1],
                reverse=True,
            )[:12]
            stats_lines.append(f"- filename_keywords(top): {top_keywords}")

        groups = structure.get("candidate_groups") or []
        if isinstance(groups, list) and groups:
            stats_lines.append(f"- candidate_groups(sample): {one_line(groups[:8], 260)}")

        env_summary = environment_event.get("summary") if isinstance(environment_event, dict) else None
        if env_summary:
            uncertainty_lines.append(f"- environment_event: {one_line(env_summary, 220)}")
        host_mem = physical_host_state.get("memory_pressure") if isinstance(physical_host_state, dict) else None
        host_net = physical_host_state.get("network_health") if isinstance(physical_host_state, dict) else None
        if host_mem is not None or host_net is not None:
            uncertainty_lines.append(
                f"- physical_host_state: memory_pressure={host_mem}; network_health={host_net}"
            )

        analysis_summary = self._cap_lines(evidence_lines, self.max_evidence_tokens)
        sample_summary = self._cap_lines(evidence_lines, self.max_evidence_tokens // 2)
        schema_summary = self._cap_lines(stats_lines, self.max_stats_tokens)
        uncertainty_summary = self._cap_lines(uncertainty_lines, self.max_uncertainty_tokens)
        return {
            "analysis_summary": analysis_summary,
            "sample_summary": sample_summary,
            "schema_summary": schema_summary,
            "uncertainty_summary": uncertainty_summary,
        }

    def _cap_lines(self, lines: List[str], max_tokens: int) -> str:
        if not lines:
            return ""
        selected: List[str] = []
        total = 0
        for line in lines:
            tokens = estimate_token_count(line)
            if selected and total + tokens > max_tokens:
                break
            selected.append(line)
            total += tokens
        return "\n".join(selected)


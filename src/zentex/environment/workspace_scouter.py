from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


TEXT_SAMPLE_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml",
    ".md", ".txt", ".toml", ".ini", ".cfg", ".conf", ".log", ".sh",
}
RISK_FILE_NAMES = {
    ".env", ".env.local", "secrets.json", "credentials.json", "id_rsa", "known_hosts",
}
MAX_SCAN_FILES = 400
MAX_SAMPLE_FILES = 8
MAX_SAMPLE_BYTES = 2048


class WorkspaceScouter:
    """Compatibility shim for legacy environment workspace scanning imports."""

    def __init__(self, workspace_root: Union[str, os].PathLike[Optional[str]] = None) -> None:
        self._workspace_root = Path(workspace_root or os.getcwd()).resolve()

    def get_full_analysis(self) -> dict[str, Any]:
        return {
            "workspace_structure_analysis": self._build_workspace_structure_analysis(),
            "workspace_content_samples": self._build_workspace_content_samples(),
        }

    def _build_workspace_structure_analysis(self) -> dict[str, Any]:
        root = self._workspace_root
        if not root.exists() or not root.is_dir():
            return {}

        suffix_counter: Counter[str] = Counter()
        keyword_counter: Counter[str] = Counter()
        top_level_dirs: list[str] = []
        candidate_groups: list[str] = []
        risk_files: list[str] = []
        tree_rows: list[dict[str, Any]] = []
        group_details: list[dict[str, Any]] = []
        scanned_files = 0

        for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if child.name.startswith(".") and child.name not in {".github", ".vscode"}:
                continue
            if child.is_dir():
                top_level_dirs.append(child.name)
                file_count = 0
                for nested in child.rglob("*"):
                    if scanned_files >= MAX_SCAN_FILES:
                        break
                    if not nested.is_file():
                        continue
                    scanned_files += 1
                    file_count += 1
                    suffix = nested.suffix.lower()
                    if suffix:
                        suffix_counter[suffix] += 1
                    for token in re.findall(r"[A-Za-z]+", nested.stem.lower()):
                        if len(token) >= 4:
                            keyword_counter[token] += 1
                    if nested.name.lower() in RISK_FILE_NAMES:
                        risk_files.append(str(nested.relative_to(root)))
                tree_rows.append(
                    {
                        "row_id": f"dir-{child.name}",
                        "path": child.name,
                        "label": child.name,
                        "depth": 0,
                        "kind": "directory",
                        "file_count": file_count,
                    }
                )
            elif child.is_file():
                scanned_files += 1
                suffix = child.suffix.lower()
                if suffix:
                    suffix_counter[suffix] += 1
                for token in re.findall(r"[A-Za-z]+", child.stem.lower()):
                    if len(token) >= 4:
                        keyword_counter[token] += 1
                if child.name.lower() in RISK_FILE_NAMES:
                    risk_files.append(child.name)

        top_suffixes = {suffix: count for suffix, count in suffix_counter.most_common(8)}
        top_keywords = {keyword: count for keyword, count in keyword_counter.most_common(8)}

        if any(ext in suffix_counter for ext in (".py", ".ts", ".tsx", ".js", ".jsx")):
            candidate_groups.append("application_code")
        if ".md" in suffix_counter:
            candidate_groups.append("documentation")
        if ".log" in suffix_counter:
            candidate_groups.append("runtime_logs")
        if any(name in top_level_dirs for name in ("tests", "test")):
            candidate_groups.append("test_suite")

        for label in candidate_groups:
            group_details.append(
                {
                    "group_id": label,
                    "label": label,
                    "summary": f"Detected from workspace structure: {label}",
                }
            )

        hierarchy_summary = (
            f"Workspace root '{root.name}' contains {len(top_level_dirs)} top-level directories; "
            f"dominant suffixes: {', '.join(top_suffixes.keys()) or 'unknown'}."
        )

        return {
            "directory_hierarchy_summary": hierarchy_summary,
            "top_level_dirs": top_level_dirs,
            "file_total_count": sum(suffix_counter.values()),
            "suffix_distribution": top_suffixes,
            "high_frequency_filename_keywords": top_keywords,
            "candidate_groups": candidate_groups,
            "obvious_risk_files": risk_files[:8],
            "directory_tree_rows": tree_rows,
            "candidate_group_details": group_details,
            "obvious_risk_file_details": [{"path": path, "severity": "medium"} for path in risk_files[:8]],
            "analyzer_snapshot": {
                "workspace_root": str(root),
                "scan_limited": scanned_files >= MAX_SCAN_FILES,
                "scanned_files": scanned_files,
            },
        }

    def _build_workspace_content_samples(self) -> dict[str, Any]:
        root = self._workspace_root
        if not root.exists() or not root.is_dir():
            return {}

        sampled: list[dict[str, Any]] = []
        anomalies: list[str] = []
        candidate_files: list[Path] = []

        for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
            if len(candidate_files) >= MAX_SAMPLE_FILES:
                break
            if not path.is_file():
                continue
            if any(part.startswith(".") and part not in {".github", ".vscode"} for part in path.parts):
                continue
            if path.suffix.lower() not in TEXT_SAMPLE_SUFFIXES:
                continue
            candidate_files.append(path)

        for path in candidate_files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:MAX_SAMPLE_BYTES]
            except Exception:
                continue
            stripped = text.strip()
            if not stripped:
                continue
            first_line = stripped.splitlines()[0][:160]
            sampled.append(
                {
                    "path": str(path.relative_to(root)),
                    "title": path.name,
                    "summary": f"{path.suffix.lower() or 'text'} file under {path.parent.name or '.'}",
                    "snippet": first_line,
                    "first_lines": "\n".join(stripped.splitlines()[:6])[:400],
                }
            )
            if any(marker in stripped.lower() for marker in ("error", "exception", "traceback", "fatal", "critical")):
                anomalies.append(f"{path.relative_to(root)}: {first_line}")

        return {
            "sampled_file_summaries": sampled,
            "log_anomaly_snippets": anomalies[:8],
            "sampler_snapshot": {
                "workspace_root": str(root),
                "sampled_paths": [item["path"] for item in sampled],
                "sample_limit": MAX_SAMPLE_FILES,
            },
        }

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

from zentex.core.plugin_base import PluginLifecycleStatus


def build_runtime_workspace_snapshot(
    *,
    workspace_root: str,
    cognitive_registry: object | None,
    execution_registry: object | None,
    task_service: object | None,
    environment_summary: str,
    host_telemetry_plugin: object | None = None,
    mcp_service: object | None = None,
    cli_service: object | None = None,
) -> dict[str, object]:
    root = Path(workspace_root).resolve()
    top_level_dirs: list[str] = []
    suffix_distribution: dict[str, int] = {}
    keyword_distribution: dict[str, int] = {}
    sampled_file_summaries: list[dict[str, str]] = []
    obvious_risk_files: list[str] = []
    file_total_count = 0
    candidate_groups: set[str] = set()

    ignored_dirs = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", "dist", "build"}
    risk_markers = ("key", "secret", "token", "password", "credential")

    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in ignored_dirs and not name.startswith(".")]
        current_path = Path(current_root)
        if current_path == root:
            top_level_dirs.extend(sorted(dirnames))
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            file_total_count += 1
            path = current_path / filename
            rel_path = str(path.relative_to(root))
            suffix = path.suffix.lower()
            if suffix:
                suffix_distribution[suffix] = suffix_distribution.get(suffix, 0) + 1
            stem_parts = [part.lower() for part in path.stem.replace("-", "_").split("_") if part]
            for part in stem_parts[:3]:
                if len(part) >= 3:
                    keyword_distribution[part] = keyword_distribution.get(part, 0) + 1
            if any(marker in rel_path.lower() for marker in risk_markers):
                obvious_risk_files.append(rel_path)
            if suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}:
                candidate_groups.add("source_code")
            if suffix in {".md", ".txt", ".rst"}:
                candidate_groups.add("documentation")
            if suffix in {".json", ".yaml", ".yml", ".toml", ".ini"}:
                candidate_groups.add("configuration")
            if suffix in {".log"}:
                candidate_groups.add("logs")
            if len(sampled_file_summaries) >= 12:
                continue
            try:
                with path.open("r", encoding="utf-8", errors="ignore") as handle:
                    lines = handle.read(400).splitlines()
            except OSError:
                continue
            summary = lines[0].strip() if lines else ""
            snippet = lines[1].strip() if len(lines) > 1 else summary
            sampled_file_summaries.append(
                {
                    "path": rel_path,
                    "summary": summary[:160],
                    "snippet": snippet[:200],
                    "header": summary[:200],
                }
            )

    active_cognitive_tools: list[str] = []
    cognitive_tool_rows: list[dict[str, str]] = []
    if cognitive_registry is not None and hasattr(cognitive_registry, "list_registrations"):
        try:
            registrations = list(cognitive_registry.list_registrations())
            active_cognitive_tools = sorted(
                registration.plugin_id
                for registration in registrations
                if registration.status == PluginLifecycleStatus.ACTIVE
                and callable(getattr(registration.spec, "plugin_kind", None))
                and registration.spec.plugin_kind() == "cognitive_tool"
            )
            cognitive_tool_rows = [
                {
                    "id": registration.plugin_id,
                    "name": " ".join(
                        chunk.capitalize()
                        for chunk in registration.plugin_id.replace(":", " ").replace(".", " ").replace("-", " ").replace("_", " ").split()
                    ) or registration.plugin_id,
                    "introduction": str(getattr(registration.spec, "purpose", "") or "").strip()
                    or f"{registration.plugin_id} 是当前运行态中的认知工具。",
                    "function_description": str(getattr(registration.spec, "purpose", "") or "").strip()
                    or f"{registration.plugin_id} 负责提供认知推理能力。",
                }
                for registration in registrations
                if registration.status == PluginLifecycleStatus.ACTIVE
                and callable(getattr(registration.spec, "plugin_kind", None))
                and registration.spec.plugin_kind() == "cognitive_tool"
            ]
        except Exception:
            active_cognitive_tools = []
            cognitive_tool_rows = []

    execution_tools: list[str] = []
    execution_tool_rows: list[dict[str, str]] = []
    if execution_registry is not None and hasattr(execution_registry, "list_registrations"):
        try:
            execution_registrations = list(execution_registry.list_registrations())
            execution_tools = sorted(
                registration.plugin_id
                for registration in execution_registrations
                if getattr(registration.spec, "status", None) == PluginLifecycleStatus.ACTIVE
            )
            execution_tool_rows = [
                {
                    "id": registration.plugin_id,
                    "name": " ".join(
                        chunk.capitalize()
                        for chunk in registration.plugin_id.replace(":", " ").replace(".", " ").replace("-", " ").replace("_", " ").split()
                    ) or registration.plugin_id,
                    "introduction": str(getattr(registration.spec, "purpose", "") or "").strip()
                    or f"{registration.plugin_id} 是当前可用的执行域能力。",
                    "function_description": str(getattr(registration.spec, "purpose", "") or "").strip()
                    or f"{registration.plugin_id} 用于执行外部动作或系统操作。",
                }
                for registration in execution_registrations
                if getattr(registration.spec, "status", None) == PluginLifecycleStatus.ACTIVE
            ]
        except Exception:
            execution_tools = []
            execution_tool_rows = []

    cli_tool_states: list[dict[str, object]] = []
    if cli_service is not None and hasattr(cli_service, "list_tools"):
        try:
            cli_tool_states = [
                {
                    "command_name": str(tool.command_name),
                    "description": str(getattr(tool, "description", "") or ""),
                    "mapped_domain": str(getattr(tool, "mapped_domain", "") or ""),
                    "plugin_id": str(getattr(tool, "plugin_id", "") or tool.command_name),
                    "feature_code": str(getattr(tool, "feature_code", "") or ""),
                    "read_only": bool(getattr(tool, "read_only", False)),
                    "status": str(getattr(tool, "status", "") or "unknown"),
                }
                for tool in cli_service.list_tools()
            ]
        except Exception:
            cli_tool_states = []

    mcp_server_states: list[dict[str, object]] = []
    if mcp_service is not None and hasattr(mcp_service, "list_servers"):
        try:
            mcp_server_states = [
                {
                    "server_id": str(server.server_id),
                    "transport_type": str(getattr(server, "transport_type", "") or ""),
                    "status": str(getattr(server, "status", "") or "unknown"),
                    "tool_count": int(getattr(server, "tool_count", 0) or 0),
                    "tools": [
                        {
                            "tool_name": str(tool.tool_name),
                            "description": str(getattr(tool, "description", "") or ""),
                            "plugin_id": str(getattr(tool, "plugin_id", "") or f"mcp:{server.server_id}:{tool.tool_name}"),
                            "feature_code": str(getattr(tool, "feature_code", "") or ""),
                        }
                        for tool in list(getattr(server, "tools", []) or [])
                    ],
                }
                for server in mcp_service.list_servers()
            ]
        except Exception:
            mcp_server_states = []

    deduped_execution_rows: list[dict[str, str]] = []
    seen_execution_ids: set[str] = set()
    for row in execution_tool_rows:
        row_id = str(row.get("id") or "").strip()
        if not row_id or row_id in seen_execution_ids:
            continue
        seen_execution_ids.add(row_id)
        deduped_execution_rows.append(row)
    execution_tool_rows = deduped_execution_rows

    persistent_task_state: list[dict[str, Any]] = []
    if task_service is not None and hasattr(task_service, "list_tasks"):
        try:
            persistent_task_state = [
                {
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": task.status,
                    "progress": task.progress,
                    "target_id": task.target_id,
                }
                for task in task_service.list_tasks()
            ]
        except Exception:
            persistent_task_state = []

    host_state = {
        "cwd": str(root),
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "memory_pressure": "unknown",
        "network_health": "unknown",
    }
    if host_telemetry_plugin is not None and callable(
        getattr(host_telemetry_plugin, "capture_host_state", None)
    ):
        try:
            captured = host_telemetry_plugin.capture_host_state({"workspace_root": str(root)})
            if isinstance(captured, dict):
                host_state.update(
                    {
                        str(key): value
                        for key, value in captured.items()
                        if isinstance(key, str)
                    }
                )
        except Exception:
            pass

    return {
        "workspace_structure_analysis": {
            "directory_hierarchy_summary": ", ".join(f"{name}/" for name in top_level_dirs[:12]),
            "top_level_dirs": top_level_dirs,
            "file_total_count": file_total_count,
            "suffix_distribution": suffix_distribution,
            "high_frequency_filename_keywords": dict(
                sorted(keyword_distribution.items(), key=lambda item: (-item[1], item[0]))[:12]
            ),
            "candidate_groups": sorted(candidate_groups),
            "obvious_risk_files": obvious_risk_files[:12],
        },
        "workspace_content_samples": {
            "sampled_file_summaries": sampled_file_summaries,
            "log_anomaly_snippets": [],
        },
        "environment_event": {
            "kind": "cold_start",
            "summary": environment_summary,
            "workspace_root": str(root),
        },
        "physical_host_state": {
            **host_state,
        },
        "identity_kernel_snapshot": {
            "meta_motivation": "Maintain an auditable, truthful runtime control plane.",
            "values_prohibition": "No fabricated runtime state, no hidden failures, no unsafe escalation.",
            "non_bypassable_constraints": [
                "NO_FAKE_RUNTIME_STATE",
                "NO_SKIP_AUDIT",
                "NO_UNAUTHORIZED_WRITE_ACTION",
            ],
        },
        "active_tools": {
            "available_cognitive_tools": active_cognitive_tools,
            "available_execution_tools": execution_tools,
            "mcp_servers": mcp_server_states,
            "cli_tools": cli_tool_states,
        },
        "q3_unified_asset_inventory": {
            "available_cognitive_tools": active_cognitive_tools,
            "available_execution_tools": execution_tools,
            "connected_agents": [],
            "activated_strategy_patches": [],
            "accessible_workspace_zones": [str(root)],
        },
        "q3_humanized_asset_inventory": {
            "cognitive_tool_rows": cognitive_tool_rows,
            "execution_tool_rows": execution_tool_rows,
            "connected_agent_rows": [],
            "mcp_servers": mcp_server_states,
            "cli_tools": cli_tool_states,
        },
        "workspace_assets": {
            "accessible_workspace_zones": [str(root)],
            "workspace_root": str(root),
        },
        "permissions": {
            "accessible_workspace_zones": [str(root)],
            "mode": "guarded_write",
        },
        "contact_policy": ["only_audited_control_plane_actions"],
        "tenant_scope": ["web_console_runtime"],
        "agent_trust_policy": {"default": "review_required"},
        "connected_agents": [],
        "q3_connected_agents": [],
        "persistent_task_state": persistent_task_state,
    }

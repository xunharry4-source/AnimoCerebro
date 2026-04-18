from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from plugins.shared.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q3
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q3_what_do_i_have.models import Q3WhatDoIHaveInference
from plugins.nine_questions.q3_what_do_i_have.llm_prompt import build_q3_llm_request


QUESTION_REF = "我有什么"


from zentex.common.nine_questions_shared import (
    build_caller_context,
    build_model_context,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    require_model_provider,
    require_transcript_store,
)
from zentex.plugins.service import (
    execute_enabled_cognitive_plugin_functionals,
    query_cognitive_tools,
    query_plugin_records,
)

logger = logging.getLogger(__name__)


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _humanize_identifier(identifier: str) -> str:
    text = identifier.replace("_", " ").replace("-", " ").replace(":", " ").replace(".", " ").strip()
    if not text:
        return "未知资产"
    return " ".join(chunk.capitalize() for chunk in text.split())


def _describe_tool(tool_id: object, *, registry_rows: list[dict[str, str]] | None = None) -> dict[str, str]:
    tool_text = _normalize_text(tool_id)
    matched = next((row for row in (registry_rows or []) if row.get("id") == tool_text), None)
    name = matched.get("name") if matched else ""
    introduction = matched.get("introduction") if matched else ""
    function_description = matched.get("function_description") if matched else ""
    if not name:
        name = _humanize_identifier(tool_text)
    if not introduction:
        introduction = f"{name} 是当前运行态可直接调度的一项能力资产。"
    if not function_description:
        function_description = f"{name} 用于在当前工作流中提供 {tool_text} 对应的能力支持。"
    return {
        "id": tool_text,
        "name": name,
        "introduction": introduction,
        "function_description": function_description,
    }


def _describe_agent(agent: dict[str, Any]) -> dict[str, str]:
    agent_id = _normalize_text(agent.get("agent_id") or agent.get("id") or agent.get("name"))
    name = _normalize_text(agent.get("name")) or _humanize_identifier(agent_id)
    role = _normalize_text(agent.get("role") or agent.get("scope") or agent.get("status"))
    summary = _normalize_text(agent.get("summary") or agent.get("description"))
    introduction = summary or f"{name} 是当前已连接的协同 Agent。"
    function_description = (
        f"{name} 负责 {role} 相关的协作、分析或执行支持。"
        if role
        else f"{name} 用于承接需要多 Agent 协同的任务。"
    )
    return {
        "id": agent_id or name,
        "name": name,
        "introduction": introduction,
        "function_description": function_description,
        "status": _normalize_text(agent.get("status")) or "unknown",
    }


def _resource_status_label(status: str) -> str:
    mapping = {
        "sufficient": "资源充沛",
        "degraded": "资源降级",
        "critically_lacking": "关键资源匮乏",
    }
    return mapping.get(status, status or "未知")


def _resource_status_explanation(status: str) -> str:
    mapping = {
        "sufficient": "当前关键工具、执行能力与协同代理基本齐备，可以支撑正常推演与执行。",
        "degraded": "当前具备部分关键资源，但存在明显短板或瓶颈，需要保守决策与补足关键能力。",
        "critically_lacking": "当前缺少关键资源，无法安全完成核心任务，应先补足基础资产再继续执行。",
    }
    return mapping.get(status, "当前资源状态尚未形成可解释结论，需要进一步核查。")


def _safe_provider_plugin_id(provider: Any) -> str | None:
    candidate = getattr(provider, "plugin_id", None) or getattr(provider, "provider_name", None)
    if isinstance(candidate, str):
        text = candidate.strip()
        return text or None
    return None


def _json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_payload(item) for key, item in value.items()}
    return None


def _catalog_rows_from_runtime_context(context: dict[str, Any], *, plugin_ids: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    managed_records = context.get("managed_plugin_records")
    if isinstance(managed_records, dict):
        for record in managed_records.values():
            plugin = getattr(record, "plugin", None)
            plugin_id = _normalize_text(getattr(plugin, "plugin_id", None))
            if not plugin_id or plugin_id not in plugin_ids or plugin_id in seen:
                continue
            rows.append(
                {
                    "id": plugin_id,
                    "name": _humanize_identifier(plugin_id),
                    "introduction": _normalize_text(getattr(record, "description", None))
                    or _normalize_text(getattr(plugin, "purpose", None))
                    or f"{_humanize_identifier(plugin_id)} 是当前运行态中的可用插件资产。",
                    "function_description": _normalize_text(getattr(plugin, "purpose", None))
                    or _normalize_text(getattr(record, "description", None))
                    or f"{_humanize_identifier(plugin_id)} 提供与 {plugin_id} 对应的运行能力。",
                }
            )
            seen.add(plugin_id)

    cognitive_registry = context.get("cognitive_tool_registry_runtime")
    if cognitive_registry is not None and hasattr(cognitive_registry, "list_registrations"):
        try:
            registrations = cognitive_registry.list_registrations()
        except Exception:
            registrations = []
        for registration in registrations:
            spec = getattr(registration, "spec", None)
            plugin_id = _normalize_text(getattr(spec, "plugin_id", None) or getattr(registration, "plugin_id", None))
            if not plugin_id or plugin_id not in plugin_ids or plugin_id in seen:
                continue
            purpose = _normalize_text(getattr(spec, "purpose", None))
            rows.append(
                {
                    "id": plugin_id,
                    "name": _humanize_identifier(plugin_id),
                    "introduction": purpose or f"{_humanize_identifier(plugin_id)} 是当前启用的认知插件资产。",
                    "function_description": purpose or f"{_humanize_identifier(plugin_id)} 提供与 {plugin_id} 对应的认知支持能力。",
                }
            )
            seen.add(plugin_id)

    return rows


def _derive_runtime_plugin_inventory(
    context: dict[str, Any],
) -> tuple[list[str], list[str], list[dict[str, str]], list[dict[str, str]]]:
    cognitive_tool_ids: list[str] = []
    execution_tool_ids: list[str] = []
    cognitive_rows: list[dict[str, str]] = []
    execution_rows: list[dict[str, str]] = []

    plugin_service = context.get("plugin_service")
    if plugin_service is not None:
        try:
            runtime_cognitive_rows = query_cognitive_tools(
                plugin_service,
                operational_status="enabled",
                limit=500,
            )
        except Exception:
            runtime_cognitive_rows = []
        for row in runtime_cognitive_rows:
            plugin_id = _normalize_text(row.get("plugin_id"))
            feature_code = _normalize_text(row.get("feature_code"))
            if not plugin_id:
                continue
            if feature_code.startswith("nine_questions."):
                continue
            if plugin_id not in cognitive_tool_ids:
                cognitive_tool_ids.append(plugin_id)
                cognitive_rows.append(
                    {
                        "id": plugin_id,
                        "name": _normalize_text(row.get("display_name")) or _humanize_identifier(plugin_id),
                        "introduction": _normalize_text(row.get("description")) or f"{_humanize_identifier(plugin_id)} 是当前启用的认知工具。",
                        "function_description": _normalize_text(row.get("description")) or f"{_humanize_identifier(plugin_id)} 提供与 {plugin_id} 对应的认知能力。",
                    }
                )

        try:
            runtime_functional_rows = query_plugin_records(
                plugin_service,
                category="functional",
                operational_status="enabled",
                limit=500,
            )
        except Exception:
            runtime_functional_rows = []
        for row in runtime_functional_rows:
            plugin_id = _normalize_text(row.get("plugin_id"))
            feature_code = _normalize_text(row.get("feature_code"))
            if not plugin_id:
                continue
            if feature_code.startswith("nine_questions."):
                continue
            if plugin_id not in execution_tool_ids:
                execution_tool_ids.append(plugin_id)
                execution_rows.append(
                    {
                        "id": plugin_id,
                        "name": _normalize_text(row.get("display_name")) or _humanize_identifier(plugin_id),
                        "introduction": _normalize_text(row.get("description")) or f"{_humanize_identifier(plugin_id)} 是当前可调用的功能插件。",
                        "function_description": _normalize_text(row.get("description")) or f"{_humanize_identifier(plugin_id)} 提供与 {plugin_id} 对应的执行或辅助能力。",
                    }
                )

    return cognitive_tool_ids, execution_tool_ids, cognitive_rows, execution_rows


def _derive_runtime_agent_inventory(
    context: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    agent_service = context.get("agent_service")
    if agent_service is None:
        try:
            from zentex.agents.service import get_service

            agent_service = get_service()
        except Exception:
            agent_service = None

    raw_agents: list[Any] = []
    if agent_service is not None:
        try:
            if callable(getattr(agent_service, "list_active_agents", None)):
                raw_agents = list(agent_service.list_active_agents() or [])
            elif getattr(agent_service, "manager", None) is not None and callable(
                getattr(agent_service.manager, "list_assets", None)
            ):
                raw_agents = list(agent_service.manager.list_assets() or [])
        except Exception:
            raw_agents = []

    agent_payloads: list[dict[str, Any]] = []
    humanized_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for asset in raw_agents:
        payload = asset.model_dump(mode="json") if hasattr(asset, "model_dump") else dict(asset or {})
        agent_id = _normalize_text(payload.get("agent_id") or payload.get("id") or payload.get("name"))
        if not agent_id or agent_id in seen:
            continue
        seen.add(agent_id)
        agent_payload = {
            "agent_id": agent_id,
            "name": _normalize_text(payload.get("agent_name") or payload.get("name")) or _humanize_identifier(agent_id),
            "role": _normalize_text(payload.get("role_tag") or payload.get("role") or payload.get("scope")),
            "status": _normalize_text(payload.get("status")) or "unknown",
            "summary": _normalize_text(payload.get("function_description") or payload.get("description")),
            "capabilities": payload.get("capabilities") or [],
            "scope": payload.get("scope") or [],
        }
        agent_payloads.append(agent_payload)
        humanized_rows.append(_describe_agent(agent_payload))

    return agent_payloads, humanized_rows


def _derive_runtime_cli_inventory(
    context: dict[str, Any],
) -> tuple[list[str], list[dict[str, str]], list[dict[str, Any]]]:
    cli_service = context.get("cli_service")
    if cli_service is None:
        try:
            from zentex.cli.service import get_service

            cli_service = get_service()
        except Exception:
            cli_service = None

    raw_tools: list[Any] = []
    if cli_service is not None and callable(getattr(cli_service, "list_tools", None)):
        try:
            raw_tools = list(cli_service.list_tools() or [])
        except Exception:
            raw_tools = []

    tool_ids: list[str] = []
    tool_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for tool in raw_tools:
        payload = tool.model_dump(mode="json") if hasattr(tool, "model_dump") else dict(tool or {})
        tool_id = _normalize_text(payload.get("command_name") or payload.get("cli_id") or payload.get("feature_code"))
        if not tool_id or tool_id in seen:
            continue
        seen.add(tool_id)
        tool_ids.append(tool_id)
        name = _normalize_text(payload.get("command_name")) or _humanize_identifier(tool_id)
        execution_domain = _normalize_text(payload.get("execution_domain")) or "cli"
        description = _normalize_text(payload.get("description")) or f"{name} 是当前已注册的 CLI 工具。"
        tool_rows.append(
            {
                "id": tool_id,
                "name": name,
                "introduction": description,
                "function_description": f"{name} 通过 {execution_domain} 执行域提供命令行能力。",
            }
        )

    tool_payloads: list[dict[str, Any]] = []
    for tool in raw_tools:
        payload = tool.model_dump(mode="json") if hasattr(tool, "model_dump") else dict(tool or {})
        command_name = _normalize_text(payload.get("command_name"))
        if not command_name:
            continue
        tool_payloads.append(
            {
                "command_name": command_name,
                "description": _normalize_text(payload.get("description")) or f"{command_name} 是当前已注册的 CLI 工具。",
                "mapped_domain": _normalize_text(payload.get("mapped_domain")) or "execution",
                "cli_id": _normalize_text(payload.get("cli_id")),
                "feature_code": _normalize_text(payload.get("feature_code")),
                "read_only": bool(payload.get("read_only", True)),
                "status": _normalize_text(payload.get("status")) or "active",
            }
        )

    return tool_ids, tool_rows, tool_payloads


def _derive_runtime_mcp_inventory(
    context: dict[str, Any],
) -> tuple[list[str], list[dict[str, str]], list[dict[str, Any]]]:
    mcp_service = context.get("mcp_service")
    if mcp_service is None:
        try:
            from zentex.mcp.service import get_service

            mcp_service = get_service()
        except Exception:
            mcp_service = None

    raw_servers: list[Any] = []
    if mcp_service is not None and callable(getattr(mcp_service, "list_servers", None)):
        try:
            raw_servers = list(mcp_service.list_servers() or [])
        except Exception:
            raw_servers = []

    server_ids: list[str] = []
    server_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for server in raw_servers:
        payload = server.model_dump(mode="json") if hasattr(server, "model_dump") else dict(server or {})
        status = _normalize_text(payload.get("status"))
        if status == "offline":
            continue
        server_id = _normalize_text(payload.get("server_id") or payload.get("name"))
        if not server_id or server_id in seen:
            continue
        seen.add(server_id)
        server_ids.append(server_id)
        name = _normalize_text(payload.get("name")) or _humanize_identifier(server_id)
        transport = _normalize_text(payload.get("transport_type")) or "mcp"
        description = _normalize_text(payload.get("description")) or f"{name} 是当前在线的 MCP 服务。"
        tool_count = payload.get("tool_count")
        tool_suffix = f"，当前暴露 {tool_count} 个工具" if isinstance(tool_count, int) else ""
        server_rows.append(
            {
                "id": server_id,
                "name": name,
                "introduction": description,
                "function_description": f"{name} 通过 {transport} 传输提供 MCP 能力{tool_suffix}。",
            }
        )

    server_payloads: list[dict[str, Any]] = []
    for server in raw_servers:
        payload = server.model_dump(mode="json") if hasattr(server, "model_dump") else dict(server or {})
        server_id = _normalize_text(payload.get("server_id"))
        if not server_id or _normalize_text(payload.get("status")) == "offline":
            continue
        server_payloads.append(
            {
                "server_id": server_id,
                "transport_type": _normalize_text(payload.get("transport_type")) or "mcp",
                "status": _normalize_text(payload.get("status")) or "online",
                "tool_count": int(payload.get("tool_count") or 0),
                "tools": payload.get("tools") if isinstance(payload.get("tools"), list) else [],
            }
        )

    return server_ids, server_rows, server_payloads


def _derive_runtime_workspace_and_permission_inventory(
    context: dict[str, Any],
) -> tuple[list[str], list[str], list[str], dict[str, Any], dict[str, Any]]:
    snapshot = context.get("context_snapshot", {}) or {}
    permissions = snapshot.get("permissions", {}) or {}
    workspace_assets = snapshot.get("workspace_assets", {}) or {}
    workspace_root = _normalize_text(
        snapshot.get("workspace_root") or snapshot.get("cwd") or context.get("workspace_root") or context.get("cwd")
    )
    if not workspace_root:
        try:
            workspace_root = os.getcwd()
        except Exception:
            workspace_root = ""

    workspaces = list(
        {
            item: True
            for item in (
                list((permissions or {}).get("accessible_workspace_zones", []) or [])
                + list((workspace_assets or {}).get("accessible_workspace_zones", []) or [])
                + ([workspace_root] if workspace_root else [])
            )
            if _normalize_text(item)
        }.keys()
    )
    tenant_permissions = list(
        {
            item: True
            for item in (
                list((permissions or {}).get("tenant_scope", []) or [])
                + list((permissions or {}).get("mode", []) if isinstance((permissions or {}).get("mode"), list) else [])
            )
            if _normalize_text(item)
        }.keys()
    )
    if isinstance((permissions or {}).get("mode"), str) and _normalize_text((permissions or {}).get("mode")):
        tenant_permissions.append(_normalize_text((permissions or {}).get("mode")))
    tenant_permissions = list({item: True for item in tenant_permissions if item}.keys())

    execution_tokens = list(
        {
            item: True
            for item in (
                list((permissions or {}).get("brain_scope", []) or [])
                + list((permissions or {}).get("execution_tokens", []) or [])
            )
            if _normalize_text(item)
        }.keys()
    )
    foundation_service = context.get("foundation_service")
    if foundation_service is not None and callable(getattr(foundation_service, "get_capability_directory", None)):
        try:
            capability_directory = foundation_service.get_capability_directory()
            entries = capability_directory.to_dict().get("entries", []) if hasattr(capability_directory, "to_dict") else []
            execution_tokens.extend(
                _normalize_text(entry.get("name"))
                for entry in entries
                if isinstance(entry, dict) and _normalize_text(entry.get("name"))
            )
        except Exception:
            pass
    execution_tokens = list({item: True for item in execution_tokens if item}.keys())

    return workspaces, tenant_permissions, execution_tokens, workspace_assets, permissions


def _derive_runtime_memory_strategy_inventory(
    context: dict[str, Any],
) -> tuple[list[str], list[str]]:
    snapshot = context.get("context_snapshot", {}) or {}
    loaded_memories = snapshot.get("loaded_memories", {}) or {}
    strategy_patches = list((loaded_memories.get("activated_strategy_patches") or []))
    experience_logs = list((loaded_memories.get("experience_logs") or []))

    memory_service = context.get("memory_service")
    if memory_service is not None and callable(getattr(memory_service, "recall", None)):
        try:
            strategy_hits = memory_service.recall(query="strategy", limit=5)
        except Exception:
            strategy_hits = []
        try:
            experience_hits = memory_service.recall(query="experience", limit=5)
        except Exception:
            experience_hits = []

        for hit in strategy_hits:
            payload = hit.model_dump(mode="json") if hasattr(hit, "model_dump") else dict(hit or {})
            text = _normalize_text(payload.get("title")) or _normalize_text(payload.get("summary"))
            if text:
                strategy_patches.append(text)
        for hit in experience_hits:
            payload = hit.model_dump(mode="json") if hasattr(hit, "model_dump") else dict(hit or {})
            text = _normalize_text(payload.get("title")) or _normalize_text(payload.get("summary"))
            if text:
                experience_logs.append(text)

    strategy_patches = list({item: True for item in strategy_patches if _normalize_text(item)}.keys())
    experience_logs = list({item: True for item in experience_logs if _normalize_text(item)}.keys())
    return experience_logs, strategy_patches


class Q3WhatDoIHavePlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q3
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q3"
    display_name: str = "Q3: What do I have?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Q3: 我有什么 (unified asset inventory + resource evaluation)

    Red lines:
    - Must use Live LLM (fail-closed).
    - Must not scan full repo or read raw bodies; only lightweight metadata.
    - Must write prompt/context/response into BrainTranscriptStore with trace_id.
    """

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        snapshot = context.get("context_snapshot", {}) or {}
        active_tools = snapshot.get("active_tools", {}) or {}
        runtime_cog_tools, runtime_exec_domains, runtime_cognitive_rows, runtime_execution_rows = _derive_runtime_plugin_inventory(context)
        runtime_agent_payloads, runtime_agent_rows = _derive_runtime_agent_inventory(context)
        runtime_cli_tools, runtime_cli_rows, runtime_cli_payloads = _derive_runtime_cli_inventory(context)
        runtime_mcp_servers, runtime_mcp_rows, runtime_mcp_payloads = _derive_runtime_mcp_inventory(context)
        (
            accessible_workspace_zones,
            tenant_permissions,
            execution_tokens,
            runtime_workspace_assets,
            runtime_permissions,
        ) = _derive_runtime_workspace_and_permission_inventory(context)
        experience_logs, activated_strategy_patches = _derive_runtime_memory_strategy_inventory(context)
        cog_tools = list(
            {
                item: True
                for item in (list(active_tools.get("available_cognitive_tools", []) or []) + runtime_cog_tools)
                if item
            }.keys()
        )
        exec_domains = list(
            {
                item: True
                for item in (
                    list(active_tools.get("available_execution_tools", []) or [])
                    + runtime_exec_domains
                    + runtime_cli_tools
                    + runtime_mcp_servers
                )
                if item
            }.keys()
        )
        connected_agents = [
            agent
            for agent in (snapshot.get("connected_agents", []) or [])
            if isinstance(agent, dict) and agent.get("status") != "offline"
        ] + runtime_agent_payloads
        runtime_cognitive_rows = runtime_cognitive_rows or _catalog_rows_from_runtime_context(context, plugin_ids=cog_tools)
        runtime_execution_rows = runtime_execution_rows or _catalog_rows_from_runtime_context(
            context,
            plugin_ids=runtime_exec_domains,
        )
        cognitive_tool_registry = [
            _describe_tool(item, registry_rows=runtime_cognitive_rows)
            for item in cog_tools
        ]
        execution_domain_registry = [
            _describe_tool(item, registry_rows=runtime_execution_rows)
            for item in runtime_exec_domains
        ]
        execution_domain_registry.extend(runtime_cli_rows)
        execution_domain_registry.extend(runtime_mcp_rows)
        connected_agent_catalog = [_describe_agent(agent) for agent in connected_agents]
        if not connected_agent_catalog:
            connected_agent_catalog = runtime_agent_rows
        plugin_service = context.get("plugin_service")
        functional_assets: list[dict[str, Any]] = []
        if plugin_service is not None:
            functional_assets = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters=dict(context),
                trace_id=str(context.get("trace_id") or "q3"),
                originator_id=str(context.get("session_id") or "unknown-session"),
                caller_plugin_id=self.plugin_id,
            )
            for item in functional_assets:
                if item.get("status") != "done":
                    continue
                plugin_id = str(item.get("plugin_id") or "")
                result = item.get("result")
                execution_domain_registry.append(_describe_tool(plugin_id, registry_rows=runtime_execution_rows))
                if isinstance(result, dict):
                    connected_agent_catalog.extend(
                        _describe_agent(agent)
                        for agent in (result.get("connected_agents") or [])
                        if isinstance(agent, dict)
                    )
        execution_domain_registry = list({row["id"]: row for row in execution_domain_registry if row.get("id")}.values())
        connected_agent_catalog = list({row["id"]: row for row in connected_agent_catalog if row.get("id")}.values())
        exec_domains = list({item: True for item in exec_domains if item}.keys())
        connected_agents = list(
            {
                _normalize_text(item.get("agent_id") or item.get("id") or item.get("name")): item
                for item in connected_agents
                if isinstance(item, dict)
                and _normalize_text(item.get("agent_id") or item.get("id") or item.get("name"))
            }.values()
        )

        llm_request = build_q3_llm_request(
            cognitive_tool_registry=cognitive_tool_registry,
            execution_domain_registry=execution_domain_registry,
            connected_agent_catalog=connected_agent_catalog,
            cog_tools=cog_tools,
            exec_domains=exec_domains,
            connected_agents=connected_agents,
            activated_strategy_patches=activated_strategy_patches,
            accessible_workspace_zones=accessible_workspace_zones,
            workspace_assets=runtime_workspace_assets,
            permissions=runtime_permissions,
            tenant_permissions=tenant_permissions,
            execution_tokens=execution_tokens,
            experience_logs=experience_logs,
            functional_assets=functional_assets,
            cli_tool_registry=runtime_cli_rows,
            mcp_server_registry=runtime_mcp_rows,
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        trace_id = str(context.get("trace_id") or f"q3-what-do-i-have:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q3_what_do_i_have")

        caller_context = build_caller_context(
            source_module="q3_what_do_i_have_plugin",
            invocation_phase="nine_question_q3_what_do_i_have",
            question_ref=QUESTION_REF,
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q3_what_do_i_have",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": _safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "system_prompt": system_prompt,
                "context": model_context,
            },
        )

        try:
            started = perf_counter()
            raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{prompt}",
                context=model_context,
                caller_context=caller_context,
            )
            elapsed_ms = int((perf_counter() - started) * 1000)
        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q3_what_do_i_have",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            raise

        inference = Q3WhatDoIHaveInference.model_validate(raw)

        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q3_what_do_i_have",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": inference.model_dump(mode="json"),
                "raw_response": _json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": _json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": _json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": elapsed_ms,
            },
        )

        summary = (
            f"resource_status={inference.resource_evaluation.resource_status.value}; "
            f"bottleneck={inference.resource_evaluation.bottleneck_node}"
        )
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "unified_asset_inventory",
                    **inference.unified_asset_inventory.model_dump(mode="json"),
                },
                {
                    "kind": "resource_evaluation",
                    **inference.resource_evaluation.model_dump(mode="json"),
                },
            ],
            risks=[
                {
                    "kind": "missing_critical_assets",
                    "items": inference.resource_evaluation.missing_critical_assets,
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: inference.resource_evaluation.resource_status.value},
                "q3_unified_asset_inventory": inference.unified_asset_inventory.model_dump(mode="json"),
                "q3_resource_evaluation": inference.resource_evaluation.model_dump(mode="json"),
                "q3_humanized_asset_inventory": {
                    "cognitive_tool_rows": cognitive_tool_registry,
                    "execution_tool_rows": execution_domain_registry,
                    "connected_agent_rows": connected_agent_catalog,
                    "mcp_servers": runtime_mcp_payloads,
                    "cli_tools": runtime_cli_payloads,
                    "cli_tool_rows": runtime_cli_rows,
                    "mcp_server_rows": runtime_mcp_rows,
                    "functional_assets": functional_assets,
                },
                "workspaces_and_permissions": {
                    "available_workspaces": accessible_workspace_zones,
                    "tenant_permissions": tenant_permissions,
                    "execution_tokens": execution_tokens,
                },
                "memory_and_strategy": {
                    "experience_logs": experience_logs,
                    "strategy_patches": activated_strategy_patches,
                },
                "workspace_assets": runtime_workspace_assets,
                "permissions": runtime_permissions,
                "loaded_memories": {
                    "experience_logs": experience_logs,
                    "activated_strategy_patches": activated_strategy_patches,
                },
                "q3_resource_status_humanized": {
                    "label": _resource_status_label(inference.resource_evaluation.resource_status.value),
                    "explanation": _resource_status_explanation(inference.resource_evaluation.resource_status.value),
                },
            },
            confidence=0.7,
        )


def build_q3_what_do_i_have_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q3,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q3WhatDoIHavePlugin:
    return Q3WhatDoIHavePlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q3",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )

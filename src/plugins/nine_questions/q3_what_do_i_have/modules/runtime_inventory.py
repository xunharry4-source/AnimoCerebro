from __future__ import annotations

import logging
import os
from typing import Any

from zentex.common.nine_questions_shared import bind_module_runs, finish_module_run, persist_question_module_output, start_module_run
from zentex.plugins.service import query_cognitive_tools, query_plugin_records

logger = logging.getLogger(__name__)


def _log_runtime_inventory_warning(event: str, exc: Exception) -> None:
    # 严禁吞异常后伪装系统正常：Q3 运行态盘点允许降级返回空列表/空载荷，
    # 但绝不允许只留轻量 warning 把真实后台故障伪装成“当前无数据”。
    # 这里必须保留异常堆栈，否则稳定性问题无法定位，等同于功能假实现。
    logger.exception(
        "Q3 runtime inventory degraded: %s",
        event,
        extra={
            "source_module": "plugins.nine_questions.q3.runtime_inventory",
            "event": event,
            "error": str(exc),
        },
    )


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


def describe_tool(tool_id: object, *, registry_rows: list[dict[str, str]] | None = None) -> dict[str, str]:
    return _describe_tool(tool_id, registry_rows=registry_rows)


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


def describe_agent(agent: dict[str, Any]) -> dict[str, str]:
    return _describe_agent(agent)


def safe_provider_plugin_id(provider: Any) -> str | None:
    candidate = getattr(provider, "plugin_id", None) or getattr(provider, "provider_name", None)
    if isinstance(candidate, str):
        text = candidate.strip()
        return text or None
    return None


def json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [json_safe_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe_payload(item) for key, item in value.items()}
    return None


def build_resource_status_humanized(status: str) -> dict[str, str]:
    mapping = {
        "sufficient": {
            "label": "资源充沛",
            "explanation": "当前关键工具、执行能力与协同代理基本齐备，可以支撑正常推演与执行。",
        },
        "degraded": {
            "label": "资源降级",
            "explanation": "当前具备部分关键资源，但存在明显短板或瓶颈，需要保守决策与补足关键能力。",
        },
        "critically_lacking": {
            "label": "关键资源匮乏",
            "explanation": "当前缺少关键资源，无法安全完成核心任务，应先补足基础资产再继续执行。",
        },
    }
    return mapping.get(
        status,
        {
            "label": status or "未知",
            "explanation": "当前资源状态尚未形成可解释结论，需要进一步核查。",
        },
    )


def _status_for_payload(payload: Any, *, missing_code: str) -> tuple[str, str, str]:
    if payload not in (None, {}, [], ""):
        return "completed", "", ""
    return "missing", missing_code, "Module data is not available."


def build_q3_runtime_inventory_context(
    context: dict[str, Any],
    *,
    include_resource_inference_gate: bool = False,
) -> dict[str, Any]:
    runtime_inventory = build_q3_runtime_inventory(context)
    module_results = runtime_inventory.get("module_results")
    module_results = module_results if isinstance(module_results, dict) else {}
    unified_asset_inventory = {
        "available_cognitive_tools": runtime_inventory.get("cog_tools", []),
        "available_execution_tools": runtime_inventory.get("exec_domains", []),
        "connected_agents": runtime_inventory.get("connected_agents", []),
        "activated_strategy_patches": runtime_inventory.get("activated_strategy_patches", []),
        "accessible_workspace_zones": runtime_inventory.get("accessible_workspace_zones", []),
    }
    context_updates = {
        "q3_runtime_inventory": runtime_inventory,
        "q3_module_results": module_results,
        "q3_unified_asset_inventory": unified_asset_inventory,
        "q3_humanized_asset_inventory": {
            "cognitive_tool_rows": runtime_inventory.get("cognitive_tool_registry", []),
            "execution_tool_rows": runtime_inventory.get("execution_domain_registry", []),
            "connected_agent_rows": runtime_inventory.get("connected_agent_catalog", []),
            "mcp_servers": runtime_inventory.get("runtime_mcp_payloads", []),
            "cli_tools": runtime_inventory.get("runtime_cli_payloads", []),
            "cli_tool_rows": runtime_inventory.get("runtime_cli_rows", []),
            "mcp_server_rows": runtime_inventory.get("runtime_mcp_rows", []),
        },
        "workspaces_and_permissions": {
            "available_workspaces": runtime_inventory.get("accessible_workspace_zones", []),
            "tenant_permissions": runtime_inventory.get("tenant_permissions", []),
            "execution_tokens": runtime_inventory.get("execution_tokens", []),
        },
        "memory_and_strategy": {
            "experience_logs": runtime_inventory.get("experience_logs", []),
            "strategy_patches": runtime_inventory.get("activated_strategy_patches", []),
        },
        "workspace_assets": runtime_inventory.get("runtime_workspace_assets", []),
        "permissions": runtime_inventory.get("runtime_permissions", {}),
    }
    module_runs = bind_module_runs(context, "q3")
    for module_id, payload in module_results.items():
        run = start_module_run(
            module_runs,
            str(module_id),
            source="plugins.nine_questions.q3",
        )
        status, error_code, error_message = _status_for_payload(
            payload,
            missing_code=f"{module_id}_missing",
        )
        run["data"] = payload if isinstance(payload, dict) else {"value": payload}
        finish_module_run(
            run,
            status=status,
            error_code=error_code,
            error_message=error_message,
        )
        persist_question_module_output(
            context,
            question_id="q3",
            module_id=str(module_id),
            payload=payload if isinstance(payload, dict) else {"value": payload},
            status=str(run.get("status") or status),
            output_kind="evidence",
        )
    if include_resource_inference_gate:
        run = start_module_run(
            module_runs,
            "resource_sufficiency_inference",
            source="plugins.nine_questions.q3",
        )
        finish_module_run(
            run,
            status="degraded",
            error_code="resource_inference_not_rerun",
            error_message="Q3 runtime inventory was refreshed without rerunning LLM resource inference.",
        )
    return {
        "runtime_inventory": runtime_inventory,
        "module_results": module_results,
        "unified_asset_inventory": unified_asset_inventory,
        "context_updates": context_updates,
        "module_runs": list(module_runs),
    }


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
        except Exception as exc:
            _log_runtime_inventory_warning("cognitive_registry.list_registrations", exc)
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
        except Exception as exc:
            _log_runtime_inventory_warning("query_cognitive_tools", exc)
            runtime_cognitive_rows = []
        for row in runtime_cognitive_rows:
            plugin_id = _normalize_text(row.get("plugin_id"))
            feature_code = _normalize_text(row.get("feature_code"))
            if not plugin_id or feature_code.startswith("nine_questions."):
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
        except Exception as exc:
            _log_runtime_inventory_warning("query_plugin_records", exc)
            runtime_functional_rows = []
        for row in runtime_functional_rows:
            plugin_id = _normalize_text(row.get("plugin_id"))
            feature_code = _normalize_text(row.get("feature_code"))
            if not plugin_id or feature_code.startswith("nine_questions."):
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
        except Exception as exc:
            _log_runtime_inventory_warning("agents.get_service", exc)
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
        except Exception as exc:
            _log_runtime_inventory_warning("agent_service.list_active_agents", exc)
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
        except Exception as exc:
            _log_runtime_inventory_warning("cli.get_service", exc)
            cli_service = None

    raw_tools: list[Any] = []
    if cli_service is not None and callable(getattr(cli_service, "list_tools", None)):
        try:
            raw_tools = list(cli_service.list_tools() or [])
        except Exception as exc:
            _log_runtime_inventory_warning("cli_service.list_tools", exc)
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
        except Exception as exc:
            _log_runtime_inventory_warning("mcp.get_service", exc)
            mcp_service = None

    raw_servers: list[Any] = []
    if mcp_service is not None and callable(getattr(mcp_service, "list_servers", None)):
        try:
            raw_servers = list(mcp_service.list_servers() or [])
        except Exception as exc:
            _log_runtime_inventory_warning("mcp_service.list_servers", exc)
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
    permissions = context.get("permissions", {}) or {}
    workspace_assets = context.get("workspace_assets", {}) or {}
    workspace_root = _normalize_text(
        context.get("workspace_root") or context.get("cwd")
    )
    if not workspace_root:
        try:
            workspace_root = os.getcwd()
        except Exception as exc:
            _log_runtime_inventory_warning("os.getcwd", exc)
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
        except Exception as exc:
            _log_runtime_inventory_warning("foundation_service.get_capability_directory", exc)
    execution_tokens = list({item: True for item in execution_tokens if item}.keys())

    return workspaces, tenant_permissions, execution_tokens, workspace_assets, permissions


def _derive_runtime_memory_strategy_inventory(
    context: dict[str, Any],
) -> tuple[list[str], list[str]]:
    loaded_memories = context.get("loaded_memories", {}) or {}
    strategy_patches = list((loaded_memories.get("activated_strategy_patches") or []))
    experience_logs = list((loaded_memories.get("experience_logs") or []))

    strategy_patches = list({item: True for item in strategy_patches if _normalize_text(item)}.keys())
    experience_logs = list({item: True for item in experience_logs if _normalize_text(item)}.keys())
    return experience_logs, strategy_patches


def build_q3_runtime_inventory(context: dict[str, Any]) -> dict[str, Any]:
    active_tools = context.get("active_tools", {}) or {}

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
        for agent in (context.get("connected_agents", []) or [])
        if isinstance(agent, dict) and agent.get("status") != "offline"
    ] + runtime_agent_payloads

    runtime_cognitive_rows = runtime_cognitive_rows or _catalog_rows_from_runtime_context(context, plugin_ids=cog_tools)
    runtime_execution_rows = runtime_execution_rows or _catalog_rows_from_runtime_context(context, plugin_ids=runtime_exec_domains)

    cognitive_tool_registry = [_describe_tool(item, registry_rows=runtime_cognitive_rows) for item in cog_tools]
    execution_domain_registry = [_describe_tool(item, registry_rows=runtime_execution_rows) for item in runtime_exec_domains]
    execution_domain_registry.extend(runtime_cli_rows)
    execution_domain_registry.extend(runtime_mcp_rows)
    connected_agent_catalog = [_describe_agent(agent) for agent in connected_agents]
    if not connected_agent_catalog:
        connected_agent_catalog = runtime_agent_rows

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

    module_results = {
        "workspace_permission_inventory": {
            "accessible_workspace_zones": accessible_workspace_zones,
            "tenant_permissions": tenant_permissions,
            "execution_tokens": execution_tokens,
        },
        "cognitive_tools_inventory": {
            "available_cognitive_tools": cog_tools,
            "cognitive_tool_rows": cognitive_tool_registry,
        },
        "execution_tools_inventory": {
            "available_execution_tools": exec_domains,
            "execution_tool_rows": execution_domain_registry,
        },
        "connected_agents_inventory": {
            "connected_agents": connected_agents,
            "connected_agent_rows": connected_agent_catalog,
        },
        "cli_inventory": {
            "available_cli_tools": runtime_cli_tools,
            "cli_tool_rows": runtime_cli_rows,
            "cli_tools": runtime_cli_payloads,
        },
        "mcp_inventory": {
            "available_mcp_servers": runtime_mcp_servers,
            "mcp_server_rows": runtime_mcp_rows,
            "mcp_servers": runtime_mcp_payloads,
        },
        "memory_strategy_inventory": {
            "experience_logs": experience_logs,
            "activated_strategy_patches": activated_strategy_patches,
        },
    }

    return {
        "cog_tools": cog_tools,
        "exec_domains": exec_domains,
        "connected_agents": connected_agents,
        "cognitive_tool_registry": cognitive_tool_registry,
        "execution_domain_registry": execution_domain_registry,
        "connected_agent_catalog": connected_agent_catalog,
        "accessible_workspace_zones": accessible_workspace_zones,
        "tenant_permissions": tenant_permissions,
        "execution_tokens": execution_tokens,
        "runtime_workspace_assets": runtime_workspace_assets,
        "runtime_permissions": runtime_permissions,
        "experience_logs": experience_logs,
        "activated_strategy_patches": activated_strategy_patches,
        "runtime_cli_rows": runtime_cli_rows,
        "runtime_mcp_rows": runtime_mcp_rows,
        "runtime_cli_payloads": runtime_cli_payloads,
        "runtime_mcp_payloads": runtime_mcp_payloads,
        "module_results": module_results,
    }

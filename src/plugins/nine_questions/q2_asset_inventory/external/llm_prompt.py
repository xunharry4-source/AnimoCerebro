from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zentex.common.prompt_template_files import prompt_template_files, render_prompt_template

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")
_TEMPLATE_FILES = ["system_prompt.md", "user_prompt.md"]


def _render_template(name: str, values: dict[str, str] | None = None) -> str:
    return render_prompt_template(_TEMPLATE_DIR, name, values or {}, error_prefix="q2_external")


def _json_block(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, indent=2, default=str)


Q2_EXTERNAL_SYSTEM_PROMPT = _render_template("system_prompt.md")


_LEGACY_SIMULATED_VERIFICATION_STATUS = "模拟" "已学习"


def _model_dump(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    return {
        key: item
        for key in dir(value)
        if not key.startswith("_")
        and not callable(item := getattr(value, key, None))
        and isinstance(item, (str, int, float, bool, list, dict, type(None)))
    }


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _text(value: Any) -> str:
    return str(_enum_value(value) or "").strip()


def _string_list(*values: Any) -> list[str]:
    items: list[str] = []
    for value in values:
        if value is None:
            continue
        candidates = value if isinstance(value, list) else [value]
        for item in candidates:
            text = _text(item)
            if text and text not in items:
                items.append(text)
    return items


def _documentation_urls(*values: Any) -> list[str]:
    return [
        item
        for item in _string_list(*values)
        if item.startswith(("http://", "https://", "file://")) or "/" in item
    ]


def _profile_payload(profile: Any) -> dict[str, Any]:
    payload = _model_dump(profile) if profile is not None else {}
    return {
        "usage_summary": _text(payload.get("usage_summary")),
        "task_routing_hints": _string_list(payload.get("task_routing_hints")),
        "side_effects": _string_list(payload.get("side_effects")),
        "risk_notes": _string_list(payload.get("risk_notes")),
        "learning_status": _text(payload.get("learning_status")),
        "degraded": bool(payload.get("degraded", False)),
    }


def _list_usage_profiles(service: Any) -> dict[str, Any]:
    if service is None or not callable(getattr(service, "list_usage_profiles", None)):
        return {}
    profiles = service.list_usage_profiles() or {}
    return profiles if isinstance(profiles, dict) else {}


def collect_cli_tool_assets(cli_service: Any) -> list[dict[str, Any]]:
    if cli_service is None or not callable(getattr(cli_service, "list_tools", None)):
        return []
    profiles = _list_usage_profiles(cli_service)
    rows: list[dict[str, Any]] = []
    for item in cli_service.list_tools() or []:
        payload = _model_dump(item)
        name = _text(payload.get("command_name") or payload.get("tool_name"))
        if not name:
            continue
        profile = _profile_payload(profiles.get(name))
        rows.append(
            {
                "source_type": "CLI",
                "function_name": name,
                "function_introduction": _text(payload.get("description")),
                "documentation_urls": _documentation_urls(
                    payload.get("help_doc_url"),
                    payload.get("project_doc_url"),
                ),
                "status": _text(payload.get("status")),
                "execution_domain": _text(payload.get("execution_domain") or "cli"),
                "read_only": bool(payload.get("read_only", True)),
                "side_effect_free": bool(payload.get("side_effect_free", True)),
                "mutates_state": bool(payload.get("mutates_state", False)),
                "usage_profile": profile,
            }
        )
    return rows


def collect_mcp_tool_assets(mcp_service: Any) -> list[dict[str, Any]]:
    from zentex.mcp.service import resolve_service as resolve_mcp_service

    mcp_service = resolve_mcp_service(mcp_service)
    if mcp_service is None or not callable(getattr(mcp_service, "list_servers", None)):
        return []
    profiles = _list_usage_profiles(mcp_service)
    rows: list[dict[str, Any]] = []
    for server in mcp_service.list_servers() or []:
        server_payload = _model_dump(server)
        server_id = _text(server_payload.get("server_id"))
        server_name = _text(server_payload.get("name") or server_id)
        if not server_id:
            continue
        tools = [_model_dump(tool) for tool in server_payload.get("tools") or []]
        rows.append(
            {
                "source_type": "MCP",
                "server_id": server_id,
                "server_name": server_name,
                "function_name": server_name or server_id,
                "function_introduction": _mcp_server_introduction(server_payload, tools),
                "documentation_urls": _documentation_urls(
                    server_payload.get("help_doc_url"),
                    server_payload.get("project_doc_url"),
                ),
                "status": _text(server_payload.get("status")),
                "transport_type": _text(server_payload.get("transport_type")),
                "execution_domain": "mcp",
                "read_only": all(bool(tool.get("read_only", True)) for tool in tools) if tools else True,
                "side_effect_free": all(bool(tool.get("side_effect_free", True)) for tool in tools) if tools else True,
                "mutates_state": any(bool(tool.get("mutates_state", False)) for tool in tools),
                "tool_count": len(tools),
                "tool_names": [_text(tool.get("tool_name")) for tool in tools if _text(tool.get("tool_name"))],
                "usage_profile": _aggregate_mcp_server_profiles(server_id, tools, profiles),
            }
        )
    return rows


def _mcp_server_introduction(server_payload: dict[str, Any], tools: list[dict[str, Any]]) -> str:
    description = _text(server_payload.get("description"))
    if description:
        return description
    tool_names = [_text(tool.get("tool_name")) for tool in tools if _text(tool.get("tool_name"))]
    if tool_names:
        preview = "、".join(tool_names[:8])
        suffix = "等" if len(tool_names) > 8 else ""
        return f"MCP 服务，提供 {len(tool_names)} 个已注册工具能力：{preview}{suffix}。"
    return "MCP 服务，未声明工具能力明细。"


def _aggregate_mcp_server_profiles(
    server_id: str,
    tools: list[dict[str, Any]],
    profiles: dict[str, Any],
) -> dict[str, Any]:
    profile_payloads = [
        _profile_payload(profiles.get(f"{server_id}:{tool_name}"))
        for tool in tools
        if (tool_name := _text(tool.get("tool_name"))) and profiles.get(f"{server_id}:{tool_name}") is not None
    ]
    tool_descriptions = _string_list([tool.get("description") for tool in tools])
    usage_summaries = _string_list([profile.get("usage_summary") for profile in profile_payloads], tool_descriptions)
    task_routing_hints = _flatten_string_values(
        [profile.get("task_routing_hints") for profile in profile_payloads],
        tool_descriptions,
    )
    side_effects = _flatten_string_values([profile.get("side_effects") for profile in profile_payloads])
    risk_notes = _flatten_string_values([profile.get("risk_notes") for profile in profile_payloads])
    learning_statuses = {_text(profile.get("learning_status")).lower() for profile in profile_payloads}
    learning_statuses.discard("")
    degraded = any(bool(profile.get("degraded")) for profile in profile_payloads)
    if "failed" in learning_statuses or "degraded" in learning_statuses or degraded:
        learning_status = "degraded"
    elif learning_statuses:
        learning_status = "learned"
    else:
        learning_status = ""
    return {
        "usage_summary": "；".join(usage_summaries[:8]),
        "task_routing_hints": task_routing_hints[:12],
        "side_effects": side_effects[:12],
        "risk_notes": risk_notes[:12],
        "learning_status": learning_status,
        "degraded": degraded,
    }


def _flatten_string_values(*values: Any) -> list[str]:
    items: list[str] = []
    for value in values:
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            nested = candidate if isinstance(candidate, list) else [candidate]
            for item in nested:
                text = _text(item)
                if text and text not in items:
                    items.append(text)
    return items


def collect_agent_assets(agent_service: Any) -> list[dict[str, Any]]:
    if agent_service is None:
        return []
    if getattr(agent_service, "manager", None) is not None and callable(getattr(agent_service.manager, "list_assets", None)):
        raw_agents = agent_service.manager.list_assets() or []
    elif callable(getattr(agent_service, "list_active_agents", None)):
        raw_agents = agent_service.list_active_agents() or []
    elif callable(getattr(agent_service, "list_agents", None)):
        raw_agents = agent_service.list_agents() or []
    else:
        raw_agents = []
    rows: list[dict[str, Any]] = []
    for item in raw_agents:
        payload = _model_dump(item)
        agent_id = _text(payload.get("agent_id") or payload.get("id") or payload.get("name"))
        name = _text(payload.get("agent_name") or payload.get("name") or agent_id)
        if not agent_id and not name:
            continue
        rows.append(
            {
                "source_type": "Agent",
                "agent_id": agent_id,
                "function_name": name,
                "function_introduction": _text(payload.get("function_description") or payload.get("description")),
                "documentation_urls": _documentation_urls(
                    payload.get("documentation_url"),
                    payload.get("doc_url"),
                    payload.get("endpoint"),
                ),
                "status": _text(payload.get("status")),
                "trust_level": _text(payload.get("trust_level")),
                "capabilities": payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else [],
                "protocol_capabilities": _string_list(payload.get("protocol_capabilities")),
                "service_hooks": _string_list(payload.get("service_hooks")),
            }
        )
    return rows


def collect_external_service_assets(external_connector_service: Any) -> list[dict[str, Any]]:
    external_connector_service = _resolve_external_connector_service(external_connector_service)
    if external_connector_service is None or not callable(getattr(external_connector_service, "list_connectors", None)):
        return []
    rows: list[dict[str, Any]] = []
    for connector in external_connector_service.list_connectors() or []:
        payload = _model_dump(connector)
        connector_id = _text(payload.get("connector_id"))
        display_name = _text(payload.get("display_name") or connector_id)
        capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else []
        if not connector_id:
            continue
        cap_payloads = [_model_dump(capability) for capability in capabilities]
        rows.append(
            {
                "source_type": "External_Service",
                "connector_id": connector_id,
                "connector_name": display_name,
                "target_app": _text(payload.get("target_app")),
                "connector_type": _text(payload.get("connector_type")),
                "function_name": display_name or connector_id,
                "function_introduction": _external_connector_introduction(payload, cap_payloads),
                "documentation_urls": _documentation_urls(
                    payload.get("manifest_path"),
                    payload.get("documentation_url"),
                    payload.get("doc_url"),
                ),
                "status": _text(payload.get("status")),
                "read_only": all(bool(capability.get("read_only", True)) for capability in cap_payloads) if cap_payloads else True,
                "side_effect_type": "；".join(_string_list([capability.get("side_effect_type") for capability in cap_payloads])),
                "risk_level": _highest_risk_level(cap_payloads),
                "profile_level": _connector_profile_level(cap_payloads),
                "verification_mode": _connector_verification_mode(cap_payloads),
                "capability_count": len(cap_payloads),
                "capability_names": [
                    _text(capability.get("name")) for capability in cap_payloads if _text(capability.get("name"))
                ],
                "requires_confirmation": any(bool(capability.get("requires_confirmation", False)) for capability in cap_payloads),
                "evidence_required": any(bool(capability.get("evidence_required", True)) for capability in cap_payloads)
                if cap_payloads
                else True,
            }
        )
    return rows


def _external_connector_introduction(payload: dict[str, Any], capabilities: list[dict[str, Any]]) -> str:
    description = _text(payload.get("description"))
    capability_descriptions = _string_list([capability.get("description") for capability in capabilities])
    capability_names = [_text(capability.get("name")) for capability in capabilities if _text(capability.get("name"))]
    parts: list[str] = []
    if description:
        parts.append(description)
    if capability_descriptions:
        parts.append("；".join(capability_descriptions[:8]))
    elif capability_names:
        preview = "、".join(capability_names[:8])
        suffix = "等" if len(capability_names) > 8 else ""
        parts.append(f"外接连接器，提供 {len(capability_names)} 个能力：{preview}{suffix}。")
    return "；".join(parts) if parts else "外接连接器，未声明能力说明。"


def _highest_risk_level(capabilities: list[dict[str, Any]]) -> str:
    levels = [_text(capability.get("risk_level")).lower() for capability in capabilities]
    if any(level in {"critical", "high", "高", "严重"} for level in levels):
        return "high"
    if any(level in {"medium", "中"} for level in levels):
        return "medium"
    if any(level in {"low", "低"} for level in levels):
        return "low"
    return ""


def _connector_profile_level(capabilities: list[dict[str, Any]]) -> str:
    levels = _string_list([capability.get("profile_level") for capability in capabilities])
    if "真实已验证" in levels:
        return "真实已验证"
    if "未验证" in levels:
        return "未验证"
    return levels[0] if levels else ""


def _connector_verification_mode(capabilities: list[dict[str, Any]]) -> str:
    modes = _string_list([capability.get("verification_mode") for capability in capabilities])
    if modes and all(mode == "真实已验证" for mode in modes):
        return "真实已验证"
    return "未验证" if modes else ""


def _resolve_external_connector_service(external_connector_service: Any) -> Any:
    from zentex.external_connectors.service import resolve_service

    return resolve_service(external_connector_service)


def collect_external_tool_context(
    *,
    cli_service: Any = None,
    mcp_service: Any = None,
    agent_service: Any = None,
    external_connector_service: Any = None,
) -> dict[str, Any]:
    count_sources = collect_external_asset_count_sources(
        cli_service=cli_service,
        mcp_service=mcp_service,
        agent_service=agent_service,
        external_connector_service=external_connector_service,
    )
    return {
        "CLI_Tools": _normalize_external_asset_summaries(count_sources["CLI_Tools"]),
        "MCP_Tools": _normalize_external_asset_summaries(count_sources["MCP_Tools"]),
        "Agents": _normalize_external_agent_summaries(count_sources["Agents"]),
        "External_Services": _normalize_external_asset_summaries(count_sources["External_Services"]),
    }


def collect_external_asset_count_sources(
    *,
    cli_service: Any = None,
    mcp_service: Any = None,
    agent_service: Any = None,
    external_connector_service: Any = None,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "CLI_Tools": collect_cli_tool_assets(cli_service),
        "MCP_Tools": collect_mcp_tool_assets(mcp_service),
        "Agents": collect_agent_assets(agent_service),
        "External_Services": collect_external_service_assets(external_connector_service),
    }


def build_q2_external_system_prompt() -> str:
    return Q2_EXTERNAL_SYSTEM_PROMPT


def build_q2_external_llm_request(
    *,
    cli_service: Any = None,
    mcp_service: Any = None,
    agent_service: Any = None,
    external_connector_service: Any = None,
) -> dict[str, Any]:
    count_sources = collect_external_asset_count_sources(
        cli_service=cli_service,
        mcp_service=mcp_service,
        agent_service=agent_service,
        external_connector_service=external_connector_service,
    )
    model_context = {
        "CLI_Tools": _normalize_external_asset_summaries(count_sources["CLI_Tools"]),
        "MCP_Tools": _normalize_external_asset_summaries(count_sources["MCP_Tools"]),
        "Agents": _normalize_external_agent_summaries(count_sources["Agents"]),
        "External_Services": _normalize_external_asset_summaries(count_sources["External_Services"]),
    }
    template_values = {
        "CLI_TOOLS_JSON": _json_block(model_context["CLI_Tools"]),
        "MCP_TOOLS_JSON": _json_block(model_context["MCP_Tools"]),
        "AGENTS_JSON": _json_block(model_context["Agents"]),
        "EXTERNAL_SERVICES_JSON": _json_block(model_context["External_Services"]),
    }
    return {
        "system_prompt": build_q2_external_system_prompt(),
        "prompt": _render_template("user_prompt.md", template_values),
        "model_context": model_context,
        "asset_count_sources": count_sources,
        "template_files": prompt_template_files(_TEMPLATE_DIR, _TEMPLATE_FILES),
    }


def build_deterministic_external_asset_inventory(model_context: dict[str, Any]) -> dict[str, Any]:
    cli_tools = model_context.get("CLI_Tools") if isinstance(model_context.get("CLI_Tools"), list) else []
    mcp_tools = model_context.get("MCP_Tools") if isinstance(model_context.get("MCP_Tools"), list) else []
    external_services = (
        model_context.get("External_Services") if isinstance(model_context.get("External_Services"), list) else []
    )
    agents = model_context.get("Agents") if isinstance(model_context.get("Agents"), list) else []

    available_external_tools = [
        _deterministic_tool_inventory_item(item)
        for item in [*cli_tools, *mcp_tools, *external_services]
        if isinstance(item, dict) and _text(item.get("name"))
    ]
    external_agents = [
        _deterministic_agent_inventory_item(item)
        for item in agents
        if isinstance(item, dict) and (_text(item.get("name")) or _text(item.get("expertise")))
    ]
    warnings = _deterministic_unverified_warnings(available_external_tools, external_agents)
    return {
        "available_external_tools": available_external_tools,
        "external_agents": external_agents,
        "unverified_external_warnings": warnings,
    }


def _normalize_external_asset_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        usage_profile = row.get("usage_profile") if isinstance(row.get("usage_profile"), dict) else {}
        name = _text(row.get("function_name") or row.get("connector_name"))
        if not name:
            continue
        summary = {
            "asset_type": _text(row.get("source_type")),
            "name": name,
            "function": _external_function_label(row),
            "operation_object": _operation_object_name(row),
            "operation_object_capability": _operation_object_capability(row, usage_profile),
            "description": _text(row.get("function_introduction")),
            "status": _text(row.get("status")),
            "task_routing_hints": _external_task_routing_hints(row, usage_profile),
            "side_effects": _external_side_effects(row, usage_profile),
            "verification_status": _verification_status(row, usage_profile),
        }
        server_name = _text(row.get("server_name"))
        if server_name:
            summary["server_name"] = server_name
        connector_name = _text(row.get("connector_name"))
        if connector_name:
            summary["connector_name"] = connector_name
        target_app = _text(row.get("target_app"))
        if target_app:
            summary["target_app"] = target_app
        summaries.append(summary)
    return summaries


def _deterministic_tool_inventory_item(item: dict[str, Any]) -> dict[str, str]:
    name = _text(item.get("name"))
    function_label = _text(item.get("function")) or "external tool"
    object_name = _text(item.get("operation_object")) or name
    object_capability = _text(item.get("operation_object_capability") or item.get("description"))
    if not object_capability:
        object_capability = f"{object_name} 的底层能力未在外部资产注册信息中完整说明，需要先验证再用于任务路由。"
    capability_summary = (
        f"这是一个{function_label}。其底层操作对象是 {object_name}，"
        f"底层对象能力为：{object_capability}。该资产适用于需要调用该外部对象能力完成真实外部操作或信息交互的任务。"
    )
    function_description = _external_operation_description(
        name=name,
        operation_object=object_name,
        item=item,
    )
    return {
        "name": name,
        "capability_summary": capability_summary,
        "description": capability_summary,
        "function_description": function_description,
        "task_routing_hints": _join_inventory_text(item.get("task_routing_hints")),
        "side_effects": _join_inventory_text(item.get("side_effects")),
        "verification_status": _external_inventory_verification_status(item),
    }


def _external_operation_description(*, name: str, operation_object: str, item: dict[str, Any]) -> str:
    capability_names = _string_list(item.get("capability_names"), item.get("tool_names"))
    task_hints = _string_list(item.get("task_routing_hints"))
    if capability_names:
        return f"{name or operation_object} 能对 {operation_object or name} 执行 {('、'.join(capability_names[:8]))} 等操作。"
    if task_hints:
        return f"{name or operation_object} 能对 {operation_object or name} 执行相关操作：{'；'.join(task_hints[:6])}"
    return f"{name or operation_object} 能对 {operation_object or name} 执行其注册说明中声明的外部操作。"


def _deterministic_agent_inventory_item(item: dict[str, Any]) -> dict[str, str]:
    verification_status = _external_inventory_verification_status(item)
    return {
        "name": _text(item.get("name")),
        "expertise": _text(item.get("expertise")) or "未声明外部协作专长，需要验证后再调度。",
        "verification_status": verification_status,
        "credibility_level": _text(item.get("credibility_level")) or ("高" if verification_status == "真实已验证" else "低"),
    }


def _deterministic_unverified_warnings(
    tools: list[dict[str, str]],
    agents: list[dict[str, str]],
) -> list[str]:
    warnings: list[str] = []
    for item in tools:
        if item.get("verification_status") != "真实已验证":
            name = item.get("name") or "未命名外部工具"
            warnings.append(f"警告：[{name}] 未完成真实外部验证，建议下游调度器限流、降级或先执行验证。")
    for item in agents:
        if item.get("verification_status") != "真实已验证":
            name = item.get("name") or "未命名外部 Agent"
            warnings.append(f"警告：[{name}] 未完成真实外部验证，建议下游调度器限流、降级或先执行验证。")
    return warnings


def _join_inventory_text(value: Any) -> str:
    items = _string_list(value)
    return "；".join(items) if items else "未声明，需要在外部任务调度前验证。"


def _external_inventory_verification_status(item: dict[str, Any]) -> str:
    status = _text(item.get("verification_status"))
    return "真实已验证" if status == "真实已验证" else "未验证"


def _normalize_external_agent_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agents: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _text(row.get("function_name"))
        expertise = _text(row.get("function_introduction"))
        if not name and not expertise:
            continue
        verification_status = _agent_verification_status(row)
        agents.append(
            {
                "name": name,
                "expertise": expertise,
                "status": _text(row.get("status")),
                "verification_status": verification_status,
                "credibility_level": _credibility_level(row, verification_status),
            }
        )
    return agents


def _external_function_label(row: dict[str, Any]) -> str:
    source_type = _text(row.get("source_type"))
    if source_type == "CLI":
        return "CLI command"
    if source_type == "MCP":
        return "MCP tool"
    if source_type == "External_Service":
        connector_type = _text(row.get("connector_type"))
        return connector_type or "external connector capability"
    return source_type or "external asset"


def _operation_object_name(row: dict[str, Any]) -> str:
    source_type = _text(row.get("source_type"))
    target_app = _text(row.get("target_app"))
    if target_app:
        return target_app
    connector_name = _text(row.get("connector_name"))
    if source_type == "External_Service" and connector_name:
        return connector_name
    server_name = _text(row.get("server_name"))
    if source_type == "MCP" and server_name:
        return server_name
    raw_name = _text(row.get("function_name") or connector_name or server_name)
    return _strip_wrapper_terms(raw_name)


def _operation_object_capability(row: dict[str, Any], usage_profile: dict[str, Any]) -> str:
    usage_summary = _text(usage_profile.get("usage_summary"))
    description = _text(row.get("function_introduction"))
    object_name = _operation_object_name(row)
    source_type = _text(row.get("source_type"))
    if usage_summary and description and usage_summary.lower() != description.lower():
        return f"{usage_summary}；{description}"
    if usage_summary:
        return usage_summary
    if description:
        return description
    if object_name:
        return f"{object_name} 的底层能力未在注册信息中完整说明，需要 LLM 基于名称谨慎归纳并标注不确定性。"
    return f"{source_type or '外部资产'} 的底层操作对象未声明，需要验证后再用于任务路由。"


def _strip_wrapper_terms(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    for token in (
        " command line interface",
        " command-line interface",
        " command line",
        " connector cli",
        " api cli",
        " cli tool",
        " cli",
        " mcp tool",
        " connector",
        " adapter",
        " wrapper",
        " 调用器",
        " 连接器",
        " 工具",
    ):
        if text.lower().endswith(token):
            text = text[: -len(token)].strip(" -_/：:（）()")
    return text or value.strip()


def _external_task_routing_hints(row: dict[str, Any], usage_profile: dict[str, Any]) -> list[str]:
    hints = _string_list(usage_profile.get("task_routing_hints"))
    if hints:
        return hints
    description = _text(row.get("function_introduction"))
    return [description] if description else []


def _external_side_effects(row: dict[str, Any], usage_profile: dict[str, Any]) -> list[str]:
    side_effects = _string_list(usage_profile.get("side_effects"), row.get("side_effect_type"))
    if side_effects:
        return side_effects
    if bool(row.get("mutates_state", False)):
        return ["会修改外部系统状态，执行前需要确认影响范围。"]
    if bool(row.get("side_effect_free", False)):
        return ["未声明写入副作用，但仍属于外部执行资产，首次调度前需要验证。"]
    return ["副作用未知，需要在外部任务调度前验证。"]


def _verification_status(row: dict[str, Any], usage_profile: dict[str, Any]) -> str:
    explicit = _text(row.get("verification_status") or row.get("verification_mode") or row.get("profile_level"))
    explicit_lower = explicit.lower()
    learning_status = _text(usage_profile.get("learning_status")).lower()
    status = _text(row.get("status")).lower()
    if explicit == "真实已验证" or explicit_lower in {"real_verified", "verified", "true_verified"}:
        return "真实已验证"
    if explicit == "未验证" or explicit == _LEGACY_SIMULATED_VERIFICATION_STATUS or explicit_lower in {
        "unverified",
        "pending",
        "verification_failed",
        "failed",
        "degraded",
        "learned",
        "completed",
        "success",
        "simulated",
        "simulated_learned",
    }:
        return "未验证"
    if explicit in {"真实已验证", "未验证"}:
        return explicit
    if not usage_profile:
        return "未验证"
    if learning_status or usage_profile.get("degraded"):
        return "未验证"
    if status in {"enabled", "active", "healthy", "ready"}:
        return "真实已验证"
    return "未验证"


def _agent_verification_status(row: dict[str, Any]) -> str:
    explicit = _text(row.get("verification_status") or row.get("verification_mode") or row.get("profile_level"))
    explicit_lower = explicit.lower()
    if explicit == "真实已验证" or explicit_lower in {"real_verified", "verified", "true_verified"}:
        return "真实已验证"
    if explicit == "未验证" or explicit == _LEGACY_SIMULATED_VERIFICATION_STATUS or explicit_lower in {
        "unverified",
        "pending",
        "verification_failed",
        "failed",
        "degraded",
        "learned",
        "completed",
        "success",
        "simulated",
        "simulated_learned",
    }:
        return "未验证"
    status = _text(row.get("status")).lower()
    trust_level = _text(row.get("trust_level")).lower()
    if status in {"enabled", "active", "healthy", "ready"} and trust_level not in {"", "unknown", "untrusted"}:
        return "真实已验证"
    return "未验证"


def _credibility_level(row: dict[str, Any], verification_status: str) -> str:
    trust_level = _text(row.get("trust_level")).lower()
    if verification_status == "真实已验证" and trust_level not in {"", "unknown", "untrusted"}:
        return "高"
    return "低"

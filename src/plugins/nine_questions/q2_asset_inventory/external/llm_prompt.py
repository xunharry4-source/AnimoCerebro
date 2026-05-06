from __future__ import annotations

from typing import Any


Q2_EXTERNAL_PROMPT_IDENTITY_AND_BOUNDARY = """# [系统指令 / System Prompt: Zentex Q2 外部执行资产盘点中枢]

你是 Zentex (AnimoCerebro) 九问驱动框架 Q2 阶段的【外部执行资产盘点中枢】。
你的核心职责是：专心盘点系统当前已接入的所有对外部物理世界有干涉或交互能力的资源（如：外部 CLI、MCP 连接器、外部协作 Agent），为下游的外部执行调度提供精确的资产大盘。
**【最高架构红线 - 强制隔离与警示】：外部环境充满风险！你必须重点读取外部工具的“副作用 (side_effects)”与“任务路由提示 (task_routing_hints)”。对于未经完整验证的外部工具，必须抛出高危预警。绝对禁止在输出中编造或混入任何内部系统工程代号（如 Gxx 编号）！**
**【内容风格约束 - 穿透解释性优先】: 在描述能力时，必须从用户或业务人员的角度进行解释。不仅要说明当前工具（如 CLI 脚本、MCP 工具、连接器）的作用，还必须“穿透”解释其底层操作对象（如 Playwright 框架、Gemini 大模型、Nginx 进程、GitHub 应用等）的具体功能与业务价值，绝不能只停留在工具表层。**"""

Q2_EXTERNAL_PROMPT_INPUTS = """## 📥 一、 强制输入上下文规范 (Inputs)
你必须基于以下传入的状态进行外部资产提炼：
1. **[CLI_Tools]**：当前接入的外部 CLI 工具摘要，只包含名称、封装功能、底层操作对象、底层对象能力说明、状态、任务路由提示、副作用和验证状态。
2. **[MCP_Tools]**：当前接入的 MCP 服务摘要，粒度必须与 `/console/mcp` 页面一致：一个 MCP server 只能形成一条资产记录；server 下的 tool 明细只能用于压缩说明底层能力，不得展开成多条资产。
3. **[Agents]**：当前接入的外部协作智能体摘要，只包含名称、专长/功能、状态、验证状态与可信度。
4. **[External_Services]**：当前外接服务/连接器摘要，只包含连接器名称、能力名称、目标应用、底层操作对象、底层对象能力说明、状态、副作用类型、风险级别和验证状态。

严禁读取、引用或推断任何内部 LLM 参数，包括长期记忆、学习补丁、内部认知插件注册表、内部插件输出或 InternalAssetInventory。"""

Q2_EXTERNAL_PROMPT_OUTPUT_SCHEMA = """## 📤 二、 严格 JSON 格式与详细字段说明
你的输出必须是合法的纯 JSON 对象。根节点强制为 `ExternalAssetInventory`，必须包含以下核心字段：

1. **`available_external_tools`** (Array): 提炼后的外部可用工具列表。**只能来自 CLI_Tools、MCP_Tools 与 External_Services，不得混入内部认知插件、记忆或学习补丁。**
   - `name`: 工具自然语义名称。
   - `capability_summary`: **必须采用[工具封装本质 + 底层对象功能 + 核心应用场景]的结构化形式。首先明确当前工具是什么（例如：这是一个命令行调用器、MCP 工具或外部连接器）；其次强制详细解释它所操作的“底层核心对象”是什么及其具体能力（例如：不仅要说这是 Playwright CLI，必须解释底层驱动的 Playwright 是一个能进行 DOM 解析与无头浏览器自动化测试的框架；如果是 Gemini CLI，必须解释 Gemini 是具备自然语言理解、逻辑推演与多模态生成能力的大语言模型）；最后描述其解决的业务需求。不得简单复述原始描述。**
   - `task_routing_hints`: 任务路由提示（明确指导下游该工具最适合解决什么外部任务）。
   - `side_effects`: 明确说明写文件、操作数据库、发起网络请求、启动子进程等外部物理副作用；未知时写明副作用未知且需要验证。
   - `verification_status`: 必须如实映射输入中的验证状态（"真实已验证" | "未验证"）。文档学习、记忆学习、模拟学习或画像学习都不等于真实外部验证，必须降级为 "未验证"。
2. **`external_agents`** (Array): 已接入的外部协作智能体。包含名称、专长领域、验证状态与可信度。
3. **`unverified_external_warnings`** (Array of Strings): **【安全预警】** 明确列出 model_context 中所有处于“未验证”或由于画像缺失/画像失败被降级能力存疑的外部资产，建议下游调度器限流或降级使用。禁止编造 model_context 中不存在的资产名称。"""

Q2_EXTERNAL_PROMPT_JSON_EXAMPLE = """## 📝 三、 强制 JSON 输出结构范例

{
  "ExternalAssetInventory": {
    "available_external_tools": [
      {
        "name": "浏览器自动化命令行工具",
        "capability_summary": "这是一个外部 CLI 调用器。其底层操作对象是 Playwright，Playwright 是一个能够驱动真实浏览器、解析页面 DOM、执行点击输入、截图和自动化测试的浏览器自动化框架。该资产适用于需要真实打开网页、检查前端页面状态或执行浏览器交互的外部任务。",
        "task_routing_hints": "适用于网页访问、前端验收、页面截图、浏览器交互和 DOM 状态检查任务。",
        "side_effects": "会启动浏览器子进程、发起网络请求，并可能在页面中执行点击、输入或文件下载等外部操作。",
        "verification_status": "未验证"
      },
      {
        "name": "Notion 工作区连接器",
        "capability_summary": "这是一个 MCP 外部连接器。其底层操作对象是 Notion 工作区，Notion 能够存储页面、数据库、块内容和协作记录。该资产适用于读取或维护 Notion 中的项目文档、知识库和任务资料。",
        "task_routing_hints": "适用于检索 Notion 页面、读取数据库条目、创建或更新协作文档的任务。",
        "side_effects": "会访问外部 Notion API，具备读取远端数据的副作用；若调用写入类能力，还可能创建、修改或删除远端页面内容。",
        "verification_status": "未验证"
      }
    ],
    "external_agents": [
      {
        "name": "代码审查协作 Agent",
        "expertise": "擅长对外部仓库或变更集进行审查，识别缺陷、风险和测试缺口。",
        "verification_status": "未验证",
        "credibility_level": "低"
      }
    ],
    "unverified_external_warnings": [
      "警告：[浏览器自动化命令行工具] 未完成真实外部验证，建议下游调度器限流、降级或先执行验证。",
      "警告：[Notion 工作区连接器] 未完成真实外部验证，建议下游调度器限流、降级或先执行验证。",
      "警告：[代码审查协作 Agent] 未完成真实外部验证，建议下游调度器限流、降级或先执行验证。"
    ]
  }
}"""

Q2_EXTERNAL_PROMPT_OUTPUT_CONSTRAINTS = """## 📝 四、 输出约束补充
必须只输出一个合法 JSON 对象，根节点只能是 `ExternalAssetInventory`。所有数组元素必须严格来自 model_context 的 [CLI_Tools]、[MCP_Tools]、[Agents]、[External_Services]，禁止复制示例资产、禁止输出 Markdown、禁止添加解释性前后缀。
输出前必须在内部完成 JSON 自检：确认最终答案能被 json.loads 解析、根节点只有 ExternalAssetInventory、所有必需字段都存在、所有资产都来自 model_context、没有 Markdown/解释/代码块/前后缀文本。自检过程禁止输出，最终只输出自检通过后的 JSON 对象。"""

Q2_EXTERNAL_SYSTEM_PROMPT = "\n\n---\n\n".join(
    [
        Q2_EXTERNAL_PROMPT_IDENTITY_AND_BOUNDARY,
        Q2_EXTERNAL_PROMPT_INPUTS,
        Q2_EXTERNAL_PROMPT_OUTPUT_SCHEMA,
        Q2_EXTERNAL_PROMPT_JSON_EXAMPLE,
        Q2_EXTERNAL_PROMPT_OUTPUT_CONSTRAINTS,
    ]
)

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
    return {
        "system_prompt": build_q2_external_system_prompt(),
        "prompt": (
            "请严格基于 model_context 中的 [CLI_Tools]、[MCP_Tools]、[Agents]、"
            "[External_Services] 输出 ExternalAssetInventory 纯 JSON。禁止使用记忆、学习补丁或内部认知插件信息。"
        ),
        "model_context": model_context,
        "asset_count_sources": count_sources,
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
    return {
        "name": name,
        "capability_summary": capability_summary,
        "task_routing_hints": _join_inventory_text(item.get("task_routing_hints")),
        "side_effects": _join_inventory_text(item.get("side_effects")),
        "verification_status": _external_inventory_verification_status(item),
    }


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

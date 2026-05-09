from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

from zentex.cli.models import CliToolRegistrationConfig, ToolUsageProfile
from zentex.mcp.models import McpServerConfig, McpToolDescriptor


class ToolDocumentationLearningError(RuntimeError):
    pass


_SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[a-z0-9._\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization|cookie)(\s*[=:]\s*)['\"]?[^'\"\s]+"),
    re.compile(r"(?i)(bearer\s+)[a-z0-9._\-]{16,}"),
    re.compile(r"(?i)(sk-[a-z0-9]{12,})"),
]


def redact_sensitive_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): redact_sensitive_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_payload(item) for item in value]
    if not isinstance(value, str):
        return value
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}{match.group(2) if len(match.groups()) > 1 else ''}[REDACTED]", redacted)
    return redacted


@dataclass(frozen=True)
class CliDocumentationInput:
    config: CliToolRegistrationConfig
    help_output: str = ""
    version_output: str = ""
    fetched_doc: str = ""
    fetched_project_doc: str = ""


@dataclass(frozen=True)
class McpDocumentationInput:
    config: McpServerConfig
    tool: McpToolDescriptor
    fetched_doc: str = ""
    fetched_project_doc: str = ""


class ToolDocumentationLearningService:
    """Host-side doc reader and usage-profile extractor for CLI/MCP tools."""

    def __init__(
        self,
        llm_service: Any = None,
        *,
        fetch_timeout_seconds: float = 8.0,
        allow_heuristic_fallback: bool = False,
    ) -> None:
        self._llm_service = llm_service
        self._fetch_timeout_seconds = fetch_timeout_seconds
        self._allow_heuristic_fallback = allow_heuristic_fallback

    def collect_cli_input(self, config: CliToolRegistrationConfig) -> CliDocumentationInput:
        help_output = self._run_probe(config, config.help_probe_args or ["--help"])
        version_output = self._run_probe(config, config.version_probe_args or ["--version"])
        if not help_output.strip() and not config.help_doc_url and not config.project_doc_url:
            raise ToolDocumentationLearningError(
                "CLI registration requires --help output, help_doc_url, or project_doc_url"
            )
        fetched_doc = ""
        if config.help_doc_url:
            try:
                fetched_doc = self._fetch_doc(config.help_doc_url, label="help_doc_url")
            except ToolDocumentationLearningError:
                if not help_output.strip() and not config.project_doc_url:
                    raise
        fetched_project_doc = ""
        if config.project_doc_url:
            try:
                fetched_project_doc = self._fetch_doc(config.project_doc_url, label="project_doc_url")
            except ToolDocumentationLearningError:
                if not help_output.strip() and not fetched_doc.strip():
                    raise
        return CliDocumentationInput(
            config=config,
            help_output=redact_sensitive_payload(help_output),
            version_output=redact_sensitive_payload(version_output),
            fetched_doc=redact_sensitive_payload(fetched_doc),
            fetched_project_doc=redact_sensitive_payload(fetched_project_doc),
        )

    def learn_cli_usage_profile(self, payload: CliDocumentationInput) -> ToolUsageProfile:
        context = {
            "tool_type": "cli",
            "tool_name": payload.config.tool_name,
            "description": payload.config.description,
            "command_executable": payload.config.command_executable,
            "command_args": payload.config.command_args,
            "read_only": payload.config.read_only_flag,
            "help_doc_url": payload.config.help_doc_url,
            "project_doc_url": payload.config.project_doc_url,
            "project_name": payload.config.project_name,
            "project_description": payload.config.project_description,
            "help_output": payload.help_output[:20000],
            "version_output": payload.version_output[:4000],
            "documentation": payload.fetched_doc[:30000],
            "project_documentation": payload.fetched_project_doc[:30000],
        }
        return self._extract_profile(
            context=context,
            source_type="cli",
            source_refs=[
                ref
                for ref in ["--help", "--version", payload.config.help_doc_url, payload.config.project_doc_url]
                if ref
            ],
            read_only=payload.config.read_only_flag,
        )

    def learn_mcp_tool_usage_profile(self, payload: McpDocumentationInput) -> ToolUsageProfile:
        schema = payload.tool.input_schema or {}
        if not self._schema_is_informative(schema) and not payload.fetched_doc.strip() and not payload.fetched_project_doc.strip():
            raise ToolDocumentationLearningError(
                "MCP tool registration requires informative input_schema, readable help_doc_url, or readable project_doc_url"
            )
        context = {
            "tool_type": "mcp",
            "server_id": payload.config.server_id,
            "server_name": payload.config.name,
            "server_description": payload.config.description,
            "project_doc_url": payload.config.project_doc_url,
            "auth_mode": payload.config.auth_mode,
            "tool_name": payload.tool.tool_name,
            "tool_description": payload.tool.description,
            "input_schema": schema,
            "mutates_state": payload.tool.mutates_state,
            "read_only_hint": payload.tool.read_only_hint,
            "help_doc_url": payload.config.help_doc_url,
            "documentation": payload.fetched_doc[:30000],
            "project_documentation": payload.fetched_project_doc[:30000],
        }
        return self._extract_profile(
            context=redact_sensitive_payload(context),
            source_type="mcp",
            source_refs=[
                ref
                for ref in ["tool_manifest", "input_schema", payload.config.help_doc_url, payload.config.project_doc_url]
                if ref
            ],
            read_only=payload.tool.read_only_hint and not payload.tool.mutates_state,
        )

    def fetch_mcp_doc(self, config: McpServerConfig) -> str:
        return redact_sensitive_payload(self._fetch_doc(config.help_doc_url, label="help_doc_url")) if config.help_doc_url else ""

    def fetch_mcp_project_doc(self, config: McpServerConfig) -> str:
        return (
            redact_sensitive_payload(self._fetch_doc(config.project_doc_url, label="project_doc_url"))
            if config.project_doc_url
            else ""
        )

    def _extract_profile(
        self,
        *,
        context: Dict[str, Any],
        source_type: str,
        source_refs: List[str],
        read_only: bool,
    ) -> ToolUsageProfile:
        if self._llm_service is None:
            if not self._allow_heuristic_fallback:
                raise ToolDocumentationLearningError("LLM service is required for tool documentation learning")
            raw = self._local_extract(context)
        else:
            try:
                raw = self._call_llm(context)
            except Exception:
                if not self._allow_heuristic_fallback:
                    raise
                raw = self._local_extract(context)
                raw["degraded"] = True
                raw["learning_status"] = "degraded"
        if hasattr(raw, "output"):
            raw = raw.output
        if not isinstance(raw, dict):
            raise ToolDocumentationLearningError("LLM usage-profile extraction did not return a JSON object")
        raw = redact_sensitive_payload(raw)
        raw = self._normalize_profile_payload(raw, source_type=source_type)
        raw = self._semantic_profile_payload(raw, context=context, source_type=source_type, read_only=read_only)
        if not raw.get("examples"):
            if source_type == "cli":
                executable = str(context.get("command_executable") or context.get("tool_name") or "tool").strip()
                raw["examples"] = [
                    {
                        "command": [executable, "--help"],
                        "description": "Inspect supported CLI options from the registered executable.",
                    }
                ]
            else:
                tool_name = str(context.get("tool_name") or "tool").strip()
                raw["examples"] = [
                    {
                        "tool": tool_name,
                        "arguments": {},
                        "description": "Call with arguments matching the registered MCP input schema.",
                    }
                ]
        if not raw.get("task_routing_hints"):
            raw["task_routing_hints"] = [self._fallback_routing_hint(raw, context=context, source_type=source_type)]
        if not raw.get("side_effects"):
            raw["side_effects"] = [self._fallback_side_effect(read_only=read_only, source_type=source_type)]
        if not read_only and not raw.get("risk_notes"):
            raw["risk_notes"] = ["这是外部执行域工具，调度前必须确认权限、参数和执行范围。"]
        raw.setdefault("source_type", source_type)
        raw.setdefault("source_refs", source_refs)
        raw.setdefault("degraded", False)
        raw.setdefault("learning_status", "learned")
        profile = ToolUsageProfile.model_validate(raw)
        self._validate_profile(profile, read_only=read_only)
        return profile

    def _call_llm(self, context: Dict[str, Any]) -> Any:
        prompt = (
            "# [系统指令 / System Prompt: Zentex 外部工具文档自学习与画像提炼中枢]\n\n"
            "你是 Zentex (AnimoCerebro) 架构中的【外部工具文档自学习与画像提炼中枢】"
            "(Tool Documentation Learning Service)。\n"
            "你的核心职责是：在外部执行域工具（如 CLI 命令行、MCP 连接器）接入系统时，"
            "深度阅读其原始的干瘪说明（如 `--help` 输出、Manifest、Input Schema 或官方文档 URL 抓取内容），"
            "并将其提炼为结构化、语义清晰、可直接给 Q2 与任务调度中心使用的工具用法画像 (ToolUsageProfile)，"
            "供下游的 Q2（资产盘点）与任务调度中心精确识别和使用。\n\n"
            "【最高安全红线 - 强制脱敏与防幻觉】：\n"
            "1. 绝对禁止在提取的 examples（调用示例）中保存任何明文的 API Key、Bearer Token、"
            "Cookie、密码或敏感环境变量。你必须强制将其替换为 `[REDACTED]` 占位符。\n"
            "2. 如果提供的输入文档信息极度匮乏，无法支撑基础能力判断，绝对禁止自行捏造虚假功能，"
            "必须在 risk_notes 中显式声明文档不足。\n\n"
            "【学习模拟质量红线】：\n"
            "1. 你必须在本阶段完成解释性提炼，输出必须是最终画像，不允许把原始 help、schema、manifest、"
            "注册配置、命令参数列表、JSON 片段或日志片段原样塞进 usage_summary/task_routing_hints/side_effects。\n"
            "2. usage_summary 必须说明“这个外部工具本质是什么、解决什么问题”，不要复述技术字段。\n"
            "3. task_routing_hints 必须说明“什么业务任务应该路由给它”，不要输出泛泛的工具名称或原始描述。\n"
            "4. side_effects 必须说明真实外部影响。即使是只读工具，也要说明是否会发起网络请求、启动子进程、"
            "读取本地文件或访问外部服务；未知时明确写“副作用未知，需要验证”。\n\n"
            "## 📥 一、强制输入上下文规范 (Inputs)\n"
            "你将接收到以下某一种或多种原始材料：\n"
            "1. [Raw_Help_Output]：CLI 工具的 `--help` 或 `--version` 原始输出文本。\n"
            "2. [MCP_Manifest_Schema]：MCP 服务的 Tool Manifest 与 Input Schema JSON 声明。\n"
            "3. [External_Doc_Content]：从 `help_doc_url` 或 `project_doc_url` 抓取的外部服务器文档或静态说明内容。\n\n"
            "## 📤 二、严格 JSON 格式与详细字段说明 (Strict Output Schema)\n"
            "你的输出必须是合法的纯 JSON 对象。根节点强制为 `ToolUsageProfile`，"
            "且 `ToolUsageProfile` 必须精确包含以下 10 个核心字段：\n"
            "1. usage_summary (String): 工具用法摘要，一句话概括该工具的核心作用。\n"
            "2. supported_commands (Array of Strings): 该工具支持的核心子命令或 MCP Tool 列表。\n"
            "3. argument_schema (Object): 核心参数结构说明，参数名必须对应实际作用。\n"
            "4. examples (Array of Strings): 必须严格脱敏的合法调用示例，凭据必须替换为 `[REDACTED]`。\n"
            "5. side_effects (String): 是否会产生外部物理副作用，如修改文件、操作数据库或发起真实网络请求。\n"
            "6. auth_requirements (String): 认证要求；若无则填 `无`。\n"
            "7. risk_notes (String): 安全风险与文档不足风险提示。\n"
            "8. task_routing_hints (String): 调度核心提示，说明什么业务场景最应路由到该工具。\n"
            "9. source_refs (String): 标明基于哪些文档源生成，如 `基于 --help 输出提取`。\n"
            "10. learning_status (String): 强制输出 `simulated_learned`。\n\n"
            "## 📝 三、强制 JSON 输出结构范例\n"
            "{\n"
            '  "ToolUsageProfile": {\n'
            '    "usage_summary": "无头浏览器网页自动化与 DOM 元素解析命令行工具。",\n'
            '    "supported_commands": ["npx playwright-cli open", "npx playwright-cli codegen"],\n'
            '    "argument_schema": {"--url": "目标测试网页的 URL"},\n'
            '    "examples": ["npx playwright-cli screenshot --url https://example.com output.png"],\n'
            '    "side_effects": "会启动真实浏览器子进程，并可能生成截图或 trace 文件。",\n'
            '    "auth_requirements": "若测试私有页面，依赖本地浏览器缓存或 auth.json 鉴权文件。",\n'
            '    "risk_notes": "启动缓慢可能导致短时 CPU 负载拉高。",\n'
            '    "task_routing_hints": "当需要动态 JS 渲染、E2E 页面测试或登录态 DOM 分析时，应首选此工具。",\n'
            '    "source_refs": "综合 --help 输出与官方文档提取。",\n'
            '    "learning_status": "simulated_learned"\n'
            "  }\n"
            "}\n\n"
            "输出前自检：第一行必须是 `{`，最后一行必须是 `}`，不得输出 Markdown 包装或解释性前缀。"
        )
        result = self._llm_service.generate_json(
            prompt=prompt,
            context=context,
            source_module="zentex.tools.documentation_learning",
            invocation_phase="tool_documentation_learning",
            max_output_tokens=900,
            temperature=0.0,
            metadata={
                "tool_documentation_learning": True,
                "request_timeout_seconds": 15,
                "max_json_repair_attempts": 1,
            },
        )
        return getattr(result, "output", result)

    @staticmethod
    def _normalize_profile_payload(raw: Dict[str, Any], *, source_type: str) -> Dict[str, Any]:
        wrapper = raw.get("ToolUsageProfile")
        normalized = dict(wrapper) if isinstance(wrapper, dict) else dict(raw)

        def _string_list(value: Any) -> list[str]:
            if value is None:
                return []
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if isinstance(value, str):
                text = value.strip()
                return [text] if text else []
            return [str(value).strip()] if str(value).strip() else []

        for key in (
            "supported_commands",
            "supported_tools",
            "side_effects",
            "auth_requirements",
            "risk_notes",
            "task_routing_hints",
            "source_refs",
        ):
            if key in normalized:
                normalized[key] = _string_list(normalized.get(key))
        if "supported_tools" not in normalized and source_type == "mcp":
            normalized["supported_tools"] = _string_list(normalized.get("supported_commands"))

        examples = normalized.get("examples")
        if isinstance(examples, list):
            normalized_examples: list[dict[str, Any]] = []
            for item in examples:
                if isinstance(item, dict):
                    normalized_examples.append(item)
                elif isinstance(item, str) and item.strip():
                    example_text = item.strip()
                    if source_type == "cli":
                        normalized_examples.append(
                            {
                                "command": example_text.split(),
                                "description": example_text,
                            }
                        )
                    else:
                        normalized_examples.append({"description": example_text})
            normalized["examples"] = normalized_examples
        elif isinstance(examples, str) and examples.strip():
            example_text = examples.strip()
            normalized["examples"] = [
                {
                    "command": example_text.split(),
                    "description": example_text,
                }
                if source_type == "cli"
                else {"description": example_text}
            ]

        argument_schema = normalized.get("argument_schema")
        if source_type == "cli" and not isinstance(argument_schema, dict):
            normalized["argument_schema"] = {
                "type": "array",
                "items": {"type": "string"},
            }
            argument_schema = normalized["argument_schema"]
        if isinstance(argument_schema, dict):
            schema_type = argument_schema.get("type")
            if isinstance(schema_type, list):
                preferred = next(
                    (
                        str(item)
                        for item in schema_type
                        if str(item) in {"object", "array"}
                    ),
                    "array" if source_type == "cli" else (str(schema_type[0]) if schema_type else ""),
                )
                normalized["argument_schema"] = {
                    **argument_schema,
                    "type": preferred,
                    **({"items": argument_schema.get("items") or {"type": "string"}} if source_type == "cli" and preferred == "array" else {}),
                }
            elif source_type == "cli" and schema_type not in {"object", "array"}:
                normalized["argument_schema"] = {
                    **argument_schema,
                    **({"type": "array", "items": argument_schema.get("items") or {"type": "string"}} if "type" in argument_schema else {}),
                }
            elif source_type == "mcp" and schema_type not in {"object", "array"}:
                normalized["argument_schema"] = {
                    **argument_schema,
                    "type": "object",
                }
        if source_type == "mcp" and not isinstance(normalized.get("argument_schema"), dict):
            normalized["argument_schema"] = {"type": "object"}

        return normalized

    @classmethod
    def _semantic_profile_payload(
        cls,
        raw: Dict[str, Any],
        *,
        context: Dict[str, Any],
        source_type: str,
        read_only: bool,
    ) -> Dict[str, Any]:
        normalized = dict(raw)
        normalized["usage_summary"] = cls._semantic_text(
            normalized.get("usage_summary"),
            fallback=cls._fallback_usage_summary(context, source_type=source_type),
            limit=220,
        )
        normalized["task_routing_hints"] = cls._semantic_list(
            normalized.get("task_routing_hints"),
            fallback=cls._fallback_routing_hint(normalized, context=context, source_type=source_type),
            limit=220,
            max_items=4,
        )
        normalized["side_effects"] = cls._semantic_list(
            normalized.get("side_effects"),
            fallback=cls._fallback_side_effect(read_only=read_only, source_type=source_type),
            limit=220,
            max_items=4,
        )
        normalized["risk_notes"] = cls._semantic_list(
            normalized.get("risk_notes"),
            fallback="外部工具调度前需要结合当前任务权限、参数范围和验证状态进行确认。",
            limit=220,
            max_items=4,
        )
        normalized["auth_requirements"] = cls._semantic_list(
            normalized.get("auth_requirements"),
            fallback="无",
            limit=180,
            max_items=3,
        )
        return normalized

    @staticmethod
    def _semantic_text(value: Any, *, fallback: str, limit: int) -> str:
        text = ToolDocumentationLearningService._compact_text(value)
        if not text or ToolDocumentationLearningService._looks_like_raw_dump(text):
            text = fallback
        return text[:limit].strip()

    @staticmethod
    def _semantic_list(value: Any, *, fallback: str, limit: int, max_items: int) -> list[str]:
        candidates = value if isinstance(value, list) else ([value] if value is not None else [])
        items: list[str] = []
        for candidate in candidates:
            text = ToolDocumentationLearningService._compact_text(candidate)
            if not text or ToolDocumentationLearningService._looks_like_raw_dump(text):
                continue
            text = text[:limit].strip()
            if text and text not in items:
                items.append(text)
            if len(items) >= max_items:
                break
        if not items:
            items.append(fallback[:limit].strip())
        return items

    @staticmethod
    def _compact_text(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return ""
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _looks_like_raw_dump(text: str) -> bool:
        if len(text) > 320:
            return True
        lowered = text.lower()
        raw_markers = ("usage:", "options:", "arguments:", "schema", "manifest", "{", "}", "```")
        if sum(1 for marker in raw_markers if marker in lowered) >= 2:
            return True
        if len(re.findall(r"--[a-z0-9][a-z0-9-]*", lowered)) >= 4:
            return True
        return False

    @staticmethod
    def _fallback_usage_summary(context: Dict[str, Any], *, source_type: str) -> str:
        if source_type == "cli":
            name = str(context.get("tool_name") or context.get("command_executable") or "CLI 工具").strip()
            description = str(context.get("description") or context.get("project_description") or "").strip()
            if description:
                return f"这是一个外部命令行工具，用于{description}。"
            return f"这是一个外部命令行工具，用于通过 {name} 执行宿主系统上的命令行能力。"
        name = str(context.get("tool_name") or "MCP 工具").strip()
        description = str(context.get("tool_description") or context.get("server_description") or "").strip()
        if description:
            return f"这是一个 MCP 外部连接器工具，用于{description}。"
        return f"这是一个 MCP 外部连接器工具，用于通过 {name} 调用外部服务能力。"

    @staticmethod
    def _fallback_routing_hint(raw: Dict[str, Any], *, context: Dict[str, Any], source_type: str) -> str:
        summary = ToolDocumentationLearningService._compact_text(raw.get("usage_summary"))
        if summary and not ToolDocumentationLearningService._looks_like_raw_dump(summary):
            return f"适用于需要{summary}的外部执行任务。"
        if source_type == "cli":
            description = str(context.get("description") or "调用本机命令行工具完成明确外部操作").strip()
            return f"适用于需要{description}的任务。"
        description = str(context.get("tool_description") or context.get("server_description") or "调用 MCP 连接器完成明确外部服务交互").strip()
        return f"适用于需要{description}的任务。"

    @staticmethod
    def _fallback_side_effect(*, read_only: bool, source_type: str) -> str:
        if read_only:
            if source_type == "cli":
                return "通常只读取命令行输出，不应修改外部状态；但可能启动本地子进程并读取本机环境。"
            return "通常只读取外部服务信息，不应修改远端状态；但可能发起网络请求并访问连接器权限范围内的数据。"
        if source_type == "cli":
            return "可能启动本地子进程、写入文件或改变宿主系统状态，执行前必须验证参数。"
        return "可能发起网络请求并修改外部服务或远端数据，执行前必须验证权限和影响范围。"

    def _local_extract(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic host extractor used when no LLM service is attached in tests/local dev."""
        text = "\n".join(
            str(context.get(key) or "")
            for key in ("description", "project_description", "help_output", "documentation", "project_documentation")
        )
        command_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("-") or "  " in stripped:
                command_lines.append(stripped[:240])
        examples = []
        executable = str(context.get("command_executable") or context.get("tool_name") or "tool")
        if context.get("tool_type") == "cli":
            examples.append({"command": [executable, "--help"], "description": "Inspect supported CLI options."})
        else:
            examples.append({"tool": context.get("tool_name"), "arguments": {}, "description": "Call with arguments matching input_schema."})
        schema = context.get("input_schema") if context.get("tool_type") == "mcp" else {"type": "array", "items": {"type": "string"}}
        return {
            "usage_summary": (
                str(
                    context.get("description")
                    or context.get("tool_description")
                    or "外部执行域工具画像，基于本地注册信息与可用文档进行降级提炼。"
                )
            ).strip(),
            "supported_commands": command_lines[:20] if context.get("tool_type") == "cli" else [],
            "supported_tools": [str(context.get("tool_name"))] if context.get("tool_type") == "mcp" else [],
            "argument_schema": schema or {"type": "object"},
            "examples": examples,
            "side_effects": [] if context.get("read_only") or context.get("read_only_hint") else ["May mutate external or local state."],
            "auth_requirements": [f"auth_mode={context.get('auth_mode')}"] if context.get("auth_mode") else [],
            "risk_notes": ["Execution-domain tool; task center must dispatch explicitly."] if not context.get("read_only", True) else [],
            "task_routing_hints": [
                str(
                    context.get("description")
                    or context.get("tool_description")
                    or "Use only when a task explicitly matches this registered external tool."
                )[:240]
            ],
        }

    def _run_probe(self, config: CliToolRegistrationConfig, args: List[str]) -> str:
        if not args:
            return ""
        try:
            completed = subprocess.run(  # noqa: S603
                [config.command_executable, *config.command_args, *args],
                text=True,
                capture_output=True,
                env=dict(config.env) or None,
                cwd=config.project_path,
                timeout=8,
                check=False,
            )
        except Exception:
            return ""
        return "\n".join(part for part in [completed.stdout, completed.stderr] if part)

    def _fetch_doc(self, url: Optional[str], *, label: str = "help_doc_url") -> str:
        if not url:
            return ""
        if not url.startswith(("http://", "https://")):
            raise ToolDocumentationLearningError(f"{label} must be http(s)")
        try:
            req = Request(url, headers={"User-Agent": "ZentexToolDocumentationLearning/1.0"})
            with urlopen(req, timeout=self._fetch_timeout_seconds) as response:  # noqa: S310
                return response.read(512_000).decode("utf-8", errors="replace")
        except Exception as exc:
            raise ToolDocumentationLearningError(f"failed to fetch {label}: {exc}") from exc

    @staticmethod
    def _schema_is_informative(schema: Dict[str, Any]) -> bool:
        if not isinstance(schema, dict) or not schema:
            return False
        return bool(schema.get("properties") or schema.get("required") or schema.get("description") or schema.get("type"))

    @staticmethod
    def _validate_profile(profile: ToolUsageProfile, *, read_only: bool) -> None:
        if not profile.usage_summary.strip():
            raise ToolDocumentationLearningError("usage profile missing usage_summary")
        if len(profile.usage_summary.strip()) < 20:
            raise ToolDocumentationLearningError("usage profile usage_summary is too thin")
        if profile.source_type == "cli" and not profile.supported_commands:
            raise ToolDocumentationLearningError("CLI usage profile missing supported_commands")
        if profile.source_type == "mcp" and not profile.supported_tools:
            raise ToolDocumentationLearningError("MCP usage profile missing supported_tools")
        if not isinstance(profile.argument_schema, dict) or not profile.argument_schema:
            raise ToolDocumentationLearningError("usage profile missing argument_schema")
        schema_type = profile.argument_schema.get("type")
        if schema_type is not None and schema_type not in {"object", "array"}:
            raise ToolDocumentationLearningError("usage profile argument_schema type must be object or array")
        if not profile.examples:
            raise ToolDocumentationLearningError("usage profile missing examples")
        if not profile.task_routing_hints:
            raise ToolDocumentationLearningError("usage profile missing task_routing_hints")
        if not profile.source_refs:
            raise ToolDocumentationLearningError("usage profile missing source_refs")
        if not read_only and not profile.side_effects:
            raise ToolDocumentationLearningError("mutating usage profile missing side_effects")
        if not read_only and not profile.risk_notes:
            raise ToolDocumentationLearningError("mutating usage profile missing risk_notes")
        rendered = json.dumps(profile.model_dump(mode="json"), ensure_ascii=False)
        if any(pattern.search(rendered) for pattern in _SECRET_PATTERNS):
            raise ToolDocumentationLearningError("usage profile contains unredacted sensitive material")

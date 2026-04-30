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


@dataclass(frozen=True)
class McpDocumentationInput:
    config: McpServerConfig
    tool: McpToolDescriptor
    fetched_doc: str = ""


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
        if not help_output.strip() and not config.help_doc_url:
            raise ToolDocumentationLearningError("CLI registration requires --help output or help_doc_url")
        fetched_doc = ""
        if config.help_doc_url:
            try:
                fetched_doc = self._fetch_doc(config.help_doc_url)
            except ToolDocumentationLearningError:
                if not help_output.strip():
                    raise
        return CliDocumentationInput(
            config=config,
            help_output=redact_sensitive_payload(help_output),
            version_output=redact_sensitive_payload(version_output),
            fetched_doc=redact_sensitive_payload(fetched_doc),
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
            "help_output": payload.help_output[:20000],
            "version_output": payload.version_output[:4000],
            "documentation": payload.fetched_doc[:30000],
        }
        return self._extract_profile(
            context=context,
            source_type="cli",
            source_refs=[ref for ref in ["--help", "--version", payload.config.help_doc_url] if ref],
            read_only=payload.config.read_only_flag,
        )

    def learn_mcp_tool_usage_profile(self, payload: McpDocumentationInput) -> ToolUsageProfile:
        schema = payload.tool.input_schema or {}
        if not self._schema_is_informative(schema) and not payload.fetched_doc.strip():
            raise ToolDocumentationLearningError("MCP tool registration requires informative input_schema or readable help_doc_url")
        context = {
            "tool_type": "mcp",
            "server_id": payload.config.server_id,
            "server_name": payload.config.name,
            "server_description": payload.config.description,
            "auth_mode": payload.config.auth_mode,
            "tool_name": payload.tool.tool_name,
            "tool_description": payload.tool.description,
            "input_schema": schema,
            "mutates_state": payload.tool.mutates_state,
            "read_only_hint": payload.tool.read_only_hint,
            "help_doc_url": payload.config.help_doc_url,
            "documentation": payload.fetched_doc[:30000],
        }
        return self._extract_profile(
            context=redact_sensitive_payload(context),
            source_type="mcp",
            source_refs=[ref for ref in ["tool_manifest", "input_schema", payload.config.help_doc_url] if ref],
            read_only=payload.tool.read_only_hint and not payload.tool.mutates_state,
        )

    def fetch_mcp_doc(self, config: McpServerConfig) -> str:
        return redact_sensitive_payload(self._fetch_doc(config.help_doc_url)) if config.help_doc_url else ""

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
            raw = self._call_llm(context)
        if hasattr(raw, "output"):
            raw = raw.output
        if not isinstance(raw, dict):
            raise ToolDocumentationLearningError("LLM usage-profile extraction did not return a JSON object")
        raw = redact_sensitive_payload(raw)
        raw = self._normalize_profile_payload(raw, source_type=source_type)
        raw.setdefault("source_type", source_type)
        raw.setdefault("source_refs", source_refs)
        raw.setdefault("degraded", False)
        raw.setdefault("learning_status", "learned")
        profile = ToolUsageProfile.model_validate(raw)
        self._validate_profile(profile, read_only=read_only)
        return profile

    def _call_llm(self, context: Dict[str, Any]) -> Any:
        prompt = (
            "Extract a structured Zentex tool usage profile from the provided CLI/MCP documentation. "
            "Return JSON with exactly these semantic fields: usage_summary, supported_commands, "
            "supported_tools, argument_schema, examples, side_effects, auth_requirements, risk_notes, "
            "task_routing_hints. Redact secrets and never include tokens, cookies, auth headers, or raw sensitive env."
        )
        result = self._llm_service.generate_json(
            prompt=prompt,
            context=context,
            source_module="zentex.tools.documentation_learning",
            invocation_phase="tool_documentation_learning",
            max_output_tokens=2000,
            temperature=0.0,
            metadata={"tool_documentation_learning": True},
        )
        return getattr(result, "output", result)

    @staticmethod
    def _normalize_profile_payload(raw: Dict[str, Any], *, source_type: str) -> Dict[str, Any]:
        normalized = dict(raw)

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
        if source_type == "cli":
            normalized["argument_schema"] = {
                "type": "array",
                "items": {"type": "string"},
            }
            return normalized
        if source_type == "cli" and not isinstance(argument_schema, dict):
            argument_schema = {"type": "array", "items": {"type": "string"}}
            normalized["argument_schema"] = argument_schema
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
                    "type": "array",
                    "items": argument_schema.get("items") or {"type": "string"},
                }

        return normalized

    def _local_extract(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic host extractor used when no LLM service is attached in tests/local dev."""
        text = "\n".join(str(context.get(key) or "") for key in ("description", "help_output", "documentation"))
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
            "usage_summary": (str(context.get("description") or context.get("tool_description") or "External tool.")).strip(),
            "supported_commands": command_lines[:20] if context.get("tool_type") == "cli" else [],
            "supported_tools": [str(context.get("tool_name"))] if context.get("tool_type") == "mcp" else [],
            "argument_schema": schema or {"type": "object"},
            "examples": examples,
            "side_effects": [] if context.get("read_only") or context.get("read_only_hint") else ["May mutate external or local state."],
            "auth_requirements": [f"auth_mode={context.get('auth_mode')}"] if context.get("auth_mode") else [],
            "risk_notes": ["Execution-domain tool; task center must dispatch explicitly."] if not context.get("read_only", True) else [],
            "task_routing_hints": [str(context.get("description") or context.get("tool_description") or "")[:240]],
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

    def _fetch_doc(self, url: Optional[str]) -> str:
        if not url:
            return ""
        if not url.startswith(("http://", "https://")):
            raise ToolDocumentationLearningError("help_doc_url must be http(s)")
        try:
            req = Request(url, headers={"User-Agent": "ZentexToolDocumentationLearning/1.0"})
            with urlopen(req, timeout=self._fetch_timeout_seconds) as response:  # noqa: S310
                return response.read(512_000).decode("utf-8", errors="replace")
        except Exception as exc:
            raise ToolDocumentationLearningError(f"failed to fetch help_doc_url: {exc}") from exc

    @staticmethod
    def _schema_is_informative(schema: Dict[str, Any]) -> bool:
        if not isinstance(schema, dict) or not schema:
            return False
        return bool(schema.get("properties") or schema.get("required") or schema.get("description") or schema.get("type"))

    @staticmethod
    def _validate_profile(profile: ToolUsageProfile, *, read_only: bool) -> None:
        if not profile.usage_summary.strip():
            raise ToolDocumentationLearningError("usage profile missing usage_summary")
        if not isinstance(profile.argument_schema, dict) or not profile.argument_schema:
            raise ToolDocumentationLearningError("usage profile missing argument_schema")
        schema_type = profile.argument_schema.get("type")
        if schema_type is not None and schema_type not in {"object", "array"}:
            raise ToolDocumentationLearningError("usage profile argument_schema type must be object or array")
        rendered = json.dumps(profile.model_dump(mode="json"), ensure_ascii=False)
        if any(pattern.search(rendered) for pattern in _SECRET_PATTERNS):
            raise ToolDocumentationLearningError("usage profile contains unredacted sensitive material")

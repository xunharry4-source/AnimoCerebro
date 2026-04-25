#!/usr/bin/env python3
"""
Agent local LLM client.

文件用途:
    为 Agent 工作流提供本地 LLM 调用实现，避免调用 src/zentex 下的内部代码。

主要职责:
    - 读取项目 `.env` 和 `config/provider_tools.yml` 中的 provider 配置。
    - 使用 Agent 自己的代码调用 Gemini 或 OpenAI-compatible JSON 生成接口。
    - 输出统一的 JSON object 结果，并带 trace 元数据。
    - 在 provider、网络、鉴权、JSON 解析失败时 fail-closed。

不负责:
    - 不 import `zentex.*`。
    - 不把 `src/` 加入 `sys.path`。
    - 不生成 fallback 内容或 mock cognition state。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROVIDER_CONFIG_PATH = PROJECT_ROOT / "config" / "provider_tools.yml"
DEFAULT_DOTENV_PATH = PROJECT_ROOT / ".env"


class AgentLLMError(RuntimeError):
    """Structured local Agent LLM failure."""

    def __init__(self, message: str, *, code: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class AgentModelCallerContext:
    source_module: str
    invocation_phase: str
    decision_id: str
    trace_id: str


@dataclass(frozen=True)
class AgentLLMResult:
    output: Dict[str, Any]
    provider_key: str
    model: str


@dataclass(frozen=True)
class ProviderConfig:
    provider_name: str
    api_base: str
    api_key_env: Optional[str]
    default_model: str
    timeout_seconds: int


class AgentLocalLLMService:
    """Agent-owned provider client with JSON-only output."""

    def __init__(
        self,
        *,
        config_path: Path = DEFAULT_PROVIDER_CONFIG_PATH,
        dotenv_path: Path = DEFAULT_DOTENV_PATH,
    ) -> None:
        self.config_path = Path(config_path)
        self.dotenv_path = Path(dotenv_path)

    def generate_json(
        self,
        *,
        prompt: str,
        context: Dict[str, Any],
        caller_context: AgentModelCallerContext,
        source_module: str,
        invocation_phase: str,
        decision_id: str,
        provider_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_output_tokens: int = 1200,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentLLMResult:
        """Generate a JSON object through an Agent-owned provider integration."""
        configs, default_provider = self._load_provider_configs()
        selected_provider = provider_key or self._resolve_env_value("ZENTEX_DEFAULT_PROVIDER") or default_provider
        provider_config = configs.get(str(selected_provider))
        if provider_config is None:
            raise AgentLLMError(
                "Unknown LLM provider configured for Agent",
                code="agent_llm_provider_unknown",
                details={"provider_key": selected_provider},
            )
        selected_model = model or provider_config.default_model
        api_key = self._resolve_api_key(provider_config)
        user_prompt = self._render_prompt(prompt=prompt, context=context)

        if provider_config.provider_name == "gemini":
            output_text = self._call_gemini(
                api_key=api_key,
                model=selected_model,
                user_prompt=user_prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        elif provider_config.provider_name in {"openai", "openai_compat", "chatgpt"}:
            output_text = self._call_openai_compatible(
                api_base=provider_config.api_base,
                api_key=api_key,
                model=selected_model,
                user_prompt=user_prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                timeout_seconds=provider_config.timeout_seconds,
            )
        else:
            raise AgentLLMError(
                "Provider is not implemented in Agent local LLM client",
                code="agent_llm_provider_not_implemented",
                details={"provider_name": provider_config.provider_name, "provider_key": selected_provider},
            )

        output = self._parse_json_output(output_text)
        return AgentLLMResult(output=output, provider_key=str(selected_provider), model=selected_model)

    def _call_gemini(
        self,
        *,
        api_key: str,
        model: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        try:
            from google import genai
            from google.genai import types
        except Exception as exc:
            raise AgentLLMError(
                "google-genai is required for Agent Gemini provider",
                code="agent_llm_sdk_missing",
                details={"package": "google-genai"},
            ) from exc

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    response_mime_type="application/json",
                ),
            )
            return str(getattr(response, "text", "") or "")
        except Exception as exc:
            raise AgentLLMError(
                f"Agent Gemini provider invocation failed: {exc.__class__.__name__}: {exc}",
                code="agent_llm_invocation_failed",
                details={"provider": "gemini", "model": model},
            ) from exc

    def _call_openai_compatible(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
        timeout_seconds: int,
    ) -> str:
        url = f"{api_base.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return only a valid JSON object."},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            raise AgentLLMError(
                "Agent OpenAI-compatible provider returned HTTP error",
                code="agent_llm_http_error",
                details={"status": exc.code, "body": body},
            ) from exc
        except (URLError, json.JSONDecodeError) as exc:
            raise AgentLLMError(
                f"Agent OpenAI-compatible provider invocation failed: {exc.__class__.__name__}: {exc}",
                code="agent_llm_invocation_failed",
                details={"provider": "openai_compatible"},
            ) from exc
        try:
            return str(parsed["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AgentLLMError(
                "Agent OpenAI-compatible response missing message content",
                code="agent_llm_response_invalid",
                details={"payload_keys": list(parsed.keys()) if isinstance(parsed, dict) else []},
            ) from exc

    def _load_provider_configs(self) -> Tuple[Dict[str, ProviderConfig], str]:
        try:
            import yaml
        except Exception as exc:
            raise AgentLLMError(
                "PyYAML is required to read provider_tools.yml",
                code="agent_llm_yaml_missing",
            ) from exc
        if not self.config_path.exists():
            raise AgentLLMError(
                "Provider config file is missing",
                code="agent_llm_config_missing",
                details={"path": str(self.config_path)},
            )
        payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        providers = payload.get("providers") or {}
        if not isinstance(providers, dict):
            raise AgentLLMError("Provider config must contain providers mapping", code="agent_llm_config_invalid")
        configs: Dict[str, ProviderConfig] = {}
        for provider_key, item in providers.items():
            if not isinstance(item, dict):
                continue
            configs[str(provider_key)] = ProviderConfig(
                provider_name=str(item.get("provider_name") or provider_key),
                api_base=str(item.get("api_base") or ""),
                api_key_env=str(item.get("api_key_env") or "") or None,
                default_model=str(item.get("default_model") or ""),
                timeout_seconds=int(item.get("timeout_seconds") or 30),
            )
        default_provider = str(payload.get("default_provider") or "gemini").strip()
        return configs, default_provider

    def _resolve_api_key(self, config: ProviderConfig) -> str:
        env_name = str(config.api_key_env or "").strip()
        value = self._resolve_env_value(env_name) if env_name else None
        if value:
            return value
        raise AgentLLMError(
            "Provider API key is missing for Agent local LLM client",
            code="agent_llm_api_key_missing",
            details={"api_key_env": env_name},
        )

    def _resolve_env_value(self, name: str) -> Optional[str]:
        key = str(name or "").strip()
        if not key:
            return None
        value = os.getenv(key)
        if value and not self._is_placeholder(value):
            return value
        dotenv_values = self._load_dotenv()
        value = dotenv_values.get(key)
        if value and not self._is_placeholder(value):
            return value
        aliases = {"GEMINI_API_KEY": ("GOOGLE_API_KEY",)}
        for alias in aliases.get(key, ()):
            alias_value = os.getenv(alias) or dotenv_values.get(alias)
            if alias_value and not self._is_placeholder(alias_value):
                return alias_value
        return None

    def _load_dotenv(self) -> Dict[str, str]:
        if not self.dotenv_path.exists():
            return {}
        values: Dict[str, str] = {}
        for raw_line in self.dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            values[key.strip()] = value
        return values

    def _render_prompt(self, *, prompt: str, context: Dict[str, Any]) -> str:
        rendered_context = json.dumps(context, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return "\n\n".join(
            [
                "Return only a valid JSON object.",
                f"Task:\n{prompt}",
                f"Context JSON:\n{rendered_context}",
            ]
        )

    def _parse_json_output(self, text: str) -> Dict[str, Any]:
        normalized = self._strip_markdown_fence(str(text or ""))
        try:
            parsed = json.loads(normalized)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        candidate = self._extract_first_json_object(normalized)
        if candidate:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        raise AgentLLMError(
            "Agent LLM provider returned non-JSON output",
            code="agent_llm_invalid_json",
            details={"output_snippet": normalized[:500]},
        )

    def _strip_markdown_fence(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()
        return stripped

    def _extract_first_json_object(self, text: str) -> Optional[str]:
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]
        return None

    def _is_placeholder(self, value: str) -> bool:
        candidate = str(value or "").strip().lower()
        return not candidate or candidate in {
            "your-openai-key-here",
            "your-anthropic-key-here",
            "your-api-key-1",
            "replace-me",
            "changeme",
        }

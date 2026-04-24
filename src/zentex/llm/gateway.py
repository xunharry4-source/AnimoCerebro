from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

from zentex.foundation.specs.model_provider import (
    ModelProviderError,
    ModelProviderAuthError,
    ModelProviderCallerContext,
    ModelProviderConfigError,
    ModelProviderParseError,
    ModelProviderRateLimitError,
    ModelProviderRemoteError,
    ModelProviderTimeoutError,
)

@dataclass(frozen=True)
class LLMTokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_optional_mapping(cls, payload: Dict[str, Optional[Any]]) -> "LLMTokenUsage":
        if not payload:
            return cls()
        input_tokens = int(payload.get("input_tokens") or 0)
        output_tokens = int(payload.get("output_tokens") or 0)
        total_tokens = int(payload.get("total_tokens") or (input_tokens + output_tokens))
        return cls(
            input_tokens=max(0, input_tokens),
            output_tokens=max(0, output_tokens),
            total_tokens=max(0, total_tokens),
        )


@dataclass(frozen=True)
class LLMGatewayCall:
    provider_key: str
    model: str
    output: Dict[str, Any]
    usage: LLMTokenUsage
    raw_response: Dict[str, Any]


class LLMGateway:
    def __init__(
        self,
        *,
        default_provider_key: Optional[str] = None,
        tools: Optional[Dict[str, Any]] = None,
    ) -> None:
        from zentex.plugins.service import build_default_provider_tools, get_default_provider_key
        
        self._tools = tools or build_default_provider_tools()
        
        if default_provider_key:
            self._default_provider_key = default_provider_key
        else:
            self._default_provider_key = get_default_provider_key()

        self._lock = Lock()
        self._request_count = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._provider_stats: Dict[str, Dict[str, int]] = {}

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()
        return stripped

    @staticmethod
    def _extract_first_json_object(text: str) -> Optional[str]:
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

    @classmethod
    def _parse_json_output(cls, output_text: str) -> Dict[str, Any]:
        normalized = cls._strip_markdown_fence(str(output_text or ""))
        try:
            parsed = json.loads(normalized)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        candidate = cls._extract_first_json_object(normalized)
        if candidate:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                logger.warning("[LLM GATEWAY] Recovered JSON object from mixed provider output.")
                return parsed

        raise ModelProviderParseError("Provider returned non-JSON output that cannot be recovered to a JSON object.")

    def stats_snapshot(self) -> Dict[str, int]:
        with self._lock:
            total = self._input_tokens + self._output_tokens
            return {
                "request_count": self._request_count,
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "total_tokens": total,
            }

    def _record_usage(self, provider_key: str, usage: LLMTokenUsage) -> None:
        with self._lock:
            self._request_count += 1
            self._input_tokens += usage.input_tokens
            self._output_tokens += usage.output_tokens

            p_stats = self._provider_stats.setdefault(provider_key, {
                "request_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "error_count": 0
            })
            p_stats["request_count"] += 1
            p_stats["input_tokens"] += usage.input_tokens
            p_stats["output_tokens"] += usage.output_tokens
            p_stats["total_tokens"] += usage.total_tokens

    def invoke_generate_json(
        self,
        *,
        prompt: str,
        context: Dict[str, Any],
        caller_context: ModelProviderCallerContext,
        provider_key: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        metadata: Dict[str, Optional[Any]] = None,
    ) -> LLMGatewayCall:
        selected_provider_key, selected_model = self._resolve_provider_and_model(
            provider_key=provider_key,
            model=model,
        )

        logger.info(
            f"[LLM GATEWAY] Invoking provider: {selected_provider_key} | "
            f"model: {selected_model}"
        )
        if not selected_provider_key:
            raise ModelProviderConfigError("provider_key must not be empty")

        tool = self._tools.get(selected_provider_key)
        if tool is None:
            raise ModelProviderConfigError(f"Unknown provider tool: {selected_provider_key}")

        rendered_context = json.dumps(context, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        user_prompt = "\n\n".join([
            "Return only a valid JSON object.",
            f"Task:\n{prompt}",
            f"Context JSON:\n{rendered_context}",
        ])
        
        from zentex.plugins.service import ToolInvocationRequest
        invocation = ToolInvocationRequest(
            model=selected_model,
            prompt=user_prompt,
            system_prompt=system_prompt or "You are a JSON generator.",
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            metadata={**(metadata or {}), "require_json_format": True},
        )

        try:
            response = tool.call(invocation)
            usage = LLMTokenUsage.from_optional_mapping(response.usage)
            self._record_usage(selected_provider_key, usage)

            try:
                output = self._parse_json_output(response.output_text)
            except Exception as exc:
                logger.error(
                    "[LLM GATEWAY] Provider returned non-JSON output | provider=%s model=%s error=%s",
                    selected_provider_key,
                    selected_model,
                    str(exc),
                )
                last_error: Exception = exc
                invalid_output = response.output_text
                for attempt in range(1, 4):
                    repair_prompt = "\n\n".join([
                        "Your previous answer was not valid JSON.",
                        "Return ONLY one valid JSON object that satisfies the original task.",
                        "No markdown, no prose, no code fence, no explanation.",
                        f"Repair attempt: {attempt}",
                        f"Original task:\n{prompt}",
                        f"Context JSON:\n{rendered_context}",
                        f"Previous invalid output:\n{invalid_output}",
                    ])
                    repair_invocation = ToolInvocationRequest(
                        model=selected_model,
                        prompt=repair_prompt,
                        system_prompt=system_prompt or "You are a strict JSON generator.",
                        temperature=0.0,
                        max_output_tokens=max_output_tokens,
                        metadata={
                            **(metadata or {}),
                            "require_json_format": True,
                            "json_repair_retry": True,
                            "json_repair_attempt": attempt,
                        },
                    )
                    try:
                        repair_response = tool.call(repair_invocation)
                        repair_usage = LLMTokenUsage.from_optional_mapping(repair_response.usage)
                        self._record_usage(selected_provider_key, repair_usage)
                        output = self._parse_json_output(repair_response.output_text)
                        response = repair_response
                        usage = repair_usage
                        logger.warning(
                            "[LLM GATEWAY] Provider JSON repair retry succeeded | provider=%s model=%s attempt=%d",
                            selected_provider_key,
                            selected_model,
                            attempt,
                        )
                        break
                    except Exception as repair_exc:
                        last_error = repair_exc
                        invalid_output = getattr(locals().get("repair_response"), "output_text", invalid_output)
                else:
                    raise ModelProviderParseError(
                        f"Provider {selected_provider_key} returned non-JSON output and repair failed: {str(last_error)}"
                    ) from last_error
            return LLMGatewayCall(
                provider_key=selected_provider_key,
                model=selected_model,
                output=output,
                usage=usage,
                raw_response=response.raw_response,
            )
        except Exception as exc:
            with self._lock:
                p_stats = self._provider_stats.setdefault(selected_provider_key, {
                    "request_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "error_count": 0
                })
                p_stats["error_count"] += 1
            categorized_error, category, root = self._map_provider_error(
                exc=exc,
                provider_key=selected_provider_key,
                model=selected_model,
                metadata=metadata or {},
            )
            logger.error(
                "[LLM GATEWAY] Provider call failed | provider=%s model=%s category=%s root_type=%s root_message=%s",
                selected_provider_key,
                selected_model,
                category,
                root.__class__.__name__,
                str(root),
            )
            raise categorized_error from exc

    def get_aggregated_stats(self) -> Dict[str, Any]:
        """Return global and per-provider stats."""
        with self._lock:
            return {
                "total_request_count": self._request_count,
                "total_input_tokens": self._input_tokens,
                "total_output_tokens": self._output_tokens,
                "total_tokens": self._input_tokens + self._output_tokens,
                "providers": self._provider_stats.copy()
            }

    def _resolve_provider_and_model(self, *, provider_key: Optional[str], model: Optional[str]) -> tuple[str, str]:
        selected_provider_key = (provider_key or self._default_provider_key).strip()
        selected_model = str(model or "").strip()
        if not selected_model:
            tool = self._tools.get(selected_provider_key)
            selected_model = str(getattr(tool, "default_model", "") or "").strip()
        if not selected_model:
            selected_model = "default-model"
        return selected_provider_key, selected_model

    def _map_provider_error(
        self,
        *,
        exc: Exception,
        provider_key: str,
        model: str,
        metadata: Dict[str, Any],
    ) -> tuple[Exception, str, Exception]:
        from zentex.llm.providers.base import (
            AuthError,
            ConfigError,
            RateLimitError,
            RemoteServiceError,
            RemoteTimeoutError,
            ResponseParseError,
        )

        root = self._root_cause(exc)
        timeout_hint = metadata.get("request_timeout_seconds")
        timeout_text = f", timeout={timeout_hint}s" if timeout_hint not in (None, "", 0) else ""
        base_message = (
            f"provider={provider_key}, model={model}{timeout_text}, "
            f"root={root.__class__.__name__}: {str(root)}"
        )

        if isinstance(exc, ModelProviderError):
            return exc, self._category_for_exception(exc), root
        if isinstance(exc, RemoteTimeoutError):
            return ModelProviderTimeoutError(f"LLM timeout ({base_message})"), "timeout", root
        if isinstance(exc, RateLimitError):
            return ModelProviderRateLimitError(f"LLM rate_limited ({base_message})"), "rate_limit", root
        if isinstance(exc, AuthError):
            return ModelProviderAuthError(f"LLM auth_failed ({base_message})"), "auth", root
        if isinstance(exc, ConfigError):
            return ModelProviderConfigError(f"LLM config_error ({base_message})"), "config", root
        if isinstance(exc, ResponseParseError):
            return ModelProviderParseError(f"LLM parse_error ({base_message})"), "parse", root
        if isinstance(exc, RemoteServiceError):
            return ModelProviderRemoteError(f"LLM remote_service_error ({base_message})"), "remote_service", root
        if isinstance(root, TimeoutError):
            return ModelProviderTimeoutError(f"LLM timeout ({base_message})"), "timeout", root
        return ModelProviderRemoteError(f"LLM remote_error ({base_message})"), "remote", root

    @staticmethod
    def _root_cause(exc: Exception) -> Exception:
        current: Exception = exc
        seen: set[int] = set()
        while True:
            marker = id(current)
            if marker in seen:
                return current
            seen.add(marker)
            cause = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
            if not isinstance(cause, Exception):
                return current
            current = cause

    @staticmethod
    def _category_for_exception(exc: Exception) -> str:
        if isinstance(exc, ModelProviderTimeoutError):
            return "timeout"
        if isinstance(exc, ModelProviderRateLimitError):
            return "rate_limit"
        if isinstance(exc, ModelProviderAuthError):
            return "auth"
        if isinstance(exc, ModelProviderConfigError):
            return "config"
        if isinstance(exc, ModelProviderParseError):
            return "parse"
        return "remote"

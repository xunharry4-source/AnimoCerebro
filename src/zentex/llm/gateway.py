from __future__ import annotations

import json
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional

from zentex.plugins.service import (
    AuthError,
    BaseProviderTool,
    ConfigError,
    OpenAICompatibleGatewayTool,
    RateLimitError,
    RemoteServiceError,
    RemoteTimeoutError,
    ResponseParseError,
    ToolInvocationRequest,
    ToolInvocationResponse,
    build_default_provider_tools,
    get_default_provider_key,
)
from zentex.foundation.specs.model_provider import (
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
    def from_optional_mapping(cls, payload: Dict[str, Any] | None) -> "LLMTokenUsage":
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
    """
    Single entrypoint for all LLM calls in the repo.

    Responsibilities:
    - select provider tool + model (default from config, overrideable per call)
    - enforce "return JSON only" contract and parse JSON
    - normalize provider errors into Zentex ModelProvider* errors
    - maintain process-level request/token counters
    """

    def __init__(
        self,
        *,
        default_provider_key: Optional[str] = None,
        tools: Dict[str, BaseProviderTool | OpenAICompatibleGatewayTool] | None = None,
    ) -> None:
        self._tools = tools or build_default_provider_tools()
        
        if default_provider_key:
            self._default_provider_key = default_provider_key
        else:
            self._default_provider_key = get_default_provider_key()

        self._lock = Lock()
        self._request_count = 0
        self._input_tokens = 0
        self._output_tokens = 0

    def __deepcopy__(self, memo: Dict[int, object]) -> "LLMGateway":
        # `ManagedPluginRecord.model_copy(deep=True)` is used in core runtime and 
        # web-console test sandboxes. Thread locks are not deepcopyable, so we 
        # recreate a new gateway while reusing the already-built tool objects.
        cloned = LLMGateway(
            default_provider_key=self._default_provider_key,
            tools=self._tools,
        )
        with self._lock:
            cloned._request_count = self._request_count
            cloned._input_tokens = self._input_tokens
            cloned._output_tokens = self._output_tokens
        return cloned

    def stats_snapshot(self) -> Dict[str, int]:
        with self._lock:
            total = self._input_tokens + self._output_tokens
            return {
                "request_count": self._request_count,
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "total_tokens": total,
            }

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
        metadata: Dict[str, Any] | None = None,
    ) -> LLMGatewayCall:
        selected_provider_key, selected_model = self._resolve_provider_and_model(
            provider_key=provider_key,
            model=model,
        )
        if not selected_provider_key:
            raise ModelProviderConfigError("provider_key must not be empty")

        tool = self._tools.get(selected_provider_key)
        if tool is None:
            raise ModelProviderConfigError(
                f"Unknown provider tool: {selected_provider_key}. Available={sorted(self._tools)}"
            )

        effective_system_prompt = system_prompt or (
            "You are a JSON generator. Output a single JSON object and nothing else."
        )
        invocation_metadata = {
            **(metadata or {}),
            "source_module": caller_context.source_module,
            "invocation_phase": caller_context.invocation_phase,
            "decision_id": caller_context.decision_id,
        }
        invocation = self._build_invocation(
            model=selected_model,
            prompt=prompt,
            context=context,
            system_prompt=effective_system_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            metadata=invocation_metadata,
        )

        self._increment_request_attempt()
        try:
            response: ToolInvocationResponse = tool.call(invocation)  # type: ignore[assignment]
        except Exception as exc:
            if self._should_retry_with_compact_context(
                exc=exc,
                provider_key=selected_provider_key,
                caller_context=caller_context,
            ):
                compact_context = self._compact_context_payload(context)
                retry_invocation = self._build_invocation(
                    model=selected_model,
                    prompt=prompt,
                    context=compact_context,
                    system_prompt=effective_system_prompt,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    metadata={
                        **invocation_metadata,
                        "context_compacted": True,
                    },
                )
                self._increment_request_attempt()
                try:
                    response = tool.call(retry_invocation)  # type: ignore[assignment]
                except Exception as retry_exc:
                    raise self._map_tool_error(retry_exc, provider_key=selected_provider_key) from retry_exc
            else:
                raise self._map_tool_error(exc, provider_key=selected_provider_key) from exc

        usage = LLMTokenUsage.from_optional_mapping(response.usage)
        self._increment_usage(usage)

        try:
            output = _parse_json_object(response.output_text)
        except ValueError as exc:
            raise ModelProviderParseError(
                f"Provider {selected_provider_key} returned non-JSON output"
            ) from exc

        return LLMGatewayCall(
            provider_key=selected_provider_key,
            model=selected_model,
            output=output,
            usage=usage,
            raw_response=response.raw_response,
        )

    @staticmethod
    def _build_invocation(
        *,
        model: str,
        prompt: str,
        context: Dict[str, Any],
        system_prompt: str,
        temperature: float,
        max_output_tokens: int,
        metadata: Dict[str, Any],
    ) -> ToolInvocationRequest:
        rendered_context = json.dumps(context, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        user_prompt = "\n\n".join(
            [
                "Return only a valid JSON object. Do not wrap it in markdown.",
                f"Task:\n{prompt}",
                f"Context JSON:\n{rendered_context}",
            ]
        )
        return ToolInvocationRequest(
            model=model,
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            metadata=metadata,
        )

    @staticmethod
    def _should_retry_with_compact_context(
        *,
        exc: Exception,
        provider_key: str,
        caller_context: ModelProviderCallerContext,
    ) -> bool:
        if provider_key != "openai_compat":
            return False
        phase = str(caller_context.invocation_phase or "")
        source = str(caller_context.source_module or "")
        is_nine_question_tail = any(
            marker in phase or marker in source
            for marker in ("q4", "q5", "q6", "q7", "q8", "q9")
        )
        if not is_nine_question_tail:
            return False
        message = str(exc).lower()
        return "500" in message or "status 500" in message or "remote provider" in message

    @classmethod
    def _compact_context_payload(cls, context: Dict[str, Any]) -> Dict[str, Any]:
        def _compact(value: Any, *, depth: int) -> Any:
            if value is None or isinstance(value, (int, float, bool)):
                return value
            if isinstance(value, str):
                text = value.strip()
                if len(text) <= 240:
                    return text
                return f"{text[:240]}...[truncated]"
            if isinstance(value, list):
                items = [_compact(item, depth=depth + 1) for item in value[:8]]
                if len(value) > 8:
                    items.append(f"...[{len(value) - 8} more items truncated]")
                return items
            if isinstance(value, dict):
                compacted: Dict[str, Any] = {}
                for index, (key, item) in enumerate(value.items()):
                    if index >= 20:
                        compacted["__truncated_keys__"] = len(value) - 20
                        break
                    normalized_key = str(key)
                    if normalized_key in {"raw_response", "reasoning_content"}:
                        continue
                    if normalized_key in {"reasoning_summary", "summary", "introduction", "function_description"}:
                        compacted[normalized_key] = _compact(item, depth=depth + 1)
                        continue
                    if depth >= 3 and isinstance(item, (dict, list)):
                        compacted[normalized_key] = "[nested structure omitted]"
                        continue
                    compacted[normalized_key] = _compact(item, depth=depth + 1)
                return compacted
            return str(value)

        compacted = _compact(context, depth=0)
        return compacted if isinstance(compacted, dict) else {"context": compacted}

    def _increment_request_attempt(self) -> None:
        with self._lock:
            self._request_count += 1

    def _increment_usage(self, usage: LLMTokenUsage) -> None:
        if usage.total_tokens <= 0 and usage.input_tokens <= 0 and usage.output_tokens <= 0:
            return
        with self._lock:
            self._input_tokens += max(0, usage.input_tokens)
            self._output_tokens += max(0, usage.output_tokens)

    def _map_tool_error(self, exc: Exception, *, provider_key: str) -> Exception:
        if isinstance(exc, ConfigError):
            return ModelProviderConfigError(str(exc))
        if isinstance(exc, AuthError):
            return ModelProviderAuthError(str(exc))
        if isinstance(exc, RateLimitError):
            return ModelProviderRateLimitError(str(exc))
        if isinstance(exc, RemoteTimeoutError):
            return ModelProviderTimeoutError(str(exc))
        if isinstance(exc, RemoteServiceError):
            return ModelProviderRemoteError(str(exc))
        if isinstance(exc, ResponseParseError):
            return ModelProviderParseError(str(exc))
        return ModelProviderRemoteError(
            f"Unexpected provider failure for {provider_key}: {exc.__class__.__name__}"
        )

    def _resolve_provider_and_model(
        self,
        *,
        provider_key: Optional[str],
        model: Optional[str],
    ) -> tuple[str, str]:
        if provider_key is not None and not provider_key.strip():
            return "", ""

        requested_provider_key = (provider_key or "").strip()
        requested_model = (model or "").strip()

        if requested_provider_key:
            selected_provider_key = requested_provider_key
        else:
            selected_provider_key = self._default_provider_key.strip()

        if not selected_provider_key:
            return "", ""

        tool = self._tools.get(selected_provider_key)
        if tool is None:
            return selected_provider_key, requested_model

        default_model = self._tool_default_model(tool)
        selected_model = requested_model or default_model
        selected_model = self._normalize_model_for_provider(
            provider_key=selected_provider_key,
            model=selected_model,
            default_model=default_model,
        )
        if not selected_model:
            raise ModelProviderConfigError("model must not be empty")
        return selected_provider_key, selected_model

    def _normalize_model_for_provider(
        self,
        *,
        provider_key: str,
        model: str,
        default_model: str,
    ) -> str:
        normalized = model.strip()
        # Strip the "(auto)" routing hint regardless of provider — it is a
        # config-level annotation that must never reach the actual API endpoint.
        if normalized.endswith("(auto)"):
            normalized = normalized.removesuffix("(auto)").strip()
        return normalized

    @staticmethod
    def _tool_default_model(tool: Any) -> str:
        return str(getattr(getattr(tool, "config", None), "default_model", "") or "").strip()


def _parse_json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty output")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Best-effort extraction when providers wrap output with extra text.
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < 0 or end <= start:
            raise
        parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("output is not a JSON object")
    return parsed

from __future__ import annotations

import json
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional

from plugins.provider_tools import (
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
)
from zentex.core.model_provider_spec import (
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
        default_provider_key: str = "openai_compat",
        tools: Dict[str, BaseProviderTool | OpenAICompatibleGatewayTool] | None = None,
    ) -> None:
        self._tools = tools or build_default_provider_tools()
        self._default_provider_key = default_provider_key

        self._lock = Lock()
        self._request_count = 0
        self._input_tokens = 0
        self._output_tokens = 0

    def __deepcopy__(self, memo: Dict[int, object]) -> "LLMGateway":
        # `ManagedPluginRecord.model_copy(deep=True)` is used to isolate web-console
        # test sandboxes. Thread locks are not deepcopyable, so we recreate a new
        # gateway while reusing the already-built tool objects.
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
        selected_provider_key = (provider_key or self._default_provider_key).strip()
        if not selected_provider_key:
            raise ModelProviderConfigError("provider_key must not be empty")

        tool = self._tools.get(selected_provider_key)
        if tool is None:
            raise ModelProviderConfigError(
                f"Unknown provider tool: {selected_provider_key}. Available={sorted(self._tools)}"
            )

        default_model = getattr(getattr(tool, "config", None), "default_model", None)
        selected_model = (model or default_model or "").strip()
        if not selected_model:
            raise ModelProviderConfigError("model must not be empty")

        # Keep the model prompt contract consistent across providers.
        rendered_context = json.dumps(context, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        user_prompt = "\n\n".join(
            [
                "Return only a valid JSON object. Do not wrap it in markdown.",
                f"Task:\n{prompt}",
                f"Context JSON:\n{rendered_context}",
            ]
        )
        effective_system_prompt = system_prompt or (
            "You are a JSON generator. Output a single JSON object and nothing else."
        )

        invocation = ToolInvocationRequest(
            model=selected_model,
            prompt=user_prompt,
            system_prompt=effective_system_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            metadata={
                **(metadata or {}),
                "source_module": caller_context.source_module,
                "invocation_phase": caller_context.invocation_phase,
                "decision_id": caller_context.decision_id,
            },
        )

        self._increment_request_attempt()
        try:
            response: ToolInvocationResponse = tool.call(invocation)  # type: ignore[assignment]
        except Exception as exc:
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

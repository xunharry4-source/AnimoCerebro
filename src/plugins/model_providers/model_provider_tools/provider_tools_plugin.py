from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from zentex.foundation.specs.model_provider import (
    ModelProviderCallerContext,
    ModelProviderConfigError,
    ModelProviderRateLimitError,
)
from zentex.llm.gateway import LLMGateway
from zentex.plugins.contracts import PluginHealthStatus
from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.provider_tools import get_default_provider_key, load_provider_tool_configs


class ProviderToolsModelProvider(BaseModel):
    """
    Metadata-backed model provider plugin for provider-tools integration.

    Responsibilities:
    - expose one configured provider as an active model-provider plugin
    - source provider_name/api_base/default_model/api_key_env from config/provider_tools.yml
    - delegate real LLM access to zentex.llm.gateway.LLMGateway

    Non-responsibilities:
    - it is not an independent LLM transport stack
    - callers should not treat this plugin as a second official request path
    - business code should prefer LLMService/LLMGateway as the canonical entrypoint
    """

    model_config = ConfigDict(extra="allow")

    plugin_id: str = "model_provider_tools"
    version: str = "1.0.0"
    feature_code: str = "model_provider.tools"
    display_name: str = "Provider Tools Model Adapter"
    description: str = "Model provider adapter via provider tools gateway."
    behavior_key: str = "model_provider_tools"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    provider_name: str = Field(default="openai_compat", min_length=1)
    api_base: str = Field(default="https://api.openai.com/v1", min_length=1)
    api_key_env: Optional[str] = Field(default=None)
    default_model: str = Field(default="stub-json-model", min_length=1)
    timeout_seconds: float = Field(default=30.0, gt=0)
    rollback_conditions: list[str] = Field(default_factory=lambda: ["provider_timeout_spike", "provider_auth_regression"])
    revocation_reasons: list[str] = Field(default_factory=lambda: ["reserved_for_runtime_audit"])

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._gateway = LLMGateway(default_provider_key=self.provider_name)
        object.__setattr__(self, "_last_token_usage", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
        object.__setattr__(self, "_last_raw_response", {})
        object.__setattr__(self, "_last_model_name", self.default_model)

    _gateway: LLMGateway = PrivateAttr()

    def generate_json(
        self,
        prompt: str,
        context: dict[str, Any],
        caller_context: Any,
        *,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        normalized_context = self._normalize_caller_context(caller_context)
        result = self._gateway.invoke_generate_json(
            prompt=prompt,
            context=context,
            caller_context=normalized_context,
            provider_key=self.provider_name,
            model=str(model or self.default_model),
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            metadata=metadata or {},
        )
        object.__setattr__(self, "_last_token_usage", result.usage.__dict__)
        object.__setattr__(self, "_last_raw_response", result.raw_response)
        object.__setattr__(self, "_last_model_name", result.model)
        return result.output

    def health_probe(self) -> PluginHealthStatus:
        try:
            result = self._gateway.invoke_generate_json(
                prompt='Respond with {"status":"ok"}',
                context={},
                caller_context=ModelProviderCallerContext(
                    source_module="model_provider.health_probe",
                    invocation_phase="health_probe",
                ),
                provider_key=self.provider_name,
                model=self.default_model,
                temperature=0.0,
                max_output_tokens=32,
            )
        except ModelProviderRateLimitError:
            return PluginHealthStatus.DEGRADED

        object.__setattr__(self, "_last_token_usage", result.usage.__dict__)
        object.__setattr__(self, "_last_raw_response", result.raw_response)
        object.__setattr__(self, "_last_model_name", result.model)
        return PluginHealthStatus.HEALTHY

    @staticmethod
    def _normalize_caller_context(caller_context: Any) -> ModelProviderCallerContext:
        if isinstance(caller_context, ModelProviderCallerContext):
            return caller_context
        if isinstance(caller_context, dict):
            return ModelProviderCallerContext.model_validate(caller_context)
        raise ModelProviderConfigError("caller_context must be a ModelProviderCallerContext or dict")

    @property
    def last_token_usage(self) -> dict[str, int]:
        return dict(getattr(self, "_last_token_usage", {}))

    @property
    def last_raw_response(self) -> dict[str, Any]:
        payload = getattr(self, "_last_raw_response", {})
        return payload if isinstance(payload, dict) else {}

    @property
    def last_model_name(self) -> Optional[str]:
        value = getattr(self, "_last_model_name", None)
        return str(value) if value else None


def build_default_provider_tools_model_provider(
    *,
    provider_name: str | None = None,
    plugin_id: str = "model_provider_tools",
    version: str = "1.0.0",
) -> ProviderToolsModelProvider:
    resolved_provider_name = str(provider_name or get_default_provider_key()).strip()
    configs = load_provider_tool_configs()
    if resolved_provider_name not in configs:
        available = ", ".join(sorted(configs))
        raise ModelProviderConfigError(
            f"Unknown provider_name for model_provider_tools: {resolved_provider_name}. "
            f"Available providers: {available}"
        )
    config = configs[resolved_provider_name]
    return ProviderToolsModelProvider(
        plugin_id=plugin_id,
        version=version,
        provider_name=resolved_provider_name,
        api_key_env=config.api_key_env,
        api_base=config.api_base,
        default_model=config.default_model,
        timeout_seconds=config.timeout_seconds,
    )

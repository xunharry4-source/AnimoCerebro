from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import Field

from plugins.provider_tools import DEFAULT_PROVIDER_CONFIG_PATH, load_provider_tool_configs
from zentex.core.model_provider_spec import (
    ModelProviderCallerContext,
    ModelProviderConfigError,
    ModelProviderAuthError,
    ModelProviderHealthError,
    ModelProviderParseError,
    ModelProviderRateLimitError,
    ModelProviderRemoteError,
    ModelProviderTimeoutError,
    ModelProviderSpec,
)
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.llm.gateway import LLMGateway, LLMTokenUsage


class ProviderToolsModelProvider(ModelProviderSpec):
    """
    ModelProvider plugin backed by `plugins.provider_tools` + `config/provider_tools.yml`.

    This is the repository-wide single entrypoint for model calls:
    every upstream component calls `ModelProviderSpec.generate_json()`,
    and this implementation routes into `zentex.llm.gateway.LLMGateway`.
    """

    provider_name: str = Field(default="openai_compat", min_length=1)
    api_base: str = Field(default="", min_length=1)
    api_key_env: str = Field(default="", min_length=1)
    default_model: str = Field(default="", min_length=1)
    timeout_seconds: float = Field(default=30.0, gt=0)
    health_probe_endpoint: str = Field(default="provider_tools://health", min_length=1)
    health_status: PluginHealthStatus = PluginHealthStatus.UNKNOWN

    def __init__(self, **data: Any) -> None:
        provider_name = str(data.get("provider_name") or "openai_compat").strip()
        configs = load_provider_tool_configs(DEFAULT_PROVIDER_CONFIG_PATH)
        if provider_name not in configs:
            raise ModelProviderConfigError(
                f"Unknown provider_name for ProviderToolsModelProvider: {provider_name}"
            )
        tool_config = configs[provider_name]
        hydrated = {
            "provider_name": tool_config.provider_name,
            "api_base": tool_config.api_base,
            "api_key_env": tool_config.api_key_env,
            "default_model": tool_config.default_model,
            "timeout_seconds": tool_config.timeout_seconds,
            "health_probe_endpoint": f"{tool_config.api_base.rstrip('/')}/health",
        }
        super().__init__(**{**data, **hydrated})
        object.__setattr__(
            self,
            "_gateway",
            LLMGateway(default_provider_key=self.provider_name),
        )
        object.__setattr__(self, "_last_token_usage", LLMTokenUsage())
        object.__setattr__(self, "_last_raw_response", {})
        object.__setattr__(self, "_last_model_name", self.default_model)

    def generate_json(
        self,
        prompt: str,
        context: Dict[str, Any],
        caller_context: ModelProviderCallerContext,
        *,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not prompt or not prompt.strip():
            raise ModelProviderConfigError("prompt must not be empty")
        if not isinstance(caller_context, ModelProviderCallerContext):
            raise ModelProviderConfigError("caller_context must be a ModelProviderCallerContext")

        call = self._gateway.invoke_generate_json(
            prompt=prompt,
            context=context,
            caller_context=caller_context,
            provider_key=self.provider_name,
            model=model,
        )
        object.__setattr__(self, "_last_token_usage", call.usage)
        object.__setattr__(self, "_last_raw_response", call.raw_response)
        object.__setattr__(self, "_last_model_name", call.model)
        return call.output

    def health_probe(self) -> PluginHealthStatus:
        try:
            call = self._gateway.invoke_generate_json(
                prompt='Respond with {"status":"ok"}',
                context={},
                caller_context=ModelProviderCallerContext(
                    source_module="ProviderToolsModelProvider",
                    invocation_phase="health_probe",
                    question_driver_refs=[],
                    decision_id="health_probe",
                ),
                provider_key=self.provider_name,
                model=None,
                temperature=0.0,
                max_output_tokens=32,
            )
            object.__setattr__(self, "_last_token_usage", call.usage)
            object.__setattr__(self, "_last_raw_response", call.raw_response)
            object.__setattr__(self, "_last_model_name", call.model)
        except ModelProviderRateLimitError:
            return PluginHealthStatus.DEGRADED
        except ModelProviderAuthError as exc:
            raise ModelProviderHealthError(
                f"Provider {self.provider_name} health probe authentication failed: {exc}"
            ) from exc
        except (ModelProviderTimeoutError, ModelProviderRemoteError):
            return PluginHealthStatus.UNHEALTHY
        except ModelProviderParseError as exc:
            raise ModelProviderHealthError(
                f"Provider {self.provider_name} health probe returned invalid JSON: {exc}"
            ) from exc
        except Exception:
            return PluginHealthStatus.UNHEALTHY
        return PluginHealthStatus.HEALTHY

    @property
    def last_token_usage(self) -> Dict[str, int]:
        usage: LLMTokenUsage = getattr(self, "_last_token_usage", LLMTokenUsage())
        return {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
        }

    @property
    def last_raw_response(self) -> Dict[str, Any]:
        payload = getattr(self, "_last_raw_response", {})
        return payload if isinstance(payload, dict) else {}

    @property
    def last_model_name(self) -> Optional[str]:
        value = getattr(self, "_last_model_name", None)
        return str(value) if value else None


def build_default_provider_tools_model_provider(
    *,
    provider_name: str = "openai_compat",
    plugin_id: str = "model-provider-openai-compat",
    version: str = "1.0.0",
) -> ProviderToolsModelProvider:
    return ProviderToolsModelProvider(
        plugin_id=plugin_id,
        version=version,
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.ACTIVE,
        rollback_conditions=["provider_timeout_spike", "provider_auth_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
        provider_name=provider_name,
    )

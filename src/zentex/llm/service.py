from __future__ import annotations

"""
Zentex LLM Service Facade.

Provides a standardized entry point for large language model operations,
encapsulating provider management, JSON enforcement, retry logic, and usage tracking.
"""

import logging
from dataclasses import dataclass, field
from zentex.plugins.service import get_default_provider_key, is_env_var_reference, resolve_env_value
from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus
from zentex.foundation.specs.model_provider import (
    ModelProviderSpec,
    ModelProviderAuthError,
    ModelProviderConfigError,
    ModelProviderHealthError,
    ModelProviderParseError,
    ModelProviderRateLimitError,
    ModelProviderRemoteError,
    ModelProviderTimeoutError,
    ModelProviderCallerContext
)
from zentex.llm.gateway import LLMGateway
from zentex.llm.retry_handler import RetryConfig, RetryHandler

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class LLMStatus:
    """Core domain model for LLM availability status."""
    available: bool
    probe_checked: bool
    provider_name: Optional[str] = None
    api_base: Optional[str] = None
    api_key_env: Optional[str] = None
    health_status: Optional[str] = None
    reason: Optional[str] = None
    missing_env: List[str] = field(default_factory=list)
    provider_error_type: Optional[str] = None


class LLMService:
    """
    Gateway service for all LLM interactions in Zentex.
    
    Wraps LLMGateway to provide high-level generation, auditing, retry logic,
    and status reporting.
    """

    def __init__(
        self,
        default_provider_key: Optional[str] = None,
        enable_retry: bool = True,
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        if default_provider_key:
            effective_default = default_provider_key
        else:
            effective_default = get_default_provider_key()

        self._gateway = LLMGateway(default_provider_key=effective_default)
        
        # Initialize retry handler if enabled
        self._enable_retry = enable_retry
        if enable_retry:
            self._retry_handler = RetryHandler(retry_config or RetryConfig())
            logger.info(
                f"LLMService initialized with retry enabled "
                f"(default_provider={effective_default}, "
                f"max_retries={self._retry_handler.config.max_retries})"
            )
        else:
            self._retry_handler = None
            logger.info(
                f"LLMService initialized without retry "
                f"(default_provider={effective_default})"
            )

    def generate_json(
        self,
        *,
        prompt: str,
        context: Dict[str, Any],
        caller_context: Optional[ModelProviderCallerContext] = None,
        source_module: str,
        invocation_phase: str = "execution",
        decision_id: Optional[str] = None,
        model_provider: Optional[str] = None,
        provider_key: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LLMGatewayCall:
        """
        Invoke the LLM to generate a structured JSON object.
        
        Args:
            prompt: The main task description for the LLM.
            context: Data to be included in the context window.
            source_module: Identifying string for the calling module (for auditing).
            invocation_phase: Current lifecycle phase of the call.
            decision_id: Optional trace ID for decision correlation.
            provider_key: Override the default provider tool.
            model: Override the default model.
            system_prompt: Optional override for the system assistant personality.
            temperature: Sampling temperature.
            max_output_tokens: Hard limit on response length.
            metadata: Additional auditing data.
            
        Returns:
            LLMGatewayCall containing output, usage, and raw response data.
        """
        effective_caller_context = caller_context or ModelProviderCallerContext(
            source_module=source_module,
            invocation_phase=invocation_phase,
            decision_id=decision_id
        )
        
        selected_provider_key = model_provider if model_provider is not None else provider_key

        # Wrap with retry if enabled
        if self._enable_retry and self._retry_handler is not None:
            return self._retry_handler.execute_with_retry(
                self._gateway.invoke_generate_json,
                prompt=prompt,
                context=context,
                caller_context=effective_caller_context,
                provider_key=selected_provider_key,
                model=model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                metadata=metadata
            )
        else:
            # No retry - direct call
            return self._gateway.invoke_generate_json(
                prompt=prompt,
                context=context,
                caller_context=effective_caller_context,
                provider_key=selected_provider_key,
                model=model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                metadata=metadata
            )

    def get_provider(self, provider_key: str) -> Any:
        """
        Retrieve a specific provider tool instance from the gateway.
        """
        return self._gateway._tools.get(provider_key)

    def get_stats(self) -> Dict[str, int]:
        """Return process-level usage statistics (tokens, requests)."""
        return self._gateway.stats_snapshot()

    def get_aggregated_usage_stats(self) -> Dict[str, Any]:
        """
        Aggregate usage statistics across all bound providers.
        Relocated from web_console/services/health.py.
        """
        providers_info = []
        total_stats = self.get_stats()
        
        for key, tool in self._gateway._tools.items():
            # In the new architecture, tools (plugins) track their own usage
            request_count = getattr(tool, "_request_count", 0)
            input_tokens = getattr(tool, "_input_tokens", 0)
            output_tokens = getattr(tool, "_output_tokens", 0)
            
            # Use raw attribute access for efficiency; fallback to 0 if missing
            providers_info.append({
                "provider_name": key,
                "api_base": str(getattr(tool, "api_base", "") or ""),
                "health_status": str(getattr(tool, "health_status", "unknown").value if hasattr(getattr(tool, "health_status", None), "value") else getattr(tool, "health_status", "unknown")),
                "request_count": request_count,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "error_count": getattr(tool, "_error_count", 0),
            })
            
        return {
            "total_request_count": total_stats.get("request_count", 0),
            "total_input_tokens": total_stats.get("input_tokens", 0),
            "total_output_tokens": total_stats.get("output_tokens", 0),
            "total_tokens": total_stats.get("total_tokens", 0),
            "providers": providers_info
        }

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic health information about the LLM gateway."""
        status = {
            "default_provider": self._gateway._default_provider_key,
            "available_providers": sorted(self._gateway._tools.keys()),
            "stats": self.get_stats()
        }
        
        # Add retry stats if enabled
        if self._enable_retry and self._retry_handler is not None:
            status["retry_enabled"] = True
            status["retry_config"] = {
                "max_retries": self._retry_handler.config.max_retries,
                "strategy": self._retry_handler.config.strategy.value,
                "base_delay": self._retry_handler.config.base_delay,
            }
            status["retry_stats"] = self._retry_handler.get_stats()
        else:
            status["retry_enabled"] = False
        
        return status

    def get_detailed_status(self, *, probe_live: bool = False) -> LLMStatus:
        """
        Compute detailed availability status for the LLM gateway.
        This reproduces the logic previously in web_console, but without the 'apologies'.
        """
        # 1. Resolve active provider
        provider = self._resolve_active_provider()
        if provider is None:
            return LLMStatus(
                available=False,
                probe_checked=False,
                reason="no_active_model_provider"
            )

        provider_name, api_base, api_key_env = self._extract_provider_status_fields(provider)

        # 2. Check credentials
        missing_env: List[str] = []
        if api_key_env and is_env_var_reference(api_key_env):
            if not resolve_env_value(api_key_env):
                missing_env.append(api_key_env)

        if missing_env:
            return LLMStatus(
                available=False,
                probe_checked=False,
                provider_name=provider_name or None,
                api_base=api_base or None,
                api_key_env=api_key_env or None,
                reason="missing_credentials",
                missing_env=missing_env
            )

        # 3. Initial baseline status
        status = LLMStatus(
            available=True,
            probe_checked=False,
            provider_name=provider_name or None,
            api_base=api_base or None,
            api_key_env=api_key_env or None,
            reason=None
        )

        # 4. Optional Live Probe
        if probe_live:
            return self._probe_health(provider, status)
        
        return status

    def _resolve_active_provider(self) -> object | None:
        """Return the actual active gateway tool, not an unrelated provider protocol type."""
        default_key = str(self._gateway._default_provider_key or "").strip()
        if default_key:
            tool = self._gateway._tools.get(default_key)
            if tool is not None:
                return tool

        for key in sorted(self._gateway._tools):
            tool = self._gateway._tools.get(key)
            if tool is not None:
                return tool
        return None

    def _extract_provider_status_fields(self, provider: object) -> tuple[str, str, str]:
        """Read provider status metadata from the active gateway tool."""
        provider_name = str(getattr(provider, "provider_name", "") or "")
        api_base = str(getattr(provider, "api_base", "") or "")
        api_key_env = str(getattr(provider, "api_key_env", "") or "")

        config = getattr(provider, "config", None)
        if config is not None:
            provider_name = provider_name or str(getattr(config, "provider_name", "") or "")
            api_base = api_base or str(getattr(config, "api_base", "") or "")
            api_key_env = api_key_env or str(getattr(config, "api_key_env", "") or "")

        return provider_name, api_base, api_key_env

    def _probe_health(self, provider: ModelProviderSpec, current_status: LLMStatus) -> LLMStatus:
        """Perform a live health probe and return updated status."""
        try:
            # We assume provider implements health_probe protocol or has it
            health_probe_fn = getattr(provider, "health_probe", None)
            if not health_probe_fn:
                 return current_status.model_copy(update={"probe_checked": True})
            
            health_status = health_probe_fn()
            
            # Update based on health status
            is_available = health_status == PluginHealthStatus.HEALTHY
            return LLMStatus(
                available=is_available,
                probe_checked=True,
                provider_name=current_status.provider_name,
                api_base=current_status.api_base,
                api_key_env=current_status.api_key_env,
                health_status=health_status.value,
                reason=None if is_available else f"provider_{health_status.value}"
            )

        except ModelProviderAuthError as exc:
            return self._status_error(current_status, PluginHealthStatus.UNHEALTHY, "auth_error", exc)
        except ModelProviderConfigError as exc:
            return self._status_error(current_status, PluginHealthStatus.UNHEALTHY, "config_error", exc)
        except ModelProviderRateLimitError as exc:
            return self._status_error(current_status, PluginHealthStatus.DEGRADED, "rate_limited", exc)
        except ModelProviderTimeoutError as exc:
            return self._status_error(current_status, PluginHealthStatus.UNHEALTHY, "timeout", exc)
        except Exception as exc:
            return self._status_error(current_status, PluginHealthStatus.UNHEALTHY, "probe_failed", exc)

    def _status_error(self, status: LLMStatus, health: PluginHealthStatus, reason: str, exc: Exception) -> LLMStatus:
        return LLMStatus(
            available=False,
            probe_checked=True,
            provider_name=status.provider_name,
            api_base=status.api_base,
            api_key_env=status.api_key_env,
            health_status=health.value,
            reason=reason,
            provider_error_type=exc.__class__.__name__
        )


# Global singleton instance
_default_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Return the shared global instance of the LLMService."""
    global _default_service
    if _default_service is None:
        _default_service = LLMService()
    return _default_service


def get_service() -> LLMService:
    """Standard service factory function for launcher assembly.
    
    Alias for get_llm_service() to maintain compatibility
    with the SystemAssembler's expectation of a get_service() function.
    """
    return get_llm_service()

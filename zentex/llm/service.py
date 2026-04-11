from __future__ import annotations

"""
Zentex LLM Service Facade.

Provides a standardized entry point for large language model operations,
encapsulating provider management, JSON enforcement, retry logic, and usage tracking.
"""

import logging
from typing import Any, Dict, Optional, Union

from zentex.core.model_provider_spec import ModelProviderCallerContext
from zentex.llm.gateway import LLMGateway, LLMGatewayCall
from zentex.llm.retry_handler import RetryHandler, RetryConfig
from zentex.plugins.service import get_default_provider_key

logger = logging.getLogger(__name__)


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
        source_module: str,
        invocation_phase: str = "execution",
        decision_id: Optional[str] = None,
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
        caller_context = ModelProviderCallerContext(
            source_module=source_module,
            invocation_phase=invocation_phase,
            decision_id=decision_id
        )
        
        # Wrap with retry if enabled
        if self._enable_retry and self._retry_handler is not None:
            return self._retry_handler.execute_with_retry(
                self._gateway.invoke_generate_json,
                prompt=prompt,
                context=context,
                caller_context=caller_context,
                provider_key=provider_key,
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
                caller_context=caller_context,
                provider_key=provider_key,
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


# Global singleton instance
_default_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Return the shared global instance of the LLMService."""
    global _default_service
    if _default_service is None:
        _default_service = LLMService()
    return _default_service

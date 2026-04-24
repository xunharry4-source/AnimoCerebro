from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

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

@dataclass(frozen=True)
class LLMStatus:
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
    def __init__(
        self,
        default_provider_key: Optional[str] = None,
        enable_retry: bool = True,
        retry_config: Optional[Any] = None,
    ) -> None:
        from zentex.llm.gateway import LLMGateway
        from zentex.llm.retry_handler import RetryConfig, RetryHandler
        from zentex.plugins.service import get_default_provider_key
        
        if default_provider_key:
            effective_default = default_provider_key
        else:
            effective_default = get_default_provider_key()

        self._gateway = LLMGateway(default_provider_key=effective_default)
        self._enable_retry = enable_retry
        
        _logger = logging.getLogger(__name__)
        if enable_retry:
            self._retry_handler = RetryHandler(retry_config or RetryConfig())
            _logger.info(f"LLMService initialized with retry enabled (default_provider={effective_default})")
        else:
            self._retry_handler = None
            _logger.info(f"LLMService initialized without retry (default_provider={effective_default})")

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
    ) -> Any:
        from zentex.llm.gateway import LLMGatewayCall
        
        effective_caller_context = caller_context or ModelProviderCallerContext(
            source_module=source_module,
            invocation_phase=invocation_phase,
            decision_id=decision_id
        )
        
        _logger = logging.getLogger(__name__)
        _logger.info(
            f"[LLM AUDIT] Calling generation | Origin: {source_module} | "
            f"Phase: {invocation_phase} | Trace: {decision_id or 'none'}"
        )

        selected_provider_key = model_provider if model_provider is not None else provider_key
        invocation_phase_text = str(invocation_phase or "").strip().lower()
        # Nine-question executions run under strict wall-clock budgets in CI/runtime.
        # Avoid multi-retry backoff storms that exceed question-level timeouts.
        disable_retry_for_nine_questions = (
            isinstance(metadata, dict)
            and bool(metadata.get("question_driver_refs"))
            and invocation_phase_text.startswith("nine_question")
        )
        is_ollama_call = str(selected_provider_key or "").strip().lower() == "ollama"

        try:
            if self._enable_retry and self._retry_handler is not None and not disable_retry_for_nine_questions:
                result = self._retry_handler.execute_with_retry(
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
                max_attempts = 2 if (disable_retry_for_nine_questions and is_ollama_call) else 1
                last_exc: Exception | None = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        result = self._gateway.invoke_generate_json(
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
                        break
                    except (ModelProviderTimeoutError, ModelProviderParseError) as retry_exc:
                        last_exc = retry_exc
                        if attempt >= max_attempts:
                            raise
                        _logger.warning(
                            "[LLM AUDIT] Retrying nine-question ollama call after %s (attempt %d/%d)",
                            retry_exc.__class__.__name__,
                            attempt,
                            max_attempts,
                        )
                        continue
                else:
                    raise last_exc or RuntimeError("LLM invocation failed without exception detail")
            
            _logger.info(
                f"[LLM AUDIT] Generation Success | Origin: {source_module} | "
                f"Trace: {decision_id or 'none'} | Tokens: {result.usage.total_tokens} | "
                f"Provider: {result.provider_key}"
            )
            return result

        except Exception as exc:
            failure_category = self._failure_category(exc)
            root = self._root_cause(exc)
            _logger.error(
                f"[LLM AUDIT] Generation Failure | Origin: {source_module} | "
                f"Trace: {decision_id or 'none'} | Category: {failure_category} | "
                f"Error: {exc.__class__.__name__}: {exc} | "
                f"Root: {root.__class__.__name__}: {root}",
                exc_info=True,
            )
            raise exc

    def get_provider(self, provider_key: str) -> Any:
        return self._gateway._tools.get(provider_key)

    def get_stats(self) -> Dict[str, int]:
        return self._gateway.stats_snapshot()

    def get_status(self) -> Dict[str, Any]:
        status = {
            "default_provider": self._gateway._default_provider_key,
            "available_providers": sorted(self._gateway._tools.keys()),
            "stats": self.get_stats()
        }
        return status

    def get_detailed_status(self, probe_live: bool = False) -> LLMStatus:
        """Produce a structured status snapshot for the web console and diagnostics."""
        provider = self._resolve_active_provider()
        
        if provider is None:
            return LLMStatus(
                available=False,
                probe_checked=probe_live,
                reason="no_active_provider",
                health_status="offline"
            )

        provider_name, api_base, api_key_env = self._extract_provider_status_fields(provider)
        
        # 1. Basic configuration check
        missing_env = []
        if api_key_env and not os.environ.get(api_key_env):
            missing_env.append(api_key_env)
        
        # 2. Optional health probe
        health_status = "online"
        reason = "online"
        error_type = None
        
        if probe_live:
            try:
                # Use a lightweight check if available on the model provider tool
                if hasattr(provider, "check_health"):
                    res = provider.check_health()
                    health_status = str(res.status.value)
                    if not res.ok:
                        reason = res.message
                else:
                    # Fallback to a simple validation or assume ok if no probe method
                    health_status = "online"
            except Exception as e:
                health_status = "error"
                reason = str(e)
                error_type = e.__class__.__name__

        return LLMStatus(
            available=(health_status == "online" and not missing_env),
            probe_checked=probe_live,
            provider_name=provider_name,
            api_base=api_base,
            api_key_env=api_key_env,
            health_status=health_status,
            reason=reason,
            missing_env=missing_env,
            provider_error_type=error_type
        )

    def get_aggregated_usage_stats(self) -> Dict[str, Any]:
        """Produce a comprehensive usage report including per-provider metrics."""
        raw_stats = self._gateway.get_aggregated_stats()
        
        # Transform providers dict into list of dicts with metadata
        providers_list = []
        for p_key, p_usage in raw_stats["providers"].items():
            tool = self._gateway._tools.get(p_key)
            provider_name, api_base, api_key_env = self._extract_provider_status_fields(tool)
            
            # Simple health check for statistics metadata (cached/lazy)
            health_status = "unknown"
            if tool is not None:
                health_status = "online" # Basic assumption if it's in the tools dict
            
            p_data = {
                "provider_name": provider_name or p_key,
                "api_base": api_base,
                "health_status": health_status,
                **p_usage
            }
            providers_list.append(p_data)
            
        return {
            "total_request_count": raw_stats["total_request_count"],
            "total_input_tokens": raw_stats["total_input_tokens"],
            "total_output_tokens": raw_stats["total_output_tokens"],
            "total_tokens": raw_stats["total_tokens"],
            "providers": providers_list
        }

    def _resolve_active_provider(self) -> Optional[object]:
        default_key = str(self._gateway._default_provider_key or "").strip()
        if default_key:
            tool = self._gateway._tools.get(default_key)
            if tool is not None:
                return tool
        return None

    def _extract_provider_status_fields(self, provider: object) -> tuple[str, str, str]:
        provider_name = str(getattr(provider, "provider_name", "") or "")
        api_base = str(getattr(provider, "api_base", "") or "")
        api_key_env = str(getattr(provider, "api_key_env", "") or "")
        return provider_name, api_base, api_key_env

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
    def _failure_category(exc: Exception) -> str:
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
        if isinstance(exc, ModelProviderHealthError):
            return "health"
        if isinstance(exc, ModelProviderRemoteError):
            return "remote"
        return "unknown"


_default_service: Optional[LLMService] = None

def get_llm_service() -> LLMService:
    return get_service()

def get_service() -> LLMService:
    global _default_service
    if _default_service is None:
        try:
            _default_service = LLMService()
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
    return _default_service

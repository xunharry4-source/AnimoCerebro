from __future__ import annotations
from typing import Dict, List


import os

from fastapi import HTTPException, Request

from plugins.provider_tools import is_env_var_reference
from zentex.core.model_provider_spec import (
    ModelProviderAuthError,
    ModelProviderConfigError,
    ModelProviderHealthError,
    ModelProviderParseError,
    ModelProviderRateLimitError,
    ModelProviderRemoteError,
    ModelProviderSpec,
    ModelProviderTimeoutError,
)
from zentex.core.plugin_base import PluginHealthStatus
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.web_console.contracts.plugins import ManagedPluginRecord
from zentex.web_console.contracts.runtime import LLMStatusPayload
from zentex.web_console.dependencies import get_managed_plugin_records


def _probe_provider_status(provider: ModelProviderSpec, status: LLMStatusPayload) -> LLMStatusPayload:
    try:
        health_status = provider.health_probe()
    except ModelProviderAuthError as exc:
        return status.model_copy(
            update={
                "available": False,
                "probe_checked": True,
                "health_status": PluginHealthStatus.UNHEALTHY.value,
                "reason": "auth_error",
                "hint": "大模型认证失败，请检查 API Key 或网关鉴权设置。",
                "provider_error_type": exc.__class__.__name__,
            }
        )
    except ModelProviderConfigError as exc:
        return status.model_copy(
            update={
                "available": False,
                "probe_checked": True,
                "health_status": PluginHealthStatus.UNHEALTHY.value,
                "reason": "config_error",
                "hint": "大模型配置错误或缺少必要参数，请检查 provider 配置。",
                "provider_error_type": exc.__class__.__name__,
            }
        )
    except ModelProviderRateLimitError as exc:
        return status.model_copy(
            update={
                "available": False,
                "probe_checked": True,
                "health_status": PluginHealthStatus.DEGRADED.value,
                "reason": "rate_limited",
                "hint": "大模型当前被限流，启动项已阻断，请稍后重试或检查额度。",
                "provider_error_type": exc.__class__.__name__,
            }
        )
    except ModelProviderTimeoutError as exc:
        return status.model_copy(
            update={
                "available": False,
                "probe_checked": True,
                "health_status": PluginHealthStatus.UNHEALTHY.value,
                "reason": "timeout",
                "hint": "大模型探针超时或网络不可达，请检查网关连通性。",
                "provider_error_type": exc.__class__.__name__,
            }
        )
    except (ModelProviderRemoteError, ModelProviderParseError, ModelProviderHealthError) as exc:
        return status.model_copy(
            update={
                "available": False,
                "probe_checked": True,
                "health_status": PluginHealthStatus.UNHEALTHY.value,
                "reason": "health_probe_failed",
                "hint": "大模型健康探针失败，请检查上游模型服务状态。",
                "provider_error_type": exc.__class__.__name__,
            }
        )
    except Exception as exc:
        return status.model_copy(
            update={
                "available": False,
                "probe_checked": True,
                "health_status": PluginHealthStatus.UNHEALTHY.value,
                "reason": "probe_unexpected_error",
                "hint": "大模型健康探针遇到未分类错误，请检查后端日志。",
                "provider_error_type": exc.__class__.__name__,
            }
        )

    if health_status == PluginHealthStatus.HEALTHY:
        return status.model_copy(
            update={
                "available": True,
                "probe_checked": True,
                "health_status": health_status.value,
                "reason": None,
                "hint": None,
                "provider_error_type": None,
            }
        )

    reason = "provider_degraded" if health_status == PluginHealthStatus.DEGRADED else "provider_unhealthy"
    hint = (
        "大模型当前处于降级状态，启动项已阻断，请稍后重试。"
        if health_status == PluginHealthStatus.DEGRADED
        else "大模型健康探针未通过，请检查网关连通性或上游服务状态。"
    )
    return status.model_copy(
        update={
            "available": False,
            "probe_checked": True,
            "health_status": health_status.value,
            "reason": reason,
            "hint": hint,
            "provider_error_type": None,
        }
    )


def compute_llm_status_from_records(
    records: Dict[str, ManagedPluginRecord],
    *,
    probe_live: bool = False,
) -> LLMStatusPayload:
    providers: List[ModelProviderSpec] = []
    for record in records.values():
        plugin = record.plugin
        if not isinstance(plugin, ModelProviderSpec):
            continue
        if plugin.status != PluginLifecycleStatus.ACTIVE:
            continue
        providers.append(plugin)

    if not providers:
        return LLMStatusPayload(
            available=False,
            probe_checked=False,
            reason="no_active_model_provider",
            hint="No active model_provider is bound. Enable a model provider plugin first.",
        )

    providers.sort(key=lambda plugin: plugin.plugin_id)
    provider = providers[0]
    missing_env: List[str] = []
    if getattr(provider, "api_key_env", None):
        api_key_ref = str(provider.api_key_env)
        if is_env_var_reference(api_key_ref) and not os.getenv(api_key_ref):
            missing_env.append(str(provider.api_key_env))

    api_base = str(getattr(provider, "api_base", "") or "")
    provider_name = str(getattr(provider, "provider_name", "") or "")

    if missing_env:
        return LLMStatusPayload(
            available=False,
            probe_checked=False,
            provider_name=provider_name or None,
            api_base=api_base or None,
            api_key_env=str(getattr(provider, "api_key_env", "") or "") or None,
            health_status=None,
            reason="missing_credentials",
            missing_env=missing_env,
            hint=f"Set required env vars: {', '.join(missing_env)}",
        )

    status = LLMStatusPayload(
        available=True,
        probe_checked=False,
        provider_name=provider_name or None,
        api_base=api_base or None,
        api_key_env=str(getattr(provider, "api_key_env", "") or "") or None,
        health_status=None,
        reason=None,
        missing_env=[],
        hint=None,
    )
    if probe_live:
        return _probe_provider_status(provider, status)
    return status


def compute_llm_status(request: Request, *, probe_live: bool = False) -> LLMStatusPayload:
    status = compute_llm_status_from_records(get_managed_plugin_records(request), probe_live=probe_live)
    request.app.state.llm_status = status
    return status


def enforce_llm_available(request: Request) -> None:
    status = compute_llm_status(request)
    if status.available:
        return
    raise HTTPException(
        status_code=503,
        detail={
            "error": "llm_unavailable",
            "reason": status.reason,
            "provider_name": status.provider_name,
            "api_base": status.api_base,
            "api_key_env": status.api_key_env,
            "missing_env": status.missing_env,
            "hint": status.hint,
        },
    )

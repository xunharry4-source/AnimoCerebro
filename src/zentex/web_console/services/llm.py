"""
LLM Service Thin Adapter — Web Console Layer.

ARCHITECTURE ROLE:
1. Thin Facade: Directs API requests to core domain services (LLMService).
2. Zero Business Logic: Strictly prohibited from implementing health probing, token math, or usage aggregation.
3. Responsibility:
   - [Query Condition Preparation]: Validating provider parameters for core status verification.
   - [Result Splicing]: Mapping technical provider status and usage stats into API contracts.

DECOUPLING POLICY (Zentex Codex §2):
This module must remain a 'Logic-Free Zone'. Any evolution of LLM provider detection, 
token calculation rules, or usage reporting must be implemented in `zentex.llm.service`.
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import Request, HTTPException
from zentex.llm.service import get_llm_service
from zentex.foundation.specs.model_provider import ModelProviderSpec
from zentex.web_console.contracts.runtime import LLMStatusPayload

def compute_llm_status(request: Request, *, probe_live: bool = False) -> LLMStatusPayload:
    """
    Thin adapter for core LLM status computation.
    Refactored to remove business logic and 'apology' hints.
    """
    llm_service = get_llm_service()
    status = llm_service.get_detailed_status(probe_live=probe_live)
    
    # Simple 'splicing' into the web console contract
    payload = LLMStatusPayload(
        available=status.available,
        probe_checked=status.probe_checked,
        provider_name=status.provider_name,
        api_base=status.api_base,
        api_key_env=status.api_key_env,
        health_status=status.health_status,
        reason=status.reason,
        missing_env=status.missing_env,
        provider_error_type=status.provider_error_type,
        hint=None  # Explicitly removing 'apology' hints from the UI layer
    )
    
    # Update request state for downstream dependencies
    request.app.state.llm_status = payload
    return payload

def resolve_active_model_provider_from_records(
    records: Dict[str, Any],
) -> Optional[ModelProviderSpec]:
    """Scan managed plugin records for an active model provider and return its spec."""
    for plugin_id, record in records.items():
        lifecycle = getattr(record, "lifecycle_status", None) or (
            record.get("lifecycle_status") if isinstance(record, dict) else None
        )
        category = getattr(record, "category", None) or (
            record.get("category") if isinstance(record, dict) else None
        )
        if str(lifecycle or "").lower() != "active":
            continue
        if str(category or "").lower() != "llm":
            continue
        spec = getattr(record, "spec", None) or (
            record.get("spec") if isinstance(record, dict) else None
        )
        if isinstance(spec, ModelProviderSpec):
            return spec
    return None


def enforce_llm_available(request: Request) -> None:
    """Enforce LLM availability without local logic, relying on core status."""
    status = compute_llm_status(request)
    if not status.available:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "llm_unavailable",
                "reason": status.reason,
                "provider_name": status.provider_name,
                "api_base": status.api_base,
                "api_key_env": status.api_key_env,
                "missing_env": status.missing_env,
                "hint": None # Purged apology
            },
        )

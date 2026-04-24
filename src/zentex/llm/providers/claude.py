"""
Anthropic Claude provider adapter (raw HTTP, Anthropic Messages API).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .base import (
    BaseProviderTool,
    ToolInvocationRequest,
)


class ClaudeTool(BaseProviderTool):
    """Anthropic Claude adapter using the Messages API over raw HTTP."""

    def _build_url(self) -> str:
        return f"{self.config.api_base.rstrip('/')}/messages"

    def _provider_headers(self, api_key: str) -> Dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

    def _build_payload(self, invocation: ToolInvocationRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": invocation.model,
            "max_tokens": invocation.max_output_tokens,
            "temperature": invocation.temperature,
            "messages": [{"role": "user", "content": invocation.prompt}],
        }
        if invocation.system_prompt:
            payload["system"] = invocation.system_prompt
        return payload

    def _extract_text(self, payload: Dict[str, Any]) -> str:
        content = payload.get("content", [])
        for item in content:
            if item.get("type") == "text":
                return str(item.get("text", ""))
        return ""

    def _extract_usage(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        usage = payload.get("usage")
        if not usage:
            return None
        return {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": (
                usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            ),
        }

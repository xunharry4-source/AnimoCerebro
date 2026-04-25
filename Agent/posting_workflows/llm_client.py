"""
Workflow LLM client.

Purpose:
    Provide a strict JSON-only ModelProvider wrapper for posting workflow nodes.

Main responsibilities:
    - Resolve the active Zentex LLM service.
    - Call ModelProvider with trace metadata.
    - Reject missing, failed, or malformed model output.

Not responsible for:
    - Building node-specific prompts.
    - Retrying with synthetic fallback content.
    - Supplying fake provider outputs in production.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

from Agent.posting_workflows.errors import PostingWorkflowError

try:
    from zentex.foundation.specs.model_provider import ModelProviderCallerContext
except ModuleNotFoundError:
    repo_src = Path(__file__).resolve().parents[2] / "src"
    if repo_src.exists():
        sys.path.insert(0, str(repo_src))
    from zentex.foundation.specs.model_provider import ModelProviderCallerContext


class WorkflowLLMClient:
    """Fail-closed JSON LLM client for workflow nodes."""

    def __init__(
        self,
        llm_service: Optional[Any] = None,
        provider_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._llm_service = llm_service
        self._provider_key = provider_key
        self._model = model

    def generate_json(
        self,
        *,
        prompt: str,
        context: Dict[str, Any],
        node: str,
        trace_id: str,
        phase: str,
        max_output_tokens: int = 1200,
    ) -> Dict[str, Any]:
        """Call the active LLM service and require a JSON object."""
        service = self._resolve_service(node)
        caller_context = ModelProviderCallerContext(
            source_module="Agent.posting_workflows",
            invocation_phase=phase,
            decision_id=trace_id,
            trace_id=trace_id,
        )

        try:
            result = service.generate_json(
                prompt=prompt,
                context=context,
                caller_context=caller_context,
                source_module="Agent.posting_workflows",
                invocation_phase=phase,
                decision_id=trace_id,
                provider_key=self._provider_key,
                model=self._model,
                temperature=0.0,
                max_output_tokens=max_output_tokens,
                metadata={"trace_id": trace_id, "workflow_node": node},
            )
        except Exception as exc:
            raise PostingWorkflowError(
                f"LLM invocation failed: {exc.__class__.__name__}: {exc}",
                node=node,
                code="llm_invocation_failed",
                details={"phase": phase},
            ) from exc

        payload = getattr(result, "output", result)
        if not isinstance(payload, dict):
            raise PostingWorkflowError(
                "LLM output must be a JSON object",
                node=node,
                code="llm_invalid_output",
                details={"phase": phase, "type": type(payload).__name__},
            )
        return payload

    def _resolve_service(self, node: str) -> Any:
        if self._llm_service is not None:
            return self._llm_service
        try:
            from zentex.llm import get_llm_service

            self._llm_service = get_llm_service()
            return self._llm_service
        except Exception as exc:
            raise PostingWorkflowError(
                f"Active LLM service unavailable: {exc.__class__.__name__}: {exc}",
                node=node,
                code="llm_unavailable",
            ) from exc

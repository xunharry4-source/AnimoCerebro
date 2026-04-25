"""
Workflow LLM client.

Purpose:
    Provide a strict JSON-only Agent-owned ModelProvider wrapper for posting workflow nodes.

Main responsibilities:
    - Resolve the active LLM provider through Agent/local_llm_client.py.
    - Call provider integrations without importing src/zentex code.
    - Reject missing, failed, or malformed model output.

Not responsible for:
    - Building node-specific prompts.
    - Retrying with synthetic fallback content.
    - Supplying fake provider outputs in production.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from Agent.local_llm_client import AgentLLMError, AgentLocalLLMService, AgentModelCallerContext
from Agent.posting_workflows.errors import PostingWorkflowError


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
        """Call the active Agent local LLM service and require a JSON object."""
        service = self._resolve_service()
        caller_context = AgentModelCallerContext(
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
        except AgentLLMError as exc:
            raise PostingWorkflowError(
                f"LLM invocation failed: {exc.__class__.__name__}: {exc}",
                node=node,
                code="llm_invocation_failed",
                details={"phase": phase, "agent_llm_code": exc.code, **exc.details},
            ) from exc
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

    def _resolve_service(self) -> Any:
        if self._llm_service is None:
            self._llm_service = AgentLocalLLMService()
        return self._llm_service

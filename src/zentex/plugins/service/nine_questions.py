from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from zentex.foundation.contracts import ServiceResponse
from zentex.kernel.cognition_flow.models import NineQuestion, NineQuestionResponse

logger = logging.getLogger(__name__)

UTC = timezone.utc

class NineQuestionPluginService:
    """Implementation service for the Nine-Questions module.
    
    This service centralizes the execution of the nine cognitive plugins
    ensuring that all implementation-specific logic (context building, 
    plugin invocation) is contained within the plugins module boundary.
    """

    def __init__(self, plugins_service: Any) -> None:
        self._plugins_service = plugins_service

    def execute_question(
        self,
        question: NineQuestion,
        context: Dict[str, Any],
        session_id: str,
        turn_id: str,
        trace_id: str,
    ) -> NineQuestionResponse:
        """Execute a single nine-question implementation.
        
        Args:
            question: The question definition (question_id, plugin_id, text).
            context: Expanded context for plugin execution.
            session_id: Current session identifier.
            turn_id: Current turn identifier.
            trace_id: Execution trace identifier.
            
        Returns:
            A NineQuestionResponse containing the result and metadata.
        """
        start_time = datetime.now(UTC)
        
        # Invoke the cognitive plugin via the generic plugins service
        # Note: In the future, this could directly call the plugin implementation
        # classes if we want to bypass the database-backed registry.
        raw = self._plugins_service.execute_cognitive_plugin(
            plugin_id=question.plugin_id,
            context={
                **context,
                "question_id": question.question_id,
                "question_text": question.text,
            },
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            originator_id=session_id or "kernel",
        )
        
        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
        
        # Build standardized response
        if isinstance(raw, ServiceResponse):
            return self._build_response_from_service_response(
                question, raw, trace_id, duration_ms
            )
        
        if raw is not None:
            return self._build_response_from_raw_dict(
                question, raw, trace_id, duration_ms
            )

        # Fallback for no response
        return NineQuestionResponse(
            question_id=question.question_id,
            answer=f"[no plugin architecture response] {question.text}",
            confidence=0.0,
            duration_ms=duration_ms,
            tool_id=f"nine_questions.{question.question_id}",
            trace_id=trace_id,
            timestamp=datetime.now(UTC).isoformat(),
        )

    def _build_response_from_service_response(
        self,
        question: NineQuestion,
        raw: ServiceResponse,
        trace_id: str,
        duration_ms: float,
    ) -> NineQuestionResponse:
        data = raw.data if isinstance(raw.data, dict) else {}
        answer = str(data.get("answer") or data.get("summary") or "").strip()
        confidence = float(data.get("confidence") or 0.0)
        embedded_error = self._extract_embedded_error(data)
        is_partial = self._is_partial_payload(data)
        
        return NineQuestionResponse(
            question_id=question.question_id,
            answer=answer,
            confidence=confidence,
            duration_ms=duration_ms,
            error=(raw.message or "execution_failed") if not raw.is_ok else embedded_error,
            tool_id=str(data.get("tool_id") or f"nine_questions.{question.question_id}"),
            trace_id=str(raw.trace_id or trace_id),
            timestamp=datetime.now(UTC).isoformat(),
            is_partial=is_partial,
            result_payload=data,
            context_updates=data.get("context_updates", {}),
        )

    def _build_response_from_raw_dict(
        self,
        question: NineQuestion,
        raw: Any,
        trace_id: str,
        duration_ms: float,
    ) -> NineQuestionResponse:
        payload = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
        answer = payload.get("answer", "") if isinstance(payload, dict) else str(payload)
        confidence = float(payload.get("confidence", 0.7)) if isinstance(payload, dict) else 0.7
        embedded_error = self._extract_embedded_error(payload if isinstance(payload, dict) else {})
        is_partial = self._is_partial_payload(payload if isinstance(payload, dict) else {})
        
        return NineQuestionResponse(
            question_id=question.question_id,
            answer=answer,
            confidence=confidence,
            duration_ms=duration_ms,
            error=embedded_error,
            tool_id=f"nine_questions.{question.question_id}",
            trace_id=trace_id,
            timestamp=datetime.now(UTC).isoformat(),
            is_partial=is_partial,
            result_payload=payload if isinstance(payload, dict) else {},
            context_updates=payload.get("context_updates", {}) if isinstance(payload, dict) else {},
        )

    @staticmethod
    def _extract_embedded_error(payload: dict[str, Any]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None

        for key in ("error_message", "error", "message"):
            value = payload.get(key)
            if isinstance(value, str):
                text = value.strip()
                if text:
                    return text
        return None

    @staticmethod
    def _is_partial_payload(payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False

        payload_status = str(payload.get("status") or "").strip().lower()
        if payload_status in {"partial_failed", "degraded", "failed"}:
            return True

        context_updates = payload.get("context_updates")
        if isinstance(context_updates, dict):
            for key, value in context_updates.items():
                if key == "execution_diagnosis" or str(key).endswith("_execution_diagnosis"):
                    if isinstance(value, dict):
                        authenticity_status = str(value.get("authenticity_status") or "").strip().lower()
                        if authenticity_status in {"degraded", "partial_failed", "failed"}:
                            return True
        return False

def get_service(plugins_service: Any) -> NineQuestionPluginService:
    """Return a NineQuestionPluginService instance."""
    return NineQuestionPluginService(plugins_service=plugins_service)

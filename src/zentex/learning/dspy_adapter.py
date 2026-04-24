from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union
import json

logger = logging.getLogger(__name__)

try:
    import dspy
    from dspy import LM
except ImportError:
    class LM:
        pass

from zentex.foundation.specs.model_provider import ModelProviderSpec, ModelProviderCallerContext
from zentex.llm.service import LLMService

class ZentexDSPyLM(LM):
    """
    Adapter that integrates Zentex's ModelProviderSpec into DSPy's LM interface.
    This ensures all DSPy calls go through the audited, fail-closed provider contract.
    """
    
    def __init__(
        self, 
        caller_context: ModelProviderCallerContext,
        provider: Optional[ModelProviderSpec] = None,
        llm_service: Optional[LLMService] = None,
        model_provider_key: Optional[str] = None,
        model_kwargs: Optional[Dict[str, Any]] = None
    ):
        super().__init__("zentex-managed-lm")
        self.provider = provider
        self.llm_service = llm_service
        self.model_provider_key = model_provider_key
        self.caller_context = caller_context
        self.model_kwargs = model_kwargs or {}
        self.history = []
        
    def __call__(self, prompt: str, **kwargs) -> List[str]:
        """
        Since our provider requires generate_json, we intercept DSPy's prompt,
        ask the provider for JSON, and dump it back as a string for DSPy to parse.
        """
        # DSPy will generate the prompt containing the expected format.
        # We wrap the invocation to satisfy ModelProviderSpec.
        
        # We create a dummy context since DSPy handles context inside the prompt string.
        context = {"raw_dspy_prompt": prompt}
        
        try:
            if self.llm_service is not None:
                source_module = self.caller_context.source_module or "learning_service"
                logger.info(
                    f"[LEARNING AUDIT] DSPy LM Union[invoked, Origin]: {source_module} | "
                    f"Trace: {self.caller_context.trace_id or 'none'}"
                )
                json_resp = self.llm_service.generate_json(
                    prompt=prompt,
                    context=context,
                    caller_context=self.caller_context,
                    source_module=source_module,
                    invocation_phase=self.caller_context.invocation_phase,
                    decision_id=self.caller_context.decision_id,
                    model_provider=self.model_provider_key,
                    metadata={
                        "trace_id": self.caller_context.trace_id,
                        "question_driver_refs": self.caller_context.question_driver_refs,
                    },
                ).output
            elif self.provider is not None:
                logger.info(f"[LEARNING AUDIT] Direct Provider LM Union[invoked, Origin]: {self.caller_context.source_module}")
                json_resp = self.provider.generate_json(
                    prompt=prompt,
                    context=context,
                    caller_context=self.caller_context
                )
            else:
                raise RuntimeError("LLM MANDATORY: missing llm_service and provider fallback")
            result_str = json.dumps(json_resp)
        except Exception as e:
            # POLICY[no-bare-logger-error]: exc_info=True is mandatory so the
            # full traceback appears in logs, not just the message string.
            logger.error(f"[LEARNING AUDIT] Learning LM Union[failed, Error]: {e}", exc_info=True)
            # Re-raise to let the retry loop or Sandbox catch it
            raise RuntimeError(f"ZentexDSPyLM failed: {str(e)}") from e
            
        self.history.append({"prompt": prompt, "response": [result_str]})
        return [result_str]
        
    def inspect_history(self, n: int = 1) -> None:
        """Log the last *n* LLM call entries from this adapter's history.

        # POLICY[no-fake-impl]: the original body was `pass`, silently discarding
        # DSPy's inspect_history() call and making it impossible to audit LLM
        # call history through the DSPy interface.
        """
        entries = self.history[-n:] if n > 0 else []
        if not entries:
            logger.info("[LEARNING AUDIT] inspect_history: no history recorded yet")
            return
        for i, entry in enumerate(entries, start=1):
            prompt_preview = str(entry.get("prompt", ""))[:200]
            response_preview = str(entry.get("response", [""])[:1])[:200]
            logger.info(
                "[LEARNING AUDIT] inspect_history entry %d/%Union[d, prompt_preview]=%Union[r, response_preview]=%r",
                i, len(entries), prompt_preview, response_preview,
            )

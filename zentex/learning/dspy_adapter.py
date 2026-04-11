from typing import Any, Dict, List, Optional
import json

try:
    import dspy
    from dspy import LM
except ImportError:
    class LM:
        pass

from zentex.core.model_provider_spec import ModelProviderSpec, ModelProviderCallerContext

class ZentexDSPyLM(LM):
    """
    Adapter that integrates Zentex's ModelProviderSpec into DSPy's LM interface.
    This ensures all DSPy calls go through the audited, fail-closed provider contract.
    """
    
    def __init__(
        self, 
        provider: ModelProviderSpec, 
        caller_context: ModelProviderCallerContext, 
        model_kwargs: Optional[Dict[str, Any]] = None
    ):
        super().__init__("zentex-managed-lm")
        self.provider = provider
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
            # We call the provider. Since provider returns a dict, we serialize it.
            json_resp = self.provider.generate_json(
                prompt=prompt,
                context=context,
                caller_context=self.caller_context
            )
            result_str = json.dumps(json_resp)
        except Exception as e:
            # Re-raise to let the retry loop or Sandbox catch it
            raise RuntimeError(f"ZentexDSPyLM failed: {str(e)}") from e
            
        self.history.append({"prompt": prompt, "response": [result_str]})
        return [result_str]
        
    def inspect_history(self, n: int = 1) -> None:
        pass

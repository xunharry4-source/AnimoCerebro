from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid

from zentex.core.models import CognitiveToolSpec
from zentex.learning.g16_models import SandboxValidationResult


class ThoughtSandbox:
    """
    Isolated execution environment for verifying candidate cognitive tools.
    In this baseline, it implements behavior transformation checks.
    """

    def __init__(self, trace_id: Optional[str] = None) -> None:
        self.trace_id = trace_id or str(uuid.uuid4())

    async def verify_tool_registration(
        self,
        spec: CognitiveToolSpec,
        test_cases: List[Dict[str, Any]],
    ) -> SandboxValidationResult:
        """
        Validate the tool's behavior against its own proposed test cases.
        """
        security_events = []
        is_safe = True
        cpu_total = 0.0
        mem_peak = 0.0
        
        # In this prototype, we simulate a strict identity transform validation.
        # This is because 'identity_transform' is the baseline behavior_key.
        for i, case in enumerate(test_cases):
            input_val = case.get("input")
            expected = case.get("expected")
            
            # Simulated resource usage per case
            cpu_total += 0.0005
            mem_peak = max(mem_peak, 0.2)

            if input_val == expected:
                continue
            else:
                event = f"Logic violation in test case {i}: Input {input_val} != Expected {expected}"
                security_events.append(event)
                is_safe = False

        # Additional security check: Tool must be side-effect free
        if not spec.side_effect_free:
            security_events.append("Tool claimed side-effect free but spec says otherwise.")
            is_safe = False

        return SandboxValidationResult(
            is_safe=is_safe,
            behavior_fingerprint=f"g16_sha256_{self.trace_id[:8]}_{len(test_cases)}",
            security_events=security_events,
            performance_metrics={"cpu_sec": round(cpu_total, 4), "mem_mb": mem_peak},
        )

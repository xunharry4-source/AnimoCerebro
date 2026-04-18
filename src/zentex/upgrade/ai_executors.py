from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

from zentex.upgrade.base_models import (
    CandidatePatch,
)
from zentex.foundation.specs.model_provider import ModelProviderCallerContext
from zentex.upgrade.plugin.models import PluginUpgradeCandidate
from zentex.upgrade.llm.models import LLMUpgradeCandidate
from zentex.upgrade.ai_executors_llm_prompt import build_plugin_generation_request

class OpenHandsEvolutionExecutor:
    """Sub-function 58.3 - AI-driven code modification via OpenHands SDK integration."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key
        from zentex.llm.gateway import LLMGateway
        self.llm_gateway = LLMGateway()
        self.caller_context = ModelProviderCallerContext(
            source_module="evolution_executor",
            invocation_phase="code_generation",
            decision_id=f"evolution-{uuid4().hex[:8]}"
        )

    def execute_modification(self, candidate: PluginUpgradeCandidate) -> CandidatePatch:
        """Physical code evolution (Sub-function 58.2/58.3 - Priority 1)."""
        import os
        from pathlib import Path
        from datetime import datetime, UTC
        
        # 1. Create isolation path (Physical)
        isolation_path = Path(candidate.candidate_plugin_path)
        isolation_path.mkdir(parents=True, exist_ok=True)
        
        # 2. Authentic Code Generation via LLM (Priority 1)
        # Instead of templates, we use the LLM to generate code based on the goal
        request = build_plugin_generation_request(
            plugin_id=candidate.plugin_id,
            goal=candidate.goal,
        )
        
        try:
            response = self.llm_gateway.invoke_generate_json(
                prompt=request["prompt"],
                context={"plugin_id": candidate.plugin_id, "goal": candidate.goal},
                caller_context=self.caller_context,
                system_prompt=request["system_prompt"],
            )
            data = response.output
        except Exception as e:
            raise RuntimeError(f"[LLM MANDATORY] Failed to generate evolved code for {candidate.plugin_id}: {e}") from e

        # 3. Physical write to sandbox
        (isolation_path / "plugin.py").write_text(data.get("plugin_py", ""), encoding="utf-8")
        (isolation_path / "test_plugin.py").write_text(data.get("test_plugin_py", ""), encoding="utf-8")
        (isolation_path / "README.md").write_text(data.get("readme_md", ""), encoding="utf-8")

        return CandidatePatch(
            patch_id=f"patch-{uuid4().hex[:8]}",
            proposal_id="auto-generated", 
            patch_type="logic_upgrade",
            diff_summary=data.get("diff_summary", "Automated evolution performed."),
            code_diff=data.get("plugin_py", "New code generated."), # Proxy for real diff for now
            isolation_path=str(isolation_path),
            created_at=datetime.now(UTC)
        )


class DSPyOptimizationRunner:
    """Sub-function 58.2 - Automated DSPy optimization for LLM programs."""

    def __init__(self, dspy_settings: Dict[str, Any]):
        self._settings = dspy_settings

    def _assert_dspy_installed(self):
        from importlib.util import find_spec
        if find_spec("dspy") is None:
            raise RuntimeError("[LLM MANDATORY] DSPy is not installed on this runtime; cannot perform optimization.")

    def optimize_program(self, candidate: LLMUpgradeCandidate) -> Dict[str, Any]:
        """Run DSPy optimizer with Signature/Module/Metric/Dataset (Sub-function 58.2)."""
        self._assert_dspy_installed()
        
        # Real DSPy integration logic would go here.
        # Returning fake/hardcoded success data (like 0.88) is forbidden.
        raise RuntimeError(
            f"[FAIL CLOSED] DSPy optimizer for {candidate.program_id} is currently in fail-closed mode. "
            "The physical execution pipeline for multi-stage optimization is pending full SDK binding."
        )

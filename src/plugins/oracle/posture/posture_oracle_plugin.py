from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.plugins.models import PluginLifecycleStatus


class BaselinePostureOracle(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = "oracle_posture"
    version: str = "1.0.0"
    feature_code: str = "oracle.posture"
    display_name: str = "Posture Oracle"
    description: str = "Return a safe operating posture for the current decision trace."
    behavior_key: str = "oracle_posture"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    rollback_conditions: list[str] = Field(default_factory=lambda: ["posture_regression"])
    revocation_reasons: list[str] = Field(default_factory=list)

    def apply_posture(self, decision_trace: dict[str, Any]) -> dict[str, Any]:
        """Derive a cognitive posture based on the evidence in the decision trace."""
        # Simple evidence-based weight derivation
        prompt = str(decision_trace.get("prompt") or "").lower()
        context = str(decision_trace.get("context") or "").lower()
        full_text = f"{prompt} {context}"
        
        # High risk keywords
        destructive_keywords = {"delete", "wipe", "overwrite", "destructive", "rm", "format", "truncate"}
        is_destructive = any(kw in full_text for kw in destructive_keywords)
        
        # Mapping: More destructive intent -> Higher risk weight (more conservative)
        risk_weight = 0.8 if is_destructive else 0.3
        
        return {
            "pack_type": "posture_pack",
            "evaluation_style": "evidence_first",
            "risk_weight": risk_weight,
            "risk_tolerance": "low" if is_destructive else "moderate",
            "confirmation_strategy": "explicit_approval" if is_destructive else "confirm_on_write",
            "action_rhythm": "slow_burn" if is_destructive else "bounded_incremental_steps",
            "evidence": {
                "detected_destructive_intent": is_destructive,
                "keywords_found": [kw for kw in destructive_keywords if kw in full_text]
            },
            "role_pack": {
                "active_role_default": "conservative_guardian" if is_destructive else "efficient_assistant",
                "identity_role": "Zentex Adaptive Kernel",
            }
        }


def build_default_posture_oracle() -> BaselinePostureOracle:
    return BaselinePostureOracle()

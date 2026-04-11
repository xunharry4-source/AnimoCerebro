from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from pydantic import BaseModel
from zentex.common.plugin_registry import PluginNotBoundError
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.runtime.nine_questions.state import NineQuestionState
from zentex.runtime.nine_questions.models import (
    ObjectiveProfile,
    EvaluationProfile,
    EvolutionProfile,
    EscalationProfile,
    Phase2EvolutionResult,
)

logger = logging.getLogger(__name__)


class NineQDrivenObjectiveEngine:
    """
    Engine to derive Subjective Profiles (Objective, Evaluation, Evolution) from NineQuestionState.
    Implements Sub-function 2 and Sub-function 3 of Phase 2 spec.
    """

    def __init__(self, identity_kernel: Any = None):
        self._identity_kernel = identity_kernel

    def derive_all_profiles(
        self, 
        nq_state: NineQuestionState, 
        resource_state: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> Phase2EvolutionResult:
        """
        Derive all profiles and apply convergence rules.
        """
        # 1. Base derivation
        obj = self.derive_objective(nq_state)
        eval_prof = self.derive_evaluation(nq_state, resource_state)
        evol = self.derive_evolution(nq_state, history)
        esc = self.derive_escalation(nq_state)

        # 2. Track traceability (Sub-function 4.3)
        driver_refs = {
            "objective": ["q8", "q2"],
            "evaluation": ["q9", "q3", "q4", "q5", "q7"],
            "evolution": ["q9", "q4", "q6", "q7"],
            "escalation": ["q5", "q7", "q8", "q9"]
        }

        # 3. Apply Dynamic Drift Convergence Rules (Sub-function 3)
        self._apply_convergence_rules(obj, eval_prof, evol, esc, nq_state, history)

        # 4. Check hard boundary violations (Sub-function 2.4 / 规则说明)
        violations = self.check_hard_boundary_violation(obj, eval_prof, evol, nq_state)
        
        if violations:
            logger.warning(f"Hard boundary violations detected: {violations}")
            # Enforce clamping/resetting to respect IdentityKernel
            self._enforce_hard_boundaries(obj, eval_prof, evol, violations)

        return Phase2EvolutionResult(
            objective=obj,
            evaluation=eval_prof,
            evolution=evol,
            escalation=esc,
            timestamp=datetime.now(timezone.utc).isoformat(),
            snapshot_version=nq_state.snapshot_version,
            question_driver_refs=driver_refs
        )

    def derive_objective(self, nq_state: NineQuestionState) -> ObjectiveProfile:
        """
        Extract ObjectiveProfile from Q8 results within NineQuestionState.
        """
        q8_data = nq_state.question_snapshots.get("q8", {})
        result = q8_data.get("context_updates", {})
        
        # Mapping from possible different formats to the standard ObjectiveProfile
        return ObjectiveProfile(
            current_mission=result.get("current_mission") or result.get("current_primary_objective") or "Idle",
            primary_objectives=result.get("primary_objectives", []),
            secondary_objectives=result.get("secondary_objectives", []),
            completion_conditions=result.get("completion_conditions", []),
            pause_conditions=result.get("pause_conditions", []),
            escalation_conditions=result.get("escalation_conditions", [])
        )

    def derive_evaluation(self, nq_state: NineQuestionState, resource_state: Optional[Dict[str, Any]] = None) -> EvaluationProfile:
        """
        Extract EvaluationProfile from Q9 results within NineQuestionState.
        Includes deeper integration with resource_state (Sub-function 4.4).
        """
        q9_data = nq_state.question_snapshots.get("q9", {})
        result = q9_data.get("context_updates", {})
        q9_eval = result.get("evaluation_profile", {})
        q2_data = nq_state.question_snapshots.get("q2", {}).get("context_updates", {})
        
        # Deep integration: if resource_state says 'critical', override profile context
        res_context = q9_eval.get("resource_context") or "Standard"
        if isinstance(resource_state, dict) and resource_state.get("asset_status") == "critical":
            res_context = f"CRITICAL - {res_context}"

        return EvaluationProfile(
            role_context=q9_eval.get("role_context") or q2_data.get("current_role") or "General Agent",
            resource_context=res_context,
            risk_level=q9_eval.get("risk_level") or nq_state.question_snapshots.get("q7", {}).get("context_updates", {}).get("risk_level", "low"),
            evaluation_weights=dict(q9_eval.get("evaluation_weights", {"accuracy": 0.2, "speed": 0.2, "risk_control": 0.2, "creativity": 0.2, "continuity": 0.2})),
            conservative_mode_triggered=q9_eval.get("conservative_mode_triggered", False),
            evaluation_style=q9_eval.get("evaluation_style", "balanced")
        )

    def derive_evolution(self, nq_state: NineQuestionState, history: Optional[List[Dict[str, Any]]] = None) -> EvolutionProfile:
        """
        Extract EvolutionProfile from Q6 results and history.
        """
        q9_data = nq_state.question_snapshots.get("q9", {})
        result = q9_data.get("context_updates", {})
        q9_evol = result.get("evolution_profile", {})
        
        return EvolutionProfile(
            allowed_directions=q9_evol.get("allowed_directions", []),
            risk_threshold=q9_evol.get("risk_threshold", 0.1),
            forbidden_directions=q9_evol.get("forbidden_directions", []),
            validation_requirements=q9_evol.get("validation_requirements", [])
        )

    def derive_escalation(self, nq_state: NineQuestionState) -> EscalationProfile:
        """
        Extract EscalationProfile from overall synthesis.
        """
        # Usually summarized from multiple questions (Q5, Q7, Q8, Q9)
        q9_result = nq_state.question_snapshots.get("q9", {}).get("context_updates", {})
        q9_esc = q9_result.get("escalation_profile", {})
        q8_result = nq_state.question_snapshots.get("q8", {}).get("context_updates", {})
        
        return EscalationProfile(
            pause_conditions=q8_result.get("pause_conditions", []) or q9_esc.get("pause_conditions", []),
            help_request_conditions=q9_esc.get("help_request_conditions", []),
            confirmation_required_conditions=q9_esc.get("confirmation_required_conditions", []),
            revisit_conditions=q9_esc.get("revisit_conditions", []),
            rollback_conditions=q9_esc.get("rollback_conditions", [])
        )

    def _apply_convergence_rules(
        self, 
        obj: ObjectiveProfile, 
        eval_prof: EvaluationProfile, 
        evol: EvolutionProfile, 
        esc: EscalationProfile,
        nq_state: NineQuestionState,
        history: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Implements Dynamic Drift Convergence Rules (Sub-function 3 / 规则说明).
        """
        # Rule 1: 资源紧张（Q3 资产不足）→ EvaluationProfile 权重向 risk_control / continuity 收敛
        q3_result = nq_state.question_snapshots.get("q3", {}).get("context_updates", {})
        if q3_result.get("asset_status") == "critical" or q3_result.get("insufficient_resources", False):
            eval_prof.evaluation_weights["risk_control"] += 0.3
            eval_prof.evaluation_weights["continuity"] += 0.3
            # Re-normalize weights
            total = sum(eval_prof.evaluation_weights.values())
            for k in eval_prof.evaluation_weights:
                eval_prof.evaluation_weights[k] /= total

        # Rule 2: 证据不足（Q4 能力不确定）→ EvaluationProfile 触发 conservative_mode (规则收件人)
        confidence_q4 = nq_state.question_snapshots.get("q4", {}).get("confidence", 1.0)
        q4_result = nq_state.question_snapshots.get("q4", {}).get("context_updates", {})
        if confidence_q4 < 0.6 or q4_result.get("uncertainty_high", False):
            eval_prof.conservative_mode_triggered = True
            eval_prof.evaluation_style = "conservative"

        # Rule 3: 协作不可用（Q5 授权受限）→ ObjectiveProfile 收缩为单脑可完成目标
        q5_result = nq_state.question_snapshots.get("q5", {}).get("context_updates", {})
        if q5_result.get("auth_restricted") or not q5_result.get("collaboration_allowed", True):
            # Filter objectives that require external help
            obj.primary_objectives = [o for o in obj.primary_objectives if "collab" not in o.lower()]
            obj.secondary_objectives = [o for o in obj.secondary_objectives if "collab" not in o.lower()]

        # Rule 4: 连续失败历史（Sub-function 3.4）→ Evolution 风险阈值降低
        if history and len(history) >= 2:
            failure_count = sum(1 for h in history[-3:] if h.get("status") == "failed")
            if failure_count >= 2:
                evol.risk_threshold *= 0.5 # Halve the risk threshold
                evol.validation_requirements.append("Post-failure verification mandatory")

    def check_hard_boundary_violation(
        self, 
        obj: ObjectiveProfile, 
        eval_prof: EvaluationProfile, 
        evol: EvolutionProfile, 
        nq_state: NineQuestionState
    ) -> List[str]:
        """
        Check if profiles violate IdentityKernel.non_bypassable_constraints (Sub-function 2.4).
        """
        violations = []
        
        # 1. Resolve IdentityKernel from Q2 snapshot
        q2_data = nq_state.question_snapshots.get("q2", {}).get("context_updates", {})
        identity_kernel = q2_data.get("identity_kernel_snapshot", {}) or {}
        constraints = identity_kernel.get("non_bypassable_constraints", [])
        
        # 2. Check Objective Profile
        for objective in obj.primary_objectives:
            for constraint in constraints:
                if constraint.lower() in objective.lower():
                    violations.append(f"Objective '{objective}' violates Identity Constraint: '{constraint}'")
        
        # 3. Check Evolution Profile
        for direction in evol.allowed_directions:
            for constraint in constraints:
                if constraint.lower() in direction.lower():
                    violations.append(f"Evolution Direction '{direction}' violates Identity Constraint: '{constraint}'")
        
        return violations

    def _enforce_hard_boundaries(
        self, 
        obj: ObjectiveProfile, 
        eval_prof: EvaluationProfile, 
        evol: EvolutionProfile, 
        violations: List[str]
    ):
        """
        Clamps or resets values to respect hard boundaries (Sub-function 2.5).
        """
        # Simple enforcement: remove violating objectives/directions and lower risk threshold
        if violations:
            eval_prof.conservative_mode_triggered = True
            eval_prof.risk_level = "critical"
            evol.risk_threshold = 0.0 # Strict mode
            
            # Filter primary objectives that might be in violations
            valid_objectives = []
            for ob in obj.primary_objectives:
                if not any(ob.lower() in v.lower() for v in violations):
                    valid_objectives.append(ob)
            obj.primary_objectives = valid_objectives

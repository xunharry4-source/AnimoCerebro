"""Sanity Auditor (G25) - Rational Audit Mechanism

## File Purpose
This file implements the G25 rational audit mechanism for Zentex, providing comprehensive
safety auditing capabilities to ensure cognitive system integrity and prevent harmful
behaviors.

## Major Responsibilities
- **Belief Conflict Detection**: Identifies contradictions between policies, rules, and goals
- **Reasoning Loop Detection**: Catches circular reasoning and infinite recursion patterns  
- **Meta-Motivation Drift Detection**: Monitors deviations from baseline motivation profiles
- **External Signal Conflict Detection**: Validates external signals against physical carrier state
- **Audit Failure Handling**: Implements freeze/rollback/human escalation for audit failures
- **Checkpoint Management**: Provides rollback capability through audit checkpoints

## Responsibility Boundaries
- **Responsible for**: Running independent safety audits, generating audit reports, managing checkpoints
- **Not Responsible for**: Making actual decisions, executing remediation actions, modifying system state
- **Input Dependencies**: World model, strategy graph, ban layer, motivation state, self-modification history
- **Output Guarantees**: Structured audit reports with clear disposition actions and evidence trails

## Key Design Principles
- **Independent Operation**: Runs independently from main brain chain to avoid interference
- **Fail-Closed Behavior**: Audit failures block G18 self-shaping to prevent "sick evolution"
- **Evidence-Based**: All findings include concrete evidence and audit trails
- **Rollback Capability**: Supports checkpoint creation and state restoration

Based on Zentex Product Document Function 22 (G25)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Literal, Optional, Set
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AuditSeverity(str, Enum):
    """Audit severity levels."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditStatus(str, Enum):
    """Audit result status."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    FROZEN = "frozen"


class DispositionAction(str, Enum):
    """Recommended disposition actions for audit failures."""
    CONTINUE = "continue"           # Continue execution
    FREEZE = "freeze"               # Freeze current operation
    ROLLBACK = "rollback"           # Rollback to previous state
    HUMAN_REVIEW = "human_review"     # Escalate to human review
    BLOCK_SELF_MOD = "block_self_mod" # Block self-modification (G18)


class BeliefConflict(BaseModel):
    """Belief conflict record - tracks contradictions in beliefs/rules/policies.

    Fields:
        conflict_id: Unique identifier for this conflict
        conflict_type: Type of conflict (policy/rule/belief/goal)
        conflict_sources: Sources that contributed to the conflict
        description: Human-readable description of the conflict
        severity: Impact severity of the conflict
    """
    model_config = ConfigDict(extra="forbid")

    conflict_id: str = Field(default_factory=lambda: str(uuid4()))
    conflict_type: Literal["policy", "rule", "belief", "goal", "strategy"]
    conflict_sources: List[str] = Field(default_factory=list)
    description: str = Field(min_length=1)
    severity: AuditSeverity = AuditSeverity.MEDIUM
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReasoningLoop(BaseModel):
    """Reasoning loop record - tracks circular reasoning or infinite recursion.

    Fields:
        loop_id: Unique identifier for this loop
        loop_path: Sequence of reasoning steps forming the loop
        truncation_point: Where the loop was detected/cut
        recurrence_count: How many times the pattern repeated
    """
    model_config = ConfigDict(extra="forbid")

    loop_id: str = Field(default_factory=lambda: str(uuid4()))
    loop_path: List[str] = Field(default_factory=list)
    truncation_point: str = Field(min_length=1)
    recurrence_count: int = Field(ge=2, default=2)
    severity: AuditSeverity = AuditSeverity.HIGH
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MotivationDrift(BaseModel):
    """Meta-motivation drift detection record.

    Fields:
        drift_id: Unique identifier for this drift
        baseline_profile: Expected motivation profile
        current_profile: Detected motivation profile
        drift_score: Calculated drift magnitude (0.0 to 1.0)
        drift_dimensions: Which motivation dimensions drifted
    """
    model_config = ConfigDict(extra="forbid")

    drift_id: str = Field(default_factory=lambda: str(uuid4()))
    baseline_profile: Dict[str, Any] = Field(default_factory=dict)
    current_profile: Dict[str, Any] = Field(default_factory=dict)
    drift_score: float = Field(ge=0.0, le=1.0)
    drift_dimensions: List[str] = Field(default_factory=list)
    severity: AuditSeverity = AuditSeverity.MEDIUM
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExternalSignalConflict(BaseModel):
    """External signal vs physical carrier state conflict.

    Fields:
        conflict_id: Unique identifier
        signal_source: Source of external signal
        carrier_state: Physical carrier state reading
        conflict_description: Description of the conflict
    """
    model_config = ConfigDict(extra="forbid")

    conflict_id: str = Field(default_factory=lambda: str(uuid4()))
    signal_source: str = Field(min_length=1)
    carrier_state: Dict[str, Any] = Field(default_factory=dict)
    signal_content: Dict[str, Any] = Field(default_factory=dict)
    conflict_description: str = Field(min_length=1)
    severity: AuditSeverity = AuditSeverity.CRITICAL
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SanityAuditReport(BaseModel):
    """Comprehensive sanity audit report (G25 output).

    Fields:
        audit_id: Unique audit identifier
        status: Overall audit status
        belief_conflicts: Detected belief conflicts
        reasoning_loops: Detected reasoning loops
        motivation_drifts: Detected motivation drifts
        external_conflicts: External signal conflicts
        drift_score: Overall system drift score
        disposition: Recommended disposition action
        audit_scope: What was audited
        created_at: Audit timestamp
    """
    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(default_factory=lambda: str(uuid4()))
    status: AuditStatus = AuditStatus.PASSED
    belief_conflicts: List[BeliefConflict] = Field(default_factory=list)
    reasoning_loops: List[ReasoningLoop] = Field(default_factory=list)
    motivation_drifts: List[MotivationDrift] = Field(default_factory=list)
    external_conflicts: List[ExternalSignalConflict] = Field(default_factory=list)
    drift_score: float = Field(ge=0.0, le=1.0, default=0.0)
    disposition: DispositionAction = DispositionAction.CONTINUE
    audit_scope: str = Field(default="full")
    summary: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_critical_issues(self) -> bool:
        """Check if report contains any critical issues."""
        checks = [
            any(c.severity == AuditSeverity.CRITICAL for c in self.belief_conflicts),
            any(l.severity == AuditSeverity.CRITICAL for l in self.reasoning_loops),
            any(d.severity == AuditSeverity.CRITICAL for d in self.motivation_drifts),
            any(e.severity == AuditSeverity.CRITICAL for e in self.external_conflicts),
        ]
        return any(checks)

    @property
    def issue_count(self) -> int:
        """Total number of issues found."""
        return (
            len(self.belief_conflicts) +
            len(self.reasoning_loops) +
            len(self.motivation_drifts) +
            len(self.external_conflicts)
        )


class AuditCheckpoint(BaseModel):
    """Audit checkpoint for rollback capability.

    Fields:
        checkpoint_id: Unique checkpoint identifier
        snapshot_version: Version of the state snapshot
        brain_state: Serialized brain state at checkpoint
        audit_context: Audit context at checkpoint time
    """
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str = Field(default_factory=lambda: str(uuid4()))
    snapshot_version: int = Field(ge=0)
    brain_state: Dict[str, Any] = Field(default_factory=dict)
    audit_context: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SanityAuditor:
    """G25 Rational Audit mechanism - independent safety auditing.

    The SanityAuditor operates independently from the main brain chain
    to avoid blocking or interference. It performs comprehensive checks:

    1. Belief conflict detection - Identifies contradictions in policies/rules
    2. Reasoning loop detection - Catches circular/infinite reasoning
    3. Motivation drift detection - Monitors meta-motivation baseline deviations
    4. External signal conflict - Validates external signals against physical state
    5. Self-modification gating - Blocks G18 self-shaping if audit fails

    Hard Redlines:
    - Runs independently, does not block main brain chain
    - Audit failures block G18 self-shaping to prevent带病进化 (sick evolution)
    - Can detect identity tampering and escalate to human review
    - Freezes on extreme external signal vs physical carrier conflicts
    """

    def __init__(
        self,
        *,
        brain_scope: str = "zentex.runtime",
        drift_threshold: float = 0.3,
        loop_recurrence_threshold: int = 3,
    ) -> None:
        self._brain_scope = brain_scope
        self._drift_threshold = drift_threshold
        self._loop_threshold = loop_recurrence_threshold
        self._checkpoints: List[AuditCheckpoint] = []
        self._audit_history: List[SanityAuditReport] = []
        self._baseline_profile: Optional[Dict[str, Any]] = None

    @property
    def brain_scope(self) -> str:
        return self._brain_scope

    @property
    def last_audit(self) -> Optional[SanityAuditReport]:
        return self._audit_history[-1] if self._audit_history else None

    def set_baseline_profile(self, profile: Dict[str, Any]) -> None:
        """Set the baseline motivation profile for drift detection."""
        self._baseline_profile = profile.copy()

    def create_checkpoint(self, brain_state: Dict[str, Any]) -> AuditCheckpoint:
        """Create an audit checkpoint for potential rollback."""
        checkpoint = AuditCheckpoint(
            snapshot_version=len(self._checkpoints),
            brain_state=brain_state.copy(),
            audit_context={
                "last_audit_id": self.last_audit.audit_id if self.last_audit else None,
                "drift_score": self.last_audit.drift_score if self.last_audit else 0.0,
            },
        )
        self._checkpoints.append(checkpoint)
        # Keep only last 10 checkpoints
        if len(self._checkpoints) > 10:
            self._checkpoints = self._checkpoints[-10:]
        return checkpoint

    def audit(
        self,
        world_model: Dict[str, Any],
        strategy_graph: Dict[str, Any],
        ban_layer: Dict[str, Any],
        motivation_state: Dict[str, Any],
        self_rewrite_history: Optional[List[Dict[str, Any]]] = None,
    ) -> SanityAuditReport:
        """Execute full sanity audit (G25 main entry point).

        Args:
            world_model: Current world model state
            strategy_graph: Current strategy/policy graph
            ban_layer: Prohibition/ban layer configuration
            motivation_state: Current meta-motivation state
            self_rewrite_history: Recent self-modification records

        Returns:
            SanityAuditReport with full audit results and disposition
        """
        self_rewrite_history = self_rewrite_history or []

        # Run all detection mechanisms
        belief_conflicts = self._detect_belief_conflicts(world_model, strategy_graph, ban_layer)
        reasoning_loops = self._detect_reasoning_loops(strategy_graph)
        motivation_drifts = self._detect_motivation_drift(motivation_state)
        external_conflicts = self._detect_external_conflicts(world_model)

        # Calculate overall drift score
        drift_score = self._calculate_drift_score(
            belief_conflicts, reasoning_loops, motivation_drifts, external_conflicts
        )

        # Determine disposition
        disposition = self._determine_disposition(
            belief_conflicts, reasoning_loops, motivation_drifts, external_conflicts, drift_score
        )

        # Determine status
        status = self._determine_status(disposition, drift_score)

        # Generate summary
        summary = self._generate_summary(
            belief_conflicts, reasoning_loops, motivation_drifts, external_conflicts, disposition
        )

        report = SanityAuditReport(
            status=status,
            belief_conflicts=belief_conflicts,
            reasoning_loops=reasoning_loops,
            motivation_drifts=motivation_drifts,
            external_conflicts=external_conflicts,
            drift_score=drift_score,
            disposition=disposition,
            summary=summary,
        )

        self._audit_history.append(report)
        # Keep only last 100 audit records
        if len(self._audit_history) > 100:
            self._audit_history = self._audit_history[-100:]

        return report

    def _detect_belief_conflicts(
        self,
        world_model: Dict[str, Any],
        strategy_graph: Dict[str, Any],
        ban_layer: Dict[str, Any],
    ) -> List[BeliefConflict]:
        """Detect contradictions between beliefs, policies, rules, and goals."""
        conflicts: List[BeliefConflict] = []

        # Check for policy contradictions
        policies = strategy_graph.get("policies", {})
        policy_ids = list(policies.keys())

        for i, p1_id in enumerate(policy_ids):
            for p2_id in policy_ids[i+1:]:
                p1 = policies[p1_id]
                p2 = policies[p2_id]
                # Check for direct contradictions
                if self._are_policies_contradictory(p1, p2):
                    conflicts.append(BeliefConflict(
                        conflict_type="policy",
                        conflict_sources=[p1_id, p2_id],
                        description=f"Policy contradiction: {p1_id} conflicts with {p2_id}",
                        severity=AuditSeverity.HIGH,
                    ))

        # Check for banned actions in strategies
        banned_actions = set(ban_layer.get("banned_actions", []))
        strategy_actions = set(strategy_graph.get("actions", []))
        violations = banned_actions & strategy_actions

        for violation in violations:
            conflicts.append(BeliefConflict(
                conflict_type="rule",
                conflict_sources=["ban_layer", "strategy_graph"],
                description=f"Banned action present in strategy: {violation}",
                severity=AuditSeverity.CRITICAL,
            ))

        # Check for goal conflicts
        goals = world_model.get("active_goals", [])
        for i, g1 in enumerate(goals):
            for g2 in goals[i+1:]:
                if self._are_goals_conflicting(g1, g2):
                    conflicts.append(BeliefConflict(
                        conflict_type="goal",
                        conflict_sources=[g1.get("id"), g2.get("id")],
                        description=f"Goal conflict: {g1.get('name')} vs {g2.get('name')}",
                        severity=AuditSeverity.MEDIUM,
                    ))

        return conflicts

    def _detect_reasoning_loops(self, strategy_graph: Dict[str, Any]) -> List[ReasoningLoop]:
        """Detect circular reasoning or infinite recursion patterns."""
        loops: List[ReasoningLoop] = []

        # Extract reasoning chains from strategy graph
        reasoning_chains = strategy_graph.get("reasoning_chains", [])

        for chain in reasoning_chains:
            path = chain.get("path", [])
            # Check for cycles in the path
            seen: Set[str] = set()
            cycle_start = None
            for i, node in enumerate(path):
                node_id = str(node)
                if node_id in seen:
                    cycle_start = node_id
                    # Count recurrences
                    recurrences = sum(1 for p in path if str(p) == node_id)
                    if recurrences >= self._loop_threshold:
                        loops.append(ReasoningLoop(
                            loop_path=[str(p) for p in path],
                            truncation_point=node_id,
                            recurrence_count=recurrences,
                            severity=AuditSeverity.HIGH if recurrences > 5 else AuditSeverity.MEDIUM,
                        ))
                    break
                seen.add(node_id)

        return loops

    def _detect_motivation_drift(self, motivation_state: Dict[str, Any]) -> List[MotivationDrift]:
        """Detect drift from baseline motivation profile."""
        drifts: List[MotivationDrift] = []

        if self._baseline_profile is None:
            # First run - set baseline
            self._baseline_profile = motivation_state.copy()
            return drifts

        # Compare current with baseline
        drift_dimensions = []
        total_drift = 0.0
        dimension_count = 0

        for key in self._baseline_profile:
            baseline_val = self._baseline_profile.get(key, 0)
            current_val = motivation_state.get(key, baseline_val)
            if isinstance(baseline_val, (int, float)) and isinstance(current_val, (int, float)):
                diff = abs(current_val - baseline_val)
                max_val = max(abs(baseline_val), abs(current_val), 1.0)
                normalized_drift = diff / max_val
                total_drift += normalized_drift
                dimension_count += 1
                if normalized_drift > self._drift_threshold:
                    drift_dimensions.append(key)

        if dimension_count > 0:
            avg_drift = total_drift / dimension_count
            if avg_drift > self._drift_threshold or drift_dimensions:
                drifts.append(MotivationDrift(
                    baseline_profile=self._baseline_profile.copy(),
                    current_profile=motivation_state.copy(),
                    drift_score=avg_drift,
                    drift_dimensions=drift_dimensions,
                    severity=AuditSeverity.HIGH if avg_drift > 0.5 else AuditSeverity.MEDIUM,
                ))

        return drifts

    def _detect_external_conflicts(self, world_model: Dict[str, Any]) -> List[ExternalSignalConflict]:
        """Detect conflicts between external signals and physical carrier state."""
        conflicts: List[ExternalSignalConflict] = []

        # Get external signals and physical state from world model
        external_signals = world_model.get("external_signals", [])
        physical_state = world_model.get("physical_host_state", {})

        for signal in external_signals:
            signal_source = signal.get("source", "unknown")
            signal_content = signal.get("content", {})

            # Check for conflicts with physical state
            conflict_desc = self._check_signal_physical_conflict(signal_content, physical_state)
            if conflict_desc != "no_conflict":
                conflicts.append(ExternalSignalConflict(
                    signal_source=signal_source,
                    carrier_state=physical_state.copy(),
                    signal_content=signal_content,
                    conflict_description=conflict_desc,
                    severity=AuditSeverity.CRITICAL,
                ))

        return conflicts

    def _calculate_drift_score(
        self,
        belief_conflicts: List[BeliefConflict],
        reasoning_loops: List[ReasoningLoop],
        motivation_drifts: List[MotivationDrift],
        external_conflicts: List[ExternalSignalConflict],
    ) -> float:
        """Calculate overall system drift score (0.0 to 1.0)."""
        scores = []

        # Weight by severity
        severity_weights = {
            AuditSeverity.INFO: 0.05,
            AuditSeverity.LOW: 0.1,
            AuditSeverity.MEDIUM: 0.2,
            AuditSeverity.HIGH: 0.4,
            AuditSeverity.CRITICAL: 0.8,
        }

        for conflict in belief_conflicts:
            scores.append(severity_weights.get(conflict.severity, 0.1))

        for loop in reasoning_loops:
            scores.append(severity_weights.get(loop.severity, 0.2))

        for drift in motivation_drifts:
            scores.append(drift.drift_score)

        for conflict in external_conflicts:
            scores.append(severity_weights.get(conflict.severity, 0.8))

        if not scores:
            return 0.0

        # Use max score weighted by issue count
        max_score = max(scores) if scores else 0.0
        count_penalty = min(0.2, len(scores) * 0.05)

        return min(1.0, max_score + count_penalty)

    def _determine_disposition(
        self,
        belief_conflicts: List[BeliefConflict],
        reasoning_loops: List[ReasoningLoop],
        motivation_drifts: List[MotivationDrift],
        external_conflicts: List[ExternalSignalConflict],
        drift_score: float,
    ) -> DispositionAction:
        """Determine recommended disposition based on findings."""
        # Check for critical external conflicts - always freeze
        if any(e.severity == AuditSeverity.CRITICAL for e in external_conflicts):
            return DispositionAction.FREEZE

        # Check for critical belief conflicts
        critical_belief = any(c.severity == AuditSeverity.CRITICAL for c in belief_conflicts)
        critical_loop = any(l.severity == AuditSeverity.CRITICAL for l in reasoning_loops)

        if critical_belief or critical_loop:
            if drift_score > 0.7:
                return DispositionAction.HUMAN_REVIEW
            return DispositionAction.BLOCK_SELF_MOD

        # High drift score triggers human review
        if drift_score > 0.8:
            return DispositionAction.HUMAN_REVIEW

        # Moderate drift blocks self-modification
        if drift_score > 0.5:
            return DispositionAction.BLOCK_SELF_MOD

        # High but not critical - freeze but may continue after review
        if drift_score > 0.3:
            return DispositionAction.FREEZE

        return DispositionAction.CONTINUE

    def _determine_status(self, disposition: DispositionAction, drift_score: float) -> AuditStatus:
        """Determine overall audit status."""
        if disposition == DispositionAction.CONTINUE:
            return AuditStatus.PASSED
        if disposition == DispositionAction.FREEZE:
            return AuditStatus.FROZEN
        if drift_score > 0.5:
            return AuditStatus.FAILED
        return AuditStatus.WARNING

    def _generate_summary(
        self,
        belief_conflicts: List[BeliefConflict],
        reasoning_loops: List[ReasoningLoop],
        motivation_drifts: List[MotivationDrift],
        external_conflicts: List[ExternalSignalConflict],
        disposition: DispositionAction,
    ) -> str:
        """Generate human-readable audit summary."""
        parts = []

        total_issues = len(belief_conflicts) + len(reasoning_loops) + len(motivation_drifts) + len(external_conflicts)

        if total_issues == 0:
            parts.append("Audit passed. No issues detected.")
        else:
            parts.append(f"Audit found {total_issues} issue(s):")
            if belief_conflicts:
                parts.append(f"- {len(belief_conflicts)} belief conflict(s)")
            if reasoning_loops:
                parts.append(f"- {len(reasoning_loops)} reasoning loop(s)")
            if motivation_drifts:
                parts.append(f"- {len(motivation_drifts)} motivation drift(s)")
            if external_conflicts:
                parts.append(f"- {len(external_conflicts)} external signal conflict(s)")

        parts.append(f"Recommended disposition: {disposition.value}")

        return "\n".join(parts)

    def _are_policies_contradictory(self, p1: Dict[str, Any], p2: Dict[str, Any]) -> bool:
        """Check if two policies are contradictory."""
        # Simple heuristic: check for opposite actions or mutually exclusive conditions
        p1_action = p1.get("action", "")
        p2_action = p2.get("action", "")

        # Check for negation patterns
        if p1_action.startswith("!") and p1_action[1:] == p2_action:
            return True
        if p2_action.startswith("!") and p2_action[1:] == p1_action:
            return True

        # Check for condition mutual exclusivity
        p1_conditions = set(p1.get("conditions", []))
        p2_conditions = set(p2.get("conditions", []))

        # If same conditions but different actions, likely contradictory
        if p1_conditions == p2_conditions and p1_action != p2_action:
            return True

        return False

    def _are_goals_conflicting(self, g1: Dict[str, Any], g2: Dict[str, Any]) -> bool:
        """Check if two goals are in conflict."""
        # Check for resource competition
        g1_resources = set(g1.get("required_resources", []))
        g2_resources = set(g2.get("required_resources", []))

        if g1_resources & g2_resources:
            # Same resource requirements, check priorities
            p1 = g1.get("priority", 0)
            p2 = g2.get("priority", 0)
            # If same priority and same resources, potential conflict
            if p1 == p2:
                return True

        # Check for mutually exclusive outcomes
        g1_outcome = g1.get("target_outcome", "")
        g2_outcome = g2.get("target_outcome", "")
        if g1_outcome.startswith("!") and g1_outcome[1:] == g2_outcome:
            return True
        if g2_outcome.startswith("!") and g2_outcome[1:] == g1_outcome:
            return True

        return False

    def _check_signal_physical_conflict(
        self,
        signal_content: Dict[str, Any],
        physical_state: Dict[str, Any],
    ) -> str:
        """Check if signal conflicts with physical state.
        
        Returns:
            Conflict description string, or "no_conflict" if no conflicts detected.
        """
        conflicts = []
        
        # Check memory claims
        signal_memory = signal_content.get("memory_status")
        physical_memory = physical_state.get("memory")

        if signal_memory and physical_memory:
            if signal_memory == "critical" and physical_memory.get("status") != "critical":
                conflicts.append(f"Signal claims critical memory but physical state shows {physical_memory.get('status')}")

        # Check network claims
        signal_network = signal_content.get("network_status")
        physical_network = physical_state.get("network")

        if signal_network and physical_network:
            if signal_network == "disconnected" and physical_network.get("status") == "connected":
                conflicts.append("Signal claims network disconnected but physical shows connected")

        return conflicts[0] if conflicts else "no_conflict"

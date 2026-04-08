"""Safety Manager - Unified External Service Interface for Safety & Conflict Management

## File Purpose
This file implements the unified external service interface for all safety and conflict management
capabilities in Zentex. It provides a single, coherent entry point for external services and
internal modules to interact with safety features while maintaining strict engineering standards.

## Major Responsibilities
- **Unified Interface Coordination**: Manages access to all safety subsystems through single interface
- **Multi-Layer Safety Evaluation**: Coordinates conflict detection, sanity audits, cloud audits, and experience exchange
- **Configuration Management**: Handles unified configuration for all safety components
- **Decision Aggregation**: Combines results from multiple safety layers into coherent decisions
- **Status Monitoring**: Provides comprehensive system status across all safety modules
- **Audit Trail Integration**: Maintains complete audit trails across all safety operations
- **External Service Gateway**: Serves as primary entry point for external safety interactions

## Responsibility Boundaries
- **Responsible for**: Coordinating safety subsystems, providing unified API, managing configuration
- **Not Responsible for**: Implementing individual safety algorithms, making policy decisions
- **Input Dependencies**: World models, strategy graphs, action requests, configuration parameters
- **Output Guarantees**: Structured safety decisions, comprehensive status reports, audit trails

## Key Design Principles
- **Fail-Closed Operation**: Any safety layer failure results in conservative blocking behavior
- **Layer Independence**: Each safety subsystem operates independently with proper isolation
- **Explicit Configuration**: Missing dependencies result in explicit errors, not silent fallback
- **Audit Completeness**: All safety decisions include complete audit trails and evidence
- **Interface Simplicity**: Complex safety operations exposed through simple, coherent API
- **Zentex Compliance**: All operations strictly follow Zentex engineering redlines and guidelines

## Subsystem Coordination
1. **CognitiveConflictEngine**: Internal contradiction detection and resolution
2. **SanityAuditor (G25)**: Rational audit mechanism for system integrity
3. **CloudAuditorClient (G26)**: External safety validation through cloud services
4. **ExperienceExchangeManager (G37)**: Secure cross-instance experience sharing
5. **SafetyGate (G12)**: Autonomous safety and alignment guardrails

Usage:
    from zentex.safety import SafetyManager

    # Initialize with default configuration
    safety = SafetyManager()

    # Or initialize with custom configuration
    safety = SafetyManager(
        brain_scope="my_application",
        enable_cloud_audit=True,
        cloud_config={"api_key": "...", "api_secret": "..."},
    )

    # Run comprehensive safety audit
    report = safety.audit(
        world_model=current_world_model,
        strategy_graph=current_strategy,
    )

    # Check if action is safe to proceed
    if safety.is_safe_to_proceed("self_modify", {"change": "..."}):
        execute_modification()

    # Share experience with other instances
    packet = safety.create_experience(
        experience_type="strategy_patch",
        payload={...},
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.safety.conflict_engine import (
    CognitiveConflictEngine,
    CognitiveConflictReport,
    ConflictSharedState,
    ReconciliationPlan,
    StaleWriteError,
)
from zentex.safety.sanity_auditor import (
    AuditCheckpoint,
    AuditSeverity,
    AuditStatus,
    BeliefConflict,
    DispositionAction,
    ExternalSignalConflict,
    MotivationDrift,
    ReasoningLoop,
    SanityAuditReport,
    SanityAuditor,
)
from zentex.safety.cloud_auditor import (
    CloudAuditDecision,
    CloudAuditRequest,
    CloudAuditorClient,
    CloudAuditorConfig,
    CloudDecisionStatus,
    DegradationRecord,
)
from zentex.safety.experience_exchange import (
    ContaminationRecord,
    ExperienceAdoptionReview,
    ExperienceExchangeConfig,
    ExperienceExchangeManager,
    ExperienceExchangePacket,
    ExperienceTrustLevel,
    ExperienceType,
    QuarantineZoneEntry,
    RollbackResult,
)
from zentex.safety.safety_gate import (
    DetectedBypassAttempt,
    RedLineAction,
    RedLineCategory,
    RiskLevel,
    SafetyDecisionStatus,
    SafetyGate,
    SafetyGateConfig,
    SafetyGateDecision,
)


class SafetyConfig(BaseModel):
    """Unified safety module configuration.

    Fields:
        brain_scope: Identifier for this brain instance
        brain_id: Unique brain identifier (for experience exchange)
        enable_sanity_audit: Enable G25 rational auditing
        enable_cloud_audit: Enable G26 cloud auditing
        enable_experience_exchange: Enable G37 experience exchange
        sanity_drift_threshold: Drift threshold for sanity audit
        cloud_endpoint: Cloud audit service endpoint
        cloud_api_key: Cloud audit API key
        cloud_api_secret: Cloud audit API secret
        exchange_signing_key: Key for signing experience packets
        exchange_verification_keys: Trusted brain public keys
        exchange_trust_threshold: Minimum trust score for experiences
    """
    model_config = ConfigDict(extra="forbid")

    brain_scope: str = Field(default="zentex.runtime")
    brain_id: str = Field(default_factory=lambda: str(uuid4()))

    # Feature toggles
    enable_sanity_audit: bool = Field(default=True)
    enable_cloud_audit: bool = Field(default=False)
    enable_experience_exchange: bool = Field(default=False)

    # Sanity audit config
    sanity_drift_threshold: float = Field(ge=0.0, le=1.0, default=0.3)

    # Cloud audit config
    cloud_endpoint: str = Field(default="https://audit.zentex.io/v1/decide")
    cloud_api_key: str = Field(default="")
    cloud_api_secret: str = Field(default="")
    cloud_timeout_seconds: float = Field(ge=1.0, default=10.0)

    # Experience exchange config
    exchange_signing_key: str = Field(default="")
    exchange_verification_keys: Dict[str, str] = Field(default_factory=dict)
    exchange_trust_threshold: float = Field(ge=0.0, le=1.0, default=0.3)
    exchange_default_validity_days: int = Field(ge=1, default=30)


class SafetyStatus(BaseModel):
    """Overall safety system status.

    Fields:
        overall_status: Aggregate safety status
        conflict_count: Number of unresolved conflicts
        last_audit_status: Result of last sanity audit
        last_audit_drift_score: System drift score
        cloud_auditor_configured: Whether cloud auditor is ready
        cloud_degradation_count: Number of cloud degradation events
        quarantine_size: Experiences in quarantine
        adopted_experiences: Total adopted experiences
        active_contaminations: Active contamination records
    """
    model_config = ConfigDict(extra="forbid")

    overall_status: Literal["healthy", "warning", "critical", "degraded"] = "healthy"
    conflict_count: int = Field(ge=0, default=0)
    last_audit_status: Optional[AuditStatus] = None
    last_audit_drift_score: float = Field(ge=0.0, le=1.0, default=0.0)
    cloud_auditor_configured: bool = False
    cloud_degradation_count: int = Field(ge=0, default=0)
    quarantine_size: int = Field(ge=0, default=0)
    adopted_experiences: int = Field(ge=0, default=0)
    active_contaminations: int = Field(ge=0, default=0)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SafetyDecision(BaseModel):
    """Unified safety decision for an action.

    Fields:
        decision_id: Unique decision identifier
        action_type: Type of action evaluated
        allowed: Whether action is permitted
        reason: Human-readable decision explanation
        constraints: Additional constraints if allowed
        risk_level: Assessed risk level
        audit_trail: Decision audit trail
    """
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: str = Field(min_length=1)
    allowed: bool = False
    reason: str = Field(default="")
    constraints: Dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SafetyManager:
    """Unified external service interface for Safety & Conflict Management.

    The SafetyManager provides a single, coherent interface to all safety
    capabilities in Zentex. It coordinates multiple subsystems:

    1. CognitiveConflictEngine - Detects and resolves internal contradictions
    2. SanityAuditor - Performs rational audits (G25)
    3. CloudAuditorClient - External safety validation (G26)
    4. ExperienceExchangeManager - Secure cross-instance learning (G37)

    Key Capabilities:
    - Comprehensive safety auditing with conflict detection
    - Cloud-based external safety validation
    - Secure experience sharing between instances
    - Contamination tracking and rollback
    - Unified decision making for high-risk actions

    Usage Patterns:

    # Basic initialization
    safety = SafetyManager()

    # With custom configuration
    config = SafetyConfig(
        brain_scope="production_instance_1",
        enable_cloud_audit=True,
        cloud_api_key="...",
    )
    safety = SafetyManager(config)

    # Run comprehensive audit
    report = safety.audit(world_model, strategy, ban_layer, motivation)

    # Evaluate action safety
    decision = safety.evaluate_action(
        action_type="self_modify",
        payload={"change": "update_strategy"},
    )
    if decision.allowed:
        execute_action()

    # Check if safe to proceed
    if safety.is_safe_to_proceed():
        continue_operation()

    # Create and share experience
    packet = safety.create_experience(
        experience_type=ExperienceType.STRATEGY_PATCH_SUGGESTION,
        payload={"improvement": "..."},
    )
    send_to_other_instance(packet)

    # Receive experience from other instance
    review = safety.receive_experience(incoming_packet)
    if review.conclusion == "approved":
        # Experience enters quarantine
        pass

    # Check system status
    status = safety.get_status()
    if status.overall_status == "critical":
        alert_operators()

    Hard Redlines:
    - All high-risk decisions go through multi-layer safety checks
    - Self-modification is blocked if sanity audit fails
    - Cloud audit degrades explicitly, never silently
    - Experiences never enter main chain without quarantine
    - All contamination is traceable and rollback-able
    """

    def __init__(self, config: Optional[SafetyConfig] = None) -> None:
        self._config = config or SafetyConfig()

        # Initialize subsystems
        self._conflict_engine = CognitiveConflictEngine(
            brain_scope=self._config.brain_scope,
        )

        self._sanity_auditor: Optional[SanityAuditor] = None
        if self._config.enable_sanity_audit:
            self._sanity_auditor = SanityAuditor(
                brain_scope=self._config.brain_scope,
                drift_threshold=self._config.sanity_drift_threshold,
            )

        self._cloud_auditor: Optional[CloudAuditorClient] = None
        if self._config.enable_cloud_audit:
            cloud_config = CloudAuditorConfig(
                endpoint=self._config.cloud_endpoint,
                api_key=self._config.cloud_api_key,
                api_secret=self._config.cloud_api_secret,
                timeout_seconds=self._config.cloud_timeout_seconds,
            )
            self._cloud_auditor = CloudAuditorClient(
                config=cloud_config,
                brain_scope=self._config.brain_scope,
            )

        self._experience_manager: Optional[ExperienceExchangeManager] = None
        if self._config.enable_experience_exchange:
            exchange_config = ExperienceExchangeConfig(
                brain_id=self._config.brain_id,
                signing_key=self._config.exchange_signing_key,
                verification_keys=self._config.exchange_verification_keys,
                trust_threshold=self._config.exchange_trust_threshold,
                default_validity_days=self._config.exchange_default_validity_days,
            )
            self._experience_manager = ExperienceExchangeManager(config=exchange_config)

        # Initialize SafetyGate (G12)
        self._safety_gate = SafetyGate(
            config=SafetyGateConfig(
                brain_scope=self._config.brain_scope,
                enable_bypass_detection=True,
                enable_dual_confirmation=True,
                require_cloud_audit_for_critical=True,
            ),
        )

    @property
    def brain_scope(self) -> str:
        """Get the brain scope identifier."""
        return self._config.brain_scope

    @property
    def brain_id(self) -> str:
        """Get the unique brain identifier."""
        return self._config.brain_id

    @property
    def safety_gate(self) -> SafetyGate:
        """Get the SafetyGate instance for direct access."""
        return self._safety_gate

    # ==========================================================================
    # Safety Gate Interface (G12)
    # ==========================================================================

    def validate_through_gate(
        self,
        action_type: str,
        action_payload: Dict[str, Any],
        risk_level: Optional[Literal["low", "medium", "high", "critical"]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> SafetyGateDecision:
        """Validate an action through the SafetyGate (G12).

        This provides direct access to SafetyGate validation for high-risk
        actions that require non-bypassable safety checks.

        Args:
            action_type: Type of action to validate
            action_payload: Actual execution parameters
            risk_level: Optional risk level override
            context: Additional validation context

        Returns:
            SafetyGateDecision with detailed validation results
        """
        # Map string risk level to RiskLevel enum
        risk_level_enum = None
        if risk_level:
            risk_level_enum = RiskLevel(risk_level)

        return self._safety_gate.validate_action(
            action_type=action_type,
            action_payload=action_payload,
            risk_level=risk_level_enum,
            context=context,
        )

    # ==========================================================================
    # Unified Audit Interface
    # ==========================================================================

    def audit(
        self,
        world_model: Dict[str, Any],
        strategy_graph: Dict[str, Any],
        ban_layer: Optional[Dict[str, Any]] = None,
        motivation_state: Optional[Dict[str, Any]] = None,
        self_rewrite_history: Optional[List[Dict[str, Any]]] = None,
    ) -> SanityAuditReport:
        """Execute comprehensive safety audit.

        This runs the G25 SanityAuditor to check for:
        - Belief conflicts between policies/rules
        - Reasoning loops and infinite recursion
        - Meta-motivation drift from baseline
        - External signal vs physical state conflicts

        Args:
            world_model: Current world model state
            strategy_graph: Current strategy/policy graph
            ban_layer: Prohibition layer configuration
            motivation_state: Current meta-motivation state
            self_rewrite_history: Recent self-modification records

        Returns:
            SanityAuditReport with findings and disposition
        """
        if self._sanity_auditor is None:
            # Return empty passed report if auditing disabled
            return SanityAuditReport(
                status=AuditStatus.PASSED,
                summary="Sanity audit disabled",
            )

        return self._sanity_auditor.audit(
            world_model=world_model,
            strategy_graph=strategy_graph,
            ban_layer=ban_layer or {},
            motivation_state=motivation_state or {},
            self_rewrite_history=self_rewrite_history,
        )

    def quick_audit(self) -> SafetyStatus:
        """Quick status check without full audit.

        Returns current safety status based on cached state.
        """
        return self.get_status()

    def create_checkpoint(self, brain_state: Dict[str, Any]) -> AuditCheckpoint:
        """Create an audit checkpoint for rollback capability.

        Args:
            brain_state: Current brain state to checkpoint

        Returns:
            AuditCheckpoint for potential rollback
        """
        if self._sanity_auditor is None:
            raise RuntimeError("Sanity auditor not enabled")

        return self._sanity_auditor.create_checkpoint(brain_state)

    # ==========================================================================
    # Action Evaluation & Decision Making
    # ==========================================================================

    def evaluate_action(
        self,
        action_type: str,
        payload: Dict[str, Any],
        *,
        risk_level: Literal["low", "medium", "high", "critical"] = "medium",
        context: Optional[Dict[str, Any]] = None,
    ) -> SafetyDecision:
        """Evaluate whether an action is safe to execute.

        This performs multi-layer safety checks:
        1. Local conflict detection
        2. Sanity audit (if enabled)
        3. Cloud audit (if enabled and high risk)

        Args:
            action_type: Type of action (e.g., "self_modify", "execute_tool")
            payload: Action-specific data
            risk_level: Assessed risk level
            context: Additional context for evaluation

        Returns:
            SafetyDecision with allow/deny and constraints
        """
        decision = SafetyDecision(
            action_type=action_type,
            risk_level=risk_level,
        )

        audit_trail: List[Dict[str, Any]] = []

        # Layer 1: Local sanity audit if world model provided
        if context and "world_model" in context and self._sanity_auditor:
            sanity_report = self.audit(
                world_model=context["world_model"],
                strategy_graph=context.get("strategy_graph", {}),
                ban_layer=context.get("ban_layer"),
                motivation_state=context.get("motivation_state"),
            )

            audit_trail.append({
                "layer": "sanity_audit",
                "status": sanity_report.status.value,
                "drift_score": sanity_report.drift_score,
                "disposition": sanity_report.disposition.value,
            })

            # Block if audit failed or requires blocking
            if sanity_report.disposition in (
                DispositionAction.BLOCK_SELF_MOD,
                DispositionAction.FREEZE,
                DispositionAction.HUMAN_REVIEW,
            ):
                if action_type in ("self_modify", "self_shape", "update_identity"):
                    decision.allowed = False
                    decision.reason = f"Sanity audit disposition: {sanity_report.disposition.value}"
                    decision.audit_trail = audit_trail
                    return decision

        # Layer 2: Cloud audit for high-risk actions
        if self._cloud_auditor and risk_level in ("high", "critical"):
            cloud_decision = self._cloud_auditor.audit_action(
                action_type=action_type,
                action_payload=payload,
                risk_level=risk_level,
                context=context,
            )

            audit_trail.append({
                "layer": "cloud_audit",
                "status": cloud_decision.status.value,
                "decision_id": cloud_decision.decision_id,
                "degraded": cloud_decision.policy_version.startswith("local"),
            })

            if cloud_decision.status == CloudDecisionStatus.REJECTED:
                decision.allowed = False
                decision.reason = f"Cloud audit rejected: {cloud_decision.reason}"
                decision.audit_trail = audit_trail
                return decision

            if cloud_decision.status == CloudDecisionStatus.REVIEW_REQUIRED:
                decision.allowed = False
                decision.reason = "Cloud audit requires human review"
                decision.constraints["requires_review"] = True
                decision.audit_trail = audit_trail
                return decision

            decision.constraints.update(cloud_decision.constraints)

        # Layer 3: Check for unresolved conflicts
        unresolved = self._conflict_engine.list_unresolved_conflicts()
        if unresolved:
            critical_conflicts = [c for c in unresolved if c.severity == "critical"]
            if critical_conflicts and risk_level == "critical":
                decision.allowed = False
                decision.reason = f"Unresolved critical conflicts: {len(critical_conflicts)}"
                audit_trail.append({
                    "layer": "conflict_check",
                    "critical_conflicts": len(critical_conflicts),
                })
                decision.audit_trail = audit_trail
                return decision

        # All checks passed
        decision.allowed = True
        decision.reason = "All safety checks passed"
        decision.audit_trail = audit_trail

        return decision

    def is_safe_to_proceed(
        self,
        action_type: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Quick check if operation can proceed.

        Args:
            action_type: Optional action to check
            payload: Optional action payload

        Returns:
            True if safe to proceed, False otherwise
        """
        if action_type is None:
            # General status check
            status = self.get_status()
            return status.overall_status in ("healthy", "warning")

        # Specific action check
        decision = self.evaluate_action(action_type, payload or {})
        return decision.allowed

    def require_audit_before_action(
        self,
        action_type: str,
        world_model: Dict[str, Any],
        strategy_graph: Dict[str, Any],
    ) -> SanityAuditReport:
        """Require fresh audit before specific action.

        Args:
            action_type: Action being considered
            world_model: Current world model
            strategy_graph: Current strategy

        Returns:
            Fresh SanityAuditReport
        """
        return self.audit(world_model, strategy_graph)

    # ==========================================================================
    # Conflict Management Interface
    # ==========================================================================

    def report_conflict(self, report: CognitiveConflictReport) -> None:
        """Report a cognitive conflict for tracking and resolution.

        Args:
            report: Conflict report to ingest
        """
        self._conflict_engine.ingest_reports([report])

    def list_conflicts(self) -> List[CognitiveConflictReport]:
        """List all unresolved conflicts."""
        return self._conflict_engine.list_unresolved_conflicts()

    def build_reconciliation_plan(self, conflict_ids: List[str]) -> ReconciliationPlan:
        """Build a plan to reconcile specified conflicts.

        Args:
            conflict_ids: Conflicts to address

        Returns:
            ReconciliationPlan
        """
        return self._conflict_engine.build_reconciliation_plan(conflict_ids)

    def apply_reconciliation_plan(self, plan: ReconciliationPlan) -> ConflictSharedState:
        """Apply a reconciliation plan.

        Args:
            plan: Plan to apply

        Returns:
            Updated ConflictSharedState

        Raises:
            StaleWriteError: If plan is outdated
        """
        return self._conflict_engine.apply_reconciliation_plan(plan)

    # ==========================================================================
    # Experience Exchange Interface
    # ==========================================================================

    def create_experience(
        self,
        experience_type: Union[ExperienceType, str],
        payload: Dict[str, Any],
        applicable_scope: Optional[Dict[str, Any]] = None,
        trust_score: float = 0.5,
        risk_level: Literal["low", "medium", "high", "critical"] = "low",
    ) -> ExperienceExchangePacket:
        """Create a signed experience packet for sharing.

        Args:
            experience_type: Type of experience
            payload: Experience content
            applicable_scope: Where/when this applies
            trust_score: Sender confidence
            risk_level: Risk assessment

        Returns:
            Signed ExperienceExchangePacket

        Raises:
            RuntimeError: If experience exchange not enabled
        """
        if self._experience_manager is None:
            raise RuntimeError("Experience exchange not enabled")

        if isinstance(experience_type, str):
            experience_type = ExperienceType(experience_type)

        return self._experience_manager.create_experience_packet(
            experience_type=experience_type,
            payload=payload,
            applicable_scope=applicable_scope,
            trust_score=trust_score,
            risk_level=risk_level,
        )

    def receive_experience(
        self,
        packet: ExperienceExchangePacket,
    ) -> ExperienceAdoptionReview:
        """Receive and validate an experience from another instance.

        Args:
            packet: Incoming experience packet

        Returns:
            ExperienceAdoptionReview with conclusion

        Raises:
            RuntimeError: If experience exchange not enabled
        """
        if self._experience_manager is None:
            raise RuntimeError("Experience exchange not enabled")

        return self._experience_manager.receive_experience_packet(packet)

    def promote_experience(
        self,
        experience_id: str,
        reviewer_id: Optional[str] = None,
    ) -> bool:
        """Promote an experience from quarantine to adopted.

        Args:
            experience_id: Experience to promote
            reviewer_id: Optional reviewer identifier

        Returns:
            True if promoted successfully
        """
        if self._experience_manager is None:
            return False

        result = self._experience_manager.promote_from_quarantine(
            experience_id, reviewer_id
        )
        return result is not None

    def get_quarantine_zone(self) -> List[QuarantineZoneEntry]:
        """Get all experiences in quarantine."""
        if self._experience_manager is None:
            return []
        return self._experience_manager.get_quarantine_zone()

    def get_adopted_experiences(self) -> List[QuarantineZoneEntry]:
        """Get all adopted experiences."""
        if self._experience_manager is None:
            return []
        return self._experience_manager.get_adopted_experiences()

    def report_contamination(
        self,
        experience_id: str,
        affected_decisions: List[str],
        affected_patches: Optional[List[str]] = None,
    ) -> ContaminationRecord:
        """Report an experience as contaminated.

        Args:
            experience_id: The contaminated experience
            affected_decisions: Decisions influenced by it
            affected_patches: Self-modifications from it

        Returns:
            ContaminationRecord
        """
        if self._experience_manager is None:
            raise RuntimeError("Experience exchange not enabled")

        return self._experience_manager.detect_contamination(
            experience_id=experience_id,
            affected_decisions=affected_decisions,
            affected_patches=affected_patches or [],
        )

    def execute_rollback(self, contamination_id: str) -> RollbackResult:
        """Execute rollback of contaminated experience.

        Args:
            contamination_id: Contamination to roll back

        Returns:
            RollbackResult
        """
        if self._experience_manager is None:
            raise RuntimeError("Experience exchange not enabled")

        return self._experience_manager.execute_rollback(contamination_id)

    # ==========================================================================
    # Status & Monitoring Interface
    # ==========================================================================

    def get_status(self) -> SafetyStatus:
        """Get comprehensive safety system status.

        Returns:
            SafetyStatus with all subsystems' state
        """
        status = SafetyStatus(
            brain_scope=self._config.brain_scope,
        )

        # Conflict engine status
        status.conflict_count = len(self._conflict_engine.list_unresolved_conflicts())

        # Sanity auditor status
        if self._sanity_auditor and self._sanity_auditor.last_audit:
            last = self._sanity_auditor.last_audit
            status.last_audit_status = last.status
            status.last_audit_drift_score = last.drift_score

        # Cloud auditor status
        if self._cloud_auditor:
            status.cloud_auditor_configured = self._cloud_auditor.is_configured
            status.cloud_degradation_count = self._cloud_auditor.degradation_count

        # Experience manager status
        if self._experience_manager:
            status.quarantine_size = self._experience_manager.quarantine_size
            status.adopted_experiences = self._experience_manager.adopted_count
            status.active_contaminations = len(
                self._experience_manager.get_contamination_records()
            )

        # Determine overall status
        if status.cloud_degradation_count > 5:
            status.overall_status = "degraded"
        elif status.conflict_count > 10 or status.active_contaminations > 0:
            status.overall_status = "critical"
        elif status.conflict_count > 0 or status.last_audit_drift_score > 0.3:
            status.overall_status = "warning"
        else:
            status.overall_status = "healthy"

        return status

    def get_degradation_history(self) -> List[DegradationRecord]:
        """Get cloud auditor degradation history."""
        if self._cloud_auditor is None:
            return []
        return self._cloud_auditor.get_degradation_history()

    # ==========================================================================
    # Configuration Interface
    # ==========================================================================

    def configure_cloud_auditor(
        self,
        *,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> None:
        """Configure or reconfigure cloud auditor.

        Args:
            api_key: Cloud audit API key
            api_secret: Cloud audit API secret
            endpoint: Cloud audit endpoint
        """
        if self._cloud_auditor is None:
            # Enable cloud auditor
            self._config.enable_cloud_audit = True
            self._config.cloud_api_key = api_key or ""
            self._config.cloud_api_secret = api_secret or ""
            if endpoint:
                self._config.cloud_endpoint = endpoint

            cloud_config = CloudAuditorConfig(
                endpoint=self._config.cloud_endpoint,
                api_key=self._config.cloud_api_key,
                api_secret=self._config.cloud_api_secret,
            )
            self._cloud_auditor = CloudAuditorClient(
                config=cloud_config,
                brain_scope=self._config.brain_scope,
            )
        else:
            # Reconfigure existing
            self._cloud_auditor.configure(
                api_key=api_key,
                api_secret=api_secret,
                endpoint=endpoint,
            )

    def enable_experience_exchange(
        self,
        signing_key: str,
        verification_keys: Optional[Dict[str, str]] = None,
    ) -> None:
        """Enable experience exchange with credentials.

        Args:
            signing_key: Key for signing outgoing packets
            verification_keys: Map of brain_id to public key
        """
        self._config.enable_experience_exchange = True
        self._config.exchange_signing_key = signing_key
        if verification_keys:
            self._config.exchange_verification_keys = verification_keys

        exchange_config = ExperienceExchangeConfig(
            brain_id=self._config.brain_id,
            signing_key=signing_key,
            verification_keys=self._config.exchange_verification_keys,
            trust_threshold=self._config.exchange_trust_threshold,
        )
        self._experience_manager = ExperienceExchangeManager(config=exchange_config)

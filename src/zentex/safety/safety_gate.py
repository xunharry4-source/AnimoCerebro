from __future__ import annotations
"""Safety Gate (G12) - Autonomous Safety and Alignment Guardrails

## File Purpose
This file implements the G12 SafetyGate for Zentex, providing non-bypassable safety
validation for all high-risk actions. It ensures that any deletion, overwrite, privilege
escalation, or identity-related operations must pass strict safety validation before execution.

## Major Responsibilities
- **RedLineAction Validation**: Validates high-risk actions against identity kernel redlines
- **Non-Bypassable Constraints**: Enforces constraints that cannot be circumvented through aliases, batching, or rewrapping
- **Dual Confirmation Flow**: Implements mandatory dual confirmation for critical-risk actions
- **Bypass Interception**: Detects and blocks attempts to bypass safety through aliasing, batch splitting, or secondary encapsulation
- **Identity Write Protection**: Special protection category for all identity-related write operations
- **Replanning Feedback**: Provides structured feedback to goal generator when actions are blocked
- **Audit Trail**: All safety decisions are logged with complete traceability

## Responsibility Boundaries
- **Responsible for**: Validating action parameters against redlines, enforcing non-bypassable constraints,
  coordinating with cloud audit for high-risk actions, providing structured rejection feedback
- **Not Responsible for**: Making policy decisions about what constitutes risk, implementing actual execution
  of actions, modifying identity kernel directly
- **Input Dependencies**: Action types, payloads, risk classifications, identity kernel redlines,
  cloud audit decisions
- **Output Guarantees**: Structured safety decisions with clear allow/deny status, detailed rejection reasons,
  complete audit trails

## Key Design Principles
- **Fail-Closed Operation**: Any validation failure or missing dependency results in blocking behavior
- **Non-Bypassable**: Constraints are enforced at multiple levels to prevent circumvention
- **Parameter-Level Validation**: Validates actual execution parameters, not abstract intentions
- **Explicit Rejection**: All rejections include detailed reasons and guidance for replanning
- **Zentex Compliance**: Strictly follows Zentex engineering redlines and fail-closed requirements

Based on Zentex Product Document Function 8 (G12)
"""


import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Set
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Action risk levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SafetyDecisionStatus(str, Enum):
    """Safety gate decision status."""
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    REQUIRES_CLOUD_AUDIT = "requires_cloud_audit"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


class RedLineCategory(str, Enum):
    """Categories of redline (forbidden) actions."""
    DATA_DESTRUCTION = "data_destruction"           # Delete, overwrite, corrupt data
    PRIVILEGE_ESCALATION = "privilege_escalation"   # Escalate permissions, bypass auth
    SECURITY_DOWNGRADE = "security_downgrade"       # Disable firewalls, weaken security
    IDENTITY_WRITE = "identity_write"               # Modify identity kernel, core constraints
    RESOURCE_EXHAUSTION = "resource_exhaustion"       # Exhaust resources, cause DoS
    EXTERNAL_LEAKAGE = "external_leakage"           # Leak data to unauthorized external


class RedLineAction(BaseModel):
    """Definition of a redline (high-risk) action.

    Fields:
        action_type: Type of action that triggers redline review
        category: Red line category for this action
        description: Human-readable description of the risk
        non_bypassable_constraints: Constraints that cannot be circumvented
        requires_dual_confirmation: Whether action requires dual confirmation
        requires_cloud_audit: Whether action requires cloud audit
        requires_human_review: Whether action always requires human review
    """
    model_config = ConfigDict(extra="forbid")

    action_type: str = Field(min_length=1)
    category: RedLineCategory
    description: str = Field(min_length=1)
    non_bypassable_constraints: List[str] = Field(default_factory=list)
    requires_dual_confirmation: bool = False
    requires_cloud_audit: bool = False
    requires_human_review: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BypassAttemptType(str, Enum):
    """Types of bypass attempts that can be detected."""
    ALIAS_CALL = "alias_call"                           # Using different name for same action
    BATCH_SPLIT = "batch_split"                       # Splitting action into smaller pieces
    REWRAPPED = "rewrapped"                           # Wrapping in indirect container
    INDIRECT_TRIGGER = "indirect_trigger"             # Triggering through side effects
    ENCODED_PAYLOAD = "encoded_payload"               # Encoding to hide true nature


class DetectedBypassAttempt(BaseModel):
    """Record of a detected bypass attempt.

    Fields:
        attempt_id: Unique attempt identifier
        attempt_type: Type of bypass attempt detected
        original_action: The action being attempted
        detected_method: How the bypass was detected
        confidence: Confidence score (0.0 to 1.0)
    """
    model_config = ConfigDict(extra="forbid")

    attempt_id: str = Field(default_factory=lambda: str(uuid4()))
    attempt_type: BypassAttemptType
    original_action: str
    detected_method: str
    confidence: float = Field(ge=0.0, le=1.0)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SafetyGateDecision(BaseModel):
    """Safety gate decision for an action.

    Fields:
        decision_id: Unique decision identifier
        action_type: Type of action evaluated
        action_payload: The actual execution parameters (not abstract intent)
        status: Decision status
        allowed: Whether action is permitted to proceed
        reason: Human-readable decision explanation
        risk_level: Assessed risk level
        redline_category: Red line category if applicable
        bypass_attempts: Detected bypass attempts
        constraints: Additional constraints if allowed
        requires_confirmation_from: Who must confirm (if dual confirmation needed)
        audit_trail: Complete decision audit trail
        replanning_feedback: Structured feedback for goal generator if blocked
    """
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: str = Field(min_length=1)
    action_payload: Dict[str, Any] = Field(default_factory=dict)
    status: SafetyDecisionStatus = SafetyDecisionStatus.BLOCKED
    allowed: bool = False
    reason: str = Field(default="")
    risk_level: RiskLevel = RiskLevel.LOW
    redline_category: Optional[RedLineCategory] = None
    bypass_attempts: List[DetectedBypassAttempt] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    requires_confirmation_from: Optional[str] = None
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)
    replanning_feedback: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReplanningFeedback(BaseModel):
    """Structured feedback for goal generator when action is blocked.

    Fields:
        blocked_action: The action that was blocked
        block_reason: Why it was blocked
        suggested_alternatives: Alternative approaches to achieve goal
        required_modifications: What would need to change for approval
        escalation_path: How to escalate to human if needed
    """
    model_config = ConfigDict(extra="forbid")

    blocked_action: str
    block_reason: str
    suggested_alternatives: List[str] = Field(default_factory=list)
    required_modifications: List[str] = Field(default_factory=list)
    escalation_path: Optional[str] = None


class SafetyGateConfig(BaseModel):
    """Configuration for SafetyGate.

    Fields:
        brain_scope: Identifier for this brain instance
        enable_bypass_detection: Enable bypass attempt detection
        enable_dual_confirmation: Enable dual confirmation for critical actions
        require_cloud_audit_for_critical: Require cloud audit for critical risk
        identity_kernel_redlines: List of actions forbidden by identity kernel
        custom_redlines: Additional custom redline definitions
        alias_mappings: Known aliases for redline actions
    """
    model_config = ConfigDict(extra="forbid")

    brain_scope: str = Field(default="zentex.runtime")
    enable_bypass_detection: bool = Field(default=True)
    enable_dual_confirmation: bool = Field(default=True)
    require_cloud_audit_for_critical: bool = Field(default=True)
    identity_kernel_redlines: List[str] = Field(default_factory=list)
    custom_redlines: List[RedLineAction] = Field(default_factory=list)
    alias_mappings: Dict[str, List[str]] = Field(default_factory=dict)


class SafetyGate:
    """G12 Safety Gate - Autonomous safety and alignment guardrails.

    The SafetyGate provides non-bypassable safety validation for all high-risk
    actions in Zentex. It ensures:

    1. All high-risk actions pass through unskippable validation
    2. Redline actions (delete, overwrite, privilege escalation) require extra scrutiny
    3. Identity-related writes have special protection category
    4. Bypass attempts through aliasing, batching, or rewrapping are detected and blocked
    5. Blocked actions provide structured feedback for replanning
    6. All decisions are fully auditable

    Hard Redlines:
    - SafetyGate validation object must be actual execution parameters, not abstract intent
    - Main brain real execution stage fails if it hasn't passed SafetyGate
    - High-risk actions missing cloud audit approval cannot enter real execution
    - All rejections are logged to audit trail
    - Non-bypassable constraints are enforced at multiple validation layers
    """

    # Default redline definitions based on product requirements
    DEFAULT_REDLINES: List[RedLineAction] = [
        RedLineAction(
            action_type="delete_file",
            category=RedLineCategory.DATA_DESTRUCTION,
            description="File deletion operation",
            non_bypassable_constraints=["require_backup_confirmation", "log_pre_delete_state"],
            requires_dual_confirmation=True,
        ),
        RedLineAction(
            action_type="overwrite_file",
            category=RedLineCategory.DATA_DESTRUCTION,
            description="File overwrite operation",
            non_bypassable_constraints=["require_backup_confirmation", "preserve_history"],
            requires_dual_confirmation=True,
        ),
        RedLineAction(
            action_type="delete_backup",
            category=RedLineCategory.DATA_DESTRUCTION,
            description="Backup deletion - critical data protection",
            non_bypassable_constraints=["require_multi_approval", "verify_retention_policy"],
            requires_dual_confirmation=True,
            requires_cloud_audit=True,
            requires_human_review=True,
        ),
        RedLineAction(
            action_type="modify_api_key",
            category=RedLineCategory.PRIVILEGE_ESCALATION,
            description="API key modification",
            non_bypassable_constraints=["verify_key_rotation_policy", "audit_all_access"],
            requires_dual_confirmation=True,
            requires_cloud_audit=True,
        ),
        RedLineAction(
            action_type="disable_firewall",
            category=RedLineCategory.SECURITY_DOWNGRADE,
            description="Firewall disable operation",
            non_bypassable_constraints=["require_emergency_authorization", "time_limited"],
            requires_dual_confirmation=True,
            requires_human_review=True,
        ),
        RedLineAction(
            action_type="update_identity_kernel",
            category=RedLineCategory.IDENTITY_WRITE,
            description="Identity kernel modification - highest protection",
            non_bypassable_constraints=[
                "require_identity_continuity_check",
                "require_human_authorization",
                "verify_signature_chain",
            ],
            requires_dual_confirmation=True,
            requires_cloud_audit=True,
            requires_human_review=True,
        ),
        RedLineAction(
            action_type="modify_core_constraints",
            category=RedLineCategory.IDENTITY_WRITE,
            description="Core constraint modification",
            non_bypassable_constraints=[
                "require_continuity_verification",
                "require_human_authorization",
            ],
            requires_dual_confirmation=True,
            requires_cloud_audit=True,
            requires_human_review=True,
        ),
        RedLineAction(
            action_type="self_modify",
            category=RedLineCategory.IDENTITY_WRITE,
            description="Self-modification operation",
            non_bypassable_constraints=[
                "require_sanity_audit_pass",
                "require_identity_continuity_check",
            ],
            requires_dual_confirmation=True,
            requires_cloud_audit=True,
        ),
    ]

    # Known aliases for bypass detection
    DEFAULT_ALIASES: Dict[str, List[str]] = {
        "delete_file": ["remove_file", "unlink", "rm", "erase", "destroy_file"],
        "overwrite_file": ["replace_file", "write_file", "save_over", "truncate_write"],
        "delete_backup": ["clean_backup", "purge_backup", "remove_history", "clear_archive"],
        "modify_api_key": ["update_key", "rotate_key", "change_credentials", "renew_token"],
        "disable_firewall": ["stop_firewall", "pause_security", "allow_all", "open_ports"],
        "update_identity_kernel": ["modify_identity", "change_core", "update_self", "rewrite_kernel"],
        "self_modify": ["self_update", "auto_patch", "self_shape", "evolve"],
    }

    def __init__(
        self,
        config: Optional[SafetyGateConfig] = None,
        identity_kernel: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._config = config or SafetyGateConfig()
        self._identity_kernel = identity_kernel or {}
        self._redlines: Dict[str, RedLineAction] = {}
        self._alias_map: Dict[str, str] = {}  # alias -> canonical action_type
        self._audit_log: List[SafetyGateDecision] = []
        self._pending_confirmations: Dict[str, SafetyGateDecision] = {}

        # Initialize redlines
        self._initialize_redlines()

    def _initialize_redlines(self) -> None:
        """Initialize redline definitions and alias mappings."""
        # Load default redlines
        for redline in self.DEFAULT_REDLINES:
            self._redlines[redline.action_type] = redline

        # Load custom redlines
        for redline in self._config.custom_redlines:
            self._redlines[redline.action_type] = redline

        # Initialize alias mappings
        alias_mappings = {**self.DEFAULT_ALIASES, **self._config.alias_mappings}
        for canonical, aliases in alias_mappings.items():
            for alias in aliases:
                self._alias_map[alias] = canonical

    @property
    def brain_scope(self) -> str:
        """Get the brain scope identifier."""
        return self._config.brain_scope

    @property
    def redline_count(self) -> int:
        """Get number of defined redlines."""
        return len(self._redlines)

    def validate_action(
        self,
        action_type: str,
        action_payload: Dict[str, Any],
        risk_level: Optional[RiskLevel] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> SafetyGateDecision:
        """Validate an action through the SafetyGate.

        This is the main entry point for safety validation. It performs:
        1. Redline detection and categorization
        2. Bypass attempt detection
        3. Identity kernel redline enforcement
        4. Risk level assessment
        5. Constraint validation
        6. Dual confirmation requirement determination

        Args:
            action_type: Type of action being validated
            action_payload: Actual execution parameters (not abstract intent)
            risk_level: Assessed risk level (will be determined if not provided)
            context: Additional context for validation

        Returns:
            SafetyGateDecision with allow/deny status and constraints

        Hard Redline: Must validate actual execution parameters, not abstract intent
        """
        audit_trail: List[Dict[str, Any]] = []
        bypass_attempts: List[DetectedBypassAttempt] = []

        # Step 1: Check for alias bypass attempts
        canonical_action = self._resolve_action_type(action_type)
        if canonical_action != action_type:
            bypass_attempts.append(DetectedBypassAttempt(
                attempt_type=BypassAttemptType.ALIAS_CALL,
                original_action=action_type,
                detected_method=f"Resolved alias: {action_type} -> {canonical_action}",
                confidence=1.0,
            ))
            audit_trail.append({
                "step": "alias_detection",
                "original_action": action_type,
                "canonical_action": canonical_action,
            })
            action_type = canonical_action

        # Step 2: Detect other bypass attempts in payload
        if self._config.enable_bypass_detection:
            detected = self._detect_bypass_attempts(action_type, action_payload)
            bypass_attempts.extend(detected)
            if detected:
                audit_trail.append({
                    "step": "bypass_detection",
                    "attempts_found": len(detected),
                    "attempt_types": [a.attempt_type.value for a in detected],
                })

        # Step 3: Check if action is a redline
        redline = self._redlines.get(action_type)
        if redline:
            audit_trail.append({
                "step": "redline_check",
                "is_redline": True,
                "category": redline.category.value,
                "constraints": redline.non_bypassable_constraints,
            })

        # Step 4: Check identity kernel redlines
        identity_violation = self._check_identity_kernel_redlines(action_type, action_payload)
        if identity_violation:
            audit_trail.append({
                "step": "identity_kernel_check",
                "violation": identity_violation,
            })

        # Step 5: Determine risk level
        if risk_level is None:
            risk_level = self._assess_risk_level(action_type, action_payload, redline is not None)

        audit_trail.append({
            "step": "risk_assessment",
            "risk_level": risk_level.value,
        })

        # Step 6: Determine if bypass attempts block action
        if bypass_attempts and any(a.confidence > 0.7 for a in bypass_attempts):
            # High-confidence bypass attempt detected - block and alert
            feedback = ReplanningFeedback(
                blocked_action=action_type,
                block_reason=f"Bypass attempt detected: {[a.attempt_type.value for a in bypass_attempts if a.confidence > 0.7]}",
                suggested_alternatives=["Use canonical action name", "Request explicit authorization"],
                required_modifications=["Remove bypass techniques", "Use direct action invocation"],
                escalation_path="Contact system administrator if action is legitimate",
            )

            decision = SafetyGateDecision(
                action_type=action_type,
                action_payload=action_payload,
                status=SafetyDecisionStatus.BLOCKED,
                allowed=False,
                reason=f"Bypass attempt detected: {[a.attempt_type.value for a in bypass_attempts if a.confidence > 0.7]}",
                risk_level=risk_level,
                redline_category=redline.category if redline else None,
                bypass_attempts=bypass_attempts,
                audit_trail=audit_trail,
                replanning_feedback=feedback.model_dump(),
            )
            self._audit_log.append(decision)
            return decision

        # Step 7: Determine decision based on redlines and risk
        if redline and redline.requires_human_review:
            # Human review required for this redline
            feedback = ReplanningFeedback(
                blocked_action=action_type,
                block_reason=f"Action requires human review: {redline.description}",
                suggested_alternatives=["Submit for human review", "Use lower-risk alternative"],
                required_modifications=["Obtain human authorization"],
                escalation_path="Submit to human review queue",
            )

            decision = SafetyGateDecision(
                action_type=action_type,
                action_payload=action_payload,
                status=SafetyDecisionStatus.REQUIRES_HUMAN_REVIEW,
                allowed=False,
                reason=f"Redline action requires human review: {redline.description}",
                risk_level=RiskLevel.CRITICAL,
                redline_category=redline.category,
                bypass_attempts=bypass_attempts,
                constraints={"requires_human_review": True, "redline": redline.model_dump()},
                audit_trail=audit_trail,
                replanning_feedback=feedback.model_dump(),
            )
            self._audit_log.append(decision)
            return decision

        if redline and redline.requires_cloud_audit:
            # Cloud audit required
            decision = SafetyGateDecision(
                action_type=action_type,
                action_payload=action_payload,
                status=SafetyDecisionStatus.REQUIRES_CLOUD_AUDIT,
                allowed=False,
                reason=f"Redline action requires cloud audit: {redline.description}",
                risk_level=risk_level,
                redline_category=redline.category,
                bypass_attempts=bypass_attempts,
                constraints={"requires_cloud_audit": True, "redline": redline.model_dump()},
                audit_trail=audit_trail,
            )
            self._audit_log.append(decision)
            return decision

        if redline and redline.requires_dual_confirmation:
            # Dual confirmation required
            decision = SafetyGateDecision(
                action_type=action_type,
                action_payload=action_payload,
                status=SafetyDecisionStatus.REQUIRES_CONFIRMATION,
                allowed=False,
                reason=f"Redline action requires dual confirmation: {redline.description}",
                risk_level=risk_level,
                redline_category=redline.category,
                bypass_attempts=bypass_attempts,
                constraints={"requires_dual_confirmation": True, "redline": redline.model_dump()},
                requires_confirmation_from="human_operator",
                audit_trail=audit_trail,
            )
            self._pending_confirmations[decision.decision_id] = decision
            self._audit_log.append(decision)
            return decision

        if identity_violation:
            # Identity kernel violation - always block
            feedback = ReplanningFeedback(
                blocked_action=action_type,
                block_reason=f"Identity kernel redline violation: {identity_violation}",
                suggested_alternatives=["Request identity modification through proper channels"],
                required_modifications=["Remove identity-modifying operations"],
                escalation_path="Contact identity administrator",
            )

            decision = SafetyGateDecision(
                action_type=action_type,
                action_payload=action_payload,
                status=SafetyDecisionStatus.BLOCKED,
                allowed=False,
                reason=f"Identity kernel redline violation: {identity_violation}",
                risk_level=RiskLevel.CRITICAL,
                redline_category=RedLineCategory.IDENTITY_WRITE,
                bypass_attempts=bypass_attempts,
                audit_trail=audit_trail,
                replanning_feedback=feedback.model_dump(),
            )
            self._audit_log.append(decision)
            return decision

        # Step 8: High-risk actions require cloud audit
        if risk_level == RiskLevel.CRITICAL and self._config.require_cloud_audit_for_critical:
            decision = SafetyGateDecision(
                action_type=action_type,
                action_payload=action_payload,
                status=SafetyDecisionStatus.REQUIRES_CLOUD_AUDIT,
                allowed=False,
                reason="Critical risk action requires cloud audit approval",
                risk_level=risk_level,
                redline_category=redline.category if redline else None,
                bypass_attempts=bypass_attempts,
                constraints={"requires_cloud_audit": True},
                audit_trail=audit_trail,
            )
            self._audit_log.append(decision)
            return decision

        # All checks passed - allow action
        constraints = {}
        if redline:
            constraints["non_bypassable_constraints"] = redline.non_bypassable_constraints

        decision = SafetyGateDecision(
            action_type=action_type,
            action_payload=action_payload,
            status=SafetyDecisionStatus.ALLOWED,
            allowed=True,
            reason="All safety checks passed",
            risk_level=risk_level,
            redline_category=redline.category if redline else None,
            bypass_attempts=bypass_attempts,
            constraints=constraints,
            audit_trail=audit_trail,
        )
        self._audit_log.append(decision)
        return decision

    def confirm_action(
        self,
        decision_id: str,
        confirmed_by: str,
        confirmation_context: Optional[Dict[str, Any]] = None,
    ) -> SafetyGateDecision:
        """Confirm a pending action that requires dual confirmation.

        Args:
            decision_id: The decision to confirm
            confirmed_by: Who is confirming the action
            confirmation_context: Additional context for confirmation

        Returns:
            Updated SafetyGateDecision

        Raises:
            ValueError: If decision_id not found or not pending confirmation
        """
        pending = self._pending_confirmations.get(decision_id)
        if not pending:
            raise ValueError(f"No pending confirmation found for decision {decision_id}")

        # Create new decision with confirmation
        new_decision = SafetyGateDecision(
            action_type=pending.action_type,
            action_payload=pending.action_payload,
            status=SafetyDecisionStatus.ALLOWED,
            allowed=True,
            reason=f"Confirmed by {confirmed_by}. Original requirement: {pending.reason}",
            risk_level=pending.risk_level,
            redline_category=pending.redline_category,
            bypass_attempts=pending.bypass_attempts,
            constraints={
                **pending.constraints,
                "confirmed_by": confirmed_by,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
                "confirmation_context": confirmation_context or {},
            },
            audit_trail=[
                *pending.audit_trail,
                {
                    "step": "dual_confirmation",
                    "confirmed_by": confirmed_by,
                    "confirmed_at": datetime.now(timezone.utc).isoformat(),
                },
            ],
        )

        # Remove from pending and add to audit log
        del self._pending_confirmations[decision_id]
        self._audit_log.append(new_decision)

        return new_decision

    def add_redline(self, redline: RedLineAction) -> None:
        """Add a custom redline action definition.

        Args:
            redline: Redline definition to add
        """
        self._redlines[redline.action_type] = redline

    def remove_redline(self, action_type: str) -> Optional[RedLineAction]:
        """Remove a redline definition.

        Args:
            action_type: Action type to remove from redlines

        Returns:
            The removed redline if it existed, None otherwise
        """
        return self._redlines.pop(action_type, None)

    def get_audit_log(
        self,
        action_type: Optional[str] = None,
        status: Optional[SafetyDecisionStatus] = None,
        since: Optional[datetime] = None,
    ) -> List[SafetyGateDecision]:
        """Get audit log with optional filtering.

        Args:
            action_type: Filter by action type
            status: Filter by decision status
            since: Filter by timestamp

        Returns:
            Filtered list of safety decisions
        """
        results = self._audit_log

        if action_type:
            results = [d for d in results if d.action_type == action_type]

        if status:
            results = [d for d in results if d.status == status]

        if since:
            results = [d for d in results if d.created_at >= since]

        return results

    def _resolve_action_type(self, action_type: str) -> str:
        """Resolve action type, detecting aliases."""
        return self._alias_map.get(action_type, action_type)

    def _detect_bypass_attempts(
        self,
        action_type: str,
        action_payload: Dict[str, Any],
    ) -> List[DetectedBypassAttempt]:
        """Detect various bypass attempts in the action payload."""
        attempts: List[DetectedBypassAttempt] = []

        # Check for batch split patterns
        if self._is_batch_split_attempt(action_payload):
            attempts.append(DetectedBypassAttempt(
                attempt_type=BypassAttemptType.BATCH_SPLIT,
                original_action=action_type,
                detected_method="Multiple similar operations detected in sequence",
                confidence=0.8,
            ))

        # Check for rewrapped payload
        if self._is_rewrapped_payload(action_payload):
            attempts.append(DetectedBypassAttempt(
                attempt_type=BypassAttemptType.REWRAPPED,
                original_action=action_type,
                detected_method="Action nested in wrapper structure",
                confidence=0.75,
            ))

        # Check for encoded/encrypted payload hiding true nature
        if self._is_encoded_payload(action_payload):
            attempts.append(DetectedBypassAttempt(
                attempt_type=BypassAttemptType.ENCODED_PAYLOAD,
                original_action=action_type,
                detected_method="Encoded or encrypted payload detected",
                confidence=0.6,
            ))

        return attempts

    def _is_batch_split_attempt(self, payload: Dict[str, Any]) -> bool:
        """Detect if payload represents a batch split bypass attempt."""
        # Check for batch markers or multiple sub-operations
        operations = payload.get("operations", [])
        if isinstance(operations, list) and len(operations) > 5:
            # Large batch of similar operations might be split bypass
            op_types = [op.get("type") for op in operations if isinstance(op, dict)]
            if len(set(op_types)) == 1:
                return True
        return False

    def _is_rewrapped_payload(self, payload: Dict[str, Any]) -> bool:
        """Detect if payload is rewrapped to hide true nature."""
        # Check for deeply nested wrapper structures
        if "wrapper" in payload or "container" in payload:
            inner = payload.get("wrapper") or payload.get("container")
            if isinstance(inner, dict) and ("action" in inner or "operation" in inner):
                return True
        return False

    def _is_encoded_payload(self, payload: Dict[str, Any]) -> bool:
        """Detect if payload uses encoding or obfuscation to obscure content.
        
        Policy: Fail-Closed. Any high-entropy or binary-wrapped payload is flagged.
        """
        # 1. Check for explicit obfuscation markers in keys OR values
        obfuscation_keywords = {"encoded", "encrypted", "base64", "obfuscated", "hex", "secret", "hidden"}
        
        def _scan(data: Any) -> bool:
            if isinstance(data, dict):
                for k, v in data.items():
                    if any(kw in str(k).lower() for kw in obfuscation_keywords):
                        return True
                    if _scan(v):
                        return True
            elif isinstance(data, list):
                return any(_scan(i) for i in data)
            elif isinstance(data, str):
                # Structural density check: detect suspicious encoding patterns
                if any(kw in data.lower() for kw in obfuscation_keywords):
                    return True
                # Detect non-human readable high-entropy strings (e.g. data: URI or large base64)
                if len(data) > 100 and not any(c in data for c in " \n\t"):
                     return True
            return False

        return _scan(payload)

    def _check_identity_kernel_redlines(
        self,
        action_type: str,
        action_payload: Dict[str, Any],
    ) -> Optional[str]:
        """Check if action violates identity kernel redlines using canonical paths.
        
        Hard Redline: Protecting the 'Self' from unauthorized modification.
        """
        identity_redlines = self._config.identity_kernel_redlines or [
            "update_identity_kernel",
            "modify_core_constraints",
            "tamper_continuity_lock",
            "violate_self_binding",
        ]

        if action_type in identity_redlines:
            return f"Action '{action_type}' is a restricted identity-kernel operation."

        # Authentic Path-Based Verification
        # Check for writes to core identity assets
        target = str(action_payload.get("target", action_payload.get("path", ""))).lower()
        
        PROTECTED_PATHS = [
            ".zentex/identity/",
            "config/identity",
            "src/zentex/kernel/",
            "src/zentex/foundation/meta.py",
            ".zentex/continuity_lock"
        ]
        
        for protected in PROTECTED_PATHS:
            if protected in target:
                logger.critical(f"IDENTITY PROTECTION BREACH: Action {action_type} attempted to modify protected path: {target}")
                return f"Unauthorized write attempt to protected identity asset: {target}"

        return None

    def _assess_risk_level(
        self,
        action_type: str,
        action_payload: Dict[str, Any],
        is_redline: bool,
    ) -> RiskLevel:
        """Assess the risk level of an action with Fail-Closed defaults.
        
        Policy: Any unknown action with IO side-effects is HIGH risk.
        """
        if is_redline:
            return RiskLevel.HIGH

        # 1. IO Intensity Assessment
        io_keywords = ["write", "delete", "rm", "send", "post", "execute", "run"]
        if action_type in io_keywords or any(k in action_type for k in io_keywords):
            return RiskLevel.HIGH

        # 2. Structural Risk (e.g. scripts, command lines)
        payload_str = str(action_payload).lower()
        if "command" in payload_str or "script" in payload_str or "exec" in payload_str:
            return RiskLevel.HIGH

        # 3. Payload-level danger flags
        if action_payload.get("irreversible", False):
            return RiskLevel.HIGH

        if action_payload.get("affects_system_state", False):
            return RiskLevel.MEDIUM

        # 4. Default for unknown operations
        if action_type not in ["read_file", "list_dir", "get_status", "search_web"]:
            return RiskLevel.MEDIUM

        # Standard redline: do not leave dead risk-classification fragments behind
        # after refactors. That kind of fake implementation can make safety checks
        # look complete in tests while real runtime branches are never executed.
        return RiskLevel.LOW


class SafetyGateException(Exception):
    """Base exception for SafetyGate errors."""


class RedLineViolation(SafetyGateException):
    """Raised when a redline is violated."""


class BypassDetected(SafetyGateException):
    """Raised when a bypass attempt is detected with high confidence."""

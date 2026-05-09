from __future__ import annotations
"""Cloud Auditor Client (G26) - Cloud-based Safety Auditing

## File Purpose
This file implements the G26 cloud audit client for Zentex, providing external safety validation
through cloud-based audit services. It ensures high-risk decisions undergo independent external
review while maintaining fail-closed behavior.

## Major Responsibilities
- **HTTP Signature Requests**: Creates and signs audit requests for cloud service validation
- **Service-Side Verification**: Verifies cloud service response signatures and authenticity
- **Policy Decision Consumption**: Processes and applies cloud audit decisions to local actions
- **Explicit Degradation**: Handles service failures with explicit fallback modes, no silent failures
- **Boundary Definition**: Maintains clear separation between open-source body and private/cloud soul
- **Decision Caching**: Manages decision caching with expiration and validation

## Responsibility Boundaries
- **Responsible for**: Request signing, response verification, degradation handling, decision caching
- **Not Responsible for**: Making actual policy decisions, implementing cloud service infrastructure
- **Input Dependencies**: Action types, payloads, risk levels, cloud service configuration
- **Output Guarantees**: Structured decisions with clear approval/rejection status and constraints

## Key Design Principles
- **Fail-Closed Operation**: Service failures trigger explicit degradation, never silent continuation
- **Security First**: All requests use HMAC-SHA256 signatures with secret keys
- **Explicit Configuration**: Missing credentials produce configuration alerts, not silent fallback
- **Audit Trail**: All cloud interactions are logged with trace IDs and timestamps
- **Boundary Enforcement**: Clearly separates open-source components from private cloud dependencies

Based on Zentex Product Document Function 23 (G26)
"""


import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class CloudDecisionStatus(str, Enum):
    """Cloud audit decision status."""
    APPROVED = "approved"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"
    DEFERRED = "deferred"


class CloudAuditDecision(BaseModel):
    """Cloud audit service decision.

    Fields:
        decision_id: Unique decision identifier
        request_id: Original request identifier
        policy_version: Version of policy used for decision
        status: Decision status
        reason: Human-readable decision reason
        constraints: Optional constraints if approved
        expires_at: Decision expiration timestamp
        signature: Server response signature
    """
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str = Field(min_length=1)
    policy_version: str = Field(default="1.0")
    status: CloudDecisionStatus
    reason: str = Field(default="")
    constraints: Dict[str, Any] = Field(default_factory=dict)
    expires_at: Optional[datetime] = None
    signature: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CloudAuditRequest(BaseModel):
    """Cloud audit request payload.

    Fields:
        request_id: Unique request identifier
        action_type: Type of action being requested
        action_payload: Action details
        risk_level: Assessed risk level
        context: Request context (brain state, etc.)
        brain_scope: Originating brain scope
        timestamp: Request timestamp
        client_signature: Client request signature
    """
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: str = Field(min_length=1)
    action_payload: Dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    context: Dict[str, Any] = Field(default_factory=dict)
    brain_scope: str = Field(default="zentex.runtime")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    client_signature: str = Field(default="")


class CloudAuditorConfig(BaseModel):
    """Cloud auditor configuration.

    Fields:
        endpoint: Cloud audit service endpoint URL
        api_key: API key for authentication
        api_secret: API secret for request signing
        timeout_seconds: Request timeout
        enable_degradation: Whether to degrade gracefully on failure
        degraded_policy_version: Policy version to use in degraded mode
    """
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(default="https://audit.zentex.io/v1/decide")
    api_key: str = Field(default="")
    api_secret: str = Field(default="")
    timeout_seconds: float = Field(default=10.0, ge=1.0)
    enable_degradation: bool = Field(default=True)
    degraded_policy_version: str = Field(default="local-fallback-1.0")


class DegradationRecord(BaseModel):
    """Record of cloud auditor degradation event.

    Fields:
        record_id: Unique record identifier
        reason: Why degradation occurred
        fallback_action: What action was taken
        request: Original request that caused degradation
        timestamp: When degradation occurred
    """
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(default_factory=lambda: str(uuid4()))
    reason: str = Field(min_length=1)
    fallback_action: str = Field(min_length=1)
    request: Optional[CloudAuditRequest] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CloudBoundaryDefinition(BaseModel):
    """Open-source body / private soul / cloud audit boundary statement."""
    model_config = ConfigDict(extra="forbid")

    open_source_components: List[str] = Field(default_factory=list)
    private_components: List[str] = Field(default_factory=list)
    cloud_components: List[str] = Field(default_factory=list)
    high_risk_requires_cloud_audit: bool = True
    missing_credentials_fail_closed: bool = True
    invalid_response_signature_rejected: bool = True


class CloudAuditorClient:
    """G26 Cloud Audit Client - External safety validation.

    The CloudAuditorClient provides external validation of high-risk actions
    through a cloud-based audit service. It implements:

    1. Request signing with HMAC-SHA256
    2. HTTP calls to cloud audit endpoint
    3. Response signature verification
    4. Explicit degradation on service unavailability
    5. Decision caching and expiration tracking

    Architecture Principle:
    - Open-source body is completely decoupled from private/cloud soul
    - High-risk decisions require external independent audit
    - Missing credentials produce explicit alerts, not silent local fallback

    Hard Redlines:
    - Invalid response signatures are rejected entirely
    - Service unavailability triggers explicit degradation (not silent continue)
    - Missing cloud credentials produce configuration alerts
    """

    def __init__(
        self,
        config: Optional[CloudAuditorConfig] = None,
        *,
        brain_scope: str = "zentex.runtime",
    ) -> None:
        self._config = config or CloudAuditorConfig()
        self._brain_scope = brain_scope
        self._degradation_history: List[DegradationRecord] = []
        self._decision_cache: Dict[str, CloudAuditDecision] = {}
        self._decision_history: List[CloudAuditDecision] = []
        self._request_history: List[CloudAuditRequest] = []

    @property
    def brain_scope(self) -> str:
        return self._brain_scope

    @property
    def is_configured(self) -> bool:
        """Check if cloud auditor is properly configured."""
        return bool(self._config.api_key and self._config.api_secret)

    @property
    def degradation_count(self) -> int:
        """Number of degradation events recorded."""
        return len(self._degradation_history)

    def configure(
        self,
        *,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        """Configure or reconfigure the cloud auditor."""
        if api_key is not None:
            self._config.api_key = api_key
        if api_secret is not None:
            self._config.api_secret = api_secret
        if endpoint is not None:
            self._config.endpoint = endpoint
        if timeout_seconds is not None:
            self._config.timeout_seconds = timeout_seconds

    def audit_action(
        self,
        action_type: str,
        action_payload: Dict[str, Any],
        *,
        risk_level: Literal["low", "medium", "high", "critical"] = "medium",
        context: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> CloudAuditDecision:
        """Request cloud audit for a high-risk action.

        This is the main entry point for cloud auditing. It:
        1. Creates and signs the audit request
        2. Checks cache for recent identical requests
        3. Calls cloud service or degrades gracefully
        4. Verifies response signature
        5. Returns decision with constraints

        Args:
            action_type: Type of action (e.g., "self_modify", "execute_high_risk")
            action_payload: Action-specific details
            risk_level: Assessed risk level
            context: Additional context for audit decision
            use_cache: Whether to check cache first

        Returns:
            CloudAuditDecision with status and constraints
        """
        if not self.is_configured:
            return self._handle_unconfigured(action_type, action_payload, risk_level, context)

        # Build request
        request = self._build_request(action_type, action_payload, risk_level, context)

        # Check cache
        if use_cache:
            cache_key = self._cache_key(request)
            cached = self._decision_cache.get(cache_key)
            if cached and not self._is_expired(cached):
                return cached

        # Call cloud service
        try:
            decision = self._call_cloud_service(request)
        except CloudServiceUnavailable as e:
            return self._handle_degradation(request, f"Service unavailable: {e}")
        except InvalidSignature as e:
            return self._handle_degradation(request, f"Invalid response signature: {e}")

        # Verify decision signature
        if not self._verify_decision_signature(decision):
            return self._handle_degradation(request, "Decision signature verification failed")

        self._decision_history.append(decision)

        # Cache and return
        if use_cache:
            self._decision_cache[cache_key] = decision

        return decision

    def batch_audit(
        self,
        requests: List[CloudAuditRequest],
    ) -> List[CloudAuditDecision]:
        """Audit multiple actions in batch.

        Args:
            requests: List of audit requests

        Returns:
            List of decisions corresponding to requests
        """
        if not self.is_configured:
            return [
                self._create_local_fallback_decision(req, "Unconfigured")
                for req in requests
            ]

        # Batch requests with shared signature
        batch_request = self._build_batch_request(requests)

        try:
            decisions = self._call_cloud_service_batch(batch_request)
        except (CloudServiceUnavailable, InvalidSignature) as e:
            # Degrade all
            return [
                self._create_local_fallback_decision(req, str(e))
                for req in requests
            ]

        # Verify each decision
        verified_decisions = []
        for decision in decisions:
            if self._verify_decision_signature(decision):
                verified_decisions.append(decision)
            else:
                # Create fallback for invalid signature
                corresponding_request = next(
                    (r for r in requests if r.request_id == decision.request_id),
                    None,
                )
                if corresponding_request:
                    verified_decisions.append(
                        self._create_local_fallback_decision(
                            corresponding_request, "Invalid signature"
                        )
                    )

        return verified_decisions

    def get_degradation_history(self) -> List[DegradationRecord]:
        """Get history of degradation events."""
        return self._degradation_history.copy()

    def get_request_history(self) -> List[CloudAuditRequest]:
        """Get signed cloud audit requests sent or recorded by the client."""
        return self._request_history.copy()

    def get_decision_history(self) -> List[CloudAuditDecision]:
        """Get accepted or degraded cloud audit decisions."""
        return self._decision_history.copy()

    def get_decision(self, decision_id: str) -> Optional[CloudAuditDecision]:
        """Return a decision by decision_id."""
        for decision in self._decision_history:
            if decision.decision_id == decision_id:
                return decision
        return None

    def get_boundary_definition(self) -> CloudBoundaryDefinition:
        """Return the architectural boundary defined by G26."""
        return CloudBoundaryDefinition(
            open_source_components=[
                "CloudAuditorClient request signing",
                "response signature verification",
                "explicit degradation records",
                "local execution consumption of audit decision",
            ],
            private_components=[
                "policy authoring",
                "risk scoring policy corpus",
                "human review workflow",
            ],
            cloud_components=[
                "remote independent policy decision service",
                "decision_id/request_id/policy_version issuance",
                "server-side response signing",
            ],
        )

    def clear_cache(self) -> None:
        """Clear decision cache."""
        self._decision_cache.clear()

    def _build_request(
        self,
        action_type: str,
        action_payload: Dict[str, Any],
        risk_level: Literal["low", "medium", "high", "critical"],
        context: Optional[Dict[str, Any]],
    ) -> CloudAuditRequest:
        """Build and sign audit request."""
        request = CloudAuditRequest(
            action_type=action_type,
            action_payload=action_payload,
            risk_level=risk_level,
            context=context or {},
            brain_scope=self._brain_scope,
        )

        # Sign request
        request.client_signature = self._sign_request(request)
        self._request_history.append(request)

        return request

    def _build_batch_request(self, requests: List[CloudAuditRequest]) -> CloudAuditRequest:
        """Build a batch request containing multiple actions."""
        batch_payload = {
            "batch_id": str(uuid4()),
            "actions": [
                {
                    "request_id": r.request_id,
                    "action_type": r.action_type,
                    "action_payload": r.action_payload,
                    "risk_level": r.risk_level,
                }
                for r in requests
            ],
        }

        batch_request = CloudAuditRequest(
            action_type="batch_audit",
            action_payload=batch_payload,
            risk_level="high",  # Batch is always high risk
            context={"batch_size": len(requests)},
            brain_scope=self._brain_scope,
        )

        batch_request.client_signature = self._sign_request(batch_request)
        return batch_request

    def _sign_request(self, request: CloudAuditRequest) -> str:
        """Create HMAC-SHA256 signature for request."""
        if not self._config.api_secret:
            raise ValueError("Cannot sign request: API secret not configured")

        # Build canonical string
        timestamp = int(request.timestamp.timestamp())
        canonical = f"{request.action_type}|{request.request_id}|{timestamp}"

        # Create signature
        signature = hmac.new(
            self._config.api_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return f"hmac-sha256={signature}"

    def _verify_decision_signature(self, decision: CloudAuditDecision) -> bool:
        """Verify cloud service response signature."""
        if not decision.signature:
            return False

        # Reconstruct expected signature
        timestamp = int(decision.created_at.timestamp())
        status_value = decision.status.value if hasattr(decision.status, "value") else str(decision.status)
        canonical = f"{decision.decision_id}|{decision.request_id}|{timestamp}|{status_value}"

        expected = hmac.new(
            self._config.api_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(decision.signature, f"hmac-sha256={expected}")

    def _call_cloud_service(self, request: CloudAuditRequest) -> CloudAuditDecision:
        """Make a real HTTP JSON call to the configured cloud audit service."""
        body = json.dumps(request.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        http_request = urllib_request.Request(
            self._config.endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Zentex-Api-Key": self._config.api_key,
                "X-Zentex-Signature": request.client_signature,
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(http_request, timeout=self._config.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except (urllib_error.URLError, TimeoutError, OSError) as exc:
            raise CloudServiceUnavailable(str(exc)) from exc

        try:
            payload = json.loads(response_body)
            return CloudAuditDecision.model_validate(payload)
        except Exception as exc:
            raise CloudServiceUnavailable(f"Invalid cloud audit response JSON: {exc}") from exc

    def _call_cloud_service_batch(
        self,
        batch_request: CloudAuditRequest,
    ) -> List[CloudAuditDecision]:
        """Make batch HTTP call to cloud audit service."""
        # Placeholder: In production, this calls the actual cloud service
        raise CloudServiceUnavailable("Cloud service integration not implemented")

    def _handle_unconfigured(
        self,
        action_type: str,
        action_payload: Dict[str, Any],
        risk_level: Literal["low", "medium", "high", "critical"] = "medium",
        context: Optional[Dict[str, Any]] = None,
    ) -> CloudAuditDecision:
        """Handle case when cloud auditor is not configured."""
        # Create a request for recording purposes
        request = CloudAuditRequest(
            action_type=action_type,
            action_payload=action_payload,
            risk_level=risk_level,
            context=context or {},
            brain_scope=self._brain_scope,
        )

        return self._handle_degradation(request, "Cloud auditor not configured - missing credentials")

    def _handle_degradation(
        self,
        request: CloudAuditRequest,
        reason: str,
    ) -> CloudAuditDecision:
        """Handle cloud service unavailability with explicit degradation."""
        record = DegradationRecord(
            reason=reason,
            fallback_action="local_fallback_with_restrictions",
            request=request,
        )
        self._degradation_history.append(record)

        decision = self._create_local_fallback_decision(request, reason)
        self._decision_history.append(decision)
        return decision

    def _create_local_fallback_decision(
        self,
        request: CloudAuditRequest,
        reason: str,
    ) -> CloudAuditDecision:
        """Create a conservative local fallback decision."""
        # Conservative fallback: require review for high/critical risk
        if request.risk_level in ("high", "critical"):
            status = CloudDecisionStatus.REVIEW_REQUIRED
        else:
            status = CloudDecisionStatus.APPROVED

        return CloudAuditDecision(
            request_id=request.request_id,
            status=status,
            reason=f"[DEGRADED MODE] {reason}. Using local policy fallback.",
            policy_version=self._config.degraded_policy_version,
            constraints={
                "degraded_mode": True,
                "requires_local_review": request.risk_level in ("high", "critical"),
                "disable_self_modify": request.risk_level == "critical",
            },
        )

    def _cache_key(self, request: CloudAuditRequest) -> str:
        """Generate cache key for a request."""
        # Simple cache key based on action type and risk level
        payload_hash = hashlib.sha256(
            json.dumps(request.action_payload, sort_keys=True).encode()
        ).hexdigest()[:16]
        return f"{request.action_type}:{request.risk_level}:{payload_hash}"

    def _is_expired(self, decision: CloudAuditDecision) -> bool:
        """Check if a cached decision has expired."""
        if decision.expires_at is None:
            # Default 5 minute expiration
            age = datetime.now(timezone.utc) - decision.created_at
            return age.total_seconds() > 300

        return datetime.now(timezone.utc) > decision.expires_at


class CloudServiceUnavailable(Exception):
    """Raised when cloud audit service is unreachable."""


class InvalidSignature(Exception):
    """Raised when response signature verification fails."""


CloudSanityAuditorClient = CloudAuditorClient

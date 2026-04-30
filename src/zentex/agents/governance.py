"""G35 role switching and multi-agent governance."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.llm.model_provider_runtime import ModelProviderRuntime


UTC = timezone.utc


class CapabilityDescriptor(BaseModel):
    """Agent capability profile used by scheduling and permission checks."""

    model_config = ConfigDict(extra="forbid")

    name: str
    boundaries: list[str] = Field(default_factory=list)
    execution_domains: list[str] = Field(default_factory=list)
    permission_scope: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class AgentProtocol(BaseModel):
    """External agent protocol paths."""

    model_config = ConfigDict(extra="forbid")

    handshake_path: str = "/handshake"
    capabilities_path: str = "/capabilities"
    task_path: str = "/tasks"
    status_path: str = "/status"
    receipt_path_template: str = "/receipts/{receipt_id}"


class AgentDocumentProfile(BaseModel):
    """LLM-produced understanding of an external agent document."""

    model_config = ConfigDict(extra="forbid")

    provider_call_id: str
    source_url: str
    capabilities: list[CapabilityDescriptor]
    protocol: AgentProtocol
    limitations: list[str] = Field(default_factory=list)
    interaction_summary: str


class GovernedAgentRegistration(BaseModel):
    """Request to register and authenticate an external agent."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    display_name: str
    version: str
    endpoint: str
    auth_token: str = Field(min_length=1)
    scope: list[str] = Field(default_factory=list)
    requested_trust_level: str = Field(default="limited", pattern="^(pending|limited|trusted)$")
    capabilities: list[CapabilityDescriptor] = Field(default_factory=list)
    protocol: AgentProtocol = Field(default_factory=AgentProtocol)
    document_url: str | None = None
    llm_provider_id: str | None = None
    operator_id: str = "web-console-operator"


class CapabilityHandshake(BaseModel):
    """Result of a real network capability handshake."""

    model_config = ConfigDict(extra="forbid")

    handshake_id: str = Field(default_factory=lambda: f"g35-handshake-{uuid4().hex[:12]}")
    agent_id: str
    verified: bool
    remote_version: str
    remote_capabilities: list[CapabilityDescriptor]
    authenticated: bool
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GovernedAgent(BaseModel):
    """Governed external agent record."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    display_name: str
    version: str
    endpoint: str
    auth_token: str = Field(exclude=True)
    scope: list[str]
    trust_level: str = Field(pattern="^(pending|limited|trusted|revoked)$")
    status: str = Field(pattern="^(online|degraded|offline|paused)$")
    capabilities: list[CapabilityDescriptor]
    protocol: AgentProtocol
    handshake: CapabilityHandshake
    document_profile: AgentDocumentProfile | None = None
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RoleState(BaseModel):
    """G35 three-layer role state."""

    model_config = ConfigDict(extra="forbid")

    identity_role: str
    active_role: str
    task_role: str
    role_description: str
    readonly_skills: list[str]
    recompute_required: bool = False
    last_audit_id: str | None = None


class RoleOverrideRequest(BaseModel):
    """Manual active-role override request."""

    model_config = ConfigDict(extra="forbid")

    new_active_role: str
    role_description: str
    reason: str
    operator_id: str
    confirmation_phrase: str


class TaskRoleInferenceRequest(BaseModel):
    """Infer a task-slice role from task requirements."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    objective: str
    required_capabilities: list[str] = Field(default_factory=list)
    risk_level: str = "medium"


class AgentTaskRequest(BaseModel):
    """Task scheduling or submission request."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    objective: str
    required_capabilities: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)
    execution_domain: str
    priority: int = Field(default=5, ge=1, le=10)
    risk_level: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    payload: dict[str, Any] = Field(default_factory=dict)


class SchedulingDecision(BaseModel):
    """Agent scheduling decision with candidate evidence."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(default_factory=lambda: f"g35-schedule-{uuid4().hex[:12]}")
    task_id: str
    status: str = Field(pattern="^(assigned|blocked)$")
    selected_agent_id: str | None
    selected_score: float | None
    candidate_scores: list[dict[str, Any]]
    blocked_candidates: list[dict[str, Any]]
    reasons: list[str]


class AgentTaskReceipt(BaseModel):
    """Receipt returned by a real external agent task call."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    agent_id: str
    task_id: str
    status: str
    submitted_payload: dict[str, Any]
    remote_payload: dict[str, Any]
    verified_remote_receipt: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CapabilityConflict(BaseModel):
    """Conflict summary for overlapping agent capability declarations."""

    model_config = ConfigDict(extra="forbid")

    conflict_id: str = Field(default_factory=lambda: f"g35-conflict-{uuid4().hex[:12]}")
    capability: str
    agent_ids: list[str]
    conflict_type: str
    summary: str
    suggestion: str


class CollaborationOutcome(BaseModel):
    """Persisted collaboration result for future scheduling."""

    model_config = ConfigDict(extra="forbid")

    outcome_id: str = Field(default_factory=lambda: f"g35-outcome-{uuid4().hex[:12]}")
    agent_id: str
    task_id: str
    result_status: str = Field(pattern="^(succeeded|failed|partial)$")
    score: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GovernanceAuditEvent(BaseModel):
    """Audit event for role and agent governance."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(default_factory=lambda: f"g35-audit-{uuid4().hex[:12]}")
    action: str
    detail: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RoleAgentGovernanceManager:
    """G35 role and external-agent governance manager."""

    def __init__(
        self,
        *,
        identity_role: str = "Zentex Agent",
        active_role: str = "general assistant",
        task_role: str = "general task analyst",
        role_description: str = "General-purpose audited assistant role.",
        model_provider_runtime: ModelProviderRuntime | None = None,
        default_llm_provider_id: str | None = None,
    ) -> None:
        self._role_state = RoleState(
            identity_role=identity_role,
            active_role=active_role,
            task_role=task_role,
            role_description=role_description,
            readonly_skills=[],
        )
        self._model_provider_runtime = model_provider_runtime
        self._default_llm_provider_id = default_llm_provider_id
        self._agents: dict[str, GovernedAgent] = {}
        self._receipts: dict[str, AgentTaskReceipt] = {}
        self._outcomes: dict[str, CollaborationOutcome] = {}
        self._audit_events: list[GovernanceAuditEvent] = []

    def get_role_state(self) -> RoleState:
        return self._role_state.model_copy(update={"readonly_skills": self._readonly_skills()})

    def override_active_role(self, request: RoleOverrideRequest) -> RoleState:
        if request.confirmation_phrase != "CONFIRM_ROLE_OVERRIDE":
            raise ValueError("active role override requires confirmation phrase CONFIRM_ROLE_OVERRIDE")
        audit = self._audit(
            "active_role_override",
            {
                "operator_id": request.operator_id,
                "from_active_role": self._role_state.active_role,
                "to_active_role": request.new_active_role,
                "reason": request.reason,
                "identity_role_unchanged": self._role_state.identity_role,
                "recompute_required": True,
            },
        )
        self._role_state = self._role_state.model_copy(
            update={
                "active_role": request.new_active_role,
                "role_description": request.role_description,
                "recompute_required": True,
                "last_audit_id": audit.audit_id,
                "readonly_skills": self._readonly_skills(),
            }
        )
        return self.get_role_state()

    def infer_task_role(self, request: TaskRoleInferenceRequest) -> RoleState:
        if request.risk_level in {"high", "critical"}:
            task_role = "risk-bounded task reviewer"
        elif "finance" in {item.lower() for item in request.required_capabilities}:
            task_role = "financial analysis task specialist"
        elif request.required_capabilities:
            task_role = f"{request.required_capabilities[0]} task specialist"
        else:
            task_role = "general task analyst"
        audit = self._audit(
            "task_role_inferred",
            {"task_id": request.task_id, "task_role": task_role, "objective": request.objective},
        )
        self._role_state = self._role_state.model_copy(
            update={"task_role": task_role, "last_audit_id": audit.audit_id, "readonly_skills": self._readonly_skills()}
        )
        return self.get_role_state()

    def register_agent(self, request: GovernedAgentRegistration) -> GovernedAgent:
        if request.agent_id in self._agents:
            raise ValueError(f"agent already registered: {request.agent_id}")
        document_profile = self._understand_document(request) if request.document_url else None
        profile_capabilities = document_profile.capabilities if document_profile else request.capabilities
        protocol = document_profile.protocol if document_profile else request.protocol
        if not profile_capabilities:
            raise ValueError("agent registration requires at least one capability")
        handshake = self._perform_handshake(request, protocol)
        merged_capabilities = self._merge_capabilities(profile_capabilities, handshake.remote_capabilities)
        trust_level = self._trust_level_for(request, merged_capabilities)
        agent = GovernedAgent(
            agent_id=request.agent_id,
            display_name=request.display_name,
            version=request.version,
            endpoint=request.endpoint.rstrip("/"),
            auth_token=request.auth_token,
            scope=request.scope,
            trust_level=trust_level,
            status="online",
            capabilities=merged_capabilities,
            protocol=protocol,
            handshake=handshake,
            document_profile=document_profile,
        )
        self._agents[agent.agent_id] = agent
        self._role_state = self._role_state.model_copy(update={"readonly_skills": self._readonly_skills()})
        self._audit(
            "agent_registered",
            {
                "agent_id": agent.agent_id,
                "trust_level": agent.trust_level,
                "capabilities": [cap.name for cap in agent.capabilities],
                "document_profile": bool(document_profile),
                "operator_id": request.operator_id,
            },
        )
        return agent

    def list_agents(self) -> list[GovernedAgent]:
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> GovernedAgent:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise KeyError(f"Unknown agent_id: {agent_id}")
        return agent

    def monitor_agent(self, agent_id: str) -> GovernedAgent:
        agent = self.get_agent(agent_id)
        payload = self._http_json("GET", self._url(agent.endpoint, agent.protocol.status_path), agent_id=agent_id)
        status = str(payload.get("status") or "").strip().lower()
        if status not in {"online", "degraded", "offline", "paused"}:
            raise ValueError(f"agent {agent_id} returned invalid status: {status}")
        updated = agent.model_copy(update={"status": status, "last_seen_at": datetime.now(UTC)})
        self._agents[agent_id] = updated
        self._audit("agent_status_updated", {"agent_id": agent_id, "status": status})
        return updated

    def schedule_task(self, request: AgentTaskRequest) -> SchedulingDecision:
        candidate_scores: list[dict[str, Any]] = []
        blocked_candidates: list[dict[str, Any]] = []
        for agent in self._agents.values():
            block_reasons = self._agent_block_reasons(agent, request)
            if block_reasons:
                blocked_candidates.append({"agent_id": agent.agent_id, "reasons": block_reasons})
                continue
            score = self._score_agent(agent, request)
            candidate_scores.append({"agent_id": agent.agent_id, "score": score, "trust_level": agent.trust_level})
        candidate_scores.sort(key=lambda item: (item["score"], item["agent_id"]), reverse=True)
        if not candidate_scores:
            return SchedulingDecision(
                task_id=request.task_id,
                status="blocked",
                selected_agent_id=None,
                selected_score=None,
                candidate_scores=[],
                blocked_candidates=blocked_candidates,
                reasons=["no_agent_satisfies_capability_permission_health_and_trust"],
            )
        selected = candidate_scores[0]
        decision = SchedulingDecision(
            task_id=request.task_id,
            status="assigned",
            selected_agent_id=str(selected["agent_id"]),
            selected_score=float(selected["score"]),
            candidate_scores=candidate_scores,
            blocked_candidates=blocked_candidates,
            reasons=["capability_permission_health_and_trust_matched"],
        )
        self._audit("agent_scheduled", decision.model_dump(mode="json"))
        return decision

    def submit_test_task(self, agent_id: str, request: AgentTaskRequest) -> AgentTaskReceipt:
        agent = self.get_agent(agent_id)
        block_reasons = self._agent_block_reasons(agent, request)
        if block_reasons:
            self._audit("agent_test_task_rejected", {"agent_id": agent_id, "task_id": request.task_id, "reasons": block_reasons})
            raise ValueError("agent is not dispatchable: " + ",".join(block_reasons))
        payload = {
            "task_id": request.task_id,
            "objective": request.objective,
            "payload": request.payload,
            "required_capabilities": request.required_capabilities,
            "required_permissions": request.required_permissions,
            "execution_domain": request.execution_domain,
        }
        try:
            remote = self._http_json("POST", self._url(agent.endpoint, agent.protocol.task_path), body=payload, token=agent.auth_token)
        except ValueError as exc:
            self._audit("agent_test_task_failed", {"agent_id": agent_id, "task_id": request.task_id, "error": str(exc)})
            raise
        receipt_id = str(remote.get("receipt_id") or "").strip()
        if not receipt_id:
            self._audit("agent_test_task_failed", {"agent_id": agent_id, "task_id": request.task_id, "error": "missing_receipt_id"})
            raise ValueError("agent task response missing receipt_id")
        receipt = AgentTaskReceipt(
            receipt_id=receipt_id,
            agent_id=agent_id,
            task_id=request.task_id,
            status=str(remote.get("status") or "submitted"),
            submitted_payload=payload,
            remote_payload=remote,
        )
        self._receipts[receipt.receipt_id] = receipt
        self._audit("agent_test_task_submitted", {"agent_id": agent_id, "task_id": request.task_id, "receipt_id": receipt_id})
        return receipt

    def verify_receipt(self, agent_id: str, receipt_id: str) -> AgentTaskReceipt:
        receipt = self._receipts.get(receipt_id)
        if receipt is None or receipt.agent_id != agent_id:
            raise KeyError(f"Unknown receipt_id: {receipt_id}")
        agent = self.get_agent(agent_id)
        path = agent.protocol.receipt_path_template.replace("{receipt_id}", receipt_id)
        remote = self._http_json("GET", self._url(agent.endpoint, path), agent_id=agent_id)
        if str(remote.get("receipt_id")) != receipt_id:
            raise ValueError("remote receipt id mismatch")
        updated = receipt.model_copy(update={"verified_remote_receipt": remote, "status": str(remote.get("status") or receipt.status)})
        self._receipts[receipt_id] = updated
        self._audit("agent_receipt_verified", {"agent_id": agent_id, "receipt_id": receipt_id, "status": updated.status})
        return updated

    def detect_conflicts(self) -> list[CapabilityConflict]:
        by_capability: dict[str, list[GovernedAgent]] = {}
        for agent in self._agents.values():
            for cap in agent.capabilities:
                by_capability.setdefault(cap.name, []).append(agent)
        conflicts: list[CapabilityConflict] = []
        for capability, agents in by_capability.items():
            if len(agents) < 2:
                continue
            permission_sets = {
                tuple(sorted({perm for cap in agent.capabilities if cap.name == capability for perm in cap.permission_scope}))
                for agent in agents
            }
            boundary_sets = {
                tuple(sorted({boundary for cap in agent.capabilities if cap.name == capability for boundary in cap.boundaries}))
                for agent in agents
            }
            if len(permission_sets) > 1 or len(boundary_sets) > 1:
                conflicts.append(
                    CapabilityConflict(
                        capability=capability,
                        agent_ids=sorted(agent.agent_id for agent in agents),
                        conflict_type="capability_boundary_or_permission_mismatch",
                        summary=f"Capability {capability} has inconsistent boundaries or permission scopes.",
                        suggestion="keep lower-trust agents limited and require explicit task permission matching before scheduling",
                    )
                )
        return conflicts

    def record_outcome(self, outcome: CollaborationOutcome) -> CollaborationOutcome:
        self.get_agent(outcome.agent_id)
        self._outcomes[outcome.outcome_id] = outcome
        self._audit("collaboration_outcome_recorded", outcome.model_dump(mode="json"))
        return outcome

    def list_outcomes(self, agent_id: str | None = None) -> list[CollaborationOutcome]:
        rows = list(self._outcomes.values())
        if agent_id:
            rows = [row for row in rows if row.agent_id == agent_id]
        return rows

    def list_audit_events(self) -> list[GovernanceAuditEvent]:
        return list(self._audit_events)

    def diagnose_agent_governance_closure(self, *, heartbeat_freshness_seconds: int = 300) -> dict[str, Any]:
        """Return the feature-62 agent governance diagnostic report."""
        from zentex.agents.lifecycle_diagnostics import build_agent_governance_diagnostic_report

        report = build_agent_governance_diagnostic_report(
            agents=self.list_agents(),
            outcomes=self.list_outcomes(),
            conflicts=self.detect_conflicts(),
            audit_events=self.list_audit_events(),
            heartbeat_freshness_seconds=heartbeat_freshness_seconds,
        )
        self._audit("agent_governance_closure_diagnosed", report.model_dump(mode="json"))
        return report.model_dump(mode="json")

    def enforce_agent_governance_closure(self, *, heartbeat_freshness_seconds: int = 300) -> dict[str, Any]:
        """Apply feature-62 governance actions for stale, over-scoped, or trust-drifted agents."""
        report = self.diagnose_agent_governance_closure(heartbeat_freshness_seconds=heartbeat_freshness_seconds)
        actions: list[dict[str, Any]] = []
        for issue in report["issues"]:
            agent_id = str(issue.get("agent_id") or "")
            if not agent_id or agent_id not in self._agents:
                continue
            agent = self._agents[agent_id]
            if issue["type"] == "heartbeat_stale" and agent.status != "offline":
                updated = agent.model_copy(update={"status": "offline"})
                self._agents[agent_id] = updated
                actions.append({"agent_id": agent_id, "action": "marked_offline", "reason": "heartbeat_stale"})
            elif issue["type"] == "trust_level_drift" and agent.trust_level == "trusted":
                updated = agent.model_copy(update={"trust_level": "limited", "status": "degraded"})
                self._agents[agent_id] = updated
                actions.append({"agent_id": agent_id, "action": "trust_downgraded", "new_trust_level": "limited"})
            elif issue["type"] == "scope_overreach" and (agent.trust_level != "pending" or agent.status != "degraded"):
                updated = agent.model_copy(update={"trust_level": "pending", "status": "degraded"})
                self._agents[agent_id] = updated
                actions.append({"agent_id": agent_id, "action": "scope_quarantined", "new_trust_level": "pending"})
        payload = {"actions": actions, "action_count": len(actions), "diagnostic_report": report}
        self._audit("agent_governance_closure_enforced", payload)
        return payload

    def run_agent_fault_injection_matrix(self, *, heartbeat_freshness_seconds: int = 300) -> dict[str, Any]:
        """Return the feature-62 fault matrix report derived from real agent governance state."""
        from zentex.agents.lifecycle_diagnostics import (
            build_agent_fault_injection_report,
            build_agent_governance_diagnostic_report,
        )

        diagnostic = build_agent_governance_diagnostic_report(
            agents=self.list_agents(),
            outcomes=self.list_outcomes(),
            conflicts=self.detect_conflicts(),
            audit_events=self.list_audit_events(),
            heartbeat_freshness_seconds=heartbeat_freshness_seconds,
        )
        report = build_agent_fault_injection_report(diagnostic)
        self._audit("agent_fault_matrix_executed", report.model_dump(mode="json"))
        return report.model_dump(mode="json")

    def external_interface(self) -> dict[str, Any]:
        return {
            "handshake": {"method": "POST", "path": "/handshake"},
            "capabilities": {"method": "GET", "path": "/capabilities"},
            "task_submit": {"method": "POST", "path": "/tasks"},
            "status": {"method": "GET", "path": "/status"},
            "receipt": {"method": "GET", "path": "/receipts/{receipt_id}"},
            "required_auth": "Authorization: Bearer <agent token>",
        }

    def _understand_document(self, request: GovernedAgentRegistration) -> AgentDocumentProfile:
        if self._model_provider_runtime is None:
            raise ValueError("agent document understanding requires an active ModelProviderRuntime")
        provider_id = request.llm_provider_id or self._default_llm_provider_id
        if not provider_id:
            raise ValueError("agent document understanding requires llm_provider_id")
        assert request.document_url is not None
        document_text = self._fetch_text(request.document_url)
        call = self._model_provider_runtime.generate_json(
            provider_id,
            prompt=(
                "Analyze this external Agent interface document. Return JSON with capabilities, "
                "protocol, limitations, and interaction_summary. Do not invent undocumented permissions."
            ),
            context={
                "document_url": request.document_url,
                "document_text": document_text,
                "agent_endpoint": request.endpoint,
            },
            caller_context={"source_module": "g35_agent_document_understanding", "agent_id": request.agent_id},
        )
        output = call.output or {}
        capabilities = [CapabilityDescriptor.model_validate(row) for row in output.get("capabilities", [])]
        if not capabilities:
            raise ValueError("LLM document understanding returned no capabilities")
        return AgentDocumentProfile(
            provider_call_id=call.call_id,
            source_url=request.document_url,
            capabilities=capabilities,
            protocol=AgentProtocol.model_validate(output.get("protocol") or {}),
            limitations=[str(item) for item in output.get("limitations", [])],
            interaction_summary=str(output.get("interaction_summary") or ""),
        )

    def _perform_handshake(self, request: GovernedAgentRegistration, protocol: AgentProtocol) -> CapabilityHandshake:
        # The local agent_id belongs to Zentex's registry only. Do not require
        # external Agents to receive, persist, or echo it during discovery.
        payload = {"version": request.version}
        remote = self._http_json("POST", self._url(request.endpoint, protocol.handshake_path), body=payload, token=request.auth_token)
        remote_capabilities = [CapabilityDescriptor.model_validate(row) for row in remote.get("capabilities", [])]
        if not remote_capabilities:
            raise ValueError("agent handshake returned no capabilities")
        return CapabilityHandshake(
            agent_id=request.agent_id,
            verified=True,
            remote_version=str(remote.get("version") or request.version),
            remote_capabilities=remote_capabilities,
            authenticated=True,
        )

    @staticmethod
    def _merge_capabilities(
        profile_capabilities: list[CapabilityDescriptor],
        remote_capabilities: list[CapabilityDescriptor],
    ) -> list[CapabilityDescriptor]:
        remote_by_name = {cap.name: cap for cap in remote_capabilities}
        merged: list[CapabilityDescriptor] = []
        for cap in profile_capabilities:
            remote = remote_by_name.get(cap.name)
            if remote is None:
                continue
            merged.append(
                CapabilityDescriptor(
                    name=cap.name,
                    boundaries=sorted(set(cap.boundaries) | set(remote.boundaries)),
                    execution_domains=sorted(set(cap.execution_domains) | set(remote.execution_domains)),
                    permission_scope=sorted(set(cap.permission_scope) | set(remote.permission_scope)),
                    confidence=min(cap.confidence, remote.confidence),
                )
            )
        if not merged:
            raise ValueError("handshake capabilities do not match registered capability profile")
        return merged

    @staticmethod
    def _trust_level_for(request: GovernedAgentRegistration, capabilities: list[CapabilityDescriptor]) -> str:
        requested = request.requested_trust_level
        if requested == "pending":
            return "pending"
        requested_permissions = {perm for cap in capabilities for perm in cap.permission_scope}
        if requested_permissions and not requested_permissions.issubset(set(request.scope)):
            return "pending"
        return requested

    @staticmethod
    def _score_agent(agent: GovernedAgent, request: AgentTaskRequest) -> float:
        trust_score = {"trusted": 100.0, "limited": 70.0, "pending": 20.0, "revoked": 0.0}[agent.trust_level]
        confidence = max((cap.confidence for cap in agent.capabilities if cap.name in request.required_capabilities), default=0.5)
        return trust_score + confidence * 20.0 + request.priority

    @staticmethod
    def _agent_block_reasons(agent: GovernedAgent, request: AgentTaskRequest) -> list[str]:
        reasons: list[str] = []
        if agent.status != "online":
            reasons.append(f"status:{agent.status}")
        if agent.trust_level not in {"limited", "trusted"}:
            reasons.append(f"trust:{agent.trust_level}")
        if request.risk_level in {"high", "critical"} and agent.trust_level != "trusted":
            reasons.append("high_risk_requires_trusted_agent")
        capability_names = {cap.name for cap in agent.capabilities}
        missing_capabilities = sorted(set(request.required_capabilities) - capability_names)
        if missing_capabilities:
            reasons.append("missing_capabilities:" + ",".join(missing_capabilities))
        permission_scope = set(agent.scope) | {perm for cap in agent.capabilities for perm in cap.permission_scope}
        missing_permissions = sorted(set(request.required_permissions) - permission_scope)
        if missing_permissions:
            reasons.append("missing_permissions:" + ",".join(missing_permissions))
        domains = {domain for cap in agent.capabilities for domain in cap.execution_domains}
        if request.execution_domain and request.execution_domain not in domains:
            reasons.append(f"execution_domain:{request.execution_domain}")
        return reasons

    def _readonly_skills(self) -> list[str]:
        return sorted({cap.name for agent in self._agents.values() for cap in agent.capabilities})

    def _audit(self, action: str, detail: dict[str, Any]) -> GovernanceAuditEvent:
        event = GovernanceAuditEvent(action=action, detail=detail)
        self._audit_events.append(event)
        return event

    @staticmethod
    def _fetch_text(url: str) -> str:
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                text = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise ValueError(f"failed to fetch agent document: {exc}") from exc
        if not text.strip():
            raise ValueError("agent document is empty")
        return text

    @staticmethod
    def _http_json(
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        token: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        data = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif agent_id:
            headers["X-Zentex-Agent-Id"] = agent_id
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"agent HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"agent network failure: {exc}") from exc
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("agent returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise ValueError("agent returned non-object JSON")
        return decoded

    @staticmethod
    def _url(endpoint: str, path: str) -> str:
        return endpoint.rstrip("/") + "/" + path.lstrip("/")

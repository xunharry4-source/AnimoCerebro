from __future__ import annotations

"""G41 nine-question driven subject evolution mainline.

This module owns G41 business rules. Web routers and service facades should
only call these methods and must not duplicate the rules here.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_text_set(value: Any) -> set[str]:
    if isinstance(value, dict):
        items: list[Any] = []
        for key, raw in value.items():
            items.append(key)
            if isinstance(raw, (list, tuple, set)):
                items.extend(raw)
            else:
                items.append(raw)
        return {str(item).strip() for item in items if str(item).strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    text = str(value or "").strip()
    return {text} if text else set()


class G41AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: f"g41-audit-{uuid4().hex[:12]}")
    event_type: str
    entity_id: str
    reason: str
    created_at: str = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class G41CognitiveToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    tool_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    tool_type: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    required_context: list[str] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(default_factory=list)
    do_not_use_when: list[str] = Field(default_factory=list)
    read_only: bool = True
    side_effect_free: bool = True
    execution_permissions: list[str] = Field(default_factory=list)
    lifecycle_status: Literal["candidate", "active", "degraded", "revoked"] = "active"

    @model_validator(mode="after")
    def validate_subject_evolution_cognitive_tool(self) -> "G41CognitiveToolSpec":
        if not self.read_only or not self.side_effect_free:
            raise ValueError("G41 cognitive tools must be read_only=True and side_effect_free=True")
        if self.execution_permissions:
            raise ValueError("G41 cognitive tools cannot own execution permissions")
        if not self.trigger_conditions:
            raise ValueError("G41 cognitive tools must declare trigger_conditions")
        return self


class G41ToolRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    registration_id: str = Field(default_factory=lambda: f"g41-tool-reg-{uuid4().hex[:12]}")
    spec: G41CognitiveToolSpec
    registered_at: str = Field(default_factory=_utc_now)
    audit_event_id: str


class G41InvocationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(default_factory=lambda: f"g41-plan-{uuid4().hex[:12]}")
    target_phase: str
    selected_tool_ids: list[str]
    blocked_tool_reasons: dict[str, str]
    serial_steps: list[str]
    parallel_groups: list[list[str]]
    read_only: bool = True
    side_effect_free: bool = True
    execution_attempted: bool = False
    audit_event_id: str


class G41AgendaItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    item_id: str = Field(default_factory=lambda: f"g41-agenda-{uuid4().hex[:12]}")
    title: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    source_question_ids: list[str] = Field(default_factory=list)
    reminder_conditions: list[str] = Field(default_factory=list)
    status: Literal["open", "paused", "resolved"] = "open"
    external_action_allowed: bool = False
    created_at: str = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def validate_attention_only_agenda(self) -> "G41AgendaItem":
        if self.external_action_allowed:
            raise ValueError("G41 cognitive agenda is attention-only and cannot trigger external actions")
        if not self.reminder_conditions:
            raise ValueError("G41 cognitive agenda items must declare reminder_conditions")
        return self


class G41AgendaDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str
    should_revisit: bool
    trigger_reason: str
    result: Literal["attention_only", "no_revisit"] = "attention_only"
    external_action_attempted: bool = False


class G41CandidatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    patch_id: str = Field(default_factory=lambda: f"g41-candidate-{uuid4().hex[:12]}")
    source_gap_id: str
    target_component: str
    failure_patterns: list[str]
    proposed_files: list[str]
    rollback_conditions: list[str]
    validation_requirements: list[str]
    isolation_path: str
    manifest_path: str
    writes_to_mainline: bool = False
    promoted: bool = False
    created_at: str = Field(default_factory=_utc_now)


class G41CandidateVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verification_id: str = Field(default_factory=lambda: f"g41-verify-{uuid4().hex[:12]}")
    patch_id: str
    status: Literal["pass", "fail"]
    checked_manifest_exists: bool
    checked_isolation_path_exists: bool
    checked_no_mainline_write: bool
    checked_rollback_conditions: bool
    checked_validation_requirements: bool
    evidence_refs: list[str]
    created_at: str = Field(default_factory=_utc_now)


class G41BrainOrganSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organ_id: Literal["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"]
    name: str
    responsibility: str
    implementation_refs: list[str]
    integration_refs: list[str]
    direct_host_control_allowed: bool = False
    external_action_allowed: bool = False
    execution_permissions: list[str] = Field(default_factory=list)
    pure_cognitive_layer: bool = True
    overview_status: Literal["implemented"] = "implemented"
    boundary_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_pure_cognitive_boundary(self) -> "G41BrainOrganSpec":
        if self.direct_host_control_allowed or self.external_action_allowed:
            raise ValueError("G41 brain organs cannot directly control host or trigger external action")
        if self.execution_permissions:
            raise ValueError("G41 brain organs cannot own execution permissions")
        if not self.pure_cognitive_layer:
            raise ValueError("G41 brain organs must remain in the pure cognitive layer")
        if not self.implementation_refs:
            raise ValueError("G41 brain organ must declare implementation_refs")
        return self


class G41BrainOrganMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    map_id: str = Field(default="g41-brain-organ-map")
    organ_count: int
    organ_ids: list[str]
    pure_cognitive_layer: bool
    direct_host_control_allowed: bool
    external_action_allowed: bool
    execution_permissions_present: bool
    required_integration_refs: list[str]
    organs: list[G41BrainOrganSpec]


class G41BrainOrganPurityReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = Field(default_factory=lambda: f"g41-organ-purity-{uuid4().hex[:12]}")
    status: Literal["pass", "fail"]
    checked_organ_ids: list[str]
    violations: list[dict[str, Any]]
    created_at: str = Field(default_factory=_utc_now)


def _default_brain_organs() -> list[G41BrainOrganSpec]:
    return [
        G41BrainOrganSpec(
            organ_id="B1",
            name="Working memory and attention controller",
            responsibility="Maintain active cognitive workspace, attention slots, interrupts, and recovery.",
            implementation_refs=["zentex.kernel.state_domain.working_memory.WorkingMemoryController"],
            integration_refs=["G31A", "G41", "B3", "B7"],
            boundary_notes=["Attention selection only; no host execution."],
        ),
        G41BrainOrganSpec(
            organ_id="B2",
            name="Living self model",
            responsibility="Track cognitive load, confidence drift, stable weaknesses, and subject state.",
            implementation_refs=[
                "zentex.kernel.state_domain.self_model.SelfModelEngine",
                "zentex.reflection.living_self_model",
            ],
            integration_refs=["G17", "G25", "G41", "B7"],
            boundary_notes=["State estimation only; cannot rewrite identity or policy."],
        ),
        G41BrainOrganSpec(
            organ_id="B3",
            name="Internal temporal sense",
            responsibility="Maintain agenda age, review windows, reminder cooldown, and procrastination risk.",
            implementation_refs=["zentex.kernel.state_domain.temporal.CognitiveTemporalEngine"],
            integration_refs=["G31A", "G41", "B1"],
            boundary_notes=["Agenda timing only; reminders remain cognitive signals."],
        ),
        G41BrainOrganSpec(
            organ_id="B4",
            name="Multi-branch world model and simulator",
            responsibility="Support counterfactual branches, consequence estimation, and branch comparison.",
            implementation_refs=[
                "zentex.kernel.thought_sandbox",
                "zentex.cognition.simulation",
            ],
            integration_refs=["G9", "G13", "G41"],
            boundary_notes=["Simulation outputs are predictive evidence, not action authorization."],
        ),
        G41BrainOrganSpec(
            organ_id="B5",
            name="Conflict monitor and self-correction",
            responsibility="Detect contradictions and produce correction triggers before deeper reasoning continues.",
            implementation_refs=["zentex.safety.conflict_engine.CognitiveConflictEngine"],
            integration_refs=["G25", "G41", "B7"],
            boundary_notes=["Conflict reports route to cognitive correction or G25; no direct execution."],
        ),
        G41BrainOrganSpec(
            organ_id="B6",
            name="Social mind model",
            responsibility="Maintain other-entity knowledge boundaries, communication fit, and misunderstanding signals.",
            implementation_refs=[
                "zentex.cognition.theory_of_mind",
                "zentex.cognition.social_mind",
            ],
            integration_refs=["G23", "G35", "G41"],
            boundary_notes=["Intent hypotheses remain hypotheses until confirmed by upstream policy."],
        ),
        G41BrainOrganSpec(
            organ_id="B7",
            name="Meta-cognition scheduler",
            responsibility="Choose reasoning mode, cognitive tool order, and escalation decisions for a turn.",
            implementation_refs=[
                "zentex.kernel.flow_domain.think_loop",
                "zentex.nine_questions.subject_evolution_mainline.G41MainlineRuntime",
            ],
            integration_refs=["G17", "G25", "G41", "B1", "B2", "B5"],
            boundary_notes=["Schedules cognitive tools only; execution remains outside organ authority."],
        ),
        G41BrainOrganSpec(
            organ_id="B8",
            name="Sleep-like consolidation and forgetting",
            responsibility="Run offline consolidation, memory tier changes, and noise forgetting.",
            implementation_refs=["zentex.memory.consolidation.consolidation.ConsolidationEngine"],
            integration_refs=["G29", "G41"],
            boundary_notes=["Memory governance only; physical deletion is outside the organ map."],
        ),
    ]


class G41MainlineRuntime:
    """Stateful G41 runtime for cognitive tools, agenda, and patch candidates."""

    def __init__(self, *, base_dir: str | Path | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else Path(tempfile.mkdtemp(prefix="zentex-g41-"))
        self._candidate_root = self._base_dir / "candidates"
        self._candidate_root.mkdir(parents=True, exist_ok=True)
        self._tools: dict[str, G41ToolRegistration] = {}
        self._agenda: dict[str, G41AgendaItem] = {}
        self._patches: dict[str, G41CandidatePatch] = {}
        self._verifications: dict[str, G41CandidateVerification] = {}
        self._audit: list[G41AuditEvent] = []
        self._organs: dict[str, G41BrainOrganSpec] = {organ.organ_id: organ for organ in _default_brain_organs()}

    def _record_audit(self, event_type: str, entity_id: str, reason: str, metadata: dict[str, Any] | None = None) -> G41AuditEvent:
        event = G41AuditEvent(
            event_type=event_type,
            entity_id=entity_id,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        self._audit.append(event)
        return event

    def register_tool(self, spec: G41CognitiveToolSpec) -> G41ToolRegistration:
        if spec.tool_id in self._tools:
            raise ValueError(f"G41 cognitive tool already registered: {spec.tool_id}")
        event = self._record_audit("tool_registered", spec.tool_id, "registered read-only cognitive tool")
        registration = G41ToolRegistration(spec=spec, audit_event_id=event.event_id)
        self._tools[spec.tool_id] = registration
        return registration

    def list_tools(self) -> list[G41ToolRegistration]:
        return list(self._tools.values())

    def get_tool(self, tool_id: str) -> G41ToolRegistration:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise KeyError(f"Unknown G41 cognitive tool: {tool_id}") from exc

    def build_invocation_plan(self, *, context: dict[str, Any], target_phase: str) -> G41InvocationPlan:
        available = (
            _as_text_set(context.get("available_conditions"))
            | _as_text_set(context.get("signals"))
            | _as_text_set(context.get("question_driver_refs"))
        )
        blocked = _as_text_set(context.get("blocked_conditions")) | _as_text_set(context.get("do_not_use_when"))
        selected: list[str] = []
        blocked_reasons: dict[str, str] = {}

        for tool_id, registration in self._tools.items():
            spec = registration.spec
            if spec.lifecycle_status != "active":
                blocked_reasons[tool_id] = f"lifecycle_status={spec.lifecycle_status}"
                continue
            matched_block = [condition for condition in spec.do_not_use_when if condition in blocked]
            if matched_block:
                blocked_reasons[tool_id] = f"do_not_use_when matched: {', '.join(matched_block)}"
                continue
            missing_context = [key for key in spec.required_context if key not in context]
            if missing_context:
                blocked_reasons[tool_id] = f"missing required_context: {', '.join(missing_context)}"
                continue
            matched_trigger = [condition for condition in spec.trigger_conditions if condition in available]
            if not matched_trigger:
                blocked_reasons[tool_id] = "no trigger_conditions matched"
                continue
            selected.append(tool_id)

        event = self._record_audit(
            "tool_plan_built",
            target_phase,
            "selected read-only cognitive tools without execution",
            {"selected_tool_ids": selected, "blocked_tool_reasons": blocked_reasons},
        )
        return G41InvocationPlan(
            target_phase=target_phase,
            selected_tool_ids=selected,
            blocked_tool_reasons=blocked_reasons,
            serial_steps=list(selected),
            parallel_groups=[list(selected)] if len(selected) > 1 else [],
            audit_event_id=event.event_id,
        )

    def add_agenda_item(self, item: G41AgendaItem) -> G41AgendaItem:
        if item.item_id in self._agenda:
            raise ValueError(f"G41 agenda item already exists: {item.item_id}")
        self._agenda[item.item_id] = item
        self._record_audit("agenda_item_added", item.item_id, "registered internal cognitive agenda item")
        return item

    def list_agenda(self) -> list[G41AgendaItem]:
        return list(self._agenda.values())

    def evaluate_agenda(self, context: dict[str, Any]) -> list[G41AgendaDecision]:
        attention_signals = _as_text_set(context.get("attention_signals")) | _as_text_set(context.get("signals"))
        decisions: list[G41AgendaDecision] = []
        for item in self._agenda.values():
            if item.status != "open":
                decisions.append(
                    G41AgendaDecision(
                        item_id=item.item_id,
                        should_revisit=False,
                        trigger_reason=f"status={item.status}",
                        result="no_revisit",
                    )
                )
                continue
            matched = [condition for condition in item.reminder_conditions if condition in attention_signals]
            decisions.append(
                G41AgendaDecision(
                    item_id=item.item_id,
                    should_revisit=bool(matched),
                    trigger_reason=", ".join(matched) if matched else "no reminder condition matched",
                    result="attention_only" if matched else "no_revisit",
                )
            )
        self._record_audit("agenda_evaluated", "g41-agenda", "evaluated agenda without external action")
        return decisions

    def create_candidate_patch(self, payload: dict[str, Any]) -> G41CandidatePatch:
        source_gap_id = str(payload.get("source_gap_id") or "").strip()
        target_component = str(payload.get("target_component") or "").strip()
        failure_patterns = sorted(_as_text_set(payload.get("failure_patterns")))
        proposed_files = sorted(_as_text_set(payload.get("proposed_files")))
        rollback_conditions = sorted(_as_text_set(payload.get("rollback_conditions")))
        validation_requirements = sorted(_as_text_set(payload.get("validation_requirements")))
        if not source_gap_id or not target_component:
            raise ValueError("source_gap_id and target_component are required")
        if not failure_patterns:
            raise ValueError("failure_patterns are required to create a G41 candidate patch")
        if not rollback_conditions:
            raise ValueError("rollback_conditions are required")
        if not validation_requirements:
            raise ValueError("validation_requirements are required")

        patch_id = f"g41-candidate-{uuid4().hex[:12]}"
        isolation_path = self._candidate_root / patch_id
        isolation_path.mkdir(parents=False, exist_ok=False)
        manifest_path = isolation_path / "candidate_patch.json"
        manifest = {
            "patch_id": patch_id,
            "source_gap_id": source_gap_id,
            "target_component": target_component,
            "failure_patterns": failure_patterns,
            "proposed_files": proposed_files,
            "rollback_conditions": rollback_conditions,
            "validation_requirements": validation_requirements,
            "writes_to_mainline": False,
            "promoted": False,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        patch = G41CandidatePatch(
            patch_id=patch_id,
            source_gap_id=source_gap_id,
            target_component=target_component,
            failure_patterns=failure_patterns,
            proposed_files=proposed_files,
            rollback_conditions=rollback_conditions,
            validation_requirements=validation_requirements,
            isolation_path=str(isolation_path),
            manifest_path=str(manifest_path),
        )
        self._patches[patch.patch_id] = patch
        self._record_audit("candidate_patch_created", patch.patch_id, "created isolated candidate patch manifest")
        return patch

    def get_candidate_patch(self, patch_id: str) -> G41CandidatePatch:
        try:
            return self._patches[patch_id]
        except KeyError as exc:
            raise KeyError(f"Unknown G41 candidate patch: {patch_id}") from exc

    def verify_candidate_patch(self, patch_id: str) -> G41CandidateVerification:
        patch = self.get_candidate_patch(patch_id)
        manifest_path = Path(patch.manifest_path)
        isolation_path = Path(patch.isolation_path)
        manifest_ok = manifest_path.exists() and manifest_path.is_file()
        isolation_ok = isolation_path.exists() and isolation_path.is_dir()
        no_mainline_write = not patch.writes_to_mainline and not patch.promoted
        rollback_ok = bool(patch.rollback_conditions)
        validation_ok = bool(patch.validation_requirements)
        status: Literal["pass", "fail"] = (
            "pass" if all([manifest_ok, isolation_ok, no_mainline_write, rollback_ok, validation_ok]) else "fail"
        )
        verification = G41CandidateVerification(
            patch_id=patch.patch_id,
            status=status,
            checked_manifest_exists=manifest_ok,
            checked_isolation_path_exists=isolation_ok,
            checked_no_mainline_write=no_mainline_write,
            checked_rollback_conditions=rollback_ok,
            checked_validation_requirements=validation_ok,
            evidence_refs=[patch.manifest_path, patch.isolation_path],
        )
        self._verifications[verification.verification_id] = verification
        self._record_audit(
            "candidate_patch_verified",
            patch.patch_id,
            f"candidate patch verification {status}",
            verification.model_dump(mode="json"),
        )
        return verification

    def list_audit_events(self) -> list[G41AuditEvent]:
        return list(self._audit)

    def get_brain_organ_map(self) -> G41BrainOrganMap:
        organs = [self._organs[organ_id] for organ_id in sorted(self._organs)]
        execution_permissions_present = any(organ.execution_permissions for organ in organs)
        return G41BrainOrganMap(
            organ_count=len(organs),
            organ_ids=[organ.organ_id for organ in organs],
            pure_cognitive_layer=all(organ.pure_cognitive_layer for organ in organs),
            direct_host_control_allowed=any(organ.direct_host_control_allowed for organ in organs),
            external_action_allowed=any(organ.external_action_allowed for organ in organs),
            execution_permissions_present=execution_permissions_present,
            required_integration_refs=["G31A", "G17", "G25", "G41"],
            organs=organs,
        )

    def get_brain_organ(self, organ_id: str) -> G41BrainOrganSpec:
        normalized = organ_id.strip().upper()
        try:
            return self._organs[normalized]
        except KeyError as exc:
            raise KeyError(f"Unknown G41 brain organ: {organ_id}") from exc

    def verify_brain_organ_purity(self) -> G41BrainOrganPurityReport:
        violations: list[dict[str, Any]] = []
        for organ in self.get_brain_organ_map().organs:
            if organ.direct_host_control_allowed:
                violations.append({"organ_id": organ.organ_id, "field": "direct_host_control_allowed"})
            if organ.external_action_allowed:
                violations.append({"organ_id": organ.organ_id, "field": "external_action_allowed"})
            if organ.execution_permissions:
                violations.append({"organ_id": organ.organ_id, "field": "execution_permissions"})
            if not organ.pure_cognitive_layer:
                violations.append({"organ_id": organ.organ_id, "field": "pure_cognitive_layer"})
        report = G41BrainOrganPurityReport(
            status="fail" if violations else "pass",
            checked_organ_ids=self.get_brain_organ_map().organ_ids,
            violations=violations,
        )
        self._record_audit(
            "brain_organ_purity_verified",
            "g41-brain-organs",
            f"brain organ purity verification {report.status}",
            report.model_dump(mode="json"),
        )
        return report

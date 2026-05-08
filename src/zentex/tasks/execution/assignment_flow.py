from __future__ import annotations

"""G31A task assignment gate for physical subtasks.

This module is the boundary between logical decomposition and executable work.
It verifies that a real runtime owner exists before a subtask may leave
``assignment_pending``.
"""

import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from zentex.tasks.management.negotiation import NegotiationRequest
from zentex.tasks.models import TaskStatus


UTC = timezone.utc
_OWNER_PREFIXES = ("internal:", "cli:", "mcp:", "agent:", "external_connector:")


@dataclass(frozen=True)
class ResourceCandidate:
    owner_ref: str
    executor_type: str
    executor_id: str
    label: str
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    bid_proposal: dict[str, Any] | None = None


@dataclass(frozen=True)
class AssignmentDecision:
    status: str
    owner_ref: str = ""
    candidate_owners: list[str] = field(default_factory=list)
    executor_type: str = ""
    executor_id: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    missing_resources: list[str] = field(default_factory=list)
    candidates: list[ResourceCandidate] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    negotiation: dict[str, Any] | None = None

    @property
    def assigned(self) -> bool:
        return self.status == "assigned" and bool(self.owner_ref)


class ResourceMatcher:
    """Match required resources against internal plugins, CLI, MCP, connectors and agents."""

    def __init__(
        self,
        *,
        plugin_service: Any = None,
        cli_service: Any = None,
        mcp_service: Any = None,
        external_connector_service: Any = None,
        agent_service: Any = None,
    ) -> None:
        self.plugin_service = plugin_service
        self.cli_service = cli_service
        self.mcp_service = mcp_service
        self.external_connector_service = external_connector_service
        self.agent_service = agent_service

    def match(
        self,
        *,
        task: Any,
        required_capabilities: Iterable[str],
        required_resources: Iterable[str],
        designated_owner: str = "",
    ) -> AssignmentDecision:
        task_scope = _task_scope_value(task)
        required = _dedupe([*required_capabilities, *_resource_tokens(required_resources)])
        designated_owner = str(designated_owner or "").strip()
        candidates = self._collect_candidates()
        if task_scope == "internal":
            candidates = [item for item in candidates if item.executor_type == "internal"]
        elif task_scope == "external":
            candidates = [item for item in candidates if item.executor_type in {"cli", "mcp", "external_connector", "agent"}]
        required_owner_refs = _required_owner_refs(required_resources, task_scope=task_scope)
        evidence = {
            "matched_by": "G31A.ResourceMatcher",
            "required_capabilities": required,
            "required_resources": list(required_resources or []),
            "designated_owner": designated_owner,
            "task_scope": task_scope,
            "searched_asset_libraries": _searched_asset_libraries(task_scope),
            "candidate_counts_by_registry": self._candidate_counts_by_registry(candidates),
            "candidate_count": len(candidates),
            "candidate_owners": [item.owner_ref for item in candidates],
            "required_owner_refs": required_owner_refs,
        }

        if required_owner_refs:
            candidate_owners = {item.owner_ref for item in candidates}
            missing_owner_refs = [owner for owner in required_owner_refs if owner not in candidate_owners]
            if missing_owner_refs:
                return self._unassigned(
                    required=required,
                    missing=[*missing_owner_refs, *required],
                    candidates=candidates,
                    evidence={**evidence, "failure_reason": "required_owner_ref_not_available"},
                )

        if designated_owner:
            normalized_owner = _normalize_owner_ref(designated_owner, task_scope=task_scope)
            if task_scope == "internal" and not normalized_owner.startswith("internal:"):
                return self._unassigned(
                    required=required,
                    missing=[normalized_owner, *required],
                    candidates=candidates,
                    evidence={**evidence, "failure_reason": "designated_owner_scope_mismatch"},
                )
            if task_scope == "external" and normalized_owner.startswith("internal:"):
                return self._unassigned(
                    required=required,
                    missing=[normalized_owner, *required],
                    candidates=candidates,
                    evidence={**evidence, "failure_reason": "designated_owner_scope_mismatch"},
                )
            exact = [item for item in candidates if item.owner_ref == normalized_owner or item.executor_id == normalized_owner]
            if exact:
                selected = exact[0]
                return self._assigned(selected, required=required, candidates=exact, evidence=evidence)
            return self._unassigned(
                required=required,
                missing=[normalized_owner, *required],
                candidates=candidates,
                evidence={**evidence, "failure_reason": "designated_owner_not_available"},
            )

        matching = [item for item in candidates if _capability_match(required, item.capabilities)]
        if matching:
            selected = sorted(matching, key=lambda item: (item.executor_type != "internal", item.owner_ref))[0]
            return self._assigned(selected, required=required, candidates=matching, evidence=evidence)
        return self._unassigned(
            required=required,
            missing=required or ["executor"],
            candidates=candidates,
            evidence={**evidence, "failure_reason": "no_candidate_satisfies_required_capabilities"},
        )

    @staticmethod
    def _assigned(
        selected: ResourceCandidate,
        *,
        required: list[str],
        candidates: list[ResourceCandidate],
        evidence: dict[str, Any],
    ) -> AssignmentDecision:
        return AssignmentDecision(
            status="assigned",
            owner_ref=selected.owner_ref,
            candidate_owners=[item.owner_ref for item in candidates],
            executor_type=selected.executor_type,
            executor_id=selected.executor_id,
            required_capabilities=required,
            candidates=candidates,
            evidence={
                **evidence,
                "selected_owner_ref": selected.owner_ref,
                "selected_executor_type": selected.executor_type,
                "selected_executor_id": selected.executor_id,
                "bid_proposals": [item.bid_proposal for item in candidates if item.bid_proposal],
            },
        )

    @staticmethod
    def _unassigned(
        *,
        required: list[str],
        missing: list[str],
        candidates: list[ResourceCandidate],
        evidence: dict[str, Any],
    ) -> AssignmentDecision:
        return AssignmentDecision(
            status="resource_gap",
            required_capabilities=required,
            missing_resources=_dedupe(missing),
            candidates=candidates,
            evidence=evidence,
        )

    def _collect_candidates(self) -> list[ResourceCandidate]:
        candidates: list[ResourceCandidate] = []
        candidates.extend(self._internal_plugin_candidates())
        candidates.extend(self._cli_candidates())
        candidates.extend(self._mcp_candidates())
        candidates.extend(self._external_connector_candidates())
        candidates.extend(self._agent_candidates())
        return candidates

    @staticmethod
    def _candidate_counts_by_registry(candidates: list[ResourceCandidate]) -> dict[str, int]:
        counts = {
            "internal_plugin": 0,
            "cli": 0,
            "mcp": 0,
            "external_connector": 0,
            "agent": 0,
        }
        for candidate in candidates:
            executor_type = candidate.executor_type
            if executor_type == "internal":
                counts["internal_plugin"] += 1
            elif executor_type in counts:
                counts[executor_type] += 1
        return counts

    def _internal_plugin_candidates(self) -> list[ResourceCandidate]:
        if self.plugin_service is None or not callable(getattr(self.plugin_service, "get_plugins", None)):
            return []
        rows = self.plugin_service.get_plugins("FUNCTIONAL")
        candidates: list[ResourceCandidate] = []
        for row in rows or []:
            plugin_id = str(row.get("plugin_id") or row.get("id") or "").strip()
            if not plugin_id:
                continue
            lifecycle = str(row.get("lifecycle_status") or "").strip().lower()
            if lifecycle and lifecycle != "active":
                continue
            capabilities = _dedupe(row.get("capabilities") or [])
            candidates.append(
                ResourceCandidate(
                    owner_ref=f"internal:{plugin_id}",
                    executor_type="internal",
                    executor_id=plugin_id,
                    label=plugin_id,
                    capabilities=[*capabilities, plugin_id, row.get("feature_code"), row.get("behavior_key")],
                    metadata={"source": "internal_plugin_registry", "plugin": dict(row)},
                )
            )
        return candidates

    def _cli_candidates(self) -> list[ResourceCandidate]:
        if self.cli_service is None or not callable(getattr(self.cli_service, "list_tools", None)):
            return []
        candidates: list[ResourceCandidate] = []
        for state in self.cli_service.list_tools() or []:
            tool_name = str(getattr(state, "command_name", "") or "").strip()
            if not tool_name or str(getattr(state, "status", "") or "") != "active":
                continue
            health = {
                "healthy": True,
                "status": "active",
                "source": "cli_runtime_state",
            }
            candidates.append(
                ResourceCandidate(
                    owner_ref=f"cli:{tool_name}",
                    executor_type="cli",
                    executor_id=f"cli:{tool_name}",
                    label=tool_name,
                    capabilities=_dedupe(
                        [
                            "external.cli",
                            f"cli:{tool_name}",
                            f"cli.{tool_name}",
                            tool_name,
                            getattr(state, "description", ""),
                            getattr(state, "execution_domain", ""),
                        ]
                    ),
                    metadata={"source": "cli_registry", "health": dict(health)},
                )
            )
        return candidates

    def _mcp_candidates(self) -> list[ResourceCandidate]:
        if self.mcp_service is None or not callable(getattr(self.mcp_service, "list_servers", None)):
            return []
        candidates: list[ResourceCandidate] = []
        for server in self.mcp_service.list_servers() or []:
            server_id = str(getattr(server, "server_id", "") or "").strip()
            if not server_id or str(getattr(server, "status", "") or "") != "online":
                continue
            try:
                health = self.mcp_service.get_server_health(server_id)
            except Exception:
                continue
            if health.get("healthy") is not True or health.get("status") != "online":
                continue
            for tool in getattr(server, "tools", []) or []:
                if str(getattr(tool, "status", "") or "") != "active":
                    continue
                tool_name = str(getattr(tool, "tool_name", "") or "").strip()
                if not tool_name:
                    continue
                candidates.append(
                    ResourceCandidate(
                        owner_ref=f"mcp:{server_id}:{tool_name}",
                        executor_type="mcp",
                        executor_id=f"mcp:{server_id}:{tool_name}",
                        label=f"{server_id}/{tool_name}",
                        capabilities=_dedupe(
                            [
                                "external.mcp",
                                f"mcp:{server_id}:{tool_name}",
                                f"mcp.{server_id}.{tool_name}",
                                tool_name,
                                getattr(tool, "description", ""),
                                getattr(tool, "execution_domain", ""),
                            ]
                        ),
                        metadata={"source": "mcp_registry", "health": dict(health), "server_id": server_id, "tool_name": tool_name},
                    )
                )
        return candidates

    def _external_connector_candidates(self) -> list[ResourceCandidate]:
        service = self.external_connector_service
        if service is None or not callable(getattr(service, "list_connectors", None)):
            return []
        candidates: list[ResourceCandidate] = []
        for connector in service.list_connectors() or []:
            connector_id = str(getattr(connector, "connector_id", "") or "").strip()
            if not connector_id:
                continue
            status = str(getattr(getattr(connector, "status", None), "value", getattr(connector, "status", "")) or "")
            if status != "active":
                continue
            try:
                report = service.health_check(connector_id)
            except Exception:
                continue
            health = str(getattr(getattr(report, "health_status", None), "value", getattr(report, "health_status", "")) or "")
            if health != "healthy":
                continue
            for capability in getattr(connector, "capabilities", []) or []:
                name = str(getattr(capability, "name", "") or "").strip()
                if not name:
                    continue
                candidates.append(
                    ResourceCandidate(
                        owner_ref=f"external_connector:{connector_id}",
                        executor_type="external_connector",
                        executor_id=f"external_connector:{connector_id}",
                        label=f"{connector_id}/{name}",
                        capabilities=_dedupe(
                            [
                                "external.external_connector",
                                f"external_connector:{connector_id}",
                                f"external_connector.{connector_id}.{name}",
                                name,
                                getattr(capability, "description", ""),
                            ]
                        ),
                        metadata={
                            "source": "external_connector_registry",
                            "connector_id": connector_id,
                            "capability": name,
                            "health_status": health,
                        },
                    )
                )
        return candidates

    def _agent_candidates(self) -> list[ResourceCandidate]:
        service = self.agent_service
        if service is None or not callable(getattr(service, "list_active_agents", None)):
            return []
        candidates: list[ResourceCandidate] = []
        for agent in service.list_active_agents() or []:
            agent_id = str(getattr(agent, "agent_id", "") or "").strip()
            if not agent_id:
                continue
            capabilities = _agent_capability_names(agent)
            bid = {
                "type": "BidProposal",
                "agent_id": agent_id,
                "capabilities": capabilities,
                "cost": {
                    "latency_ms": getattr(agent, "latency_ms", None),
                    "success_rate": getattr(agent, "success_rate", None),
                },
                "submitted_at": datetime.now(UTC).isoformat(),
            }
            candidates.append(
                ResourceCandidate(
                    owner_ref=f"agent:{agent_id}",
                    executor_type="agent",
                    executor_id=f"agent:{agent_id}",
                    label=getattr(agent, "agent_name", agent_id),
                    capabilities=_dedupe(["external.agent", f"agent:{agent_id}", f"agent.{agent_id}", *capabilities]),
                    metadata={"source": "agent_registry", "agent_id": agent_id},
                    bid_proposal=bid,
                )
            )
        return candidates


class TaskAssignmentRouter:
    """Persist G31A assignment decisions and G9 resource-gap suspensions."""

    def __init__(self, matcher: ResourceMatcher) -> None:
        self.matcher = matcher

    async def route_assignment_pending_task(
        self,
        task_service: Any,
        task: Any,
        *,
        required_capabilities: Iterable[str],
        required_resources: Iterable[str],
        designated_owner: str = "",
        target_status: TaskStatus = TaskStatus.QUEUED,
    ) -> AssignmentDecision:
        if task.status != TaskStatus.ASSIGNMENT_PENDING:
            raise ValueError(f"G31A assignment router requires assignment_pending, got {task.status}")
        decision = self.matcher.match(
            task=task,
            required_capabilities=required_capabilities,
            required_resources=required_resources,
            designated_owner=designated_owner,
        )
        if decision.assigned:
            await self._persist_assignment(task_service, task, decision, target_status=target_status)
            return decision
        negotiation = await self._suspend_for_resource_gap(task_service, task, decision)
        return AssignmentDecision(
            **{**decision.__dict__, "negotiation": negotiation},
        )

    async def try_resume_suspended_assignment(self, task_service: Any, suspended: Any) -> AssignmentDecision | None:
        context = getattr(suspended, "suspension_context", {}) or {}
        if context.get("feature_code") != "G9" or context.get("blocked_by") != "G31A.ResourceMatcher":
            return None
        task = task_service.get_task(suspended.task_id)
        if task is None:
            return None
        decision = self.matcher.match(
            task=task,
            required_capabilities=context.get("required_capabilities") or [],
            required_resources=context.get("required_resources") or [],
            designated_owner=context.get("designated_owner") or "",
        )
        if not decision.assigned:
            return decision
        await _maybe_await(task_service.resume_task(task.task_id, remarks="G9 recovery condition satisfied by ResourceMatcher"))
        resumed = task_service.get_task(task.task_id)
        if resumed is None:
            raise RuntimeError(f"G9 resumed task {task.task_id}, but readback failed")
        if resumed.status != TaskStatus.ASSIGNMENT_PENDING:
            raise RuntimeError(f"G9 expected resumed task {task.task_id} to return to assignment_pending, got {resumed.status}")
        await self._persist_assignment(task_service, resumed, decision, target_status=TaskStatus.QUEUED)
        return decision

    async def _persist_assignment(
        self,
        task_service: Any,
        task: Any,
        decision: AssignmentDecision,
        *,
        target_status: TaskStatus,
    ) -> None:
        selected = decision.candidates[0] if decision.candidates else None
        metadata = dict(getattr(task, "metadata", {}) or {})
        metadata.update(
            {
                "owner_ref": decision.owner_ref,
                "candidate_owners": decision.candidate_owners,
                "assignment_status": "assigned",
                "resource_matched_by": "G31A.ResourceMatcher",
                "subtask_scheduled_by": "G31A.SubtaskScheduler",
                "worker_dispatch_enabled": True,
                "required_capabilities": decision.required_capabilities,
                "g31a_assignment": {
                    "status": "assigned",
                    "assigned_by": "G31A.TaskAssignmentRouter",
                    "owner_ref": decision.owner_ref,
                    "candidate_owners": decision.candidate_owners,
                    "evidence": decision.evidence,
                    "assigned_at": datetime.now(UTC).isoformat(),
                },
                "g31a_state_transition": {
                    "from_status": TaskStatus.ASSIGNMENT_PENDING.value,
                    "to_status": target_status.value,
                    "reason": "resource_matcher_assigned_owner",
                    "owner_ref": decision.owner_ref,
                },
                "precondition_check": {
                    "status": "passed",
                    "checker": "G31A.PreconditionChecker",
                    "target_id": decision.owner_ref,
                },
                "q9_plugin_binding_source": "validated_by_g31a",
            }
        )
        if selected is not None:
            metadata.update(selected.metadata)
            if decision.executor_type == "cli":
                metadata["cli_tool_name"] = decision.owner_ref.removeprefix("cli:")
            elif decision.executor_type == "mcp":
                parts = decision.owner_ref.split(":", 2)
                if len(parts) >= 2:
                    metadata["mcp_server_id"] = parts[1]
                if len(parts) == 3:
                    metadata["mcp_tool_name"] = parts[2]
            elif decision.executor_type == "external_connector":
                metadata["external_connector_id"] = decision.owner_ref.removeprefix("external_connector:")
                if selected.metadata.get("capability"):
                    metadata["external_connector_capability"] = selected.metadata["capability"]
            elif decision.executor_type == "agent":
                metadata["agent_id"] = decision.owner_ref.removeprefix("agent:")

        task.target_id = decision.owner_ref
        task.task_scope = getattr(task, "task_scope", None)
        task.status = target_status
        task.metadata = metadata
        task.last_updated_at = datetime.now(UTC)
        task_service._shared_tasks.set(task.task_id, task)
        task_service._tasks[task.task_id] = task
        if not task_service._sync_task_to_database(task):
            raise RuntimeError(f"G31A failed to persist assignment for task {task.task_id}")
        refreshed = task_service.get_task(task.task_id)
        if refreshed is None or refreshed.status != target_status or refreshed.metadata.get("owner_ref") != decision.owner_ref:
            raise RuntimeError(f"G31A assignment read-after-write failed for task {task.task_id}")
        task_service._record_audit(
            task.task_id,
            "G31A_SUBTASK_ASSIGNED",
            {
                "owner_ref": decision.owner_ref,
                "candidate_owners": decision.candidate_owners,
                "target_status": target_status.value,
                "required_capabilities": decision.required_capabilities,
            },
        )

    async def _suspend_for_resource_gap(self, task_service: Any, task: Any, decision: AssignmentDecision) -> dict[str, Any]:
        required_asset = ", ".join(decision.missing_resources or decision.required_capabilities or ["executor"])
        recovery_conditions = [
            f"Register and activate a CLI/MCP/external connector/Agent that satisfies: {required_asset}",
            "G31A.ResourceMatcher must verify the executor is query-visible and healthy before queued dispatch.",
        ]
        negotiation = NegotiationRequest(
            target_task_id=task.task_id,
            gap_type="resource_unavailable",
            required_asset=required_asset,
            proposed_tradeoff="Provide the missing permission, connector, CLI/MCP tool, or online Agent; otherwise keep the subtask suspended.",
            priority=3,
        ).model_dump(mode="json")
        negotiation.update(
            {
                "feature_code": "G9",
                "observed_error": "G31A.ResourceMatcher found no real available executor for assignment_pending subtask",
                "recovery_conditions": recovery_conditions,
                "task_context": {
                    "task_id": task.task_id,
                    "title": task.title,
                    "required_capabilities": decision.required_capabilities,
                    "missing_resources": decision.missing_resources,
                    "candidate_owners": [item.owner_ref for item in decision.candidates],
                },
                "resolution": None,
            }
        )
        await _maybe_await(
            task_service.suspend_task(
                task.task_id,
                reason=f"G9 resource gap: {required_asset}",
                recovery_conditions=recovery_conditions,
                suspension_context={
                    "feature_code": "G9",
                    "blocked_by": "G31A.ResourceMatcher",
                    "negotiation_id": negotiation["negotiation_id"],
                    "required_asset": required_asset,
                    "required_capabilities": decision.required_capabilities,
                    "required_resources": decision.evidence.get("required_resources") or [],
                    "designated_owner": decision.evidence.get("designated_owner") or "",
                    "resource_match_evidence": decision.evidence,
                },
            )
        )
        negotiations = _negotiations_from_task(task_service.get_task(task.task_id))
        negotiations.append(negotiation)
        await _maybe_await(
            task_service.update_task_metadata(
                task.task_id,
                {
                    "assignment_status": "suspended_resource_gap",
                    "g5_resource_negotiations": negotiations,
                    "g5_active_negotiation_id": negotiation["negotiation_id"],
                    "g31a_assignment": {
                        "status": "suspended_resource_gap",
                        "assigned_by": "G31A.TaskAssignmentRouter",
                        "missing_resources": decision.missing_resources,
                        "evidence": decision.evidence,
                        "suspended_at": datetime.now(UTC).isoformat(),
                    },
                },
                remarks="G9 resource negotiation request persisted",
            )
        )
        suspended = task_service.get_suspended_task(task.task_id)
        refreshed = task_service.get_task(task.task_id)
        if refreshed is None or refreshed.status != TaskStatus.SUSPENDED or suspended is None:
            raise RuntimeError(f"G9 failed to suspend task {task.task_id} with query-visible recovery context")
        task_service._record_audit(
            task.task_id,
            "G9_RESOURCE_NEGOTIATION_CREATED",
            {
                "negotiation_id": negotiation["negotiation_id"],
                "required_asset": required_asset,
                "recovery_conditions": recovery_conditions,
            },
        )
        return negotiation


def _resource_tokens(resources: Iterable[str]) -> list[str]:
    tokens: list[str] = []
    for item in resources or []:
        text = str(item or "").strip()
        if not text:
            continue
        for prefix in (
            "功能：",
            "功能:",
            "任务资源：",
            "任务资源:",
            "能力需求：",
            "能力需求:",
            "执行方钦定：",
            "执行方钦定:",
        ):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        if text:
            tokens.append(text)
    return _dedupe(tokens)


def _normalize_owner_ref(value: str, *, task_scope: str = "") -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered.startswith("connector:"):
        return f"external_connector:{text.split(':', 1)[1]}"
    if lowered.startswith(("internal:", "cli:", "mcp:", "agent:", "external_connector:")):
        return text
    if lowered.startswith("b4") or "sandbox" in lowered or "沙盒" in lowered:
        return "internal:thought_sandbox"
    if task_scope == "internal":
        return f"internal:{text}"
    return f"external_connector:{text}"


def _task_scope_value(task: Any) -> str:
    raw = getattr(getattr(task, "task_scope", None), "value", getattr(task, "task_scope", ""))
    value = str(raw or "").strip().lower()
    return value if value in {"internal", "external"} else ""


def _is_owner_ref(value: str) -> bool:
    return str(value or "").strip().startswith(_OWNER_PREFIXES)


def _required_owner_refs(required_resources: Iterable[str], *, task_scope: str) -> list[str]:
    refs: list[str] = []
    for item in required_resources or []:
        text = str(item or "").strip()
        if not text:
            continue
        owner_text = ""
        for prefix in ("执行方钦定：", "执行方钦定:"):
            if text.startswith(prefix):
                owner_text = text[len(prefix):].strip()
                break
        if not owner_text and text.startswith(("internal:", "cli:", "mcp:", "agent:", "external_connector:", "connector:")):
            owner_text = text
        if not owner_text:
            continue
        normalized = _normalize_owner_ref(owner_text, task_scope=task_scope)
        if _is_owner_ref(normalized):
            refs.append(normalized)
    return _dedupe(refs)


def _searched_asset_libraries(task_scope: str) -> list[str]:
    if task_scope == "internal":
        return ["internal_plugin"]
    if task_scope == "external":
        return ["cli", "mcp", "external_connector", "agent"]
    return ["internal_plugin", "cli", "mcp", "external_connector", "agent"]


def _capability_match(required: list[str], candidate: list[str]) -> bool:
    if not required:
        return True
    candidate_norm = {_normalize_capability(item) for item in candidate}
    for item in required:
        normalized = _normalize_capability(item)
        if normalized in candidate_norm:
            continue
        if any(normalized and normalized in cap for cap in candidate_norm):
            continue
        return False
    return True


def _normalize_capability(value: Any) -> str:
    return str(value or "").strip().lower().replace("：", ":").replace(" ", "_")


def _agent_capability_names(agent: Any) -> list[str]:
    values: list[str] = []
    for item in getattr(agent, "capabilities", []) or []:
        if isinstance(item, dict):
            values.extend([item.get("name"), item.get("capability"), item.get("description")])
        else:
            values.append(getattr(item, "name", item))
    values.extend(getattr(agent, "service_hooks", []) or [])
    values.extend(getattr(agent, "protocol_capabilities", []) or [])
    values.extend(getattr(agent, "scope", []) or [])
    return _dedupe(values)


def _negotiations_from_task(task: Any) -> list[dict[str, Any]]:
    if task is None:
        return []
    rows = (getattr(task, "metadata", {}) or {}).get("g5_resource_negotiations") or []
    return [dict(item) for item in rows if isinstance(item, dict)]


def _dedupe(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value

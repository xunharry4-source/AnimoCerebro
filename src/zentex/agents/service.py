from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field
from zentex.agents.auth import (
    AgentAuthError,
    AgentAuthService,
    AgentCredentialMetadata,
    public_auth_config,
    redact_sensitive,
)
from zentex.agents.adapters import (
    AgentAdapterError,
    AgentInvocationAdapter,
    AgentInvocationDependencies,
)
from zentex.agents.invocations import (
    AgentInvocationLedger,
    AgentInvocationRecord,
    new_callback_token,
    new_external_task_ref,
)
from zentex.agents.manager import AgentManager, AgentAsset, AgentStatus, AgentTrustLevel
from zentex.agents.bridge import AgentBridge, AgentBridgeError
from zentex.agents.verification import (
    AgentEvidenceBundle,
    AgentVerificationPlan,
    AgentVerificationService,
)
from zentex.external_capabilities import ExternalCapabilityRegistryStore
from zentex.foundation.contracts.service_response import ServiceResponse, ServiceStatus, ServiceErrorCode
from zentex.kernel import BrainTranscriptEntryType
from zentex.tasks.service import TaskStatus, TaskType, ZentexTask

logger = logging.getLogger(__name__)

_TASK_STATUS_ALIASES = {
    "pending": TaskStatus.TODO.value,
    "completed": TaskStatus.DONE.value,
    "in-progress": TaskStatus.IN_PROGRESS.value,
}


def _payload_string(payload: Dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None or value == "":
        return None
    return str(value)


class AgentRegistrationRequest(BaseModel):
    name: str # Technical ID
    agent_name: str # Human readable name
    version: str
    function_description: str
    endpoint: str
    auth_token: Optional[str] = None
    role_tag: str
    trust_level: AgentTrustLevel = AgentTrustLevel.PENDING
    scope: List[str] = Field(default_factory=list)
    adapter_type: str = "legacy_bridge"
    adapter_config: Dict[str, Any] = Field(default_factory=dict)
    auth_config: Dict[str, Any] = Field(default_factory=dict)
    service_hooks: List[str] = Field(default_factory=list)
    # Backward-compatible alias. New integrations should use service_hooks.
    protocol_capabilities: List[str] = Field(default_factory=list)


class AgentCoordinationService:
    """
    Manage Zentex-local external Agent capability entries.

    This service owns local registration, local invocation policy, local
    dispatch, and local audit evidence. It does not own, supervise, certify,
    or promote the external Agent itself.
    """
    
    def __init__(
        self,
        manager: Optional[AgentManager] = None,
        transcript_store: Any = None,
        verification_service: AgentVerificationService | None = None,
        invocation_ledger: AgentInvocationLedger | None = None,
        auth_service: AgentAuthService | None = None,
        registry_store: ExternalCapabilityRegistryStore | None = None,
    ) -> None:
        self.manager = manager or AgentManager()
        self.transcript_store = transcript_store
        self.bridge = AgentBridge()
        self.invocation_adapter = AgentInvocationAdapter(bridge=self.bridge)
        self.verification_service = verification_service or AgentVerificationService()
        self.invocation_ledger = invocation_ledger or AgentInvocationLedger.default()
        self.auth_service = auth_service or AgentAuthService()
        self._registry_store = registry_store or ExternalCapabilityRegistryStore()
        self._restore_registered_agents()

    def _adapter(self) -> AgentInvocationAdapter:
        self.invocation_adapter.bridge = self.bridge
        return self.invocation_adapter

    def _restore_registered_agents(self) -> None:
        for row in self._registry_store.list_current("agent"):
            asset = AgentAsset.model_validate(row["payload"])
            if self.manager.get_asset(asset.agent_id) is None:
                self.manager.add_asset(asset)

    def _persist_agent(self, asset: AgentAsset, *, action: str, operator_id: str | None = None) -> None:
        self._registry_store.upsert_current(
            "agent",
            asset.agent_id,
            asset.model_dump(mode="json"),
            status=asset.status.value,
            display_name=asset.agent_name,
            action=action,
            operator_id=operator_id,
        )

    def seed_demo_agents(self, agents: List[Dict[str, Any]]) -> List[AgentAsset]:
        """Seed local demo agents through the service boundary."""
        seeded_assets: List[AgentAsset] = []
        for payload in agents:
            service_hooks = list(payload.get("service_hooks") or payload.get("protocol_capabilities", []))
            protocol_capabilities = list(payload.get("protocol_capabilities") or service_hooks)
            asset = AgentAsset(
                agent_id=str(payload["agent_id"]),
                name=str(payload["name"]),
                agent_name=str(payload["agent_name"]),
                version=str(payload["version"]),
                function_description=str(payload["function_description"]),
                endpoint=str(payload["endpoint"]),
                auth_token=payload.get("auth_token"),
                role_tag=str(payload["role_tag"]),
                trust_level=AgentTrustLevel(payload.get("trust_level", AgentTrustLevel.PENDING)),
                status=AgentStatus(payload.get("status", AgentStatus.OFFLINE)),
                scope=list(payload.get("scope", [])),
                capabilities=list(payload.get("capabilities", [])),
                adapter_type=str(payload.get("adapter_type", "legacy_bridge")),
                adapter_config=dict(payload.get("adapter_config", {})),
                auth_config=public_auth_config(dict(payload.get("auth_config", {}))),
                service_hooks=service_hooks,
                protocol_capabilities=protocol_capabilities,
                latency_ms=payload.get("latency_ms"),
                success_rate=float(payload.get("success_rate", 1.0)),
            )
            self.manager.add_asset(asset)
            self._persist_agent(asset, action="seed")
            seeded_assets.append(asset)
        return seeded_assets

    def list_active_agents(self) -> List[AgentAsset]:
        """Return local capability entries currently allowed for dispatch."""
        unavailable_statuses = {
            AgentStatus.OFFLINE,
            AgentStatus.HANDSHAKE_FAILED,
            AgentStatus.AUDIT_FAILED,
            AgentStatus.INVOCATION_BLOCKED,
        }
        return [asset for asset in self.manager.list_assets() if asset.status not in unavailable_statuses]

    def record_audit(self, agent_id: str, action: str, details: Dict[str, Any]) -> None:
        """
        Leave a local physical audit trail for Zentex-side decisions/calls.
        """
        if self.transcript_store is None:
            logger.warning(
                "Skipping agent audit record because transcript_store is not attached",
                extra={"agent_id": agent_id, "action": action},
            )
            return
        self.transcript_store.write_entry(
            session_id="agent-management-audit",
            turn_id=str(uuid4()),
            entry_type=BrainTranscriptEntryType.PLUGIN_AUDIT_EVENT,
            source="AgentCoordinationService",
            trace_id=f"agent-audit:{agent_id}:{action.lower()}",
            payload={
                "agent_id": agent_id,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": redact_sensitive(details),
            }
        )

    async def register_agent(
        self,
        request: AgentRegistrationRequest,
        operator_id: str = "web-console-operator"
    ) -> AgentAsset:
        """
        Register an external Agent capability entry in Zentex-local state.

        Optional health probes may improve local status, but they are not a
        registration gate. Service hooks are optional upgrades, not requirements.
        """
        agent_id = str(uuid4())[:8]
        service_hooks = list(request.service_hooks or request.protocol_capabilities)
        protocol_capabilities = list(request.protocol_capabilities or service_hooks)
        asset = AgentAsset(
            agent_id=agent_id,
            name=request.name,
            agent_name=request.agent_name,
            version=request.version,
            function_description=request.function_description,
            endpoint=request.endpoint,
            auth_token=request.auth_token,
            role_tag=request.role_tag,
            trust_level=AgentTrustLevel.PENDING,  # Secure redline: Always start as pending
            status=AgentStatus.OFFLINE,
            scope=request.scope,
            adapter_type=request.adapter_type,
            adapter_config=request.adapter_config,
            auth_config=public_auth_config(request.auth_config),
            service_hooks=service_hooks,
            protocol_capabilities=protocol_capabilities,
        )

        is_reachable: Optional[bool] = None
        if self._should_probe_health(asset):
            is_reachable = await self._adapter().check_health(asset)
            if is_reachable:
                asset.status = AgentStatus.IDLE
                asset.last_ping_at = datetime.now(timezone.utc)

        self.manager.add_asset(asset)
        self._persist_agent(asset, action="register", operator_id=operator_id)

        self.record_audit(agent_id, "REGISTER", {
            "operator_id": operator_id,
            "request": redact_sensitive(request.model_dump(exclude={"auth_token"})),
            "health_probe": is_reachable,
        })

        logger.info(
            "External capability entry %s registered. Optional discovery endpoint: /api/web/agents/%s/handshake",
            agent_id, agent_id,
        )
        return asset

    @staticmethod
    def _should_probe_health(asset: AgentAsset) -> bool:
        hooks = set(getattr(asset, "service_hooks", []) or [])
        hooks.update(getattr(asset, "protocol_capabilities", []) or [])
        if "health_probe" in hooks:
            return True
        config = dict(getattr(asset, "adapter_config", {}) or {})
        if isinstance(config.get("health_probe"), dict):
            return True
        return str(getattr(asset, "adapter_type", "legacy_bridge")) == "legacy_bridge"

    async def perform_handshake(self, agent_id: str) -> ServiceResponse:
        """
        Optionally discover remote capabilities through the configured bridge.

        This updates Zentex-local metadata only. It does not authenticate,
        certify, or promote the external Agent itself.
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            return ServiceResponse.error(ServiceErrorCode.INVALID_ARGUMENT, f"Agent {agent_id} not found")

        logger.info(f"Initiating optional capability discovery for agent entry {agent_id} at {asset.endpoint}")
        trace_id = str(uuid4())
        
        try:
            # Optional remote capability discovery via Bridge
            handshake_data = await self.bridge.perform_handshake(asset)
            
            # Audit first: record the local metadata refresh before state update.
            self.record_audit(agent_id, "CAPABILITY_DISCOVERY_SUCCEEDED", {"data": handshake_data})
            
            self.manager.update_asset(
                agent_id, 
                status=AgentStatus.IDLE, 
                capabilities=handshake_data.get("capabilities", []),
                latency_ms=handshake_data.get("latency_ms"),
                last_ping_at=datetime.now(timezone.utc)
            )
            updated_asset = self.manager.get_asset(agent_id)
            if updated_asset:
                self._persist_agent(updated_asset, action="capability_discovery_succeeded")
            self._registry_store.append_runtime_log(
                "agent",
                agent_id,
                capability_name="handshake",
                invocation_type="perform_handshake",
                status="success",
                request={"endpoint": asset.endpoint},
                response=redact_sensitive(handshake_data),
                trace_id=trace_id,
            )
            
            # Local invocation policy is evaluated separately. Discovery never
            # promotes or certifies the external Agent itself.
            return ServiceResponse.ok(data=handshake_data, trace_id=trace_id)
            
        except AgentBridgeError as exc:
            logger.error(f"Capability discovery failed for agent entry {agent_id}: {exc}", exc_info=True)
            self.record_audit(agent_id, "CAPABILITY_DISCOVERY_FAILED", {"error": str(exc), "status_code": exc.status_code})
            self.manager.update_asset(agent_id, status=AgentStatus.HANDSHAKE_FAILED)
            updated_asset = self.manager.get_asset(agent_id)
            if updated_asset:
                self._persist_agent(updated_asset, action="capability_discovery_failed")
            self._registry_store.append_runtime_log(
                "agent",
                agent_id,
                capability_name="handshake",
                invocation_type="perform_handshake",
                status="failed",
                request={"endpoint": asset.endpoint},
                response={"status_code": exc.status_code},
                error_message=str(exc),
                trace_id=trace_id,
            )
            return self._map_bridge_error(exc, trace_id)
        except Exception as exc:
            logger.error(f"Uncaught exception during capability discovery for agent entry {agent_id}: {exc}", exc_info=True)
            self.record_audit(agent_id, "CAPABILITY_DISCOVERY_CRASHED", {"error": str(exc)})
            self.manager.update_asset(agent_id, status=AgentStatus.HANDSHAKE_FAILED)
            updated_asset = self.manager.get_asset(agent_id)
            if updated_asset:
                self._persist_agent(updated_asset, action="capability_discovery_crashed")
            self._registry_store.append_runtime_log(
                "agent",
                agent_id,
                capability_name="handshake",
                invocation_type="perform_handshake",
                status="failed",
                request={"endpoint": asset.endpoint},
                error_message=str(exc),
                trace_id=trace_id,
            )
            return ServiceResponse.error(ServiceErrorCode.INTERNAL_UNRECOVERABLE, f"Unexpected failure: {exc}", trace_id=trace_id)

    def _map_bridge_error(self, exc: AgentBridgeError, trace_id: str) -> ServiceResponse:
        """Map AgentBridgeError to standard ServiceErrorCode."""
        code = ServiceErrorCode.INTERNAL_UNRECOVERABLE
        if exc.status_code:
            if exc.status_code == 401 or exc.status_code == 403:
                code = ServiceErrorCode.PERMISSION_DENIED
            elif exc.status_code == 404:
                code = ServiceErrorCode.NOT_FOUND
            elif exc.status_code >= 500:
                code = ServiceErrorCode.DEPENDENCY_UNAVAILABLE
            elif exc.status_code == 400:
                code = ServiceErrorCode.INVALID_ARGUMENT
        elif "transport failure" in str(exc).lower() or "timeout" in str(exc).lower():
            code = ServiceErrorCode.DEPENDENCY_UNAVAILABLE
            
        return ServiceResponse.error(code, str(exc), trace_id=trace_id)

    async def evaluate_local_invocation_policy(self, agent_id: str) -> bool:
        """
        Evaluate whether Zentex may call this external capability entry.

        This is a local policy decision. It does not audit, certify, govern, or
        promote the external Agent itself.
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            return False

        logger.info(f"Evaluating local invocation policy for agent entry {agent_id} (trust_level={asset.trust_level})")
        
        # Local policy: fail closed for Zentex-side invocation.
        invocation_allowed = False
        rejection_reason = ""
        
        # 1. Zentex-side connection constraints
        if not asset.endpoint:
            rejection_reason = "Missing endpoint"
        elif (
            str(getattr(asset, "adapter_type", "legacy_bridge")) in {"legacy_bridge", "http_json", "webhook"}
            and not asset.endpoint.startswith("https://")
            and "127.0.0.1" not in asset.endpoint
            and "localhost" not in asset.endpoint
        ):
            rejection_reason = "Local invocation blocked: endpoint violates HTTPS/localhost requirement"
            
        # 2. Zentex-side auth configuration sanity. Public Agents do not need
        # credentials; Agents that declare auth_config must reference a local
        # encrypted credential unless using type=none.
        elif (
            str(getattr(asset, "adapter_type", "legacy_bridge")) in {"legacy_bridge", "http_json", "webhook"}
            and dict(getattr(asset, "auth_config", {}) or {}).get("type") not in {None, "", "none"}
            and not dict(getattr(asset, "auth_config", {}) or {}).get("credential_ref")
        ):
             rejection_reason = "Local invocation blocked: auth_config requires credential_ref"

        # 3. Zentex-side capability scope
        elif not asset.scope:
             rejection_reason = "Local invocation blocked: no defined scope"
            
        else:
            invocation_allowed = True
            
        if invocation_allowed:
            updated = self.manager.update_asset(agent_id, trust_level=AgentTrustLevel.TRUSTED)
            if updated:
                self._persist_agent(updated, action="local_invocation_policy_allowed")
            self.record_audit(agent_id, "LOCAL_INVOCATION_POLICY_ALLOWED", {})
            return True
        else:
            updated = self.manager.update_asset(agent_id, status=AgentStatus.INVOCATION_BLOCKED, trust_level=AgentTrustLevel.REVOKED)
            if updated:
                self._persist_agent(updated, action="local_invocation_policy_blocked")
            self.record_audit(agent_id, "LOCAL_INVOCATION_POLICY_BLOCKED", {"reason": rejection_reason or "Local policy violation"})
            logger.warning(f"Local invocation policy blocked agent entry {agent_id}: {rejection_reason}")
            return False

    async def perform_safety_audit(self, agent_id: str) -> bool:
        """
        Compatibility wrapper for the legacy route name.

        Prefer evaluate_local_invocation_policy(). This method does not audit
        the external Agent itself; it only evaluates Zentex-local invocation
        policy.
        """
        return await self.evaluate_local_invocation_policy(agent_id)

    async def update_policy(self, agent_id: str, trust_level: AgentTrustLevel, scope: List[str]) -> AgentAsset:
        """
        Update trust policy.
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            raise KeyError(f"Agent {agent_id} not found")
            
        # Audit first to ensure trace even if manager update fails
        self.record_audit(agent_id, "POLICY_UPDATED", {
            "trust_level_change": f"{asset.trust_level} -> {trust_level}",
            "scope_change": f"{asset.scope} -> {scope}"
        })

        new_asset = self.manager.update_asset(agent_id, trust_level=trust_level, scope=scope)
        if not new_asset:
             raise KeyError(f"Agent {agent_id} update failed")
        self._persist_agent(new_asset, action="policy_updated")
             
        return new_asset

    async def unregister_agent(self, agent_id: str, operator_id: str = "web-console-operator") -> bool:
        """
        Remove an agent from the registry.
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            return False
            
        success = self.manager.remove_asset(agent_id)
        if success:
            self._registry_store.delete_current(
                "agent",
                agent_id,
                payload=asset.model_dump(mode="json"),
                operator_id=operator_id,
            )
            self.record_audit(agent_id, "UNREGISTER", {
                "operator_id": operator_id,
                "agent_name": asset.agent_name
            })
            logger.info(f"Agent {agent_id} unregistered by {operator_id}")
        return success

    def list_agent_tasks(self, agent_id: str, tasks: List[ZentexTask]) -> List[ZentexTask]:
        return [task for task in tasks if task.target_id == agent_id]

    def build_inbox(self, agent_id: str, tasks: List[ZentexTask]) -> List[ZentexTask]:
        inbox_statuses = {
            TaskStatus.TODO,
            TaskStatus.BLOCKED,
            TaskStatus.WAITING_CONFIRMATION,
        }
        agent_tasks = self.list_agent_tasks(agent_id, tasks)
        return sorted(
            [task for task in agent_tasks if task.status in inbox_statuses],
            key=lambda task: (task.created_at, task.task_id),
            reverse=True,
        )

    def build_assigned_goal(self, agent_id: str, tasks: List[ZentexTask]) -> Optional[str]:
        agent_tasks = self.list_agent_tasks(agent_id, tasks)
        active_tasks = sorted(
            [task for task in agent_tasks if task.status == TaskStatus.IN_PROGRESS],
            key=lambda task: (task.last_updated_at, task.task_id),
            reverse=True,
        )
        if active_tasks:
            return active_tasks[0].title

        queued_tasks = self.build_inbox(agent_id, tasks)
        if queued_tasks:
            return queued_tasks[0].title
        return None

    def build_receipts(self, agent_id: str, tasks: List[ZentexTask]) -> List[ZentexTask]:
        terminal_statuses = {TaskStatus.DONE, TaskStatus.FAILED}
        agent_tasks = self.list_agent_tasks(agent_id, tasks)
        return sorted(
            [task for task in agent_tasks if task.status in terminal_statuses],
            key=lambda task: (task.completed_at or task.last_updated_at, task.task_id),
            reverse=True,
        )

    async def monitor_health(self) -> List[AgentAsset]:
        """
        Periodic health check for all registered agents.
        Updates status based on connectivity.
        """
        updated_assets = []
        for asset in self.manager.list_assets():
            if asset.status == AgentStatus.OFFLINE and not self._should_probe_health(asset):
                updated_assets.append(asset)
                continue
            
            is_healthy = await self._adapter().check_health(asset)
            if is_healthy:
                new_asset = self.manager.update_asset(
                    asset.agent_id, 
                    status=AgentStatus.IDLE, 
                    last_ping_at=datetime.now(timezone.utc)
                )
                if new_asset:
                    self._persist_agent(new_asset, action="health_check_succeeded")
                    updated_assets.append(new_asset)
            else:
                logger.warning(f"Health check failed for agent {asset.agent_id}")
                new_asset = self.manager.update_asset(asset.agent_id, status=AgentStatus.OFFLINE)
                if new_asset:
                    self._persist_agent(new_asset, action="health_check_failed")
                    updated_assets.append(new_asset)
        return updated_assets

    async def dispatch_task(
        self,
        agent_id: str,
        task_payload: Dict[str, Any],
        verification_plan: AgentVerificationPlan | Dict[str, Any] | None = None,
        zentex_task_id: str | None = None,
        idempotency_key: str | None = None,
        *,
        cli_service: Any = None,
        mcp_service: Any = None,
    ) -> ServiceResponse:
        """
        Dispatch a task to an external capability and optionally verify it.
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            return ServiceResponse.error(ServiceErrorCode.INVALID_ARGUMENT, f"Agent {agent_id} not found")
        
        if self._dispatch_block_reason(asset):
            return ServiceResponse.error(ServiceErrorCode.DEPENDENCY_UNAVAILABLE, f"Agent {agent_id} is in status {asset.status}")

        trace_id = str(uuid4())
        invocation_id = trace_id
        external_task_ref = new_external_task_ref()
        zentex_task_id = zentex_task_id or _payload_string(task_payload, "zentex_task_id") or _payload_string(task_payload, "task_id")
        callback_token = new_callback_token() if self._should_enable_callback(asset) else None
        callback_url = self._callback_url(asset, external_task_ref) if callback_token else None
        self.invocation_ledger.create_started(
            external_task_ref=external_task_ref,
            invocation_id=invocation_id,
            agent_id=agent_id,
            zentex_task_id=zentex_task_id,
            trace_id=trace_id,
            adapter_type=str(getattr(asset, "adapter_type", "legacy_bridge") or "legacy_bridge"),
            request_payload={
                **task_payload,
                **({"idempotency_key": idempotency_key} if idempotency_key else {}),
            },
            callback_token=callback_token,
            callback_url=callback_url,
        )
        try:
            invocation = await self._adapter().invoke(
                asset,
                task_payload,
                invocation_id=invocation_id,
                external_task_ref=external_task_ref,
                zentex_task_id=zentex_task_id,
                callback_url=callback_url,
                callback_token=callback_token,
                dependencies=AgentInvocationDependencies(
                    cli_service=cli_service,
                    mcp_service=mcp_service,
                    auth_service=self.auth_service,
                ),
            )
            response_payload: Dict[str, Any] = invocation.model_dump(mode="json")
            verification_payload: Dict[str, Any] | None = None

            if verification_plan is not None:
                plan = (
                    verification_plan
                    if isinstance(verification_plan, AgentVerificationPlan)
                    else AgentVerificationPlan.model_validate(verification_plan)
                )
                evidence = AgentEvidenceBundle(
                    agent_id=agent_id,
                    invocation_id=invocation_id,
                    request_payload=task_payload,
                    normalized_result=invocation.normalized_result,
                    raw_response=invocation.raw_response,
                    metadata={
                        "external_task_ref": external_task_ref,
                        "endpoint": asset.endpoint,
                        "agent_name": asset.agent_name,
                        **redact_sensitive(invocation.adapter_metadata),
                    },
                )
                verification = await self.verification_service.verify(evidence, plan)
                verification_payload = verification.model_dump(mode="json")
                response_payload["verification"] = verification_payload

            self.invocation_ledger.update_result(
                external_task_ref,
                status=invocation.status,
                normalized_result=invocation.normalized_result,
                raw_response=invocation.raw_response,
                verification=verification_payload,
            )

            self.record_audit(
                agent_id,
                "TASK_DISPATCHED",
                {
                    "payload": redact_sensitive(task_payload),
                    "external_task_ref": external_task_ref,
                    "result_summary": str(response_payload.get("normalized_result"))[:100],
                    "verification_summary": response_payload.get("verification"),
                },
            )
            self._registry_store.append_runtime_log(
                "agent",
                agent_id,
                capability_name="dispatch_task",
                invocation_type="dispatch_task",
                status=str(invocation.status),
                request=redact_sensitive(task_payload),
                response=redact_sensitive(response_payload),
                trace_id=trace_id,
            )
            return ServiceResponse.ok(data=response_payload, trace_id=trace_id)
        except AgentAuthError as exc:
            logger.error(f"Agent auth failed for agent {agent_id}: {exc}", exc_info=True)
            self.invocation_ledger.update_result(external_task_ref, status="failed", raw_response={"error": str(exc)})
            self.record_audit(agent_id, "TASK_AUTH_FAILED", {"error": str(exc), "status_code": exc.status_code})
            self._registry_store.append_runtime_log(
                "agent",
                agent_id,
                capability_name="dispatch_task",
                invocation_type="dispatch_task",
                status="failed",
                request=redact_sensitive(task_payload),
                error_message=str(exc),
                trace_id=trace_id,
            )
            return ServiceResponse.error(exc.code, str(exc), trace_id=trace_id)
        except AgentAdapterError as exc:
            logger.error(f"Task dispatch failed for agent {agent_id}: {exc}", exc_info=True)
            self.invocation_ledger.update_result(external_task_ref, status="failed", raw_response={"error": str(exc)})
            self.record_audit(agent_id, "TASK_FAILED", {"error": str(exc), "status_code": exc.status_code})
            self._registry_store.append_runtime_log(
                "agent",
                agent_id,
                capability_name="dispatch_task",
                invocation_type="dispatch_task",
                status="failed",
                request=redact_sensitive(task_payload),
                error_message=str(exc),
                trace_id=trace_id,
            )
            return ServiceResponse.error(exc.code, str(exc), trace_id=trace_id)
        except AgentBridgeError as exc:
            logger.error(f"Task dispatch failed for agent {agent_id}: {exc}", exc_info=True)
            self.invocation_ledger.update_result(external_task_ref, status="failed", raw_response={"error": str(exc)})
            self.record_audit(agent_id, "TASK_FAILED", {"error": str(exc), "status_code": exc.status_code})
            self._registry_store.append_runtime_log(
                "agent",
                agent_id,
                capability_name="dispatch_task",
                invocation_type="dispatch_task",
                status="failed",
                request=redact_sensitive(task_payload),
                error_message=str(exc),
                trace_id=trace_id,
            )
            return self._map_bridge_error(exc, trace_id)
        except Exception as exc:
            logger.error(f"Uncaught exception during task dispatch for agent {agent_id}: {exc}", exc_info=True)
            self.invocation_ledger.update_result(external_task_ref, status="failed", raw_response={"error": str(exc)})
            self.record_audit(agent_id, "TASK_CRASHED", {"error": str(exc)})
            self._registry_store.append_runtime_log(
                "agent",
                agent_id,
                capability_name="dispatch_task",
                invocation_type="dispatch_task",
                status="failed",
                request=redact_sensitive(task_payload),
                error_message=str(exc),
                trace_id=trace_id,
            )
            return ServiceResponse.error(ServiceErrorCode.INTERNAL_UNRECOVERABLE, f"Unexpected failure: {exc}", trace_id=trace_id)

    def get_invocation_by_external_task_ref(self, external_task_ref: str) -> AgentInvocationRecord | None:
        return self.invocation_ledger.get_by_external_task_ref(external_task_ref)

    def list_invocations_for_agent(self, agent_id: str, *, limit: int = 100) -> List[AgentInvocationRecord]:
        return self.invocation_ledger.list_by_agent_id(agent_id, limit=limit)

    def list_invocations_for_task(self, zentex_task_id: str, *, limit: int = 100) -> List[AgentInvocationRecord]:
        return self.invocation_ledger.list_by_zentex_task_id(zentex_task_id, limit=limit)

    def public_auth_config_for_agent(self, agent_id: str) -> Dict[str, Any]:
        asset = self.manager.get_asset(agent_id)
        if not asset:
            raise KeyError(f"Agent {agent_id} not found")
        summary = public_auth_config(getattr(asset, "auth_config", {}) or {})
        if summary.get("credential_ref"):
            metadata = self.auth_service.vault.get_metadata(str(summary["credential_ref"]))
            if metadata is not None:
                summary["last_auth_status"] = metadata.last_auth_status
                summary["expires_at"] = metadata.expires_at
        return summary

    def store_agent_credential(
        self,
        agent_id: str,
        *,
        credential_type: str,
        secret_payload: Dict[str, Any],
        credential_id: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> AgentCredentialMetadata:
        if not self.manager.get_asset(agent_id):
            raise KeyError(f"Agent {agent_id} not found")
        record = self.auth_service.store_credential(
            agent_id=agent_id,
            credential_type=credential_type,
            secret_payload=secret_payload,
            credential_id=credential_id,
            metadata=metadata,
        )
        self.record_audit(
            agent_id,
            "AGENT_CREDENTIAL_STORED",
            {
                "credential_id": record.credential_id,
                "credential_type": credential_type,
                "metadata": metadata or {},
            },
        )
        return record

    def store_integration_credential(
        self,
        owner_type: str,
        owner_id: str,
        *,
        credential_type: str,
        secret_payload: Dict[str, Any],
        credential_id: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> AgentCredentialMetadata:
        if owner_type not in {"agent", "cli", "mcp"}:
            raise ValueError(f"Unsupported credential owner_type: {owner_type}")
        agent_id = owner_id if owner_type == "agent" else f"{owner_type}:{owner_id}"
        record = self.auth_service.store_credential(
            agent_id=agent_id,
            owner_type=owner_type,
            owner_id=owner_id,
            credential_type=credential_type,
            secret_payload=secret_payload,
            credential_id=credential_id,
            metadata=metadata,
        )
        self.record_audit(
            agent_id,
            "INTEGRATION_CREDENTIAL_STORED",
            {"owner_type": owner_type, "owner_id": owner_id, "credential_id": record.credential_id, "credential_type": credential_type},
        )
        return record

    def list_integration_credentials(self, owner_type: str, owner_id: str) -> List[AgentCredentialMetadata]:
        if owner_type not in {"agent", "cli", "mcp"}:
            raise ValueError(f"Unsupported credential owner_type: {owner_type}")
        return self.auth_service.vault.list_metadata_for_owner(owner_type, owner_id)

    def delete_integration_credential(self, owner_type: str, owner_id: str, credential_id: str) -> bool:
        if owner_type not in {"agent", "cli", "mcp"}:
            raise ValueError(f"Unsupported credential owner_type: {owner_type}")
        return self.auth_service.delete_credential_for_owner(
            owner_type=owner_type,
            owner_id=owner_id,
            credential_id=credential_id,
        )

    async def test_integration_auth(
        self,
        owner_type: str,
        owner_id: str,
        *,
        auth_config: Dict[str, Any],
        endpoint: str = "",
        force_refresh: bool = False,
    ) -> ServiceResponse:
        if owner_type not in {"agent", "cli", "mcp"}:
            return ServiceResponse.error(ServiceErrorCode.INVALID_ARGUMENT, f"Unsupported credential owner_type: {owner_type}")
        try:
            resolved = await self.auth_service.resolve_owner(
                owner_type=owner_type,
                owner_id=owner_id,
                auth_config=auth_config,
                endpoint=endpoint,
                force_refresh=force_refresh,
            )
        except AgentAuthError as exc:
            return ServiceResponse.error(exc.code, str(exc))
        return ServiceResponse.ok(
            data={
                "auth_type": resolved.metadata.get("auth_type"),
                "credential_ref": resolved.metadata.get("credential_ref"),
                "headers": redact_sensitive(resolved.headers),
                "query": redact_sensitive(resolved.query),
                "env": redact_sensitive(resolved.env),
                "refreshable": resolved.refreshable,
            }
        )

    def list_agent_credentials(self, agent_id: str) -> List[AgentCredentialMetadata]:
        if not self.manager.get_asset(agent_id):
            raise KeyError(f"Agent {agent_id} not found")
        return self.auth_service.vault.list_metadata(agent_id)

    def delete_agent_credential(self, agent_id: str, credential_id: str) -> bool:
        if not self.manager.get_asset(agent_id):
            raise KeyError(f"Agent {agent_id} not found")
        deleted = self.auth_service.delete_credential(agent_id=agent_id, credential_id=credential_id)
        if deleted:
            self.record_audit(agent_id, "AGENT_CREDENTIAL_DELETED", {"credential_id": credential_id})
        return deleted

    async def test_agent_auth(self, agent_id: str, *, force_refresh: bool = False) -> ServiceResponse:
        asset = self.manager.get_asset(agent_id)
        if not asset:
            return ServiceResponse.error(ServiceErrorCode.INVALID_ARGUMENT, f"Agent {agent_id} not found")
        try:
            resolved = await self.auth_service.resolve(asset, force_refresh=force_refresh)
        except AgentAuthError as exc:
            self.record_audit(agent_id, "AGENT_AUTH_TEST_FAILED", {"error": str(exc), "status_code": exc.status_code})
            return ServiceResponse.error(exc.code, str(exc))
        payload = {
            "auth_type": resolved.metadata.get("auth_type"),
            "credential_ref": resolved.metadata.get("credential_ref"),
            "headers": redact_sensitive(resolved.headers),
            "query": redact_sensitive(resolved.query),
            "cookies": redact_sensitive(resolved.cookies),
            "body_fields": redact_sensitive(resolved.body_fields),
            "refreshable": resolved.refreshable,
        }
        self.record_audit(agent_id, "AGENT_AUTH_TEST_SUCCEEDED", payload)
        return ServiceResponse.ok(data=payload)

    async def receive_callback_result(
        self,
        external_task_ref: str,
        *,
        callback_token: str,
        status: str,
        normalized_result: Any = None,
        raw_response: Any = None,
    ) -> ServiceResponse:
        allowed = {"submitted", "running", "waiting_external_human_review", "completed", "failed", "uncertain"}
        if status not in allowed:
            return ServiceResponse.error(ServiceErrorCode.INVALID_ARGUMENT, f"Unsupported callback status: {status}")
        try:
            record = self.invocation_ledger.update_callback(
                external_task_ref,
                token=callback_token,
                status=status,
                normalized_result=normalized_result,
                raw_response=raw_response,
            )
        except PermissionError as exc:
            return ServiceResponse.error(ServiceErrorCode.PERMISSION_DENIED, str(exc))
        if record is None:
            return ServiceResponse.error(ServiceErrorCode.INVALID_ARGUMENT, f"Invocation {external_task_ref} not found")
        self.record_audit(
            record.agent_id,
            "TASK_CALLBACK_RECEIVED",
            {"external_task_ref": external_task_ref, "status": status},
        )
        return ServiceResponse.ok(data=record.model_dump(mode="json"), trace_id=record.trace_id)

    @staticmethod
    def _should_enable_callback(asset: AgentAsset) -> bool:
        hooks = set(getattr(asset, "service_hooks", []) or [])
        hooks.update(getattr(asset, "protocol_capabilities", []) or [])
        config = dict(getattr(asset, "adapter_config", {}) or {})
        return "callback_result" in hooks or bool(config.get("enable_callback") or config.get("callback"))

    @staticmethod
    def _callback_url(asset: AgentAsset, external_task_ref: str) -> str:
        config = dict(getattr(asset, "adapter_config", {}) or {})
        path = f"/api/web/agents/callbacks/{external_task_ref}"
        base_url = str(config.get("callback_base_url") or "").strip()
        if base_url:
            return base_url.rstrip("/") + path
        return path

    def _dispatch_block_reason(self, asset: AgentAsset) -> str:
        if asset.status in [AgentStatus.HANDSHAKE_FAILED, AgentStatus.AUDIT_FAILED, AgentStatus.INVOCATION_BLOCKED]:
            return str(asset.status)
        if asset.status == AgentStatus.OFFLINE and str(getattr(asset, "adapter_type", "legacy_bridge")) == "legacy_bridge":
            return str(asset.status)
        return ""

    def calculate_credit_score(
        self,
        agent_id: str,
        task_service: Any,
    ) -> Dict[str, Any]:
        """
        Calculate credit score for an agent based on multiple dimensions.
        Core logic moved from web_console for architectural alignment.
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            raise KeyError(f"Agent {agent_id} not found")
        
        total_tasks = task_service.count_tasks(target_id=agent_id)
        completed_tasks = task_service.count_tasks(target_id=agent_id, status=TaskStatus.DONE)
        failed_tasks = task_service.count_tasks(target_id=agent_id, status=TaskStatus.FAILED)

        # POLICY[no-fake-impl]: return None total_score when there is no task history.
        # An agent that has never run a task has no earned score — not a perfect score.
        if total_tasks == 0:
            return {
                "total_score": None,
                "dimensions": [
                    {"id": "completion", "label": "Task Completion", "score": None, "weight": 0.30,
                     "description": "No task history"},
                    {"id": "latency", "label": "Latency", "score": None, "weight": 0.25,
                     "description": "No latency data"},
                    {"id": "error_rate", "label": "Error Rate", "score": None, "weight": 0.20,
                     "description": "No task history"},
                    {"id": "local_invocation_policy", "label": "Local Invocation Policy",
                     "score": None, "weight": 0.15,
                     "description": f"Trust Level: {asset.trust_level}"},
                    {"id": "stability", "label": "Stability", "score": None, "weight": 0.10,
                     "description": "No task history"},
                ],
            }

        # Dimension 1: Task Completion Rate (30% weight)
        completion_rate = completed_tasks / total_tasks * 100
        completion_score = min(completion_rate, 100)

        # Dimension 2: Response Latency Score (25% weight)
        latency_ms = asset.latency_ms
        if latency_ms is None:
            # No measured latency yet — do not fabricate a score; use 0.
            latency_score = 0.0
            latency_desc = "No latency data"
        elif latency_ms < 100:
            latency_score = 100.0
            latency_desc = f"Avg Latency {latency_ms}ms"
        elif latency_ms < 500:
            latency_score = 80.0
            latency_desc = f"Avg Latency {latency_ms}ms"
        else:
            latency_score = 60.0
            latency_desc = f"Avg Latency {latency_ms}ms"

        # Dimension 3: Error Rate Score (20% weight)
        error_rate = failed_tasks / total_tasks
        error_score = max((1 - error_rate) * 100, 0)

        # Dimension 4: Zentex-local invocation policy score (15% weight)
        trust_level_scores = {
            AgentTrustLevel.TRUSTED.value: 100,
            AgentTrustLevel.PENDING.value: 40,
            AgentTrustLevel.RESTRICTED.value: 50,
            AgentTrustLevel.REVOKED.value: 0,
            AgentTrustLevel.UNKNOWN.value: 20,
        }
        audit_score = trust_level_scores.get(str(asset.trust_level.value), 20)

        # Dimension 5: Historical Stability Score (10% weight).
        # Only meaningful once there are tasks; we derive from completed/total, not the
        # default success_rate=1.0 on the asset which is an uninitialised placeholder.
        stability_score = (completed_tasks / total_tasks) * 100

        total_score = (
            completion_score * 0.30 +
            latency_score * 0.25 +
            error_score * 0.20 +
            audit_score * 0.15 +
            stability_score * 0.10
        )

        return {
            "total_score": round(total_score, 2),
            "dimensions": [
                {
                    "id": "completion",
                    "label": "Task Completion",
                    "score": round(completion_score, 2),
                    "weight": 0.30,
                    "description": f"Completed {completed_tasks}/{total_tasks} tasks",
                },
                {
                    "id": "latency",
                    "label": "Latency",
                    "score": round(latency_score, 2),
                    "weight": 0.25,
                    "description": latency_desc,
                },
                {
                    "id": "error_rate",
                    "label": "Error Rate",
                    "score": round(error_score, 2),
                    "weight": 0.20,
                    "description": f"Failure rate {error_rate * 100:.1f}%",
                },
                {
                    "id": "local_invocation_policy",
                    "label": "Local Invocation Policy",
                    "score": round(audit_score, 2),
                    "weight": 0.15,
                    "description": f"Trust Level: {asset.trust_level}",
                },
                {
                    "id": "stability",
                    "label": "Stability",
                    "score": round(stability_score, 2),
                    "weight": 0.10,
                    "description": f"Completion rate {stability_score:.1f}%",
                },
            ],
        }

    def get_statistics(
        self,
        agent_id: str,
        task_service: Any,
    ) -> Dict[str, Any]:
        """Aggregate performance statistics for an agent."""
        total_tasks = task_service.count_tasks(target_id=agent_id)
        completed_tasks = task_service.count_tasks(target_id=agent_id, status=TaskStatus.DONE)
        failed_tasks = task_service.count_tasks(target_id=agent_id, status=TaskStatus.FAILED)
        in_progress_tasks = task_service.count_tasks(target_id=agent_id, status=TaskStatus.IN_PROGRESS)
        pending_tasks = total_tasks - completed_tasks - failed_tasks - in_progress_tasks
        
        # Avg completion time
        completed_with_time = [
            t for t in task_service.list_tasks(target_id=agent_id, status=TaskStatus.DONE, limit=500, offset=0)
            if t.started_at and t.completed_at
        ]
        avg_completion_time = (
            sum((t.completed_at - t.started_at).total_seconds() for t in completed_with_time) / len(completed_with_time)
            if completed_with_time else 0
        )

        # uptime_percentage: not tracked — no server-side heartbeat log available.
        # Callers must not display this field as if it were real uptime data.
        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "in_progress_tasks": in_progress_tasks,
            "pending_tasks": max(0, pending_tasks),
            "avg_completion_time": round(avg_completion_time, 2),
            "uptime_percentage": None,  # POLICY[no-fake-impl]: real uptime unavailable
        }

    def query_agent_tasks(
        self,
        agent_id: str,
        task_service: Any,
        *,
        status_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "started_at",
        order: str = "desc",
        search: str = "",
        task_type: str = "",
        originator: str = "",
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Advanced task querying with filtering and pagination.
        Migrated from web_console for zero-logic UI.
        """
        status_values = [
            _TASK_STATUS_ALIASES.get(s.strip().lower(), s.strip().lower())
            for s in status_filter.split(",")
        ] if status_filter else []
        db_status = TaskStatus(status_values[0]) if len(status_values) == 1 and status_values[0] else None
        db_task_type = TaskType(task_type) if task_type else None
        offset = max(0, (page - 1) * page_size)

        can_page_in_db = not search and not date_from and not date_to and sort_by == "started_at" and order.lower() == "desc"
        if can_page_in_db:
            total = task_service.count_tasks(
                target_id=agent_id,
                status=db_status,
                task_type=db_task_type,
                originator_id=originator or None,
            )
            tasks = task_service.list_tasks(
                target_id=agent_id,
                status=db_status,
                task_type=db_task_type,
                originator_id=originator or None,
                limit=page_size,
                offset=offset,
            )
            total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
            return {
                "tasks": tasks,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                }
            }

        tasks = task_service.list_tasks(
            target_id=agent_id,
            status=db_status,
            task_type=db_task_type,
            originator_id=originator or None,
            limit=500,
            offset=0,
        )
        
        # 2. Status filter
        if status_filter:
            statuses = [s.strip().lower() for s in status_filter.split(",")]
            tasks = [t for t in tasks if str(t.status.value).lower() in statuses]
            
        # 3. Search
        if search:
            search_lower = search.lower()
            tasks = [
                t for t in tasks
                if search_lower in (t.title or "").lower() or search_lower in (t.task_id or "").lower()
            ]
            
        # 4. Dimension filters
        if task_type:
            tasks = [t for t in tasks if str(t.task_type.value).lower() == task_type.lower()]
        if originator:
            tasks = [t for t in tasks if t.originator_id == originator]
            
        # 5. Date filters
        if date_from:
            tasks = [t for t in tasks if t.started_at and t.started_at >= date_from]
        if date_to:
            tasks = [t for t in tasks if t.started_at and t.started_at <= date_to]
            
        # 6. Sorting
        reverse = order.lower() == "desc"
        if sort_by == "completed_at":
            tasks.sort(key=lambda t: t.completed_at or datetime.min.replace(tzinfo=timezone.utc), reverse=reverse)
        elif sort_by == "priority":
            tasks.sort(key=lambda t: getattr(t, 'priority', 0), reverse=reverse)
        else: # Default: started_at
            tasks.sort(key=lambda t: t.started_at or datetime.min.replace(tzinfo=timezone.utc), reverse=reverse)
            
        # 7. Pagination
        total = len(tasks)
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_tasks = tasks[start_idx:end_idx]
        
        return {
            "tasks": paginated_tasks,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            }
        }


__all__ = [
    "AgentCoordinationService",
    "AgentRegistrationRequest",
    "AgentManager",
    "AgentAsset",
    "AgentStatus",
    "AgentTrustLevel",
]


# Global singleton instance for agents service
_default_service: Optional[AgentCoordinationService] = None


def get_service() -> AgentCoordinationService:
    """Standard service factory function for launcher assembly.
    
    Returns the global AgentCoordinationService instance, creating it if necessary.
    This function is required by the SystemAssembler to initialize the agents service.
    
    Note: This creates a minimal instance. For full initialization with dependencies,
    use the AgentCoordinationService constructor directly or initialize via the kernel.
    """
    global _default_service
    if _default_service is None:
        # Create a minimal instance - will be properly initialized by kernel
        _default_service = AgentCoordinationService(
            manager=None,  # Will use default AgentManager
            transcript_store=None,  # Will be set by kernel
        )
    return _default_service

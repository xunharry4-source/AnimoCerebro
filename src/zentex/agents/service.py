from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field
from zentex.agents.manager import AgentManager, AgentAsset, AgentStatus, AgentTrustLevel
from zentex.agents.bridge import AgentBridge, AgentBridgeError
from zentex.foundation.contracts.service_response import ServiceResponse, ServiceStatus, ServiceErrorCode
from zentex.kernel import BrainTranscriptEntryType
from zentex.tasks.service import TaskStatus, TaskType, ZentexTask

logger = logging.getLogger(__name__)

_TASK_STATUS_ALIASES = {
    "pending": TaskStatus.TODO.value,
    "completed": TaskStatus.DONE.value,
    "in-progress": TaskStatus.IN_PROGRESS.value,
}


class AgentRegistrationRequest(BaseModel):
    name: str # Technical ID
    agent_name: str # Human readable name
    version: str
    function_description: str
    endpoint: str
    auth_token: str
    role_tag: str
    trust_level: AgentTrustLevel = AgentTrustLevel.PENDING
    scope: List[str] = Field(default_factory=list)


class AgentCoordinationService:
    """
    Establish secure coordination with external Agents.
    Enforces mandatory handshake and security audit before enabling assets.
    """
    
    def __init__(self, manager: Optional[AgentManager] = None, transcript_store: Any = None) -> None:
        self.manager = manager or AgentManager()
        self.transcript_store = transcript_store
        self.bridge = AgentBridge()

    def seed_demo_agents(self, agents: List[Dict[str, Any]]) -> List[AgentAsset]:
        """Seed local demo agents through the service boundary."""
        seeded_assets: List[AgentAsset] = []
        for payload in agents:
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
                latency_ms=payload.get("latency_ms"),
                success_rate=float(payload.get("success_rate", 1.0)),
            )
            self.manager.add_asset(asset)
            seeded_assets.append(asset)
        return seeded_assets

    def list_active_agents(self) -> List[AgentAsset]:
        """Return agents that are currently usable for task dispatch."""
        unavailable_statuses = {
            AgentStatus.OFFLINE,
            AgentStatus.HANDSHAKE_FAILED,
            AgentStatus.AUDIT_FAILED,
        }
        return [asset for asset in self.manager.list_assets() if asset.status not in unavailable_statuses]

    def record_audit(self, agent_id: str, action: str, details: Dict[str, Any]) -> None:
        """
        Leave a permanent physical audit trail.
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
                "details": details,
            }
        )

    async def register_agent(
        self,
        request: AgentRegistrationRequest,
        operator_id: str = "web-console-operator"
    ) -> AgentAsset:
        """
        Mandatory Step 1: Securely register a new agent.

        Fail-closed: the agent endpoint is health-probed before the asset is
        added to the registry.  An unreachable endpoint raises AgentBridgeError
        which the router maps to HTTP 400.
        """
        agent_id = str(uuid4())[:8]
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
        )

        # Connectivity check — must pass before we store the asset.
        is_reachable = await self.bridge.check_health(asset)
        if not is_reachable:
            raise AgentBridgeError(
                f"Agent endpoint '{request.endpoint}' is not reachable. "
                "Ensure the agent is running and the endpoint is correct before registering."
            )

        self.manager.add_asset(asset)

        self.record_audit(agent_id, "REGISTER", {
            "operator_id": operator_id,
            "request": request.model_dump(exclude={"auth_token"}),
        })

        logger.info(
            "Agent %s registered. Trigger handshake via /api/web/agents/%s/handshake",
            agent_id, agent_id,
        )
        return asset

    async def perform_handshake(self, agent_id: str) -> ServiceResponse:
        """
        Step 2: Capabilities Discovery (Handshake).
        Uses AgentBridge to communicate with external agent.
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            return ServiceResponse.error(ServiceErrorCode.INVALID_ARGUMENT, f"Agent {agent_id} not found")

        logger.info(f"Initiating handshake for agent {agent_id} at {asset.endpoint}")
        trace_id = str(uuid4())
        
        try:
            # Real network handshake via Bridge
            handshake_data = await self.bridge.perform_handshake(asset)
            
            # Audit first: record the discovery before promoting state
            self.record_audit(agent_id, "HANDSHAKE_SUCCESS", {"data": handshake_data})
            
            self.manager.update_asset(
                agent_id, 
                status=AgentStatus.IDLE, 
                capabilities=handshake_data.get("capabilities", []),
                latency_ms=handshake_data.get("latency_ms"),
                last_ping_at=datetime.now(timezone.utc)
            )
            
            # Safety audit is NOT triggered automatically here.
            # Callers must invoke /agents/{id}/safety-audit explicitly after handshake.
            return ServiceResponse.ok(data=handshake_data, trace_id=trace_id)
            
        except AgentBridgeError as exc:
            logger.error(f"Handshake failed for agent {agent_id}: {exc}", exc_info=True)
            self.record_audit(agent_id, "HANDSHAKE_FAILED", {"error": str(exc), "status_code": exc.status_code})
            self.manager.update_asset(agent_id, status=AgentStatus.HANDSHAKE_FAILED)
            return self._map_bridge_error(exc, trace_id)
        except Exception as exc:
            logger.error(f"Uncaught exception during handshake for agent {agent_id}: {exc}", exc_info=True)
            self.record_audit(agent_id, "HANDSHAKE_CRASHED", {"error": str(exc)})
            self.manager.update_asset(agent_id, status=AgentStatus.HANDSHAKE_FAILED)
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

    async def perform_safety_audit(self, agent_id: str) -> bool:
        """
        Step 3: Security & Cloud Audit Redline.
        Mandatory verification before promotion to 执行池 (execution pool).
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            return False

        logger.info(f"Running safety audit for agent {agent_id} (trust_level={asset.trust_level})")
        
        # POLICY: Fail-Closed. Rejection is the default.
        compliance_check = False
        rejection_reason = ""
        
        # 1. Connection Security Constraints
        if not asset.endpoint:
            rejection_reason = "Missing endpoint"
        elif not asset.endpoint.startswith("https://") and "127.0.0.1" not in asset.endpoint and "localhost" not in asset.endpoint:
            rejection_reason = "Insecure connection: Endpoint violates mandatory HTTPS/Localhost requirement"
            
        # 2. Authentication Integrity
        elif not asset.auth_token:
             rejection_reason = "Authentication token absent"
             
        # 3. Operational Presence
        elif not asset.scope:
             rejection_reason = "Agent has no defined operational scope (empty manifest)"
            
        else:
            # Audit Passed: All mandatory security gates cleared.
            compliance_check = True
            
        if compliance_check:
            # Promotion to TRUSTED is only possible if audit passes
            self.manager.update_asset(agent_id, trust_level=AgentTrustLevel.TRUSTED)
            self.record_audit(agent_id, "AUDIT_PASSED", {})
            return True
        else:
            self.manager.update_asset(agent_id, status=AgentStatus.AUDIT_FAILED, trust_level=AgentTrustLevel.REVOKED)
            self.record_audit(agent_id, "AUDIT_FAILED", {"reason": rejection_reason or "Policy Violation"})
            logger.warning(f"Safety Audit REJECTED for agent {agent_id}: {rejection_reason}")
            return False

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
            if asset.status == AgentStatus.OFFLINE:
                updated_assets.append(asset)
                continue
            
            is_healthy = await self.bridge.check_health(asset)
            if is_healthy:
                new_asset = self.manager.update_asset(
                    asset.agent_id, 
                    status=AgentStatus.IDLE, 
                    last_ping_at=datetime.now(timezone.utc)
                )
                if new_asset:
                    updated_assets.append(new_asset)
            else:
                logger.warning(f"Health check failed for agent {asset.agent_id}")
                new_asset = self.manager.update_asset(asset.agent_id, status=AgentStatus.OFFLINE)
                if new_asset:
                    updated_assets.append(new_asset)
        return updated_assets

    async def dispatch_task(self, agent_id: str, task_payload: Dict[str, Any]) -> ServiceResponse:
        """
        Dispatch a task to an external agent via the Bridge.
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            return ServiceResponse.error(ServiceErrorCode.INVALID_ARGUMENT, f"Agent {agent_id} not found")
        
        if asset.status in [AgentStatus.OFFLINE, AgentStatus.HANDSHAKE_FAILED, AgentStatus.AUDIT_FAILED]:
            return ServiceResponse.error(ServiceErrorCode.DEPENDENCY_UNAVAILABLE, f"Agent {agent_id} is in status {asset.status}")

        trace_id = str(uuid4())
        try:
            result = await self.bridge.execute_task(asset, task_payload)
            self.record_audit(agent_id, "TASK_DISPATCHED", {"payload": task_payload, "result_summary": str(result)[:100]})
            return ServiceResponse.ok(data=result, trace_id=trace_id)
        except AgentBridgeError as exc:
            logger.error(f"Task dispatch failed for agent {agent_id}: {exc}", exc_info=True)
            self.record_audit(agent_id, "TASK_FAILED", {"error": str(exc), "status_code": exc.status_code})
            return self._map_bridge_error(exc, trace_id)
        except Exception as exc:
            logger.error(f"Uncaught exception during task dispatch for agent {agent_id}: {exc}", exc_info=True)
            self.record_audit(agent_id, "TASK_CRASHED", {"error": str(exc)})
            return ServiceResponse.error(ServiceErrorCode.INTERNAL_UNRECOVERABLE, f"Unexpected failure: {exc}", trace_id=trace_id)

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
                    {"id": "audit", "label": "Audit Compliance",
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

        # Dimension 4: Audit Compliance Score (15% weight)
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
                    "id": "audit",
                    "label": "Audit Compliance",
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

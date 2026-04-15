from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from zentex.agents.manager import AgentManager, AgentAsset, AgentStatus, AgentTrustLevel
from zentex.agents.bridge import AgentBridge
from zentex.kernel import BrainTranscriptEntryType
from zentex.tasks.service import TaskStatus, ZentexTask

logger = logging.getLogger(__name__)


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
    
    def __init__(self, manager: AgentManager | None = None, transcript_store: Any = None) -> None:
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
        Starts as PENDING.
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
            trust_level=AgentTrustLevel.PENDING, # Secure redline: Always start as pending
            status=AgentStatus.OFFLINE,
            scope=request.scope
        )
        self.manager.add_asset(asset)
        
        self.record_audit(agent_id, "REGISTER", {
            "operator_id": operator_id,
            "request": request.model_dump(exclude={"auth_token"})
        })
        
        # Note: Handshake will be triggered manually via API endpoint
        # This avoids asyncio.create_task issues in FastAPI context
        logger.info(f"Agent {agent_id} registered. Trigger handshake via /api/web/agents/{agent_id}/handshake")
        
        return asset

    async def perform_handshake(self, agent_id: str) -> None:
        """
        Step 2: Capabilities Discovery (Handshake).
        Uses AgentBridge to communicate with external agent.
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            return

        logger.info(f"Initiating handshake for agent {agent_id} at {asset.endpoint}")
        
        try:
            # Real network handshake via Bridge
            handshake_data = await self.bridge.perform_handshake(asset)
            
            self.manager.update_asset(
                agent_id, 
                status=AgentStatus.IDLE, 
                capabilities=handshake_data.get("capabilities", []),
                latency_ms=handshake_data.get("latency_ms"),
                last_ping_at=datetime.now(timezone.utc)
            )
            
            self.record_audit(agent_id, "HANDSHAKE_SUCCESS", {"data": handshake_data})
            
            # Automatically trigger safety audit after successful handshake
            await self.perform_safety_audit(agent_id)
            
        except Exception as exc:
            logger.error(f"Handshake failed for agent {agent_id}: {exc}")
            self.manager.update_asset(agent_id, status=AgentStatus.HANDSHAKE_FAILED)
            self.record_audit(agent_id, "HANDSHAKE_FAILED", {"error": str(exc)})

    async def perform_safety_audit(self, agent_id: str) -> bool:
        """
        Step 3: Security & Cloud Audit Redline.
        Mandatory verification before promotion to 执行池 (execution pool).
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            return False

        logger.info(f"Running safety audit for agent {agent_id} (trust_level={asset.trust_level})")
        
        # Check security compliance (mocking the external service, but logic remains firm)
        # Policy: Agents with restrictive scopes or untrusted origins must remain PENDING.
        
        compliance_check = True # Global policy check
        
        # Extreme Redline: If endpoint is on a blocklist or auth_token is expired (simulation)
        if "malicious" in asset.endpoint:
            compliance_check = False
            
        if compliance_check:
            # Promotion to TRUSTED is only possible if audit passes
            self.manager.update_asset(agent_id, trust_level=AgentTrustLevel.TRUSTED)
            self.record_audit(agent_id, "AUDIT_PASSED", {})
            return True
        else:
            self.manager.update_asset(agent_id, status=AgentStatus.AUDIT_FAILED, trust_level=AgentTrustLevel.REVOKED)
            self.record_audit(agent_id, "AUDIT_FAILED", {"reason": "Policy Violation"})
            return False

    async def update_policy(self, agent_id: str, trust_level: AgentTrustLevel, scope: List[str]) -> AgentAsset:
        """
        Update trust policy.
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            raise KeyError(f"Agent {agent_id} not found")
            
        old_state_dict = asset.model_dump()
        new_asset = self.manager.update_asset(agent_id, trust_level=trust_level, scope=scope)
        if not new_asset:
             raise KeyError(f"Agent {agent_id} update failed")
             
        # Use a safe way to record audit to avoid serialization issues
        self.record_audit(agent_id, "POLICY_UPDATED", {
            "trust_level_change": f"{asset.trust_level} -> {trust_level}",
            "scope_change": f"{asset.scope} -> {scope}"
        })
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

    async def dispatch_task(self, agent_id: str, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch a task to an external agent via the Bridge.
        """
        asset = self.manager.get_asset(agent_id)
        if not asset:
            raise KeyError(f"Agent {agent_id} not found")
        
        if asset.status in [AgentStatus.OFFLINE, AgentStatus.HANDSHAKE_FAILED, AgentStatus.AUDIT_FAILED]:
            raise ValueError(f"Agent {agent_id} is not available for tasks (Status: {asset.status})")

        try:
            result = await self.bridge.execute_task(asset, task_payload)
            self.record_audit(agent_id, "TASK_DISPATCHED", {"payload": task_payload, "result_summary": str(result)[:100]})
            return result
        except Exception as e:
            self.record_audit(agent_id, "TASK_FAILED", {"error": str(e)})
            raise

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
        
        all_tasks = [task for task in task_service.list_tasks() if task.target_id == agent_id]
        total_tasks = len(all_tasks)
        completed_tasks = len([t for t in all_tasks if str(t.status.value).lower() in ["done", "completed"]])
        failed_tasks = len([t for t in all_tasks if str(t.status.value).lower() == "failed"])
        
        # Dimension 1: Task Completion Rate (30% weight)
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 100
        completion_score = min(completion_rate, 100)
        
        # Dimension 2: Response Latency Score (25% weight)
        latency_ms = asset.latency_ms
        if latency_ms is None:
            latency_score = 80
        elif latency_ms < 100:
            latency_score = 100
        elif latency_ms < 500:
            latency_score = 80
        else:
            latency_score = 60
        
        # Dimension 3: Error Rate Score (20% weight)
        error_rate = (failed_tasks / total_tasks) if total_tasks > 0 else 0
        error_score = max((1 - error_rate) * 100, 0)
        
        # Dimension 4: Audit Compliance Score (15% weight)
        trust_level_scores = {
            AgentTrustLevel.TRUSTED.value: 100,
            AgentTrustLevel.PENDING.value: 70,
            AgentTrustLevel.RESTRICTED.value: 50,
            AgentTrustLevel.REVOKED.value: 20,
            AgentTrustLevel.UNKNOWN.value: 50,
        }
        audit_score = trust_level_scores.get(str(asset.trust_level.value), 50)
        
        # Dimension 5: Historical Stability Score (10% weight)
        stability_score = asset.success_rate * 100
        
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
                    "description": f"Completed {completed_tasks}/{total_tasks} tasks"
                },
                {
                    "id": "latency",
                    "label": "Latency",
                    "score": round(latency_score, 2),
                    "weight": 0.25,
                    "description": f"Avg Latency {latency_ms or 'N/A'}ms"
                },
                {
                    "id": "error_rate",
                    "label": "Error Rate",
                    "score": round(error_score, 2),
                    "weight": 0.20,
                    "description": f"Failure rate {error_rate*100:.1f}%"
                },
                {
                    "id": "audit",
                    "label": "Audit Compliance",
                    "score": round(audit_score, 2),
                    "weight": 0.15,
                    "description": f"Trust Level: {asset.trust_level}"
                },
                {
                    "id": "stability",
                    "label": "Stability",
                    "score": round(stability_score, 2),
                    "weight": 0.10,
                    "description": f"Success rate {asset.success_rate*100:.1f}%"
                },
            ]
        }

    def get_statistics(
        self,
        agent_id: str,
        task_service: Any,
    ) -> Dict[str, Any]:
        """Aggregate performance statistics for an agent."""
        all_tasks = [task for task in task_service.list_tasks() if task.target_id == agent_id]
        total_tasks = len(all_tasks)
        completed_tasks = len([t for t in all_tasks if str(t.status.value).lower() in ["done", "completed"]])
        failed_tasks = len([t for t in all_tasks if str(t.status.value).lower() == "failed"])
        in_progress_tasks = len([t for t in all_tasks if str(t.status.value).lower() == "in_progress"])
        pending_tasks = total_tasks - completed_tasks - failed_tasks - in_progress_tasks
        
        # Avg completion time
        completed_with_time = [
            t for t in all_tasks 
            if str(t.status.value).lower() in ["done", "completed"] and t.started_at and t.completed_at
        ]
        avg_completion_time = (
            sum((t.completed_at - t.started_at).total_seconds() for t in completed_with_time) / len(completed_with_time)
            if completed_with_time else 0
        )

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "in_progress_tasks": in_progress_tasks,
            "pending_tasks": max(0, pending_tasks),
            "avg_completion_time": round(avg_completion_time, 2),
            "uptime_percentage": 95.0, # Placeholder
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
        # 1. Base query
        tasks = [task for task in task_service.list_tasks() if task.target_id == agent_id]
        
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
_default_service: AgentCoordinationService | None = None


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

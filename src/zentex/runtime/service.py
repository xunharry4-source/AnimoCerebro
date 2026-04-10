from __future__ import annotations

"""
Zentex Runtime Service Facade.

Serves as the central control plane for the BrainRuntime, managing session lifecycles,
shared state stores, and the primary execution ThinkLoop.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from zentex.core.models import BrainRuntimeState
from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.skill_manager import SkillManager
from zentex.runtime.daemon import BrainDaemon, HeartbeatState

logger = logging.getLogger(__name__)


class RuntimeService:
    """
    Control plane service for the Zentex Runtime environment.
    
    Coordinates sessions, working memory, and the core reasoning loop.
    Assembles necessary cognitive engines from other service modules.
    """

    def __init__(
        self,
        runtime_id: Optional[str] = None,
        workspace: Optional[str] = None,
        llm_tool_name: str = "openai_compat",
        auto_assemble: bool = True
    ) -> None:
        self._runtime = BrainRuntime.build_runtime_with_default_llm(
            runtime_id=runtime_id,
            default_workspace=workspace,
            llm_tool_name=llm_tool_name
        )
        self._skill_manager = SkillManager(workspace_root=Path(workspace) if workspace else None)
        self._daemon = BrainDaemon(tick_fn=self.tick)
        
        logger.info(f"RuntimeService initialized (runtime_id={self._runtime.runtime_id})")
        
        if auto_assemble:
            self.assemble_engines()

    @property
    def runtime(self) -> BrainRuntime:
        """Access the underlying BrainRuntime container."""
        return self._runtime

    def assemble_engines(self) -> None:
        """
        Inter-module assembly: Pull dependencies from other standardized services.
        
        This method ensures the BrainRuntime is powered by the correct instances 
        of memory, cognition, and safety engines without direct implementation leaks.
        """
        logger.info("Assembling Zentex cognitive engines into runtime...")

        try:
            # 1. Memory Engine
            from zentex.memory import get_memory_service
            memory_service = get_memory_service()
            self._runtime.runtime_memory_store = memory_service._internal_service
            
            # 2. Cognition Engines
            from zentex.cognition import get_cognition_service
            try:
                cognition_service = get_cognition_service()
                self._runtime.simulation_engine = cognition_service._simulation
                self._runtime.interaction_mind_engine = cognition_service._social_mind
                # The counterfactual_engine in runtime often points to the same simulation engine
                self._runtime.counterfactual_engine = cognition_service._simulation
            except RuntimeError:
                logger.warning("CognitionService not initialized; skipping cognition engines.")

            # 3. Safety/Conflict Engine
            from zentex.safety import get_safety_service
            safety_service = get_safety_service()
            self._runtime.conflict_engine = safety_service._manager
            
            logger.info("Runtime assembly complete.")
        except Exception as e:
            logger.error(f"Engine assembly failed: {e}")

    def create_session(self, session_id: str) -> Any:
        """Initialize a new cognitive session within the runtime."""
        return self._runtime.create_session(session_id)

    def get_session(self, session_id: str) -> Any:
        """Retrieve an existing session by ID."""
        return self._runtime.get_session(session_id)

    def get_state(self) -> BrainRuntimeState:
        """Capture a snapshot of the current runtime state."""
        return self._runtime.get_runtime_state()

    def request_intervention(
        self,
        action: str,
        reason: str,
        operator_id: str = "system",
        phase: str = "execution"
    ) -> Dict[str, Any]:
        """Trigger a manual intervention or pause in the reasoning loop."""
        return self._runtime.request_intervention(
            action=action,
            operator_id=operator_id,
            reason=reason,
            phase_name=phase
        )

    def sync_skills(self) -> Dict[str, bool]:
        """Synchronize all core engineering skills from the remote repository."""
        logger.info("Synchronizing agentic skills from remote...")
        return self._skill_manager.sync_core_methodology_skills()

    def tick(self) -> None:
        """
        The core cognitive tick executed by the BrainDaemon.
        
        Orchestrates observation, risk detection, and nine-question processing.
        """
        logger.debug("RuntimeService.tick() starting...")
        
        # 1. Process pending nine-question events
        self._runtime.process_nine_question_events()
        
        # 2. Trigger memory consolidation check (idle cycle governance)
        if self._runtime.consolidation_engine:
            self._runtime.consolidation_engine.check_and_trigger_automatic_consolidation()
            
        logger.debug("RuntimeService.tick() complete.")

    def start_daemon(self) -> None:
        """Resume autonomous system execution."""
        self._daemon.start()

    def stop_daemon(self) -> None:
        """Pause autonomous system execution."""
        self._daemon.stop()

    def reset_daemon(self) -> None:
        """Recovery action for fused daemons."""
        self._daemon.reset()

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic health and status information for the runtime."""
        state = self.get_state()
        return {
            "runtime_id": state.runtime_id,
            "status": "ready" if not state.degraded_mode else "degraded",
            "active_sessions": len(state.active_session_ids),
            "read_only": state.read_only_mode,
            "bootstrap_status": self._runtime.get_nine_question_bootstrap_status(),
            "engines_attached": {
                "memory": self._runtime.runtime_memory_store is not None,
                "simulation": self._runtime.simulation_engine is not None,
                "safety": self._runtime.conflict_engine is not None,
            },
            "skill_status": self._skill_manager.get_status(),
            "daemon_status": self._daemon.get_status()
        }

    def get_transcript_store(self) -> Any:
        """Controlled access to the transcript store for audit logging."""
        return getattr(self._runtime, "transcript_store", None)

    def get_tool_registry(self) -> Any:
        """Controlled access to the cognitive tool registry."""
        return getattr(self._runtime, "tool_registry", None)

    def get_identity_store(self) -> Any:
        """Controlled access to the identity kernel store."""
        return getattr(self._runtime, "identity_store", None)

    def get_motivation_engine(self) -> Any:
        """Controlled access to the motivation/meta-drive engine."""
        return getattr(self._runtime, "motivation_engine", None)

    def get_shared_state_accessor(self, namespace: str) -> Any:
        """
        Provides a scoped shared state store for cross-process coordination.
        
        Usage: 
            store = runtime.get_shared_state_accessor("sessions")
        """
        from zentex.common.state import SharedStateStore
        runtime_id = getattr(self._runtime, "runtime_id", "default")
        return SharedStateStore(f"{runtime_id}:{namespace}")

    def get_conflict_engine(self) -> Any:
        """Controlled access to the cognitive conflict engine."""
        return getattr(self._runtime, "conflict_engine", None)

    def get_temporal_engine(self) -> Any:
        """Controlled access to the cognitive temporal engine."""
        return getattr(self._runtime, "temporal_engine", None)

    def get_simulation_engine(self) -> Any:
        """Controlled access to the counterfactual simulation engine."""
        return getattr(self._runtime, "simulation_engine", None)

    def get_interaction_mind_engine(self) -> Any:
        """Controlled access to the interaction/social mind engine."""
        return getattr(self._runtime, "interaction_mind_engine", None)

    def get_consolidation_engine(self) -> Any:
        """Controlled access to the memory consolidation engine."""
        return getattr(self._runtime, "consolidation_engine", None)


# Global singleton instance
_default_service: Optional[RuntimeService] = None


def get_runtime_service() -> RuntimeService:
    """Return the global shared RuntimeService instance."""
    global _default_service
    if _default_service is None:
        _default_service = RuntimeService()
    return _default_service


def init_runtime_service(
    runtime_id: Optional[str] = None,
    workspace: Optional[str] = None,
    llm_tool_name: str = "openai_compat",
    auto_assemble: bool = True
) -> RuntimeService:
    """Initialize the global runtime service with specific parameters."""
    global _default_service
    _default_service = RuntimeService(
        runtime_id=runtime_id,
        workspace=workspace,
        llm_tool_name=llm_tool_name,
        auto_assemble=auto_assemble
    )
    return _default_service

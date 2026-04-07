from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from zentex.core.plugin_base import FunctionalPluginSpec


class SensoryPluginSpec(FunctionalPluginSpec, ABC):
    """
    Plugin family for sensory input (Q1 dependency).
    Focuses on ingestion, sanitization, and interpretation.
    """
    
    signal_type: str = Field(min_length=1)
    
    @classmethod
    def plugin_kind(cls) -> str:
        return "sensory"

    @abstractmethod
    def ingest(self, source: Any) -> Any:
        """Raw signal capture."""
        pass

    @abstractmethod
    def sanitize(self, raw_signal: Any) -> Any:
        """Signal cleaning and normalization."""
        pass

    @abstractmethod
    def interpret(self, clean_signal: Any) -> Dict[str, Any]:
        """Signal semantics and context extraction."""
        pass


class IdentityPackageSpec(FunctionalPluginSpec, ABC):
    """
    Plugin family for identity and persona (Q2 dependency).
    Includes role packs, constraint packs, and experience packs.
    """
    
    pack_type: str # role_pack, constraint_pack, experience_pack
    
    @classmethod
    def plugin_kind(cls) -> str:
        return "identity_package"

    @abstractmethod
    def get_payload(self) -> Dict[str, Any]:
        """Return the structured data for the persona."""
        pass


class SubjectiveWeightSpec(FunctionalPluginSpec, ABC):
    """
    Plugin family for subjective cognitive bias (Q2 dependency).
    Controls risk, cost, and creative preferences.
    """
    
    target_metric: str # risk, cost, creativity, etc.
    
    @classmethod
    def plugin_kind(cls) -> str:
        return "subjective_weight"

    @abstractmethod
    def calculate_weight(self, task_context: Dict[str, Any]) -> float:
        """Return a normalized weight [0.0, 1.0]."""
        pass


class ExecutionPluginSpec(FunctionalPluginSpec, ABC):
    """
    Plugin family for physical execution (Q3 output dependency).
    Maps capability declarations to real-world drivers.
    """
    
    execution_domain: str # system, cloud, browser, legacy_io
    
    @classmethod
    def plugin_kind(cls) -> str:
        return "execution"

    @abstractmethod
    def execute_action(self, action_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Physical driver execution."""
        pass


class CompliancePluginSpec(FunctionalPluginSpec, ABC):
    """
    Plugin family for compliance and authorization (Q5 dependency).
    Focuses on 'subtractive cropping' of actions based on specific rules.
    """

    @classmethod
    def plugin_kind(cls) -> str:
        return "compliance"

    @abstractmethod
    def check_compliance(self, action_trace: Dict[str, Any]) -> Dict[str, Any]:
        """Return a checklist of allowed/blocked actions with audit reasons."""
        pass


class TrustPolicySpec(FunctionalPluginSpec, ABC):
    """
    Plugin family for Contact & Trust Policy (Q5 dependency).
    Defines delegation limits and whitelists.
    """

    @classmethod
    def plugin_kind(cls) -> str:
        return "trust_policy"

    @abstractmethod
    def get_whitelist(self) -> List[str]:
        """Authorized contact entities."""
        pass

    @abstractmethod
    def get_agent_scope(self, agent_id: str) -> str:
        """Read-only, limited, or full execution."""
        pass


class RedlinePluginSpec(FunctionalPluginSpec, ABC):
    """
    Plugin family for Forbidden Zones and Red-lines (Q6 dependency).
    Specifies absolute no-go areas regardless of performance goals.
    """

    @classmethod
    def plugin_kind(cls) -> str:
        return "redline"

    @abstractmethod
    def get_forbidden_zones(self) -> List[Dict[str, Any]]:
        """A list of structured forbidden actions or states."""
        pass


class AlternativeSpec(FunctionalPluginSpec, ABC):
    """
    Plugin family for alternative strategies and downgrades (Q7 dependency).
    Defines backup plans and resource-degraded maneuvers.
    """

    @classmethod
    def plugin_kind(cls) -> str:
        return "alternative"

    @abstractmethod
    def get_downgrade_options(self, block_context: Dict[str, Any]) -> List[Any]:
        """Return prioritized alternative maneuvers."""
        pass


class ObjectiveSpec(FunctionalPluginSpec, ABC):
    """
    Plugin family for main objective and task queueing (Q8 dependency).
    Focuses on task prioritization and unblocking logic.
    """

    @classmethod
    def plugin_kind(cls) -> str:
        return "objective"

    @abstractmethod
    def refine_task_queue(self, task_queue: List[Any], context: Dict[str, Any]) -> List[Any]:
        """Return a refined or re-ranked task queue."""
        pass


class PostureSpec(FunctionalPluginSpec, ABC):
    """
    Plugin family for action posture and evaluation style (Q9 dependency).
    Controls risk appetite, confirmation triggers, and evaluation bias.
    """

    @classmethod
    def plugin_kind(cls) -> str:
        return "posture"

    @abstractmethod
    def apply_posture(self, decision_trace: Dict[str, Any]) -> Dict[str, Any]:
        """Return posture adjustments (e.g., force_human_confirm=True)."""
        pass


class HostTelemetryPluginSpec(FunctionalPluginSpec, ABC):
    """
    Plugin family for local host telemetry (Q1 dependency).

    Provides real, read-only host status such as memory pressure and network
    posture. It must never mutate the host.
    """

    telemetry_domain: str = "host"

    @classmethod
    def plugin_kind(cls) -> str:
        return "host_telemetry"

    @abstractmethod
    def capture_host_state(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Return a structured host-state snapshot for Q1."""
        pass

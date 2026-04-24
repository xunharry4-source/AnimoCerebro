"""Execution domain specs — domain levels, plugin contract, and domain configuration."""

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from zentex.foundation.contracts import ActionIntent, ActionResult, AuditEntry, SafetyDecision
from zentex.foundation.specs.plugin_spec import (
    PluginCapabilitySpec,
    PluginIsolationSpec,
    PluginLifecycleSpec,
)


class ExecutionDomainLevel(str, Enum):
    """Permission tiers governing what an execution plugin may do."""

    strict = "strict"       # no network, no file write
    standard = "standard"   # file read allowed
    elevated = "elevated"   # network allowed


class ExecutionPluginSpec(PluginLifecycleSpec, PluginCapabilitySpec, PluginIsolationSpec):
    """Full abstract interface for execution plugins.

    Implementors must satisfy PluginLifecycleSpec, PluginCapabilitySpec, and
    PluginIsolationSpec in addition to the execution-specific methods below.
    """

    @abstractmethod
    def pre_execution_safety_check(self, intent: ActionIntent) -> SafetyDecision:
        """Evaluate an action intent for safety before execution begins."""
        ...

    @abstractmethod
    def execute(self, intent: ActionIntent) -> ActionResult:
        """Execute the given action intent and return the result."""
        ...

    @abstractmethod
    def post_execution_audit(self, result: ActionResult) -> AuditEntry:
        """Produce an immutable audit entry for a completed execution result."""
        ...

    @property
    @abstractmethod
    def domain_level(self) -> ExecutionDomainLevel:
        """Return the domain permission level claimed by this plugin."""
        ...


@dataclass
class ExecutionDomainSpec:
    """Configuration for an execution domain, specifying allowed permissions and limits."""

    allowed_level: ExecutionDomainLevel
    max_duration_seconds: int = 30
    requires_audit: bool = True

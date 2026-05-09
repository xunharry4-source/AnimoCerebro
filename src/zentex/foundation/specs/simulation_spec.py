"""Abstract spec for simulation plugins."""

from abc import abstractmethod

from zentex.foundation.contracts import SimulationIntent, SimulationResult
from zentex.foundation.specs.plugin_spec import (
    PluginCapabilitySpec,
    PluginIsolationSpec,
    PluginLifecycleSpec,
)


class SimulationPluginSpec(PluginLifecycleSpec, PluginCapabilitySpec, PluginIsolationSpec):
    """Full abstract interface for simulation plugins.

    Implementors must satisfy PluginLifecycleSpec, PluginCapabilitySpec, and
    PluginIsolationSpec in addition to the simulation-specific methods below.

    IMPORTANT: implementations MUST NOT produce real side effects. Simulations are
    purely predictive — no external state may be modified during a simulation run.
    """

    @abstractmethod
    def simulate(self, intent: SimulationIntent) -> SimulationResult:
        """Run a simulation for the given intent and return the result.

        Implementations MUST NOT produce real side effects.
        """
        ...

    @abstractmethod
    def can_handle(self, intent: SimulationIntent) -> bool:
        """Return True if this plugin is capable of handling the given simulation scenario."""
        ...

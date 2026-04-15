"""Abstract base classes declaring the interface contracts plugins must fulfill."""

from abc import ABC, abstractmethod

from zentex.foundation.contracts import PluginContract, PluginHealthReport
from zentex.foundation.meta import FeatureFamily


class PluginLifecycleSpec(ABC):
    """Declares the lifecycle interface every plugin must implement."""

    @abstractmethod
    def initialize(self) -> None:
        """Perform plugin startup and resource acquisition."""
        ...

    @abstractmethod
    def health_check(self) -> PluginHealthReport:
        """Return the plugin's current health status."""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """Perform graceful shutdown and resource release."""
        ...

    @property
    @abstractmethod
    def contract(self) -> PluginContract:
        """Return the plugin's contract descriptor."""
        ...


class PluginCapabilitySpec(ABC):
    """Declares the capability advertisement interface every plugin must implement."""

    @abstractmethod
    def supported_families(self) -> list[FeatureFamily]:
        """Return the feature families this plugin serves."""
        ...

    @abstractmethod
    def input_schema(self) -> dict:
        """Return a JSON schema dict describing the expected input."""
        ...

    @abstractmethod
    def output_schema(self) -> dict:
        """Return a JSON schema dict describing the expected output."""
        ...


class PluginIsolationSpec(ABC):
    """Declares the isolation contract plugins must uphold for statelessness guarantees."""

    @abstractmethod
    def is_stateless(self) -> bool:
        """Return True if the plugin holds no cross-turn mutable state."""
        ...

    @abstractmethod
    def reset_turn_state(self) -> None:
        """Clear any temporary state between turns.

        Called by the runtime at the boundary of each turn.
        """
        ...

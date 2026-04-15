"""Abstract base classes for the sensory pipeline: ingest, sanitize, interpret."""

from abc import ABC, abstractmethod

from zentex.foundation.contracts import (
    EnvironmentEvent,
    RawSignal,
    SanitizedSignal,
    SignalSecurityTag,
)


class SignalIngestSpec(ABC):
    """Contract for the first stage of the sensory pipeline: accepting raw signals."""

    @abstractmethod
    def ingest(self, raw: RawSignal) -> RawSignal:
        """Validate and accept a raw signal from an external source.

        Raises if the signal cannot be accepted.
        """
        ...

    @abstractmethod
    def validate_source(self, source: str) -> bool:
        """Return True if the named source is permitted to submit signals."""
        ...


class SignalSanitizeSpec(ABC):
    """Contract for the second stage of the sensory pipeline: security filtering."""

    @abstractmethod
    def sanitize(self, signal: RawSignal) -> SanitizedSignal:
        """Apply security filtering and return a sanitized signal."""
        ...

    @abstractmethod
    def tag(self, signal: RawSignal) -> SignalSecurityTag:
        """Determine and return the appropriate security tag for a raw signal."""
        ...


class SignalInterpretSpec(ABC):
    """Contract for the third stage of the sensory pipeline: domain interpretation."""

    @abstractmethod
    def interpret(self, signal: SanitizedSignal) -> EnvironmentEvent:
        """Convert a sanitized signal into a domain-level environment event."""
        ...

    @abstractmethod
    def can_interpret(self, signal: SanitizedSignal) -> bool:
        """Return True if this interpreter is capable of handling the given signal."""
        ...

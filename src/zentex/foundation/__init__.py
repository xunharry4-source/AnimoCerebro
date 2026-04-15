"""
Foundation module — pure protocol and capability layer for zentex.

RESPONSIBILITY:
This module defines all system protocols, contracts, and capabilities that form
the baseline for other modules. It contains no business logic, no execution code,
and no dependencies on external services.

PROVIDES:
- Protocol definitions (sessions, turns, plugins)
- Capability registry and feature families
- System-wide identity and version information
- Plugin interface specifications and audit requirements

DOES NOT:
- Execute turns or manage sessions (kernel's responsibility)
- Start the system or assemble services (launcher's responsibility)
- Interact with external services directly
- Contain any __runtime, __core, or __boot internal modules

PUBLIC API:
Only import FoundationService and get_service() from this module.
All other submodules (contracts, specs, identity, meta) are internal.
"""

from zentex.foundation.service import FoundationService, get_service

__all__ = ["FoundationService", "get_service"]

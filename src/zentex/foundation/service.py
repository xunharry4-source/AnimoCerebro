from __future__ import annotations
"""
Public service boundary for zentex.foundation.

All external modules (kernel, launcher, etc.) MUST interact with foundation
exclusively through this file. No direct imports from foundation submodules.
"""


from typing import Any, Dict, List, Optional, Union

import logging
import os
import json
from pathlib import Path
from datetime import datetime, timezone

from zentex.foundation.contracts import ZentexBaseModel
from zentex.foundation.identity import IdentityCore, IdentityService, IdentityVersion
from zentex.foundation.identity.identity_contract import IdentityLock
from zentex.foundation.meta import (
    AUDIT_RETENTION_DAYS,
    DEFAULT_CAPABILITY_DIRECTORY,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    FEATURE_FAMILY_REGISTRY,
    FOUNDATION_VERSION,
    KERNEL_PROTOCOL_VERSION,
    MAX_TRANSCRIPT_ENTRIES_PER_SESSION,
    NINE_QUESTION_COUNT,
    NINE_QUESTIONS_MAX_CONCURRENCY,
    PHASE_COUNT,
    PLUGIN_HEALTH_CHECK_INTERVAL_SECONDS,
    SENSORY_SIGNAL_QUEUE_MAX_SIZE,
    SESSION_DEFAULT_TIMEOUT_SECONDS,
    TURN_MAX_DURATION_SECONDS,
    WORKING_MEMORY_MAX_SLOTS,
    CapabilityDirectory,
    FeatureFamily,
    FeatureFamilyMeta,
    SystemVersionInfo,
    get_family_meta,
)

UTC = timezone.utc
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default identity used when no identity is provided at construction
# ---------------------------------------------------------------------------

_DEFAULT_IDENTITY = IdentityCore(
    role_name="Zentex Agent",
    mission="Serve users faithfully, safely, and transparently.",
    core_values=("integrity", "safety", "transparency", "helpfulness"),
    continuity_lock=IdentityLock(
        locked_fields=frozenset(["role_name", "mission", "core_values"]),
        lock_reason="Core identity fields are immutable after initialization.",
    ),
    version=IdentityVersion(created_at=datetime.now(UTC), description="Default foundation identity"),
)

def _load_identity_from_file() -> Optional[IdentityCore]:
    """Attempt to load custom identity from the local .zentex directory."""
    path = Path(".zentex/identity.json")
    if not path.exists():
        return None
        
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Identity file must contain a JSON object.")
            
        # Handle nested core values (IdentityCore expects tuple)
        if "core_values" in payload and isinstance(payload["core_values"], list):
            payload["core_values"] = tuple(payload["core_values"])
        
        return IdentityCore(
            role_name=payload.get("role_name", _DEFAULT_IDENTITY.role_name),
            mission=payload.get("mission", _DEFAULT_IDENTITY.mission),
            core_values=payload.get("core_values", _DEFAULT_IDENTITY.core_values),
            continuity_lock=IdentityLock(
                locked_fields=frozenset(["role_name", "mission", "core_values"]),
                lock_reason="Loaded from .zentex/identity.json",
            ),
            version=IdentityVersion(created_at=datetime.now(UTC), description="Identity loaded from JSON file"),
        )
    except Exception as exc:
        logger.error(f"CRITICAL: Failed to load identity from .zentex/identity.json: {exc}")
        # FAIL-CLOSED: No silent fallback to default identity if a specific one was intended.
        raise RuntimeError(f"Identity Corruption: {exc}. Startup halted to prevent identity drift.") from exc

class FoundationService:
    """Single public interface for the foundation module.

    External callers (kernel, launcher, plugins) must only interact with the
    foundation through this class.  Direct imports from any foundation submodule
    are prohibited.
    """

    def __init__(self, identity: Optional[IdentityCore] = None) -> None:
        if identity is None:
            identity = _load_identity_from_file()
            
        resolved_identity = identity if identity is not None else _DEFAULT_IDENTITY
        self._identity_service: IdentityService = IdentityService(resolved_identity)
        self._capability_directory: CapabilityDirectory = DEFAULT_CAPABILITY_DIRECTORY
        self._start_time: datetime = datetime.now(timezone.utc)
        self._initialized: bool = True

    # ------------------------------------------------------------------
    # Version & compatibility
    # ------------------------------------------------------------------

    def get_runtime_id(self) -> str:
        """Return a unique ID for this foundation service instance."""
        return f"zentex-{os.getpid()}"

    def get_start_time(self) -> datetime:
        """Return the initialization time of this foundation service."""
        return self._start_time

    def get_protocol_version(self) -> SystemVersionInfo:
        """Parse and return FOUNDATION_VERSION as a SystemVersionInfo."""
        return SystemVersionInfo.from_string(FOUNDATION_VERSION)

    def get_kernel_expected_version(self) -> SystemVersionInfo:
        """Parse and return KERNEL_PROTOCOL_VERSION as a SystemVersionInfo."""
        return SystemVersionInfo.from_string(KERNEL_PROTOCOL_VERSION)

    def check_version_compatibility(self) -> bool:
        """Return True if the foundation version is compatible with the kernel expected version."""
        foundation = self.get_protocol_version()
        kernel = self.get_kernel_expected_version()
        return foundation.is_compatible_with(kernel)

    # ------------------------------------------------------------------
    # Capability directory
    # ------------------------------------------------------------------

    def get_capability_directory(self) -> CapabilityDirectory:
        """Return the capability directory for this foundation instance."""
        return self._capability_directory

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def get_identity_snapshot(self) -> IdentityCore:
        """Return the current identity snapshot."""
        return self._identity_service.get_snapshot()

    def validate_identity_field_change(self, field: str, new_value: str) -> bool:
        """Return True if changing the named field is permitted (field is not locked)."""
        return self._identity_service.validate_request(field, new_value)

    def detect_identity_drift(self, candidate: IdentityCore) -> dict:
        """Compare a candidate identity to the stored one and report any drift.

        Returns:
            {"drifted_fields": list[str], "is_clean": bool}
        """
        return self._identity_service.detect_drift(candidate)

    # ------------------------------------------------------------------
    # Feature families
    # ------------------------------------------------------------------

    def get_feature_families(self) -> list[FeatureFamily]:
        """Return all known feature families."""
        return list(FeatureFamily)

    def get_family_meta(self, family: FeatureFamily) -> FeatureFamilyMeta:
        """Return the metadata for the given feature family."""
        return get_family_meta(family)

    # ------------------------------------------------------------------
    # System constants
    # ------------------------------------------------------------------

    def get_system_constants(self) -> dict:
        """Return a dict of all system constants keyed by name."""
        return {
            "TURN_MAX_DURATION_SECONDS": TURN_MAX_DURATION_SECONDS,
            "NINE_QUESTIONS_MAX_CONCURRENCY": NINE_QUESTIONS_MAX_CONCURRENCY,
            "SESSION_DEFAULT_TIMEOUT_SECONDS": SESSION_DEFAULT_TIMEOUT_SECONDS,
            "AUDIT_RETENTION_DAYS": AUDIT_RETENTION_DAYS,
            "SENSORY_SIGNAL_QUEUE_MAX_SIZE": SENSORY_SIGNAL_QUEUE_MAX_SIZE,
            "WORKING_MEMORY_MAX_SLOTS": WORKING_MEMORY_MAX_SLOTS,
            "PHASE_COUNT": PHASE_COUNT,
            "NINE_QUESTION_COUNT": NINE_QUESTION_COUNT,
            "MAX_TRANSCRIPT_ENTRIES_PER_SESSION": MAX_TRANSCRIPT_ENTRIES_PER_SESSION,
            "DEFAULT_LLM_TIMEOUT_SECONDS": DEFAULT_LLM_TIMEOUT_SECONDS,
            "PLUGIN_HEALTH_CHECK_INTERVAL_SECONDS": PLUGIN_HEALTH_CHECK_INTERVAL_SECONDS,
        }

    # ------------------------------------------------------------------
    # Protocol & Specification APIs (Phase A Required APIs)
    # ------------------------------------------------------------------

    def get_plugin_spec(self) -> dict:
        """
        Return the unified plugin specification.

        This API defines what all plugins must conform to:
        - Input contract (expected context, parameters)
        - Output contract (return structure, audit fields)
        - Lifecycle contract (initialization, cleanup)

        Returns:
            dict with keys: plugin_interface, lifecycle_rules, audit_requirements
        """
        return {
            "plugin_interface": {
                "execute": "async def execute(context: dict) -> PluginResult",
                "health_check": "async def health_check() -> bool",
                "get_metadata": "def get_metadata() -> PluginMetadata",
            },
            "lifecycle_rules": {
                "must_initialize": True,
                "must_cleanup": True,
                "must_handle_timeout": True,
                "concurrent_safe": True,
            },
            "audit_requirements": {
                "must_include_trace_id": True,
                "must_include_caller_plugin_id": True,
                "must_record_duration_ms": True,
                "must_record_result_status": True,
            },
        }

    def get_session_protocol(self) -> dict:
        """
        Return the session lifecycle protocol.

        Defines how sessions are created, maintained, and destroyed:
        - Session creation requirements
        - Session state transitions
        - Session timeout behavior
        - Data isolation guarantees

        Returns:
            dict with keys: creation, state_machine, timeout, isolation
        """
        return {
            "creation": {
                "required_fields": ["user_id", "workspace_id"],
                "optional_fields": ["initial_metadata", "session_timeout_seconds"],
                "default_timeout_seconds": SESSION_DEFAULT_TIMEOUT_SECONDS,
            },
            "state_machine": {
                "states": ["created", "active", "paused", "closed"],
                "transitions": {
                    "created_to_active": "after first turn",
                    "active_to_paused": "on explicit request",
                    "paused_to_active": "on resume request",
                    "any_to_closed": "on explicit close or timeout",
                },
            },
            "timeout": {
                "default_seconds": SESSION_DEFAULT_TIMEOUT_SECONDS,
                "enforcement": "server-side tracked",
                "grace_period_seconds": 60,
            },
            "isolation": {
                "tenant_scoped": True,
                "user_scoped": True,
                "no_cross_session_data_leak": True,
            },
        }

    def get_turn_protocol(self) -> dict:
        """
        Return the turn execution protocol.

        Defines how each turn (conversation cycle) is structured:
        - Input validation
        - Phase structure (9 phases)
        - Output format
        - Error handling

        Returns:
            dict with keys: input_contract, phases, output_contract, error_handling
        """
        return {
            "input_contract": {
                "required_fields": ["session_id", "user_input"],
                "optional_fields": ["context", "trace_id"],
                "max_input_length": 10000,
            },
            "phases": {
                "phase_count": PHASE_COUNT,
                "phase_names": [
                    "observe",
                    "perceive",
                    "recognize",
                    "reason",
                    "decide",
                    "plan",
                    "prepare",
                    "act",
                    "consolidate",
                ],
                "max_phase_duration_seconds": TURN_MAX_DURATION_SECONDS,
            },
            "output_contract": {
                "required_fields": ["session_id", "turn_id", "status", "result"],
                "always_include": ["trace_id", "duration_ms", "audit_log"],
                "result_structure": {
                    "cognitive_output": "Optional[dict]",
                    "action_recommendations": "list[dict]",
                    "next_actions": "list[dict]",
                },
            },
            "error_handling": {
                "timeout_max_seconds": TURN_MAX_DURATION_SECONDS,
                "must_return_partial_result": True,
                "error_codes": ["timeout", "resource_exhausted", "internal_error"],
            },
        }

    def list_capabilities(self) -> list[dict]:
        """
        Return a list of all system capabilities available in this foundation.

        Each capability is described by:
        - name: Capability name (e.g., 'nine_questions', 'memory', 'reflection')
        - family: Feature family this belongs to
        - status: 'available' | 'degraded' | 'unavailable'
        - version: Semantic version string

        Returns:
            list of capability descriptors
        """
        return [
            {
                "name": "nine_questions",
                "family": "cognition",
                "status": "available",
                "version": FOUNDATION_VERSION,
                "description": "Nine-question cognitive bootstrap and steering framework",
            },
            {
                "name": "session_management",
                "family": "runtime",
                "status": "available",
                "version": FOUNDATION_VERSION,
                "description": "Session creation, lifecycle, and isolation",
            },
            {
                "name": "turn_execution",
                "family": "runtime",
                "status": "available",
                "version": FOUNDATION_VERSION,
                "description": "Nine-phase turn execution protocol",
            },
            {
                "name": "plugin_contract",
                "family": "integration",
                "status": "available",
                "version": FOUNDATION_VERSION,
                "description": "Unified plugin interface and lifecycle management",
            },
            {
                "name": "identity_management",
                "family": "security",
                "status": "available",
                "version": FOUNDATION_VERSION,
                "description": "Identity core, role definition, and mutation control",
            },
            {
                "name": "audit_trail",
                "family": "observability",
                "status": "available",
                "version": FOUNDATION_VERSION,
                "description": "Centralized audit logging and trace tracking",
            },
        ]

    def get_version(self) -> str:
        """
        Return the foundation module version string.

        Format: "major.minor.patch"
        """
        return FOUNDATION_VERSION


# ---------------------------------------------------------------------------
# Module-level lazy singleton
# ---------------------------------------------------------------------------

_default_service: Optional[FoundationService] = None


def get_service(identity: Optional[IdentityCore] = None) -> FoundationService:
    """Return the module-level FoundationService singleton, creating it if necessary.

    If an identity is supplied on first call it is used to construct the
    singleton.  Subsequent calls ignore the argument and return the cached
    instance.
    """
    global _default_service
    if _default_service is None:
        _default_service = FoundationService(identity)
    return _default_service

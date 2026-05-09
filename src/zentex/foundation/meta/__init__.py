"""Foundation meta package — version info, feature families, constants, capabilities."""

from zentex.foundation.meta.capability_registry import (
    CapabilityDirectory,
    CapabilityEntry,
    DEFAULT_CAPABILITY_DIRECTORY,
)
from zentex.foundation.meta.feature_family import (
    FeatureFamily,
    FeatureFamilyMeta,
    FEATURE_FAMILY_REGISTRY,
    get_family_meta,
)
from zentex.foundation.meta.system_constants import (
    AUDIT_RETENTION_DAYS,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    MAX_TRANSCRIPT_ENTRIES_PER_SESSION,
    NINE_QUESTION_COUNT,
    NINE_QUESTIONS_MAX_CONCURRENCY,
    PHASE_COUNT,
    PLUGIN_HEALTH_CHECK_INTERVAL_SECONDS,
    SENSORY_SIGNAL_QUEUE_MAX_SIZE,
    SESSION_DEFAULT_TIMEOUT_SECONDS,
    TURN_MAX_DURATION_SECONDS,
    WORKING_MEMORY_MAX_SLOTS,
)
from zentex.foundation.meta.version import (
    FOUNDATION_VERSION,
    KERNEL_PROTOCOL_VERSION,
    SystemVersionInfo,
)

__all__ = [
    # version
    "FOUNDATION_VERSION",
    "KERNEL_PROTOCOL_VERSION",
    "SystemVersionInfo",
    # feature family
    "FeatureFamily",
    "FeatureFamilyMeta",
    "FEATURE_FAMILY_REGISTRY",
    "get_family_meta",
    # system constants
    "TURN_MAX_DURATION_SECONDS",
    "NINE_QUESTIONS_MAX_CONCURRENCY",
    "SESSION_DEFAULT_TIMEOUT_SECONDS",
    "AUDIT_RETENTION_DAYS",
    "SENSORY_SIGNAL_QUEUE_MAX_SIZE",
    "WORKING_MEMORY_MAX_SLOTS",
    "PHASE_COUNT",
    "NINE_QUESTION_COUNT",
    "MAX_TRANSCRIPT_ENTRIES_PER_SESSION",
    "DEFAULT_LLM_TIMEOUT_SECONDS",
    "PLUGIN_HEALTH_CHECK_INTERVAL_SECONDS",
    # capability registry
    "CapabilityEntry",
    "CapabilityDirectory",
    "DEFAULT_CAPABILITY_DIRECTORY",
]

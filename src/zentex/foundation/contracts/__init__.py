"""Foundation contracts package — all public contract types in one namespace."""

# base models
from zentex.foundation.contracts.base_models import (
    AuditableModel,
    TimestampedModel,
    ZentexBaseModel,
)

# event models
from zentex.foundation.contracts.event_models import (
    EventEnvelope,
    ZentexEvent,
    ZentexEventType,
)

# plugin contract
from zentex.foundation.contracts.plugin_contract import (
    PluginContract,
    PluginHealthReport,
    PluginStatus,
)

# execution contract
from zentex.foundation.contracts.execution_contract import (
    ActionIntent,
    ActionResult,
    ActionStatus,
    SafetyDecision,
)

# sensory contract
from zentex.foundation.contracts.sensory_contract import (
    EnvironmentEvent,
    RawSignal,
    SanitizedSignal,
    SignalSecurityTag,
)

# simulation contract
from zentex.foundation.contracts.simulation_contract import (
    SimulationBranch,
    SimulationIntent,
    SimulationResult,
)

# turn contract
from zentex.foundation.contracts.turn_contract import (
    PhaseResult,
    TurnRequest,
    TurnResult,
    TurnStatus,
)

# session contract
from zentex.foundation.contracts.session_contract import (
    SessionMeta,
    SessionSnapshot,
    SessionStatus,
)

# audit contract
from zentex.foundation.contracts.audit_contract import (
    AuditDecision,
    AuditEntry,
    AuditTrail,
)

# service response
from zentex.foundation.contracts.service_response import (
    ServiceCallContext,
    ServiceErrorCode,
    ServiceResponse,
    ServiceStatus,
)

__all__ = [
    # base models
    "ZentexBaseModel",
    "TimestampedModel",
    "AuditableModel",
    # event models
    "ZentexEventType",
    "ZentexEvent",
    "EventEnvelope",
    # plugin contract
    "PluginStatus",
    "PluginContract",
    "PluginHealthReport",
    # execution contract
    "ActionStatus",
    "ActionIntent",
    "ActionResult",
    "SafetyDecision",
    # sensory contract
    "SignalSecurityTag",
    "RawSignal",
    "SanitizedSignal",
    "EnvironmentEvent",
    # simulation contract
    "SimulationBranch",
    "SimulationIntent",
    "SimulationResult",
    # turn contract
    "TurnStatus",
    "PhaseResult",
    "TurnRequest",
    "TurnResult",
    # session contract
    "SessionStatus",
    "SessionMeta",
    "SessionSnapshot",
    # audit contract
    "AuditEntry",
    "AuditTrail",
    "AuditDecision",
    # service response
    "ServiceCallContext",
    "ServiceErrorCode",
    "ServiceResponse",
    "ServiceStatus",
]

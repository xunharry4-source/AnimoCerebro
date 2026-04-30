"""
Zentex external Agent capability module.

Handles Zentex-local registration, invocation policy, adapter-facing calls,
observation, and verification for external Agent capabilities.
"""
from zentex.agents.manager import AgentManager, AgentAsset, AgentStatus, AgentTrustLevel
from zentex.agents.service import AgentCoordinationService, AgentRegistrationRequest
from zentex.agents.bridge import AgentBridge
from zentex.agents.adapters import (
    AgentAdapterError,
    AgentInvocationContext,
    AgentInvocationAdapter,
    AgentInvocationDependencies,
    AgentInvocationResult,
)
from zentex.agents.invocations import AgentInvocationLedger, AgentInvocationRecord
from zentex.agents.auth import (
    AgentAuthError,
    AgentAuthService,
    AgentCredentialMetadata,
    AgentCredentialVault,
    AgentResolvedAuth,
)
from zentex.agents.verification import (
    ActiveProbeConfig,
    AgentEvidenceBundle,
    AgentVerificationCheck,
    AgentVerificationMethod,
    AgentVerificationPlan,
    AgentVerificationResult,
    AgentVerificationService,
    AgentVerificationStatus,
    LlmAnalysisConfig,
    RemoteResultViewConfig,
    RuleAnalysisConfig,
)

__all__ = [
    "AgentManager",
    "AgentAsset",
    "AgentStatus",
    "AgentTrustLevel",
    "AgentCoordinationService",
    "AgentRegistrationRequest",
    "AgentBridge",
    "AgentAdapterError",
    "AgentInvocationContext",
    "AgentInvocationAdapter",
    "AgentInvocationDependencies",
    "AgentInvocationResult",
    "AgentInvocationLedger",
    "AgentInvocationRecord",
    "AgentAuthError",
    "AgentAuthService",
    "AgentCredentialMetadata",
    "AgentCredentialVault",
    "AgentResolvedAuth",
    "ActiveProbeConfig",
    "AgentEvidenceBundle",
    "AgentVerificationCheck",
    "AgentVerificationMethod",
    "AgentVerificationPlan",
    "AgentVerificationResult",
    "AgentVerificationService",
    "AgentVerificationStatus",
    "LlmAnalysisConfig",
    "RemoteResultViewConfig",
    "RuleAnalysisConfig",
]

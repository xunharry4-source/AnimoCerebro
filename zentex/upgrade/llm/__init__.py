"""
LLM upgrade package.

This package contains the planning contracts and service entrypoint for
DSPy-driven LLM optimization jobs.
"""

from zentex.upgrade.llm.models import (
    LLMUpgradeCandidate,
    LLMUpgradeExecutionPlan,
    LLMUpgradeRequest,
)
from zentex.upgrade.llm.runtime import LLMUpgradeRuntime
from zentex.upgrade.llm.service import DSPyLLMUpgradeService

__all__ = [
    "DSPyLLMUpgradeService",
    "LLMUpgradeCandidate",
    "LLMUpgradeExecutionPlan",
    "LLMUpgradeRequest",
    "LLMUpgradeRuntime",
]

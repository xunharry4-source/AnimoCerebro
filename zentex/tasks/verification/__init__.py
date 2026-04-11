"""
任务验证模块 - Task Verification Module

提供多Agent协作场景下的任务完成自动验证功能。
支持自动化测试、LLM评估、规则检查等多种验证方式。
"""

from zentex.tasks.verification.models import (
    VerificationType,
    VerificationStrategy,
    VerificationStatus,
    VerifierConfig,
    VerificationConfig,
    SingleVerifierResult,
    VerificationResult,
)
from zentex.tasks.verification.verifiers import (
    BaseVerifier,
    AutomatedTestVerifier,
    LLMEvaluationVerifier,
    RuleBasedVerifier,
)
from zentex.tasks.verification.engine import VerificationEngine
from zentex.tasks.verification.registry import VerifierRegistry

__all__ = [
    "VerificationType",
    "VerificationStrategy",
    "VerificationStatus",
    "VerifierConfig",
    "VerificationConfig",
    "SingleVerifierResult",
    "VerificationResult",
    "BaseVerifier",
    "AutomatedTestVerifier",
    "LLMEvaluationVerifier",
    "RuleBasedVerifier",
    "VerificationEngine",
    "VerifierRegistry",
]

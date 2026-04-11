"""
任务验证数据模型 - Task Verification Models

定义验证相关的枚举、配置和结果模型。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class VerificationType(str, Enum):
    """验证类型枚举"""

    AUTOMATED_TEST = "automated_test"  # 自动化测试（执行命令/脚本）
    LLM_EVALUATION = "llm_evaluation"  # LLM语义评估
    RULE_BASED = "rule_based"  # 规则检查（结构化字段校验）
    MANUAL_REVIEW = "manual_review"  # 人工审核
    COMBINED = "combined"  # 组合验证


class VerificationStrategy(str, Enum):
    """验证策略枚举"""

    ALL_MUST_PASS = "all_must_pass"  # 所有验证器都必须通过
    MAJORITY_WINS = "majority_wins"  # 多数通过即可
    ANY_PASSES = "any_passes"  # 任一通过即可
    WEIGHTED_VOTE = "weighted_vote"  # 加权投票


class VerificationStatus(str, Enum):
    """验证状态枚举"""

    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    PASSED = "passed"  # 通过
    FAILED = "failed"  # 失败
    PARTIAL = "partial"  # 部分通过
    TIMEOUT = "timeout"  # 超时
    ERROR = "error"  # 错误


class VerifierConfig(BaseModel):
    """
    单个验证器配置
    
    用于配置单个验证器的行为，包括类型、超时、重试等。
    """

    verifier_id: str  # 验证器唯一标识
    verifier_type: VerificationType  # 验证器类型
    weight: float = 1.0  # 权重（用于加权投票策略）
    timeout_seconds: int = 60  # 超时时间（秒）
    required: bool = True  # 是否必需（非必需验证器失败不影响整体）
    retry_on_failure: bool = True  # 失败时是否重试
    max_retries: int = 2  # 最大重试次数
    config: Dict[str, Any] = Field(
        default_factory=dict
    )  # 验证器特定配置参数


class VerificationConfig(BaseModel):
    """
    任务级验证配置
    
    嵌入到TaskContract中，控制任务的验证行为。
    默认禁用，需要显式启用才会触发验证流程。
    """

    enabled: bool = False  # 是否启用验证（默认关闭，保持向后兼容）
    strategy: VerificationStrategy = VerificationStrategy.ALL_MUST_PASS  # 验证策略
    verifiers: List[VerifierConfig] = Field(
        default_factory=list
    )  # 验证器列表
    auto_trigger: bool = True  # Worker完成后是否自动触发验证
    fallback_action: str = "retry"  # 验证失败后的动作: retry/fail/escalate
    max_total_retries: int = 3  # 总重试次数
    escalation_target: Optional[str] = (
        None  # 升级目标（如人工审核Agent ID）
    )


class SingleVerifierResult(BaseModel):
    """
    单个验证器的执行结果
    
    记录单个验证器的执行状态、结果和详细信息。
    """

    verifier_id: str  # 验证器ID
    verifier_type: str  # 验证器类型
    status: VerificationStatus  # 执行状态
    passed: bool  # 是否通过
    confidence: float = 0.0  # 置信度（0.0-1.0）
    summary: str = ""  # 简要总结
    details: Dict[str, Any] = Field(
        default_factory=dict
    )  # 详细结果数据
    error: Optional[str] = None  # 错误信息（如果有）
    execution_time_ms: int = 0  # 执行耗时（毫秒）
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )  # 执行时间戳
    retry_count: int = 0  # 重试次数


class VerificationResult(BaseModel):
    """
    整体验证结果
    
    汇总所有验证器的执行结果，并根据策略得出最终结论。
    """

    task_id: str  # 任务ID
    overall_status: VerificationStatus  # 整体验证状态
    overall_passed: bool  # 整体是否通过
    strategy: str  # 使用的验证策略
    verifier_results: List[SingleVerifierResult] = Field(
        default_factory=list
    )  # 各验证器结果
    summary: str = ""  # 总体摘要
    recommendation: str = ""  # 建议动作：accept/retry/escalate/reject
    confidence_score: float = 0.0  # 整体置信度（0.0-1.0）
    total_execution_time_ms: int = 0  # 总执行耗时（毫秒）
    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )  # 完成时间

    def get_passed_verifiers(self) -> List[SingleVerifierResult]:
        """获取通过的验证器列表"""
        return [r for r in self.verifier_results if r.passed]

    def get_failed_verifiers(self) -> List[SingleVerifierResult]:
        """获取失败的验证器列表"""
        return [r for r in self.verifier_results if not r.passed]

    def get_error_verifiers(self) -> List[SingleVerifierResult]:
        """获取出错的验证器列表"""
        return [
            r
            for r in self.verifier_results
            if r.status == VerificationStatus.ERROR
        ]

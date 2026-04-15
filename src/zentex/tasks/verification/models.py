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


class FailureType(str, Enum):
    """Phase C2: 任务失败类型分类
    
    用于将失败分类到特定类别，便于监督系统路由和处理。
    """
    # 执行器失败
    EXECUTOR_CRASH = "executor_crash"  # 执行器崩溃
    EXECUTOR_TIMEOUT = "executor_timeout"  # 执行器超时
    EXECUTOR_UNAVAILABLE = "executor_unavailable"  # 执行器不可用
    
    # 逻辑/设计失败
    INCORRECT_OUTPUT = "incorrect_output"  # 输出不正确
    PARTIAL_OUTPUT = "partial_output"  # 输出不完整
    OUTPUT_QUALITY_LOW = "output_quality_low"  # 输出质量低
    MISSING_REQUIREMENT = "missing_requirement"  # 遗漏需求
    
    # 资源失败
    OUT_OF_MEMORY = "out_of_memory"  # 内存不足
    DISK_FULL = "disk_full"  # 磁盘满
    NETWORK_ERROR = "network_error"  # 网络错误
    
    # 依赖失败
    DEPENDENCY_FAILED = "dependency_failed"  # 依赖失败
    CIRCULAR_DEPENDENCY = "circular_dependency"  # 循环依赖
    
    # 数据失败
    INVALID_INPUT = "invalid_input"  # 输入无效
    DATA_CORRUPTION = "data_corruption"  # 数据损坏
    
    # 未知
    UNKNOWN = "unknown"  # 未知错误


class FailureSeverity(str, Enum):
    """Phase C2: 失败严重程度
    
    用于确定监督系统的响应优先级。
    """
    CRITICAL = "critical"  # 严重 - 必须立即升级
    HIGH = "high"  # 高 - 应该升级
    MEDIUM = "medium"  # 中 - 可以重试或升级
    LOW = "low"  # 低 - 尝试替代方案或日志记录
    INFO = "info"  # 信息 - 仅作为信息


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


class VerificationEvidence(BaseModel):
    """
    Phase C2: 验证证据和追踪信息
    
    记录支持验证决定的痕迹和证据。
    用于审计路径和监督系统的决策制定。
    """
    # 证据类型
    evidence_type: str = Field(
        description="证据类型: trace, log, metric, comparison, screenshot, 等"
    )
    
    # 内容和元数据
    content: str = Field(description="证据内容 (日志摘录、指标值等)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = Field(description="证据来源 (执行器、系统、断言等)")
    
    # 置信度
    confidence: float = Field(
        ge=0, le=1,
        description="对该证据的置信度 (0-1)"
    )
    
    # 关联项
    related_field: Optional[str] = Field(
        default=None,
        description="该证据关联到的输出字段"
    )


class FailureClassification(BaseModel):
    """
    Phase C2: 任务失败的结构化分类
    
    根据失败类型和严重程度，路由到相应的监督行动。
    """
    # 标识
    task_id: str = Field(description="失败的任务ID")
    failure_type: FailureType = Field(description="失败类别")
    failure_severity: FailureSeverity = Field(description="失败严重程度")
    
    # 分析
    root_cause: str = Field(
        description="失败的根本原因 (不仅仅是症状)"
    )
    immediate_symptoms: List[str] = Field(
        default_factory=list,
        description="表明失败的可观察症状"
    )
    
    # 上下文
    execution_stage: str = Field(
        description="失败发生的阶段: setup, execution, verification, cleanup"
    )
    failed_executor_id: Optional[str] = Field(
        default=None,
        description="如果是执行器相关，是哪个执行器失败"
    )
    
    # 证据
    evidence: List[VerificationEvidence] = Field(
        default_factory=list,
        description="支持这个分类的证据"
    )
    
    # 监督路由
    recommended_action: str = Field(
        description="推荐的行动: retry, fallback, escalate, abort, manual_intervention"
    )
    action_priority: int = Field(
        ge=1, le=5,
        description="监督的优先级 (1=紧急, 5=低)"
    )
    
    # 元数据
    classified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    classifier_version: str = Field(default="1.0", description="分类器算法版本")


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
    
    # Phase C2: 失败分类信息 (当 overall_passed 为 False 时)
    failure_classification: Optional[FailureClassification] = Field(
        default=None,
        description="详细的失败分析和分类 (仅当整体失败时)"
    )
    
    # 输出质量指标
    output_quality_score: Optional[float] = Field(
        default=None,
        ge=0, le=1,
        description="输出质量评分 (0-1)"
    )
    completeness_score: Optional[float] = Field(
        default=None,
        ge=0, le=1,
        description="相对于需求的完整度评分"
    )
    
    # 重试和恢复信息
    is_retryable: bool = Field(
        default=False,
        description="是否应该重试该任务"
    )
    suggested_retry_strategy: Optional[str] = Field(
        default=None,
        description="重试策略: 使用相同执行器、不同执行器或不同方法"
    )

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
    
    # Phase C2: 失败分类辅助方法
    def is_success(self) -> bool:
        """快速检查验证是否通过"""
        return self.overall_passed
    
    def is_recoverable(self) -> bool:
        """检查失败是否可恢复"""
        if not self.failure_classification:
            return False
        return self.failure_classification.recommended_action in [
            "retry", "fallback"
        ]
    
    def get_failure_type(self) -> Optional[FailureType]:
        """获取失败类型"""
        if self.failure_classification:
            return self.failure_classification.failure_type
        return None
    
    def get_failure_severity(self) -> Optional[FailureSeverity]:
        """获取失败严重程度"""
        if self.failure_classification:
            return self.failure_classification.failure_severity
        return None

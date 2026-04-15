"""
Phase D1/D2: 任务监督系统 - Task Supervision System

根据失败分类结果做出智能决策和监督行动。
支持多种行动类型：重试、降级、升级、中止、人工干预。
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from pydantic import BaseModel, Field


class SupervisionAction(str, Enum):
    """监督行动类型"""
    RETRY = "retry"  # 重新尝试
    FALLBACK = "fallback"  # 使用备用方案
    ESCALATE = "escalate"  # 升级到人工/高级系统
    ABORT = "abort"  # 中止任务
    MANUAL_INTERVENTION = "manual_intervention"  # 需要人工干预
    QUARANTINE = "quarantine"  # 隔离/暂停任务
    COMPENSATE = "compensate"  # 补偿行动（回滚相关操作）


class RetryStrategy(str, Enum):
    """重试策略"""
    IMMEDIATE = "immediate"  # 立即重试
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # 指数退避
    LINEAR_BACKOFF = "linear_backoff"  # 线性退避
    RANDOM_BACKOFF = "random_backoff"  # 随机退避


class FallbackStrategy(str, Enum):
    """降级策略"""
    ALTERNATE_EXECUTOR = "alternate_executor"  # 使用备用执行器
    SIMPLIFIED_VERSION = "simplified_version"  # 简化版本的任务
    CACHED_RESULT = "cached_result"  # 使用缓存结果
    DEFAULT_VALUE = "default_value"  # 使用默认值


class EscalationTarget(str, Enum):
    """升级目标"""
    HUMAN_OPERATOR = "human_operator"  # 人工操作员
    MANAGEMENT_SYSTEM = "management_system"  # 管理系统
    EMERGENCY_HANDLER = "emergency_handler"  # 紧急处理
    EXTERNAL_SERVICE = "external_service"  # 外部服务


class SupervisionDecision(BaseModel):
    """
    Phase D1: 监督决策
    
    基于失败分类做出的决策，包括建议行动和参数。
    """
    # 任务标识
    task_id: str = Field(description="失败的任务ID")
    failure_type: str = Field(description="失败类型")
    failure_severity: str = Field(description="失败严重程度")
    
    # 决策
    recommended_action: SupervisionAction = Field(
        description="推荐的监督行动"
    )
    confidence: float = Field(
        ge=0, le=1,
        description="决策的置信度 (0-1)"
    )
    
    # 行动参数
    action_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="特定于行动的参数"
    )
    
    # 详情
    decision_reasoning: str = Field(
        description="做出该决策的原因"
    )
    alternative_actions: List[SupervisionAction] = Field(
        default_factory=list,
        description="可选的备选行动"
    )
    
    # 元数据
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decision_maker: str = Field(
        default="supervision_engine",
        description="做出决策的系统/人员"
    )


class RetryDecision(BaseModel):
    """
    Phase D2: 重试决策
    
    具体的重试参数和策略。
    """
    strategy: RetryStrategy = Field(description="重试策略")
    max_attempts: int = Field(ge=1, description="最大重试次数")
    initial_delay_seconds: float = Field(
        ge=0,
        description="初始延迟时间（秒）"
    )
    max_delay_seconds: float = Field(
        ge=0,
        description="最大延迟时间（秒）"
    )
    backoff_multiplier: float = Field(
        ge=1,
        default=2.0,
        description="指数退避乘数"
    )
    jitter_enabled: bool = Field(
        default=True,
        description="是否启用抖动"
    )
    preserve_context: bool = Field(
        default=True,
        description="是否保留任务执行上下文"
    )


class FallbackDecision(BaseModel):
    """
    Phase D2: 降级决策
    
    具体的备选执行器或方案信息。
    """
    strategy: FallbackStrategy = Field(description="降级策略")
    fallback_executor_id: Optional[str] = Field(
        default=None,
        description="备用执行器ID（如适用）"
    )
    fallback_resource_pool: Optional[str] = Field(
        default=None,
        description="备用资源池（如适用）"
    )
    expected_quality_impact: float = Field(
        ge=-1, le=1,
        description="质量预期影响 (-1=显著下降, 0=无影响, 1=改进)"
    )
    timeout_adjustment: float = Field(
        ge=0.1,
        default=1.5,
        description="超时时间调整倍数"
    )


class EscalationDecision(BaseModel):
    """
    Phase D2: 升级决策
    
    具体的升级目标和通知信息。
    """
    target: EscalationTarget = Field(description="升级目标")
    priority: int = Field(
        ge=1, le=5,
        description="升级优先级 (1=紧急, 5=低)"
    )
    notification_recipients: List[str] = Field(
        default_factory=list,
        description="应该被通知的人/系统列表"
    )
    context_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="提供给升级处理的上下文数据"
    )
    reason_for_escalation: str = Field(
        description="升级原因说明"
    )


class CompensationAction(BaseModel):
    """
    Phase D2: 补偿行动
    
    当任务失败时需要执行的补偿操作。
    """
    affected_resource_ids: List[str] = Field(
        description="受影响的资源ID列表"
    )
    compensation_type: str = Field(
        description="补偿类型: rollback, cleanup, notify, restore, 等"
    )
    compensation_priority: int = Field(
        ge=1, le=5,
        description="补偿优先级"
    )
    must_complete: bool = Field(
        default=True,
        description="补偿操作是否必须完成"
    )


class SupervisionResult(BaseModel):
    """
    Phase D2: 监督结果
    
    监督动作执行后的结果。
    """
    # 结果标识
    task_id: str = Field(description="被监督的任务ID")
    decision_id: str = Field(description="相关的监督决策ID")
    
    # 执行状态
    status: str = Field(
        description="执行状态: pending, in_progress, completed, failed"
    )
    action_taken: SupervisionAction = Field(description="实际执行的行动")
    
    # 结果信息
    success: bool = Field(description="监督行动是否成功")
    message: str = Field(description="执行结果消息")
    error: Optional[str] = Field(
        default=None,
        description="如果失败，失败原因"
    )
    
    # 新任务信息
    new_task_id: Optional[str] = Field(
        default=None,
        description="如果创建了新任务（重试/降级），新任务的ID"
    )
    
    # 补偿
    compensation_executed: bool = Field(
        default=False,
        description="是否执行了补偿行动"
    )
    compensation_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="补偿行动的结果"
    )
    
    # 元数据
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_duration_seconds: float = Field(
        default=0,
        description="执行耗时"
    )


class SupervisionPolicy(BaseModel):
    """
    监督策略
    
    定义不同失败场景下的监督策略。
    """
    # 基本信息
    policy_name: str = Field(description="策略名称")
    description: str = Field(description="策略描述")
    
    # 关键参数
    retry_config: RetryDecision = Field(
        description="默认重试配置"
    )
    max_escalation_depth: int = Field(
        ge=1,
        default=3,
        description="最大升级深度"
    )
    enable_compensation: bool = Field(
        default=True,
        description="是否启用补偿行动"
    )
    
    # 超时
    decision_timeout_seconds: int = Field(
        ge=1,
        default=30,
        description="监督决策超时"
    )
    action_execution_timeout_seconds: int = Field(
        ge=1,
        default=300,
        description="监督行动执行超时"
    )


class FailureResponseMapping(BaseModel):
    """
    Phase D1: 失败-应对映射
    
    将特定的失败类型映射到监督行动。
    """
    # 映射标识
    failure_type: str = Field(description="失败类型")
    failure_severity: str = Field(description="失败严重程度")
    
    # 应对策略
    primary_action: SupervisionAction = Field(description="主要行动")
    fallback_actions: List[SupervisionAction] = Field(
        default_factory=list,
        description="备选行动列表"
    )
    
    # 条件和参数
    conditions: Dict[str, Any] = Field(
        default_factory=dict,
        description="触发该映射的额外条件"
    )
    action_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="行动参数"
    )
    
    # 优先级
    priority: int = Field(
        ge=1, le=100,
        default=50,
        description="映射优先级 (1=最高, 100=最低)"
    )
    
    # 有效期
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_until: Optional[datetime] = Field(
        default=None,
        description="映射失效时间"
    )

"""
Alignment - 用户偏好辨析与意图对齐 - 数据模型层

定义用户偏好、意图歧义案例、异常候选等核心数据结构。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PreferenceStatus(str, Enum):
    """偏好状态枚举"""
    PENDING = "pending"  # 待确认
    CONFIRMED = "confirmed"  # 已确认
    REVOKED = "revoked"  # 已撤销
    EXPIRED = "expired"  # 已过期


class ConfirmationStatus(str, Enum):
    """确认状态枚举"""
    UNCONFIRMED = "unconfirmed"  # 未确认
    CONFIRMED_AS_PREFERENCE = "confirmed_as_preference"  # 确认为偏好
    CONFIRMED_AS_ANOMALY = "confirmed_as_anomaly"  # 确认为异常
    REQUIRES_INVESTIGATION = "requires_investigation"  # 需要进一步调查


class AnomalyType(str, Enum):
    """异常类型枚举"""
    UNCONVENTIONAL_STRUCTURE = "unconventional_structure"  # 非常规结构
    UNUSUAL_DEPLOYMENT_TIME = "unusual_deployment_time"  # 非常规部署时段
    CUSTOM_THRESHOLD = "custom_threshold"  # 定制阈值
    DEVIATION_FROM_NORM = "deviation_from_norm"  # 偏离常态
    EXTREME_SIGNAL = "extreme_signal"  # 极端信号
    INJECTION_ATTEMPT = "injection_attempt"  # 注入尝试


class RiskLevel(str, Enum):
    """风险等级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UserDecision(str, Enum):
    """用户决策枚举"""
    CONFIRM_AS_PREFERENCE = "confirm_as_preference"
    MARK_AS_ANOMALY = "mark_as_anomaly"
    NEEDS_INVESTIGATION = "needs_investigation"


class UserPreference(BaseModel):
    """
    用户偏好对象
    
    记录已确认的个人偏好和适用边界，确保系统不会将用户的故意配置误判为故障并自动修复。
    """
    preference_id: str = Field(..., description="偏好唯一标识")
    content: str = Field(..., description="偏好内容，描述用户希望系统遵循的个性化设置或习惯")
    confirmed_at: datetime = Field(..., description="该偏好被用户正式确认的时间点")
    source: str = Field(..., description="信息来源，如 manual_user_input / learned_from_behavior")
    applicable_scope: Dict[str, Any] = Field(
        default_factory=dict,
        description="适用范围，说明该偏好在哪些场景下生效",
        examples=[{"domains": ["filesystem"], "paths": ["/home/user/custom_dir"]}]
    )
    can_override_safety_redline: bool = Field(
        default=False,
        description="是否可覆盖安全红线，通常应为 False"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="置信度，表示对该偏好的把握程度"
    )
    status: PreferenceStatus = Field(default=PreferenceStatus.CONFIRMED, description="当前状态")
    expires_at: Optional[datetime] = Field(None, description="过期时间，None 表示永久有效")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class IntentAmbiguityCase(BaseModel):
    """
    意图歧义案例
    
    记录系统无法确定用户真实意图的场景和待确认项，用于后续学习和避免重复误判。
    """
    case_id: str = Field(..., description="案例唯一标识")
    anomaly_description: str = Field(..., description="异常描述，说明检测到的非标准状态")
    preference_hypothesis: Optional[str] = Field(
        None,
        description="偏好假设，系统猜测这可能是用户偏好的解释"
    )
    confirmation_status: ConfirmationStatus = Field(
        default=ConfirmationStatus.UNCONFIRMED,
        description="确认状态"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    resolved_at: Optional[datetime] = Field(None, description="解决时间")
    resolution_action: Optional[str] = Field(
        None,
        description="解决动作，如 confirmed_preference / marked_as_anomaly / auto_fixed"
    )
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="支持该假设的历史交互或行为线索引用"
    )
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, description="风险等级")
    related_anomaly_id: Optional[str] = Field(None, description="关联的异常候选 ID")
    user_feedback: Optional[str] = Field(None, description="用户反馈内容")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AnomalyCandidate(BaseModel):
    """
    异常候选
    
    系统检测到的可能异常状态，需要进一步判断是用户偏好还是真实故障。
    """
    candidate_id: str = Field(..., description="候选唯一标识")
    detected_state: Dict[str, Any] = Field(..., description="检测到的状态快照")
    anomaly_type: AnomalyType = Field(..., description="异常类型")
    severity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="严重程度，0-1 之间"
    )
    detection_source: str = Field(..., description="检测来源，如 environment_scouter / safety_gate")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="检测时间")
    context_snapshot: Optional[Dict[str, Any]] = Field(
        None,
        description="上下文快照，包含检测时的环境信息"
    )
    suggested_action: Optional[str] = Field(
        None,
        description="建议动作，如 wait_for_confirmation / auto_fix / ignore"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class PreferenceCandidate(BaseModel):
    """
    偏好候选
    
    系统推测某异常可能是用户偏好，需要用户确认后才能正式记录。
    """
    candidate_id: str = Field(..., description="候选唯一标识")
    related_anomaly_id: str = Field(..., description="关联的异常候选 ID")
    hypothesized_preference: str = Field(..., description="假设的偏好内容")
    confidence_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="置信度分数，基于历史数据和模式匹配计算"
    )
    requires_confirmation: bool = Field(
        default=True,
        description="是否需要用户确认"
    )
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, description="如果误判的风险等级")
    supporting_evidence: List[str] = Field(
        default_factory=list,
        description="支持该假设的证据列表"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    expires_at: Optional[datetime] = Field(
        None,
        description="过期时间，超时未确认则自动失效"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ExtremeSignalRecord(BaseModel):
    """
    极端信号记录
    
    记录被判定为极端或高风险的外部信号，用于审计和模式学习。
    """
    record_id: str = Field(..., description="记录唯一标识")
    signal_content: str = Field(..., description="信号内容")
    signal_source: str = Field(..., description="信号来源")
    risk_indicators: List[str] = Field(
        default_factory=list,
        description="风险指标列表，如 contains_injection_pattern / contradicts_physical_state"
    )
    risk_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="风险评分"
    )
    intercepted_at: datetime = Field(default_factory=datetime.utcnow, description="拦截时间")
    confirmation_required: bool = Field(
        default=True,
        description="是否要求二次确认"
    )
    confirmation_result: Optional[str] = Field(
        None,
        description="确认结果，如 approved / rejected / escalated"
    )
    is_malicious: Optional[bool] = Field(None, description="是否被标记为恶意")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AttackSample(BaseModel):
    """
    攻击样本
    
    记录已确认的恶意信号模式，用于未来检测和防护。
    """
    sample_id: str = Field(..., description="样本唯一标识")
    signal_content_hash: str = Field(..., description="信号内容哈希（SHA256，保护隐私）")
    attack_type: str = Field(..., description="攻击类型，如 injection / spoofing / manipulation")
    risk_indicators: List[str] = Field(default_factory=list, description="风险指标")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    marked_at: datetime = Field(..., description="标记时间")
    marked_by: str = Field(..., description="标记者，analyst_id 或 'auto'")
    pattern_signature: str = Field(..., description="用于模式匹配的特征签名")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ===== 引擎返回类型 =====

class JudgmentConclusion(str, Enum):
    """判断结论枚举"""
    KNOWN_PREFERENCE = "known_preference"  # 已知偏好
    REQUIRES_CONFIRMATION = "requires_confirmation"  # 需要确认
    AUTO_CONFIRMED_PREFERENCE = "auto_confirmed_preference"  # 自动确认的偏好
    CONFIRMED_ANOMALY = "confirmed_anomaly"  # 确认为异常


class ActionRequired(str, Enum):
    """所需动作枚举"""
    NONE = "none"  # 无需动作
    USER_CONFIRMATION = "user_confirmation"  # 需要用户确认
    AUDIT_ONLY = "audit_only"  # 仅审计
    ESCALATE = "escalate"  # 升级处理


class JudgmentResult(BaseModel):
    """判断流程结果"""
    conclusion: JudgmentConclusion = Field(..., description="判断结论")
    preference: Optional[UserPreference] = Field(None, description="匹配的偏好（如果有）")
    ambiguity_case: Optional[IntentAmbiguityCase] = Field(None, description="创建的歧义案例（如果需要确认）")
    action_required: ActionRequired = Field(..., description="需要的后续动作")
    reasoning: Optional[str] = Field(None, description="推理说明")


class PreferenceMatchResult(BaseModel):
    """偏好匹配结果"""
    is_known_preference: bool = Field(..., description="是否为已知偏好")
    preference: Optional[UserPreference] = Field(None, description="匹配的偏好")
    similarity_score: float = Field(default=0.0, ge=0.0, le=1.0, description="相似度分数")


class RiskAssessment(BaseModel):
    """风险评估结果"""
    risk_score: float = Field(..., ge=0.0, le=1.0, description="风险评分")
    risk_indicators: List[str] = Field(default_factory=list, description="风险指标列表")
    requires_confirmation: bool = Field(..., description="是否需要确认")
    is_potentially_malicious: bool = Field(default=False, description="是否可能为恶意")


class EscalationLevel(str, Enum):
    """升级级别"""
    STANDARD = "standard"
    HIGH = "high"
    CRITICAL = "critical"


class ConfirmationRequest(BaseModel):
    """确认请求"""
    request_id: str = Field(..., description="请求唯一标识")
    case_id: Optional[str] = Field(None, description="关联的案例 ID")
    signal_record_id: Optional[str] = Field(None, description="关联的信号记录 ID")
    description: str = Field(..., description="确认请求描述")
    risk_level: RiskLevel = Field(..., description="风险等级")
    suggested_actions: List[str] = Field(
        default_factory=lambda: ["approve", "reject", "escalate"],
        description="建议的操作选项"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    expires_at: Optional[datetime] = Field(None, description="过期时间")


class DecisionBlock(BaseModel):
    """决策阻断记录"""
    block_id: str = Field(..., description="阻断唯一标识")
    decision_context: Dict[str, Any] = Field(..., description="决策上下文")
    blocking_reason: str = Field(..., description="阻断原因")
    blocked_at: datetime = Field(default_factory=datetime.utcnow, description="阻断时间")
    requires_approval: bool = Field(default=True, description="是否需要人工审批才能继续")


class BatchClearResult(BaseModel):
    """批量清除结果"""
    affected_count: int = Field(..., description="受影响的偏好数量")
    affected_preferences: List[str] = Field(default_factory=list, description="受影响的偏好 ID 列表")
    dry_run: bool = Field(default=False, description="是否为预览模式")


class BatchItemResult(BaseModel):
    """批量操作单项结果"""
    case_id: str = Field(..., description="案例 ID")
    success: bool = Field(..., description="是否成功")
    error: Optional[str] = Field(None, description="错误信息（如果失败）")


class BatchConfirmResult(BaseModel):
    """批量确认结果"""
    results: List[BatchItemResult] = Field(default_factory=list, description="各项结果")
    
    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)
    
    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.results if not r.success)


class RedlineCheckResult(BaseModel):
    """红线检查结果"""
    passed: bool = Field(..., description="是否通过检查")
    warning: Optional[str] = Field(None, description="警告信息")
    violation_details: Optional[str] = Field(None, description="违规详情")
    blocked: bool = Field(default=False, description="是否被阻断")
    requires_audit: bool = Field(default=False, description="是否需要审计")


class DecisionAdjustment(BaseModel):
    """决策调整建议"""
    adjusted_priorities: Dict[str, float] = Field(
        default_factory=dict,
        description="调整后的优先级映射"
    )
    reasoning: str = Field(..., description="调整理由")


class MindModelAdjustment(BaseModel):
    """心智模型调整建议"""
    adjusted_trust_level: Optional[float] = Field(None, description="调整后的信任级别")
    adjusted_interpretation_strategy: Optional[str] = Field(None, description="调整后的解释策略")
    reasoning: str = Field(..., description="调整理由")


class AttackMatch(BaseModel):
    """攻击匹配结果"""
    matched_sample_id: str = Field(..., description="匹配的样本 ID")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="相似度分数")
    attack_type: str = Field(..., description="攻击类型")
    confidence: float = Field(..., ge=0.0, le=1.0, description="匹配置信度")


class CacheEntry:
    """缓存条目"""
    def __init__(self, preferences: List[UserPreference], timestamp: float):
        self.preferences = preferences
        self.timestamp = timestamp

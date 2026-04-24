from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class GovernanceStatus(str, Enum):
    """治理状态"""
    ACTIVE = "active"            # 活跃
    VERIFIED = "verified"        # 已验证
    SUSPECT = "suspect"          # 可疑
    ARCHIVED = "archived"        # 已归档
    DEPRECATED = "deprecated"    # 已废弃
    HIDDEN = "hidden"            # 已隐藏

class ReflectionType(str, Enum):
    """反思类型"""
    DECISION_REFLECTION = "decision_reflection"      # 决策反思
    ACTION_REFLECTION = "action_reflection"          # 行动反思
    OUTCOME_REFLECTION = "outcome_reflection"        # 结果反思
    PROCESS_REFLECTION = "process_reflection"        # 过程反思
    STRATEGY_REFLECTION = "strategy_reflection"      # 策略反思
    ERROR_REFLECTION = "error_reflection"            # 错误反思
    SUCCESS_REFLECTION = "success_reflection"        # 成功反思
    LEARNING_REFLECTION = "learning_reflection"        # 学习总结

class ReflectionDepth(str, Enum):
    """反思深度"""
    SURFACE = "surface"          # 表层反思
    ANALYTICAL = "analytical"    # 分析性反思
    STRATEGIC = "strategic"      # 战略性反思
    SYSTEMIC = "systemic"        # 系统性反思

class ReflectionQuality(str, Enum):
    """反思质量"""
    POOR = "poor"              # 质量差
    FAIR = "fair"              # 质量一般
    GOOD = "good"              # 质量良好
    EXCELLENT = "excellent"    # 质量优秀

class ReflectionTrigger(str, Enum):
    """反思触发器"""
    AUTOMATIC = "automatic"      # 自动触发
    MANUAL = "manual"           # 手动触发
    SCHEDULED = "scheduled"     # 定时触发
    EVENT_DRIVEN = "event_driven"  # 事件驱动
    ERROR_TRIGGERED = "error_triggered"  # 错误触发

class ReflectionItem(BaseModel):
    """原子反思项目模型"""
    item_id: str = Field(default_factory=lambda: f"item_{uuid4().hex[:8]}", description="项目唯一标识")
    name: Optional[str] = Field(default=None, description="项目名称")
    content: str = Field(description="反思内容")
    description: Optional[str] = Field(default=None, description="项目描述")
    category: str = Field(description="类别: insight/lesson/risk/meta/safety/core/improvement")
    is_immutable: bool = Field(default=False, description="是否不可修改（名称和描述）")
    can_be_removed: bool = Field(default=True, description="是否可以被删除")
    priority: int = Field(default=5, ge=1, le=10, description="优先级（1最高）")
    integrity_score: float = Field(default=1.0, ge=0.0, le=1.0, description="完整度/正确性评分")
    
    # 状态跟踪
    is_active: bool = Field(default=True, description="是否激活")
    reflection_count: int = Field(default=0, description="反思次数")
    last_reflected_at: Optional[datetime] = Field(default=None, description="最后反思时间")
    
    # 时间信息
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # 元数据
    tags: List[str] = Field(default_factory=list, description="标签")
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ReflectionRecord(BaseModel):
    """反思记录模型"""
    
    # 基础标识
    reflection_id: str = Field(description="反思唯一标识")
    trace_id: Optional[str] = Field(default=None, description="关联的追踪ID")
    audit_id: Optional[str] = Field(default=None, description="审计流程ID，跨模块溯源用")
    # Legacy field kept for backward compatibility; use audit_id for new code.
    session_id: Optional[str] = Field(default=None, description="会话ID（已废弃，请使用 audit_id）")
    
    # 反思分类
    reflection_type: ReflectionType = Field(description="反思类型")
    depth: ReflectionDepth = Field(default=ReflectionDepth.ANALYTICAL, description="反思深度")
    quality: ReflectionQuality = Field(default=ReflectionQuality.GOOD, description="反思质量")
    trigger: ReflectionTrigger = Field(description="触发器")
    
    # 时间信息
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="创建时间")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="更新时间")
    reflection_timestamp: datetime = Field(description="反思对应的时间戳")
    
    # 反思内容
    subject: str = Field(description="反思主题")
    context: Dict[str, Any] = Field(default_factory=dict, description="反思上下文")
    
    # 反思结果
    summary: str = Field(description="反思摘要")
    insights: List[str] = Field(default_factory=list, description="洞察列表 (已废弃，请使用 reflection_list)")
    lessons: List[str] = Field(default_factory=list, description="经验教训 (已废弃，请使用 reflection_list)")
    risks: List[str] = Field(default_factory=list, description="识别的风险 (已废弃，请使用 reflection_list)")
    improvements: List[str] = Field(default_factory=list, description="改进建议 (已废弃，请使用 reflection_list)")
    
    # 新增结构化反思列表
    reflection_list: List[ReflectionItem] = Field(default_factory=list, description="结构化反思项目列表")
    
    # 评估指标
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="反思置信度")
    impact_score: float = Field(default=0.5, ge=0.0, le=1.0, description="影响评分")
    actionability: float = Field(default=0.5, ge=0.0, le=1.0, description="可执行性评分")
    
    # 关联信息
    related_decisions: List[str] = Field(default_factory=list, description="相关决策ID")
    related_actions: List[str] = Field(default_factory=list, description="相关行动ID")
    related_outcomes: List[str] = Field(default_factory=list, description="相关结果ID")
    
    # 元数据
    tags: List[str] = Field(default_factory=list, description="标签")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")
    
    # 治理状态
    governance_status: GovernanceStatus = Field(default=GovernanceStatus.ACTIVE, description="治理状态")
    suspect_reason: Optional[str] = Field(default=None, description="可疑原因")
    verified_at: Optional[datetime] = Field(default=None, description="验证时间")
    verified_by: Optional[str] = Field(default=None, description="验证者")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ReflectionOverallRecord(BaseModel):
    """Lightweight overall summary record derived from a persisted reflection."""

    overall_id: str = Field(description="Overall record unique identifier")
    reflection_id: str = Field(description="Source reflection identifier")
    trace_id: Optional[str] = Field(default=None, description="Associated trace identifier")
    audit_id: Optional[str] = Field(default=None, description="Associated audit flow identifier")
    session_id: Optional[str] = Field(default=None, description="Legacy session identifier")
    reflection_type: ReflectionType = Field(description="Reflection type")
    subject: str = Field(description="Reflection subject")
    summary: str = Field(description="Overall summary text")
    quality: ReflectionQuality = Field(description="Reflection quality")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    impact_score: float = Field(default=0.5, ge=0.0, le=1.0)
    actionability: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GovernanceStatus(str, Enum):
    """治理状态"""
    ACTIVE = "active"            # 活跃
    VERIFIED = "verified"        # 已验证
    SUSPECT = "suspect"          # 可疑
    ARCHIVED = "archived"        # 已归档
    DEPRECATED = "deprecated"    # 已废弃
    HIDDEN = "hidden"            # 已隐藏

class ReflectionTemplate(BaseModel):
    """反思模板"""
    
    template_id: str = Field(description="模板ID")
    name: str = Field(description="模板名称")
    description: str = Field(description="模板描述")
    
    # 模板结构
    reflection_type: ReflectionType = Field(description="反思类型")
    required_fields: List[str] = Field(description="必需字段")
    optional_fields: List[str] = Field(description="可选字段")
    
    # 模板内容
    prompt_template: str = Field(description="提示模板")
    applicable_types: List[ReflectionType] = Field(default_factory=list, description="适用的反思类型")
    suggested_depth: Optional[ReflectionDepth] = Field(default=None, description="建议反思深度")
    guidance_notes: List[str] = Field(default_factory=list, description="引导说明")
    evaluation_criteria: Dict[str, Any] = Field(default_factory=dict, description="评估标准")
    
    # 使用统计
    usage_count: int = Field(default=0, description="使用次数")
    success_rate: float = Field(default=0.0, description="成功率")
    
    # 元数据
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: List[str] = Field(default_factory=list)

class ReflectionInsight(BaseModel):
    """反思洞察"""
    
    insight_id: str = Field(description="洞察ID")
    reflection_id: str = Field(description="来源反思ID")
    
    # 洞察内容
    category: str = Field(description="洞察类别")
    content: str = Field(description="洞察内容")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    
    # 洞察价值
    value_score: float = Field(default=0.5, ge=0.0, le=1.0)
    novelty_score: float = Field(default=0.5, ge=0.0, le=1.0)
    actionability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    
    # 关联信息
    related_patterns: List[str] = Field(default_factory=list)
    evidence_sources: List[str] = Field(default_factory=list)
    
    # 时间信息
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(default=None)

class ReflectionPattern(BaseModel):
    """反思模式"""
    
    pattern_id: str = Field(description="模式ID")
    name: str = Field(description="模式名称")
    description: str = Field(description="模式描述")
    
    # 模式特征
    pattern_type: str = Field(description="模式类型")
    frequency: int = Field(default=0, description="出现频率")
    strength: float = Field(default=0.5, ge=0.0, le=1.0, description="模式强度")
    
    # 模式内容
    triggers: List[str] = Field(default_factory=list, description="触发条件")
    indicators: List[str] = Field(default_factory=list, description="指标")
    consequences: List[str] = Field(default_factory=list, description="后果")
    
    # 模式分析
    success_correlation: float = Field(default=0.0, ge=-1.0, le=1.0)
    risk_impact: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # 治理信息
    status: GovernanceStatus = Field(default=GovernanceStatus.ACTIVE)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ReflectionMetrics(BaseModel):
    """反思指标"""
    
    # 基础统计
    total_reflections: int = Field(default=0, description="总反思数")
    reflections_by_type: Dict[str, int] = Field(default_factory=dict, description="按类型统计")
    reflections_by_depth: Dict[str, int] = Field(default_factory=dict, description="按深度统计")
    reflections_by_quality: Dict[str, int] = Field(default_factory=dict, description="按质量统计")
    
    # 质量指标
    average_confidence: float = Field(default=0.0, description="平均置信度")
    average_impact_score: float = Field(default=0.0, description="平均影响评分")
    average_actionability: float = Field(default=0.0, description="平均可执行性")
    
    # 时间指标
    reflections_today: int = Field(default=0, description="今日反思数")
    reflections_this_week: int = Field(default=0, description="本周反思数")
    reflections_this_month: int = Field(default=0, description="本月反思数")
    
    # 洞察统计
    total_insights: int = Field(default=0, description="总洞察数")
    high_value_insights: int = Field(default=0, description="高价值洞察数")
    
    # 模式统计
    identified_patterns: int = Field(default=0, description="识别的模式数")
    active_patterns: int = Field(default=0, description="活跃模式数")
    
    # 治理统计
    verified_reflections: int = Field(default=0, description="已验证反思数")
    suspect_reflections: int = Field(default=0, description="可疑反思数")
    archived_reflections: int = Field(default=0, description="已归档反思数")
    
    # 计算时间
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# 辅助方法
def create_reflection_id() -> str:
    """创建反思ID"""
    import uuid
    return f"reflection_{uuid.uuid4().hex[:12]}"

def create_insight_id() -> str:
    """创建洞察ID"""
    import uuid
    return f"insight_{uuid.uuid4().hex[:12]}"

def create_pattern_id() -> str:
    """创建模式ID"""
    import uuid
    return f"pattern_{uuid.uuid4().hex[:12]}"


# ============================================
# 固定的核心反思项目定义
# ============================================
# 这些项目是系统安全的基石，不能被删除或修改名称/描述
# AI只能在内容层面进行反思，不能改变项目的本质

CORE_FIXED_REFLECTION_ITEMS = [
    ReflectionItem(
        item_id="core_identity_consistency",
        name="身份一致性检查",
        content="Verify that current actions align with IdentityKernel's core identity definition",
        description="检查当前行为是否与IdentityKernel定义的核心身份保持一致",
        category="core",
        is_immutable=True,
        can_be_removed=False,
        priority=1,
        integrity_score=1.0,
        tags=["core", "identity", "safety"]
    ),
    ReflectionItem(
        item_id="core_safety_boundary",
        name="安全边界验证",
        content="Validate that current decision does not violate safety redlines or authorization boundaries",
        description="验证当前决策是否违反安全红线或授权边界",
        category="core",
        is_immutable=True,
        can_be_removed=False,
        priority=1,
        integrity_score=1.0,
        tags=["core", "safety", "redline"]
    ),
    ReflectionItem(
        item_id="core_continuity_lock",
        name="主体连续性锁验证",
        content="Ensure evolution, memory compression operations do not break subject continuity",
        description="确保进化、记忆压缩等操作不会破坏主体连续性",
        category="core",
        is_immutable=True,
        can_be_removed=False,
        priority=1,
        integrity_score=1.0,
        tags=["core", "continuity", "evolution"]
    ),
    ReflectionItem(
        item_id="core_metamotivation_drift",
        name="元动机漂移检测",
        content="Monitor whether meta-motivation deviates from original definition to prevent willpower tampering",
        description="监测元动机是否偏离原始定义，防止意志力被篡改",
        category="core",
        is_immutable=True,
        can_be_removed=False,
        priority=1,
        integrity_score=1.0,
        tags=["core", "metamotivation", "willpower"]
    ),
    ReflectionItem(
        item_id="core_audit_completeness",
        name="审计链完整性检查",
        content="Confirm all critical decisions have complete audit trail",
        description="确认所有关键决策都有完整的审计留痕",
        category="core",
        is_immutable=True,
        can_be_removed=False,
        priority=2,
        integrity_score=1.0,
        tags=["core", "audit", "compliance"]
    ),
]

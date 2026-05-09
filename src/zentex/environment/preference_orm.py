"""
Alignment - SQLAlchemy ORM 模型定义

使用 SQLAlchemy 2.0 风格定义 Alignment 模块的数据模型。
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


class UserPreferenceORM(Base):
    """
    用户偏好 ORM 模型
    
    存储已确认的用户偏好，用于匹配类似场景。
    """
    
    __tablename__ = "user_preferences"
    
    # 主键
    preference_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 偏好内容
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 确认时间
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # 来源
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    
    # 适用范围（JSON 字符串）
    applicable_scope: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 是否可覆盖安全红线
    can_override_safety_redline: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    
    # 置信度
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    
    # 状态
    status: Mapped[str] = mapped_column(String(32), default="confirmed", nullable=False)
    
    # 过期时间
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 元数据（JSON 字符串）
    metadata_json: Mapped[Optional[str]] = mapped_column("metadata", Text, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    
    # 索引
    __table_args__ = (
        Index("idx_preferences_status", "status"),
        Index("idx_preferences_source", "source"),
        Index("idx_preferences_confirmed_at", "confirmed_at"),
        Index("idx_preferences_expires_at", "expires_at"),
    )
    
    def __repr__(self) -> str:
        return f"<UserPreferenceORM(id={self.preference_id}, status={self.status})>"


class IntentAmbiguityCaseORM(Base):
    """
    意图歧义案例 ORM 模型
    
    存储需要用户确认的歧义案例。
    """
    
    __tablename__ = "intent_ambiguity_cases"
    
    # 主键
    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 异常描述
    anomaly_description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 偏好假设
    preference_hypothesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 确认状态
    confirmation_status: Mapped[str] = mapped_column(
        String(32), default="unconfirmed", nullable=False
    )
    
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # 解决时间
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 解决动作
    resolution_action: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    
    # 证据引用（JSON 数组字符串）
    evidence_refs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 风险等级
    risk_level: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    
    # 关联的异常候选 ID
    related_anomaly_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    # 用户反馈
    user_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 元数据（JSON 字符串）
    metadata_json: Mapped[Optional[str]] = mapped_column("metadata", Text, nullable=True)
    
    # 索引
    __table_args__ = (
        Index("idx_cases_status", "confirmation_status"),
        Index("idx_cases_risk_level", "risk_level"),
        Index("idx_cases_created_at", "created_at"),
        Index("idx_cases_resolved_at", "resolved_at"),
    )
    
    def __repr__(self) -> str:
        return f"<IntentAmbiguityCaseORM(id={self.case_id}, status={self.confirmation_status})>"


class AnomalyCandidateORM(Base):
    """
    异常候选 ORM 模型
    
    存储检测到的异常状态候选。
    """
    
    __tablename__ = "anomaly_candidates"
    
    # 主键
    candidate_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 检测到的状态（JSON 字符串）
    detected_state: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 异常类型
    anomaly_type: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # 严重程度
    severity: Mapped[float] = mapped_column(Float, nullable=False)
    
    # 检测来源
    detection_source: Mapped[str] = mapped_column(String(256), nullable=False)
    
    # 时间戳
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # 上下文快照（JSON 字符串）
    context_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 建议动作
    suggested_action: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    
    # 元数据（JSON 字符串）
    metadata_json: Mapped[Optional[str]] = mapped_column("metadata", Text, nullable=True)
    
    # 索引
    __table_args__ = (
        Index("idx_anomalies_type", "anomaly_type"),
        Index("idx_anomalies_severity", "severity"),
        Index("idx_anomalies_timestamp", "timestamp"),
        Index("idx_anomalies_source", "detection_source"),
    )
    
    def __repr__(self) -> str:
        return f"<AnomalyCandidateORM(id={self.candidate_id}, type={self.anomaly_type})>"


class AttackSampleORM(Base):
    """
    攻击样本 ORM 模型
    
    存储标记的恶意攻击样本，用于模式匹配。
    """
    
    __tablename__ = "attack_samples"
    
    # 主键
    sample_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 信号内容哈希（保护隐私）
    signal_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # 攻击类型
    attack_type: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # 风险指标（JSON 数组字符串）
    risk_indicators: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 置信度
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    
    # 标记时间
    marked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # 标记者
    marked_by: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # 模式签名（用于相似度匹配）
    pattern_signature: Mapped[str] = mapped_column(String(256), nullable=False)
    
    # 元数据（JSON 字符串）
    metadata_json: Mapped[Optional[str]] = mapped_column("metadata", Text, nullable=True)
    
    # 索引
    __table_args__ = (
        Index("idx_attacks_type", "attack_type"),
        Index("idx_attacks_signature", "pattern_signature"),
        Index("idx_attacks_marked_at", "marked_at"),
        Index("idx_attacks_confidence", "confidence"),
    )
    
    def __repr__(self) -> str:
        return f"<AttackSampleORM(id={self.sample_id}, type={self.attack_type})>"

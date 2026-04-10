"""
G19 - 用户偏好辨析与意图对齐 - 极端信号拦截器

负责评估信号风险、强制二次确认、阻断高风险决策。
"""

import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .preference_models import (
    ConfirmationRequest,
    DecisionBlock,
    EscalationLevel,
    ExtremeSignalRecord,
    RiskAssessment,
    RiskLevel,
)


class ExtremeSignalInterceptor:
    """极端信号拦截器"""

    def __init__(self):
        """初始化拦截器"""
        # 风险阈值配置
        self.confirmation_threshold = 0.7
        self.malicious_threshold = 0.8
        self.block_threshold = 0.9

    async def assess_signal_risk(
        self,
        signal_content: str,
        signal_source: str,
        context: Optional[Dict[str, Any]] = None
    ) -> RiskAssessment:
        """
        评估信号风险等级
        
        Args:
            signal_content: 信号内容
            signal_source: 信号来源
            context: 上下文信息
            
        Returns:
            RiskAssessment: 风险评估结果
        """
        risk_indicators = []
        risk_score = 0.0

        # 检查注入模式
        if self._contains_injection_pattern(signal_content):
            risk_indicators.append("injection_pattern_detected")
            risk_score += 0.4

        # 检查与物理状态冲突
        if context and self._contradicts_physical_state(signal_content, context.get("physical_state")):
            risk_indicators.append("contradicts_physical_state")
            risk_score += 0.3

        # 检查是否包含极端指令
        if self._contains_extreme_command(signal_content):
            risk_indicators.append("contains_extreme_command")
            risk_score += 0.3

        # 检查来自未信任源
        if context and not context.get("is_trusted_source", True):
            risk_indicators.append("untrusted_source")
            risk_score += 0.2

        # 归一化到 0-1
        risk_score = min(risk_score, 1.0)

        return RiskAssessment(
            risk_score=risk_score,
            risk_indicators=risk_indicators,
            requires_confirmation=risk_score >= self.confirmation_threshold,
            is_potentially_malicious=risk_score >= self.malicious_threshold
        )

    def _contains_injection_pattern(self, content: str) -> bool:
        """检查是否包含注入模式"""
        injection_patterns = [
            "ignore previous",
            "bypass security",
            "delete all",
            "drop table",
            "exec(",
            "eval(",
            "<script>",
            "javascript:",
        ]
        
        content_lower = content.lower()
        return any(pattern in content_lower for pattern in injection_patterns)

    def _contradicts_physical_state(
        self, 
        signal_content: str,
        physical_state: Optional[Dict[str, Any]]
    ) -> bool:
        """检查是否与物理状态冲突"""
        if not physical_state:
            return False
        
        # 简化实现：检查信号是否声称与物理状态不符的情况
        # 例如：信号说磁盘已满，但物理状态显示磁盘使用率仅 45%
        
        if "disk full" in signal_content.lower() and physical_state.get("disk_usage", 0) < 0.9:
            return True
        
        if "memory exhausted" in signal_content.lower() and physical_state.get("memory_usage", 0) < 0.9:
            return True
        
        return False

    def _contains_extreme_command(self, content: str) -> bool:
        """检查是否包含极端指令"""
        extreme_patterns = [
            "delete all",
            "format",
            "destroy",
            "wipe",
            "erase everything",
            "shutdown now",
            "kill process",
        ]
        
        content_lower = content.lower()
        return any(pattern in content_lower for pattern in extreme_patterns)

    async def force_secondary_confirmation(
        self,
        signal_record: ExtremeSignalRecord,
        escalation_level: EscalationLevel = EscalationLevel.STANDARD
    ) -> ConfirmationRequest:
        """
        强制转入二次确认
        
        Args:
            signal_record: 极端信号记录
            escalation_level: 升级级别
            
        Returns:
            ConfirmationRequest: 确认请求对象
        """
        # 确定风险等级
        if signal_record.risk_score >= self.block_threshold:
            risk_level = RiskLevel.CRITICAL
        elif signal_record.risk_score >= self.malicious_threshold:
            risk_level = RiskLevel.HIGH
        elif signal_record.risk_score >= self.confirmation_threshold:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        # 根据升级级别调整建议操作
        if escalation_level == EscalationLevel.CRITICAL:
            suggested_actions = ["approve_with_supervision", "reject", "escalate_to_security_team"]
        elif escalation_level == EscalationLevel.HIGH:
            suggested_actions = ["approve", "reject", "escalate"]
        else:
            suggested_actions = ["approve", "reject", "snooze"]

        return ConfirmationRequest(
            request_id=f"conf_{uuid.uuid4().hex[:8]}",
            signal_record_id=signal_record.record_id,
            description=f"高风险信号需要确认 (风险评分: {signal_record.risk_score:.2f})",
            risk_level=risk_level,
            suggested_actions=suggested_actions,
            created_at=datetime.utcnow(),
        )

    async def block_high_risk_decision(
        self,
        decision_context: Dict[str, Any],
        blocking_reason: str
    ) -> DecisionBlock:
        """
        阻断高风险决策
        
        Args:
            decision_context: 决策上下文
            blocking_reason: 阻断原因
            
        Returns:
            DecisionBlock: 阻断记录
        """
        return DecisionBlock(
            block_id=f"block_{uuid.uuid4().hex[:8]}",
            decision_context=decision_context,
            blocking_reason=blocking_reason,
            blocked_at=datetime.utcnow(),
            requires_approval=True
        )

    def create_extreme_signal_record(
        self,
        signal_content: str,
        signal_source: str,
        risk_assessment: RiskAssessment,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ExtremeSignalRecord:
        """
        创建极端信号记录
        
        Args:
            signal_content: 信号内容
            signal_source: 信号来源
            risk_assessment: 风险评估结果
            metadata: 额外元数据
            
        Returns:
            ExtremeSignalRecord: 极端信号记录对象
        """
        return ExtremeSignalRecord(
            record_id=f"sig_{uuid.uuid4().hex[:8]}",
            signal_content=signal_content,
            signal_source=signal_source,
            risk_indicators=risk_assessment.risk_indicators,
            risk_score=risk_assessment.risk_score,
            intercepted_at=datetime.utcnow(),
            confirmation_required=risk_assessment.requires_confirmation,
            is_malicious=risk_assessment.is_potentially_malicious,
            metadata=metadata or {}
        )

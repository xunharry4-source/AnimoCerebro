"""
Alignment - 用户偏好辨析与意图对齐 - 核心引擎

实现"异常候选 -> 偏好候选 -> 需要确认"三步判断流程。
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .preference_models import (
    ActionRequired,
    AnomalyCandidate,
    AnomalyType,
    ConfirmationStatus,
    IntentAmbiguityCase,
    JudgmentConclusion,
    JudgmentResult,
    PreferenceCandidate,
    PreferenceMatchResult,
    PreferenceStatus,
    RiskLevel,
    UserPreference,
)
from .preference_storage import PreferenceStore


class PreferenceEngine:
    """
    偏好辨析引擎
    
    实现"异常候选 -> 偏好候选 -> 需要确认"三步判断流程
    """

    def __init__(self, store: Optional[PreferenceStore] = None):
        """
        初始化引擎
        
        Args:
            store: 偏好存储实例，如果为 None 则创建默认实例
        """
        self.store = store or PreferenceStore()
        
        # 配置参数
        self.auto_confirm_threshold = 0.9  # 置信度 >= 0.9 时自动确认
        self.confirmation_timeout_hours = 24  # 确认超时时间

    async def execute_three_step_judgment(
        self,
        detected_state: Dict[str, Any],
        detection_source: str,
        context: Optional[Dict[str, Any]] = None
    ) -> JudgmentResult:
        """
        执行完整的三步判断流程
        
        Args:
            detected_state: 检测到的状态
            detection_source: 检测来源
            context: 上下文信息
            
        Returns:
            JudgmentResult: 包含判定结论和后续动作
        """
        # Step 1: 生成异常候选
        anomaly = await self.detect_anomaly(detected_state, detection_source, context)
        
        # 保存异常候选
        await self.store.save_anomaly_candidate(anomaly)
        
        # Step 2: 匹配历史偏好
        match_result = await self.match_historical_preference(anomaly)
        
        if match_result.is_known_preference:
            # 已知偏好，直接返回
            return JudgmentResult(
                conclusion=JudgmentConclusion.KNOWN_PREFERENCE,
                preference=match_result.preference,
                action_required=ActionRequired.NONE,
                reasoning="Matched existing confirmed preference"
            )
        
        # Step 3: 生成偏好候选并判断是否需要确认
        preference_candidate = await self.generate_preference_candidate(
            anomaly, 
            match_result.similarity_score
        )
        
        if preference_candidate.confidence_score >= self.auto_confirm_threshold:
            # 高置信度偏好，自动应用（但仍需审计）
            preference = await self.auto_confirm_preference(preference_candidate)
            return JudgmentResult(
                conclusion=JudgmentConclusion.AUTO_CONFIRMED_PREFERENCE,
                preference=preference,
                action_required=ActionRequired.AUDIT_ONLY,
                reasoning=f"Auto-confirmed with high confidence ({preference_candidate.confidence_score})"
            )
        else:
            # 需要用户确认
            ambiguity_case = await self.create_ambiguity_case(anomaly, preference_candidate)
            
            # 保存到数据库
            await self.store.save_ambiguity_case(ambiguity_case)
            
            return JudgmentResult(
                conclusion=JudgmentConclusion.REQUIRES_CONFIRMATION,
                ambiguity_case=ambiguity_case,
                action_required=ActionRequired.USER_CONFIRMATION,
                reasoning=f"Low confidence candidate ({preference_candidate.confidence_score}), requires user confirmation"
            )

    async def detect_anomaly(
        self,
        detected_state: Dict[str, Any],
        detection_source: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AnomalyCandidate:
        """
        检测异常状态，生成异常候选
        
        Args:
            detected_state: 检测到的状态
            detection_source: 检测来源
            context: 上下文信息
            
        Returns:
            AnomalyCandidate: 异常候选对象
        """
        # 根据检测到的状态判断异常类型
        anomaly_type = self._classify_anomaly_type(detected_state)
        
        # 计算严重程度
        severity = self._calculate_severity(detected_state, anomaly_type)
        
        return AnomalyCandidate(
            candidate_id=f"anom_{uuid.uuid4().hex[:8]}",
            detected_state=detected_state,
            anomaly_type=anomaly_type,
            severity=severity,
            detection_source=detection_source,
            timestamp=datetime.utcnow(),
            context_snapshot=context,
            suggested_action="wait_for_confirmation" if severity < 0.8 else "escalate"
        )

    def _classify_anomaly_type(self, detected_state: Dict[str, Any]) -> AnomalyType:
        """分类异常类型"""
        # 简化实现：根据状态内容判断
        state_str = str(detected_state).lower()
        
        if "injection" in state_str or "malicious" in state_str:
            return AnomalyType.INJECTION_ATTEMPT
        elif "extreme" in state_str or "critical" in state_str:
            return AnomalyType.EXTREME_SIGNAL
        elif "structure" in state_str or "directory" in state_str:
            return AnomalyType.UNCONVENTIONAL_STRUCTURE
        elif "threshold" in state_str:
            return AnomalyType.CUSTOM_THRESHOLD
        elif "deployment" in state_str or "schedule" in state_str:
            return AnomalyType.UNUSUAL_DEPLOYMENT_TIME
        else:
            return AnomalyType.DEVIATION_FROM_NORM

    def _calculate_severity(
        self, 
        detected_state: Dict[str, Any],
        anomaly_type: AnomalyType
    ) -> float:
        """计算严重程度"""
        # 基础严重程度
        base_severity = {
            AnomalyType.INJECTION_ATTEMPT: 0.9,
            AnomalyType.EXTREME_SIGNAL: 0.85,
            AnomalyType.UNCONVENTIONAL_STRUCTURE: 0.4,
            AnomalyType.CUSTOM_THRESHOLD: 0.5,
            AnomalyType.UNUSUAL_DEPLOYMENT_TIME: 0.6,
            AnomalyType.DEVIATION_FROM_NORM: 0.5,
        }.get(anomaly_type, 0.5)
        
        # 可以根据 detected_state 中的具体指标调整
        return min(base_severity, 1.0)

    async def match_historical_preference(
        self,
        anomaly: AnomalyCandidate
    ) -> PreferenceMatchResult:
        """
        与历史偏好记录比对
        
        Args:
            anomaly: 异常候选
            
        Returns:
            PreferenceMatchResult: 匹配结果
        """
        # 从异常状态中提取适用范围
        scope_filter = self._extract_scope_from_anomaly(anomaly)
        
        # 查询匹配的偏好
        matching_preferences = await self.store.query_preferences_by_scope(scope_filter)
        
        if matching_preferences:
            # 找到匹配的偏好，返回相似度最高的
            best_match = matching_preferences[0]
            similarity = self._calculate_similarity(anomaly.detected_state, best_match)
            
            return PreferenceMatchResult(
                is_known_preference=True,
                preference=best_match,
                similarity_score=similarity
            )
        
        # 未找到完全匹配，尝试查找相似偏好
        # 这里可以扩展为更复杂的相似度计算
        return PreferenceMatchResult(
            is_known_preference=False,
            preference=None,
            similarity_score=0.0
        )

    def _extract_scope_from_anomaly(self, anomaly: AnomalyCandidate) -> Dict[str, Any]:
        """从异常候选中提取适用范围"""
        # 简化实现：根据异常类型和状态提取
        scope = {"domains": []}
        
        if anomaly.anomaly_type == AnomalyType.UNCONVENTIONAL_STRUCTURE:
            scope["domains"].append("filesystem")
            # 尝试从 detected_state 提取路径
            if "path" in anomaly.detected_state:
                scope["paths"] = [anomaly.detected_state["path"]]
        
        elif anomaly.anomaly_type == AnomalyType.CUSTOM_THRESHOLD:
            scope["domains"].append("monitoring")
        
        elif anomaly.anomaly_type == AnomalyType.UNUSUAL_DEPLOYMENT_TIME:
            scope["domains"].append("deployment")
        
        return scope

    def _calculate_similarity(
        self, 
        detected_state: Dict[str, Any],
        preference: UserPreference
    ) -> float:
        """计算状态与偏好的相似度"""
        # 简化实现：基于适用范围的重叠度
        pref_scope = preference.applicable_scope
        
        # 检查 domains 是否匹配
        state_domains = set(self._extract_scope_from_state(detected_state).get("domains", []))
        pref_domains = set(pref_scope.get("domains", []))
        
        if not state_domains or not pref_domains:
            return 0.5  # 默认中等相似度
        
        intersection = state_domains.intersection(pref_domains)
        union = state_domains.union(pref_domains)
        
        if not union:
            return 0.0
        
        jaccard_similarity = len(intersection) / len(union)
        
        # 可以进一步考虑 paths、patterns 等的匹配
        return min(jaccard_similarity * 1.2, 1.0)  # 稍微放大以鼓励匹配

    def _extract_scope_from_state(self, detected_state: Dict[str, Any]) -> Dict[str, Any]:
        """从状态中提取域信息"""
        # 简化实现
        return {"domains": ["general"]}

    async def generate_preference_candidate(
        self,
        anomaly: AnomalyCandidate,
        similarity_score: float
    ) -> PreferenceCandidate:
        """
        生成偏好候选
        
        Args:
            anomaly: 异常候选
            similarity_score: 与历史偏好的相似度
            
        Returns:
            PreferenceCandidate: 偏好候选对象
        """
        # 生成假设的偏好内容
        hypothesized_preference = self._generate_hypothesis(anomaly)
        
        # 计算置信度分数
        confidence_score = self._calculate_confidence(anomaly, similarity_score)
        
        # 判断是否需要确认
        requires_confirmation = confidence_score < self.auto_confirm_threshold
        
        # 评估风险等级
        risk_level = self._assess_risk_level(anomaly)
        
        # 生成支持证据
        supporting_evidence = self._generate_supporting_evidence(anomaly, similarity_score)
        
        # 设置过期时间
        expires_at = datetime.utcnow() + timedelta(hours=self.confirmation_timeout_hours)
        
        return PreferenceCandidate(
            candidate_id=f"pcand_{uuid.uuid4().hex[:8]}",
            related_anomaly_id=anomaly.candidate_id,
            hypothesized_preference=hypothesized_preference,
            confidence_score=confidence_score,
            requires_confirmation=requires_confirmation,
            risk_level=risk_level,
            supporting_evidence=supporting_evidence,
            created_at=datetime.utcnow(),
            expires_at=expires_at
        )

    def _generate_hypothesis(self, anomaly: AnomalyCandidate) -> str:
        """生成偏好假设"""
        # 简化实现：根据异常类型生成描述
        hypotheses = {
            AnomalyType.UNCONVENTIONAL_STRUCTURE: 
                f"用户可能有意保持 {anomaly.detected_state.get('path', '未知路径')} 的特殊结构",
            AnomalyType.CUSTOM_THRESHOLD:
                f"用户可能设置了自定义的阈值配置",
            AnomalyType.UNUSUAL_DEPLOYMENT_TIME:
                f"用户可能在非标准时段进行部署操作",
            AnomalyType.DEVIATION_FROM_NORM:
                f"检测到的状态可能是用户的个性化配置",
            AnomalyType.EXTREME_SIGNAL:
                f"外部信号可能需要特殊处理权限",
            AnomalyType.INJECTION_ATTEMPT:
                f"信号可能包含恶意内容，需谨慎处理",
        }
        
        return hypotheses.get(
            anomaly.anomaly_type,
            "检测到的状态可能是用户的有意配置"
        )

    def _calculate_confidence(
        self,
        anomaly: AnomalyCandidate,
        similarity_score: float
    ) -> float:
        """计算置信度分数"""
        # 基础置信度来自相似度
        base_confidence = similarity_score
        
        # 根据异常类型调整
        type_adjustments = {
            AnomalyType.UNCONVENTIONAL_STRUCTURE: 0.1,
            AnomalyType.CUSTOM_THRESHOLD: 0.05,
            AnomalyType.UNUSUAL_DEPLOYMENT_TIME: 0.0,
            AnomalyType.DEVIATION_FROM_NORM: -0.1,
            AnomalyType.EXTREME_SIGNAL: -0.2,
            AnomalyType.INJECTION_ATTEMPT: -0.3,
        }
        
        adjustment = type_adjustments.get(anomaly.anomaly_type, 0.0)
        
        # 最终置信度
        confidence = base_confidence + adjustment
        
        # 限制在 0-1 范围
        return max(0.0, min(confidence, 1.0))

    def _assess_risk_level(self, anomaly: AnomalyCandidate) -> RiskLevel:
        """评估风险等级"""
        if anomaly.severity >= 0.8:
            return RiskLevel.CRITICAL
        elif anomaly.severity >= 0.6:
            return RiskLevel.HIGH
        elif anomaly.severity >= 0.4:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _generate_supporting_evidence(
        self,
        anomaly: AnomalyCandidate,
        similarity_score: float
    ) -> list:
        """生成支持证据"""
        evidence = []
        
        if similarity_score > 0.7:
            evidence.append(f"与历史偏好相似度: {similarity_score:.2f}")
        
        if anomaly.context_snapshot:
            evidence.append("存在上下文信息支持")
        
        if anomaly.anomaly_type in [
            AnomalyType.UNCONVENTIONAL_STRUCTURE,
            AnomalyType.CUSTOM_THRESHOLD
        ]:
            evidence.append("该类型异常常见于用户自定义配置")
        
        return evidence

    async def auto_confirm_preference(
        self,
        candidate: PreferenceCandidate
    ) -> UserPreference:
        """
        自动确认偏好（高置信度情况）
        
        Args:
            candidate: 偏好候选
            
        Returns:
            UserPreference: 创建的偏好对象
        """
        preference = UserPreference(
            preference_id=f"pref_{uuid.uuid4().hex[:8]}",
            content=candidate.hypothesized_preference,
            confirmed_at=datetime.utcnow(),
            source="auto_confirmed_by_engine",
            applicable_scope={},  # 需要从 anomaly 中提取
            can_override_safety_redline=False,
            confidence=candidate.confidence_score,
            status=PreferenceStatus.CONFIRMED,
            metadata={
                "auto_confirmed": True,
                "related_anomaly_id": candidate.related_anomaly_id,
                "confirmation_reason": f"High confidence ({candidate.confidence_score})"
            }
        )
        
        # 保存到数据库
        await self.store.save_preference(preference)
        
        return preference

    async def create_ambiguity_case(
        self,
        anomaly: AnomalyCandidate,
        candidate: PreferenceCandidate
    ) -> IntentAmbiguityCase:
        """
        创建意图歧义案例
        
        Args:
            anomaly: 异常候选
            candidate: 偏好候选
            
        Returns:
            IntentAmbiguityCase: 意图歧义案例对象
        """
        return IntentAmbiguityCase(
            case_id=f"case_{uuid.uuid4().hex[:8]}",
            anomaly_description=f"检测到{anomaly.anomaly_type.value}: {str(anomaly.detected_state)[:200]}",
            preference_hypothesis=candidate.hypothesized_preference,
            confirmation_status=ConfirmationStatus.UNCONFIRMED,
            created_at=datetime.utcnow(),
            risk_level=candidate.risk_level,
            related_anomaly_id=anomaly.candidate_id,
            evidence_refs=candidate.supporting_evidence,
            metadata={
                "candidate_id": candidate.candidate_id,
                "confidence_score": candidate.confidence_score
            }
        )

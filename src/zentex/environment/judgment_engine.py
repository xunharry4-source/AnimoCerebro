"""
Alignment - PydanticAI 智能判定引擎

使用 LLM 进行智能风险评估和偏好匹配。
支持降级到规则引擎保证高可用性。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .preference_settings import AlignmentSettings, get_preference_settings
from .preference_models import (
    AnomalyCandidate,
    JudgmentConclusion,
    JudgmentResult,
    PreferenceMatchResult,
    RiskAssessment,
    RiskLevel,
)

logger = logging.getLogger(__name__)


# ============================================================================
# LLM 结构化输出模型
# ============================================================================


class LLMRiskAssessment(BaseModel):
    """LLM 输出的风险评估结果"""
    
    risk_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="风险评分 (0.0-1.0)"
    )
    risk_indicators: List[str] = Field(
        default_factory=list,
        description="风险指标列表"
    )
    requires_confirmation: bool = Field(
        ...,
        description="是否需要二次确认"
    )
    is_potentially_malicious: bool = Field(
        ...,
        description="是否可能为恶意攻击"
    )
    reasoning: str = Field(
        ...,
        description="评估理由"
    )


class LLMPreferenceMatch(BaseModel):
    """LLM 输出的偏好匹配结果"""
    
    is_known_preference: bool = Field(
        ...,
        description="是否为已知偏好"
    )
    similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="相似度评分 (0.0-1.0)"
    )
    matched_preference_id: Optional[str] = Field(
        default=None,
        description="匹配的偏好 ID（如果找到）"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="匹配置信度"
    )
    reasoning: str = Field(
        ...,
        description="匹配理由"
    )


class LLMAnomalyClassification(BaseModel):
    """LLM 输出的异常分类结果"""
    
    anomaly_type: str = Field(
        ...,
        description="异常类型"
    )
    severity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="严重程度 (0.0-1.0)"
    )
    suggested_action: str = Field(
        ...,
        description="建议动作"
    )
    reasoning: str = Field(
        ...,
        description="分类理由"
    )


# ============================================================================
# 混合判定引擎
# ============================================================================


class HybridJudgmentEngine:
    """
    混合判定引擎
    
    策略：
    1. 优先使用 LLM 判定（准确率高）
    2. LLM 失败时降级到规则引擎（可用性保障）
    3. 记录判定来源用于后续分析
    """
    
    def __init__(self, settings: Optional[AlignmentSettings] = None):
        """
        初始化混合判定引擎
        
        Args:
            settings: Alignment 配置对象
        """
        self.settings = settings or get_preference_settings()
        self.llm_enabled = self._check_llm_availability()
        
        if self.llm_enabled:
            logger.info(f"LLM judgment enabled (provider: {self.settings.llm_provider.value})")
        else:
            logger.warning("LLM not available, using rule-based engine only")
    
    def _check_llm_availability(self) -> bool:
        """
        检查 LLM 是否可用
        
        Returns:
            True 如果 LLM 可用，False 否则
        """
        # Ollama 不需要 API key
        if self.settings.llm_provider.value == "ollama":
            return True
        
        # 其他提供商需要 API key
        if self.settings.llm_api_key:
            return True
        
        # 没有 API key，LLM 不可用
        return False
    
    async def assess_signal_risk(
        self,
        signal_content: str,
        signal_source: str,
        context: Optional[Dict[str, Any]] = None
    ) -> RiskAssessment:
        """
        评估信号风险
        
        Args:
            signal_content: 信号内容
            signal_source: 信号来源
            context: 上下文信息
            
        Returns:
            RiskAssessment: 风险评估结果
        """
        if self.llm_enabled:
            try:
                return await self._llm_risk_assessment(signal_content, signal_source, context)
            except Exception as e:
                logger.warning(f"LLM risk assessment failed, falling back to rules: {e}")
                return self._rule_based_risk_assessment(signal_content, signal_source, context)
        else:
            return self._rule_based_risk_assessment(signal_content, signal_source, context)
    
    async def _llm_risk_assessment(
        self,
        signal_content: str,
        signal_source: str,
        context: Optional[Dict[str, Any]] = None
    ) -> RiskAssessment:
        """
        使用 LLM 进行风险评估
        
        Note: 实际实现需要集成 PydanticAI Agent
        这里提供框架，待安装 pydantic-ai 后完善
        """
        # TODO: 集成 PydanticAI
        # from pydantic_ai import Agent
        # agent = Agent('openai:gpt-4o-mini', result_type=LLMRiskAssessment)
        # result = await agent.run(prompt)
        
        logger.debug("LLM risk assessment (placeholder)")
        
        # 临时返回规则引擎结果
        return self._rule_based_risk_assessment(signal_content, signal_source, context)
    
    def _rule_based_risk_assessment(
        self,
        signal_content: str,
        signal_source: str,
        context: Optional[Dict[str, Any]] = None
    ) -> RiskAssessment:
        """
        基于规则的风险评估（降级方案）
        
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
        injection_patterns = [
            "ignore previous",
            "bypass security",
            "delete all",
            "drop table",
            "exec(",
            "eval(",
            "<script>",
        ]
        
        content_lower = signal_content.lower()
        for pattern in injection_patterns:
            if pattern in content_lower:
                risk_indicators.append("injection_pattern_detected")
                risk_score += 0.4
                break
        
        # 检查极端指令
        extreme_patterns = ["delete all", "format", "destroy", "wipe"]
        for pattern in extreme_patterns:
            if pattern in content_lower:
                risk_indicators.append("contains_extreme_command")
                risk_score += 0.3
                break
        
        # 检查未信任源
        if context and not context.get("is_trusted_source", True):
            risk_indicators.append("untrusted_source")
            risk_score += 0.2
        
        # 归一化
        risk_score = min(risk_score, 1.0)
        
        # 确定风险等级
        if risk_score >= self.settings.risk_block_threshold:
            risk_level = RiskLevel.CRITICAL
        elif risk_score >= self.settings.risk_malicious_threshold:
            risk_level = RiskLevel.HIGH
        elif risk_score >= self.settings.risk_confirmation_threshold:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        
        return RiskAssessment(
            risk_score=risk_score,
            risk_indicators=risk_indicators,
            requires_confirmation=risk_score >= self.settings.risk_confirmation_threshold,
            is_potentially_malicious=risk_score >= self.settings.risk_malicious_threshold,
            risk_level=risk_level,
            reasoning=f"Rule-based assessment: {', '.join(risk_indicators) if risk_indicators else 'No indicators found'}"
        )
    
    async def match_preference(
        self,
        detected_state: Dict[str, Any],
        historical_preferences: List[Dict[str, Any]]
    ) -> PreferenceMatchResult:
        """
        匹配历史偏好
        
        Args:
            detected_state: 检测到的状态
            historical_preferences: 历史偏好列表
            
        Returns:
            PreferenceMatchResult: 匹配结果
        """
        if self.llm_enabled and len(historical_preferences) > 0:
            try:
                return await self._llm_preference_match(detected_state, historical_preferences)
            except Exception as e:
                logger.warning(f"LLM preference match failed, falling back to rules: {e}")
                return self._rule_based_preference_match(detected_state, historical_preferences)
        else:
            return self._rule_based_preference_match(detected_state, historical_preferences)
    
    async def _llm_preference_match(
        self,
        detected_state: Dict[str, Any],
        historical_preferences: List[Dict[str, Any]]
    ) -> PreferenceMatchResult:
        """
        使用 LLM 进行偏好匹配
        
        Note: 实际实现需要集成 PydanticAI Agent
        """
        # TODO: 集成 PydanticAI
        logger.debug("LLM preference match (placeholder)")
        
        # 临时返回规则引擎结果
        return self._rule_based_preference_match(detected_state, historical_preferences)
    
    def _rule_based_preference_match(
        self,
        detected_state: Dict[str, Any],
        historical_preferences: List[Dict[str, Any]]
    ) -> PreferenceMatchResult:
        """
        基于规则的偏好匹配（降级方案）
        
        Args:
            detected_state: 检测到的状态
            historical_preferences: 历史偏好列表
            
        Returns:
            PreferenceMatchResult: 匹配结果
        """
        if not historical_preferences:
            return PreferenceMatchResult(
                is_known_preference=False,
                preference=None,
                similarity_score=0.0,
                reasoning="No historical preferences available"
            )
        
        # 简化实现：基于域名的简单匹配
        # TODO: 改进为更智能的相似度计算
        best_match = None
        best_score = 0.0
        
        state_domains = set(str(detected_state.get("domains", [])).lower().split())
        
        for pref in historical_preferences:
            pref_scope = pref.get("applicable_scope", {})
            pref_domains = set(str(pref_scope.get("domains", [])).lower().split())
            
            if not state_domains or not pref_domains:
                continue
            
            # Jaccard 相似度
            intersection = state_domains.intersection(pref_domains)
            union = state_domains.union(pref_domains)
            
            if union:
                score = len(intersection) / len(union)
                if score > best_score:
                    best_score = score
                    best_match = pref
        
        if best_match and best_score > 0.5:
            return PreferenceMatchResult(
                is_known_preference=True,
                preference=best_match,
                similarity_score=best_score,
                reasoning=f"Matched based on domain overlap (Jaccard={best_score:.2f})"
            )
        
        return PreferenceMatchResult(
            is_known_preference=False,
            preference=None,
            similarity_score=best_score,
            reasoning="No sufficient match found"
        )
    
    async def classify_anomaly(
        self,
        detected_state: Dict[str, Any],
        detection_source: str
    ) -> AnomalyCandidate:
        """
        分类异常并生成候选
        
        Args:
            detected_state: 检测到的状态
            detection_source: 检测来源
            
        Returns:
            AnomalyCandidate: 异常候选对象
        """
        if self.llm_enabled:
            try:
                return await self._llm_anomaly_classification(detected_state, detection_source)
            except Exception as e:
                logger.warning(f"LLM anomaly classification failed, falling back to rules: {e}")
                return self._rule_based_anomaly_classification(detected_state, detection_source)
        else:
            return self._rule_based_anomaly_classification(detected_state, detection_source)
    
    async def _llm_anomaly_classification(
        self,
        detected_state: Dict[str, Any],
        detection_source: str
    ) -> AnomalyCandidate:
        """
        使用 LLM 进行异常分类
        
        Note: 实际实现需要集成 PydanticAI Agent
        """
        # TODO: 集成 PydanticAI
        logger.debug("LLM anomaly classification (placeholder)")
        
        # 临时返回规则引擎结果
        return self._rule_based_anomaly_classification(detected_state, detection_source)
    
    def _rule_based_anomaly_classification(
        self,
        detected_state: Dict[str, Any],
        detection_source: str
    ) -> AnomalyCandidate:
        """
        基于规则的异常分类（降级方案）
        
        Args:
            detected_state: 检测到的状态
            detection_source: 检测来源
            
        Returns:
            AnomalyCandidate: 异常候选对象
        """
        from datetime import datetime
        import uuid
        
        # 根据状态内容判断异常类型
        state_str = str(detected_state).lower()
        
        if "injection" in state_str or "malicious" in state_str:
            anomaly_type = "injection_attempt"
            severity = 0.9
        elif "extreme" in state_str or "critical" in state_str:
            anomaly_type = "extreme_signal"
            severity = 0.85
        elif "structure" in state_str or "directory" in state_str:
            anomaly_type = "unconventional_structure"
            severity = 0.4
        elif "threshold" in state_str:
            anomaly_type = "custom_threshold"
            severity = 0.5
        else:
            anomaly_type = "deviation_from_norm"
            severity = 0.5
        
        return AnomalyCandidate(
            candidate_id=f"anom_{uuid.uuid4().hex[:8]}",
            detected_state=detected_state,
            anomaly_type=anomaly_type,
            severity=severity,
            detection_source=detection_source,
            timestamp=datetime.utcnow(),
            suggested_action="wait_for_confirmation" if severity < 0.8 else "escalate"
        )
    
    def get_engine_status(self) -> Dict[str, Any]:
        """
        获取引擎状态
        
        Returns:
            引擎状态信息
        """
        return {
            "llm_enabled": self.llm_enabled,
            "llm_provider": self.settings.llm_provider.value if self.llm_enabled else None,
            "fallback_mode": not self.llm_enabled,
            "risk_thresholds": {
                "confirmation": self.settings.risk_confirmation_threshold,
                "malicious": self.settings.risk_malicious_threshold,
                "block": self.settings.risk_block_threshold,
            }
        }


HybridAlignmentEngine = HybridJudgmentEngine

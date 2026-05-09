"""
Phase D1: 失败-应对映射 - Failure Response Mapping Engine

建立失败类型到监督行动的映射关系。
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging

from zentex.tasks.supervision.models import (
    FailureResponseMapping,
    SupervisionAction,
    SupervisionDecision,
    RetryDecision,
    RetryStrategy,
    FallbackDecision,
    FallbackStrategy,
    EscalationDecision,
    EscalationTarget,
    CompensationAction,
)

logger = logging.getLogger(__name__)


class FailureResponseMapper:
    """
    Phase D1: 失败-应对映射引擎
    
    将失败类型和严重程度映射到相应的监督行动。
    支持自定义映射规则和决策逻辑。
    """
    
    def __init__(self):
        """初始化映射引擎"""
        self.mappings: Dict[str, List[FailureResponseMapping]] = {}
        self._initialize_default_mappings()
    
    def _initialize_default_mappings(self) -> None:
        """
        初始化默认的失败-应对映射规则。
        
        这些规则基于失败严重程度和类型提供默认行为。
        """
        # 执行器超时 → 重试
        self._register_mapping(FailureResponseMapping(
            failure_type="executor_timeout",
            failure_severity="high",
            primary_action=SupervisionAction.RETRY,
            fallback_actions=[
                SupervisionAction.FALLBACK,
                SupervisionAction.ESCALATE,
            ],
            action_parameters={
                "retry_strategy": "exponential_backoff",
                "max_attempts": 3,
                "initial_delay": 2,
            },
            priority=10,
        ))
        
        # 执行器不可用 → 降级
        self._register_mapping(FailureResponseMapping(
            failure_type="executor_unavailable",
            failure_severity="high",
            primary_action=SupervisionAction.FALLBACK,
            fallback_actions=[
                SupervisionAction.RETRY,
                SupervisionAction.ESCALATE,
            ],
            action_parameters={
                "fallback_strategy": "alternate_executor",
            },
            priority=15,
        ))
        
        # 内存不足 → 升级
        self._register_mapping(FailureResponseMapping(
            failure_type="out_of_memory",
            failure_severity="critical",
            primary_action=SupervisionAction.ESCALATE,
            fallback_actions=[SupervisionAction.ABORT],
            action_parameters={
                "escalation_target": "emergency_handler",
                "priority": 1,
            },
            priority=5,
        ))
        
        # 执行器崩溃 → 升级
        self._register_mapping(FailureResponseMapping(
            failure_type="executor_crash",
            failure_severity="critical",
            primary_action=SupervisionAction.ESCALATE,
            fallback_actions=[SupervisionAction.ABORT],
            action_parameters={
                "escalation_target": "management_system",
                "priority": 1,
            },
            priority=5,
        ))
        
        # 网络错误 → 重试
        self._register_mapping(FailureResponseMapping(
            failure_type="network_error",
            failure_severity="high",
            primary_action=SupervisionAction.RETRY,
            fallback_actions=[
                SupervisionAction.FALLBACK,
                SupervisionAction.ESCALATE,
            ],
            action_parameters={
                "retry_strategy": "exponential_backoff",
                "max_attempts": 5,
            },
            priority=12,
        ))
        
        # 数据损坏 → 升级
        self._register_mapping(FailureResponseMapping(
            failure_type="data_corruption",
            failure_severity="critical",
            primary_action=SupervisionAction.ESCALATE,
            fallback_actions=[
                SupervisionAction.COMPENSATE,
                SupervisionAction.ABORT,
            ],
            action_parameters={
                "escalation_target": "management_system",
                "priority": 1,
            },
            priority=5,
        ))
        
        # 输出不正确 → 人工干预
        self._register_mapping(FailureResponseMapping(
            failure_type="incorrect_output",
            failure_severity="medium",
            primary_action=SupervisionAction.MANUAL_INTERVENTION,
            fallback_actions=[
                SupervisionAction.RETRY,
                SupervisionAction.ESCALATE,
            ],
            action_parameters={
                "escalation_target": "human_operator",
            },
            priority=30,
        ))
        
        # 部分输出 → 重试
        self._register_mapping(FailureResponseMapping(
            failure_type="partial_output",
            failure_severity="medium",
            primary_action=SupervisionAction.RETRY,
            fallback_actions=[
                SupervisionAction.FALLBACK,
                SupervisionAction.MANUAL_INTERVENTION,
            ],
            action_parameters={
                "retry_strategy": "linear_backoff",
                "max_attempts": 3,
            },
            priority=25,
        ))
        
        # 输出质量低 → 人工干预
        self._register_mapping(FailureResponseMapping(
            failure_type="output_quality_low",
            failure_severity="medium",
            primary_action=SupervisionAction.MANUAL_INTERVENTION,
            fallback_actions=[SupervisionAction.RETRY],
            priority=35,
        ))
        
        # 循环依赖 → 中止
        self._register_mapping(FailureResponseMapping(
            failure_type="circular_dependency",
            failure_severity="critical",
            primary_action=SupervisionAction.ABORT,
            fallback_actions=[
                SupervisionAction.ESCALATE,
                SupervisionAction.MANUAL_INTERVENTION,
            ],
            action_parameters={
                "escalation_target": "management_system",
            },
            priority=3,
        ))
        
        # 依赖失败 → 降级
        self._register_mapping(FailureResponseMapping(
            failure_type="dependency_failed",
            failure_severity="high",
            primary_action=SupervisionAction.FALLBACK,
            fallback_actions=[
                SupervisionAction.RETRY,
                SupervisionAction.ESCALATE,
            ],
            priority=20,
        ))
        
        logger.info("Initialized 12 default failure-response mappings")
    
    def _register_mapping(self, mapping: FailureResponseMapping) -> None:
        """注册一个失败-应对映射"""
        key = f"{mapping.failure_type}:{mapping.failure_severity}"
        if key not in self.mappings:
            self.mappings[key] = []
        self.mappings[key].append(mapping)
        # 按优先级排序
        self.mappings[key].sort(key=lambda x: x.priority)
    
    def get_mappings_for_failure(
        self,
        failure_type: str,
        failure_severity: str,
    ) -> List[FailureResponseMapping]:
        """
        获取特定失败类型的所有映射。
        
        Args:
            failure_type: 失败类型（小写）
            failure_severity: 失败严重程度（小写）
            
        Returns:
            映射列表（按优先级排序）
        """
        # 标准化字符串
        failure_type = failure_type.lower().replace(' ', '_')
        failure_severity = failure_severity.lower().replace(' ', '_')
        
        key = f"{failure_type}:{failure_severity}"
        if key in self.mappings:
            return self.mappings[key]
        
        # 回退到仅类型的查询
        default_key = f"{failure_type}:unknown"
        if default_key in self.mappings:
            return self.mappings[default_key]
        
        logger.warning(f"No mapping found for {key}")
        return []
    
    def decide_supervision_action(
        self,
        failure_type: str,
        failure_severity: str,
        task_id: str,
        root_cause: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> SupervisionDecision:
        """
        Phase D1: 决定监督行动
        
        基于失败类型和严重程度，决定应该采取什么监督行动。
        
        Args:
            failure_type: 失败类型
            failure_severity: 失败严重程度
            task_id: 失败的任务ID
            root_cause: 根本原因分析
            context: 额外上下文信息
            
        Returns:
            SupervisionDecision 对象
        """
        # 获取映射
        mappings = self.get_mappings_for_failure(failure_type, failure_severity)
        
        if not mappings:
            # 没有找到映射，使用默认行动
            logger.warning(
                f"No mapping for {failure_type}/{failure_severity}, "
                f"using default action"
            )
            return self._create_default_decision(
                task_id, failure_type, failure_severity, root_cause
            )
        
        # 使用第一个映射（优先级最高）
        mapping = mappings[0]
        
        # 构建行动参数
        action_params = mapping.action_parameters.copy()
        
        # 根据上下文调整参数
        if context:
            action_params.update(context)
        
        # 计算置信度
        confidence = 1.0 - (mapping.priority / 100.0)
        
        decision = SupervisionDecision(
            task_id=task_id,
            failure_type=failure_type,
            failure_severity=failure_severity,
            recommended_action=mapping.primary_action,
            confidence=confidence,
            action_params=action_params,
            decision_reasoning=f"根据失败类型 '{failure_type}' 和严重程度 '{failure_severity}' 映射规则选择",
            alternative_actions=mapping.fallback_actions,
        )
        
        logger.info(
            f"Supervision decision for {task_id}: "
            f"action={mapping.primary_action}, "
            f"confidence={confidence:.2f}"
        )
        
        return decision
    
    def _create_default_decision(
        self,
        task_id: str,
        failure_type: str,
        failure_severity: str,
        root_cause: str,
    ) -> SupervisionDecision:
        """创建默认的监督决策"""
        # 根据严重程度选择默认行动
        if failure_severity in ["critical", "high"]:
            default_action = SupervisionAction.ESCALATE
        elif failure_severity == "medium":
            default_action = SupervisionAction.RETRY
        else:
            default_action = SupervisionAction.MANUAL_INTERVENTION
        
        return SupervisionDecision(
            task_id=task_id,
            failure_type=failure_type,
            failure_severity=failure_severity,
            recommended_action=default_action,
            confidence=0.5,
            action_params={},
            decision_reasoning="使用默认决策规则（未找到具体映射）",
            alternative_actions=[
                SupervisionAction.RETRY,
                SupervisionAction.ESCALATE,
            ],
        )
    
    def register_custom_mapping(
        self,
        mapping: FailureResponseMapping,
    ) -> None:
        """
        注册自定义失败-应对映射。
        
        允许用户或系统注册特定业务场景的映射。
        
        Args:
            mapping: FailureResponseMapping 对象
        """
        self._register_mapping(mapping)
        logger.info(
            f"Registered custom mapping: {mapping.failure_type}/{mapping.failure_severity}"
        )

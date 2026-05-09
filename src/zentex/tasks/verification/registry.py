"""
验证器注册表 - Verifier Registry

管理验证器的注册、查找和实例化。
"""

import logging
from typing import Any, Dict, Optional, Type

from zentex.tasks.verification.models import VerificationType
from zentex.tasks.verification.verifiers import (
    AutomatedTestVerifier,
    BaseVerifier,
    LLMEvaluationVerifier,
    LogAuditVerifier,
    RuleBasedVerifier,
)

logger = logging.getLogger(__name__)


class VerifierRegistry:
    """
    验证器注册表
    
    负责管理所有可用的验证器类型，支持动态注册和获取验证器实例。
    """

    def __init__(self):
        # 验证器类型映射：verifier_type -> Verifier类
        self._verifier_classes: Dict[str, Type[BaseVerifier]] = {}
        
        # 注册的验证器实例缓存：verifier_id -> verifier实例
        self._verifier_instances: Dict[str, BaseVerifier] = {}
        
        # 注册内置验证器
        self._register_builtin_verifiers()

    def _register_builtin_verifiers(self):
        """注册内置验证器类型"""
        self.register_verifier_type(
            VerificationType.AUTOMATED_TEST, AutomatedTestVerifier
        )
        self.register_verifier_type(
            VerificationType.LLM_EVALUATION, LLMEvaluationVerifier
        )
        self.register_verifier_type(VerificationType.RULE_BASED, RuleBasedVerifier)
        self.register_verifier_type(VerificationType.LOG_AUDIT, LogAuditVerifier)
        logger.info("Built-in verifiers registered successfully")

    def register_verifier_type(
        self, verifier_type: VerificationType, verifier_class: Type[BaseVerifier]
    ):
        """
        注册新的验证器类型
        
        Args:
            verifier_type: 验证器类型枚举
            verifier_class: 验证器类（必须继承自BaseVerifier）
        """
        if not issubclass(verifier_class, BaseVerifier):
            raise TypeError(
                f"Verifier class must inherit from BaseVerifier, "
                f"got {verifier_class}"
            )
        
        self._verifier_classes[verifier_type.value] = verifier_class
        logger.info(f"Registered verifier type: {verifier_type.value}")

    def get_verifier(
        self, verifier_id: str, verifier_type: str, config: Dict[str, Any]
    ) -> BaseVerifier:
        """
        获取验证器实例
        
        Args:
            verifier_id: 验证器ID
            verifier_type: 验证器类型字符串
            config: 验证器配置参数
            
        Returns:
            验证器实例
            
        Raises:
            ValueError: 验证器类型未注册
        """
        # 检查缓存
        cache_key = f"{verifier_id}:{verifier_type}"
        if cache_key in self._verifier_instances:
            return self._verifier_instances[cache_key]
        
        # 获取验证器类
        verifier_class = self._verifier_classes.get(verifier_type)
        if not verifier_class:
            available_types = list(self._verifier_classes.keys())
            raise ValueError(
                f"Unknown verifier type: {verifier_type}. "
                f"Available types: {available_types}"
            )
        
        # 创建新实例
        try:
            verifier = verifier_class(verifier_id=verifier_id, config=config)
            self._verifier_instances[cache_key] = verifier
            logger.debug(f"Created verifier instance: {verifier_id} ({verifier_type})")
            return verifier
        except Exception as e:
            logger.error(f"Failed to create verifier {verifier_id}: {e}")
            raise

    def list_verifiers(self) -> Dict[str, Type[BaseVerifier]]:
        """
        列出所有已注册的验证器类型
        
        Returns:
            验证器类型字典 {type_name: verifier_class}
        """
        return self._verifier_classes.copy()

    def clear_cache(self):
        """清除验证器实例缓存"""
        self._verifier_instances.clear()
        logger.info("Verifier instance cache cleared")

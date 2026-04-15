"""
Phase C2: 失败分类器 - Failure Classifier

根据失败症状、错误类型和执行上下文自动分类失败原因。
提供映射规则和分类逻辑供监督系统使用。
"""

from typing import Dict, List, Optional, Tuple
from .models import (
    FailureType,
    FailureSeverity,
    VerificationEvidence,
    FailureClassification,
    SingleVerifierResult,
    VerificationResult,
    VerificationStatus,
)


class FailureClassifier:
    """
    失败分类器
    
    基于错误消息、执行上下文和证据自动分类失败。
    支持自定义规则和可扩展的分类逻辑。
    """
    
    # 错误关键字映射到失败类型
    ERROR_KEYWORD_MAPPING: Dict[str, FailureType] = {
        # 超时相关
        "timeout": FailureType.EXECUTOR_TIMEOUT,
        "timed out": FailureType.EXECUTOR_TIMEOUT,
        "time limit": FailureType.EXECUTOR_TIMEOUT,
        "deadline exceeded": FailureType.EXECUTOR_TIMEOUT,
        
        # 内存相关
        "memory": FailureType.OUT_OF_MEMORY,
        "oom": FailureType.OUT_OF_MEMORY,
        "out of memory": FailureType.OUT_OF_MEMORY,
        "malloc failed": FailureType.OUT_OF_MEMORY,
        
        # 磁盘相关
        "disk": FailureType.DISK_FULL,
        "disk full": FailureType.DISK_FULL,
        "no space": FailureType.DISK_FULL,
        "storage": FailureType.DISK_FULL,
        
        # 网络相关
        "connection refused": FailureType.NETWORK_ERROR,
        "network": FailureType.NETWORK_ERROR,
        "socket": FailureType.NETWORK_ERROR,
        "dns": FailureType.NETWORK_ERROR,
        "unreachable": FailureType.NETWORK_ERROR,
        
        # 可用性相关
        "unavailable": FailureType.EXECUTOR_UNAVAILABLE,
        "not available": FailureType.EXECUTOR_UNAVAILABLE,
        "offline": FailureType.EXECUTOR_UNAVAILABLE,
        "disconnected": FailureType.EXECUTOR_UNAVAILABLE,
        
        # 崩溃相关
        "crash": FailureType.EXECUTOR_CRASH,
        "segfault": FailureType.EXECUTOR_CRASH,
        "segmentation": FailureType.EXECUTOR_CRASH,
        "sigsegv": FailureType.EXECUTOR_CRASH,
        "aborted": FailureType.EXECUTOR_CRASH,
        
        # 数据相关
        "invalid": FailureType.INVALID_INPUT,
        "corrupted": FailureType.DATA_CORRUPTION,
        "corruption": FailureType.DATA_CORRUPTION,
        
        # 依赖相关
        "dependency": FailureType.DEPENDENCY_FAILED,
        "circular": FailureType.CIRCULAR_DEPENDENCY,
        
        # 输出质量相关
        "partial": FailureType.PARTIAL_OUTPUT,
        "incomplete": FailureType.PARTIAL_OUTPUT,
        "incomplete output": FailureType.PARTIAL_OUTPUT,
    }
    
    # 失败类型到严重程度的映射
    SEVERITY_MAPPING: Dict[FailureType, FailureSeverity] = {
        FailureType.EXECUTOR_CRASH: FailureSeverity.CRITICAL,
        FailureType.OUT_OF_MEMORY: FailureSeverity.CRITICAL,
        FailureType.DISK_FULL: FailureSeverity.CRITICAL,
        FailureType.CIRCULAR_DEPENDENCY: FailureSeverity.CRITICAL,
        FailureType.DATA_CORRUPTION: FailureSeverity.CRITICAL,
        
        FailureType.EXECUTOR_TIMEOUT: FailureSeverity.HIGH,
        FailureType.EXECUTOR_UNAVAILABLE: FailureSeverity.HIGH,
        FailureType.NETWORK_ERROR: FailureSeverity.HIGH,
        FailureType.DEPENDENCY_FAILED: FailureSeverity.HIGH,
        
        FailureType.INCORRECT_OUTPUT: FailureSeverity.MEDIUM,
        FailureType.PARTIAL_OUTPUT: FailureSeverity.MEDIUM,
        FailureType.OUTPUT_QUALITY_LOW: FailureSeverity.MEDIUM,
        FailureType.INVALID_INPUT: FailureSeverity.MEDIUM,
        
        FailureType.MISSING_REQUIREMENT: FailureSeverity.LOW,
        FailureType.UNKNOWN: FailureSeverity.MEDIUM,
    }
    
    # 失败类型到推荐行动的映射
    ACTION_MAPPING: Dict[FailureType, str] = {
        # 可重试的失败
        FailureType.EXECUTOR_TIMEOUT: "retry",
        FailureType.EXECUTOR_UNAVAILABLE: "fallback",
        FailureType.NETWORK_ERROR: "retry",
        
        # 需要升级的失败
        FailureType.EXECUTOR_CRASH: "escalate",
        FailureType.OUT_OF_MEMORY: "escalate",
        FailureType.DISK_FULL: "escalate",
        FailureType.DATA_CORRUPTION: "escalate",
        FailureType.CIRCULAR_DEPENDENCY: "abort",
        
        # 需要人工介入的失败
        FailureType.INCORRECT_OUTPUT: "manual_intervention",
        FailureType.MISSING_REQUIREMENT: "manual_intervention",
        FailureType.OUTPUT_QUALITY_LOW: "manual_intervention",
        
        # 默认重试
        FailureType.INVALID_INPUT: "retry",
        FailureType.DEPENDENCY_FAILED: "fallback",
        FailureType.PARTIAL_OUTPUT: "retry",
        FailureType.UNKNOWN: "escalate",
    }
    
    @classmethod
    def classify_failure(
        cls,
        task_id: str,
        error_message: Optional[str] = None,
        exception_type: Optional[str] = None,
        execution_stage: str = "execution",
        failed_executor_id: Optional[str] = None,
        evidence: Optional[List[VerificationEvidence]] = None,
        verifier_results: Optional[List[SingleVerifierResult]] = None,
    ) -> FailureClassification:
        """
        分类单个失败
        
        Args:
            task_id: 失败的任务ID
            error_message: 错误消息
            exception_type: 异常类型
            execution_stage: 执行阶段
            failed_executor_id: 失败的执行器ID
            evidence: 支持证据列表
            verifier_results: 验证器结果
            
        Returns:
            FailureClassification: 分类结果
        """
        # 从错误信息推断失败类型
        failure_type = cls._infer_failure_type(
            error_message, exception_type, verifier_results
        )
        
        # 获取严重程度
        severity = cls.SEVERITY_MAPPING.get(failure_type, FailureSeverity.MEDIUM)
        
        # 确定根本原因
        root_cause = cls._determine_root_cause(
            failure_type, error_message, exception_type
        )
        
        # 提取症状
        symptoms = cls._extract_symptoms(
            error_message, exception_type, verifier_results
        )
        
        # 推荐行动
        recommended_action = cls.ACTION_MAPPING.get(failure_type, "escalate")
        
        # 确定优先级
        action_priority = cls._calculate_priority(severity)
        
        # 准备证据
        if evidence is None:
            evidence = []
        
        return FailureClassification(
            task_id=task_id,
            failure_type=failure_type,
            failure_severity=severity,
            root_cause=root_cause,
            immediate_symptoms=symptoms,
            execution_stage=execution_stage,
            failed_executor_id=failed_executor_id,
            evidence=evidence,
            recommended_action=recommended_action,
            action_priority=action_priority,
        )
    
    @classmethod
    def classify_verification_result(
        cls,
        result: VerificationResult,
    ) -> Optional[FailureClassification]:
        """
        从验证结果分类失败
        
        Args:
            result: VerificationResult 对象
            
        Returns:
            FailureClassification 或 None (如果验证通过)
        """
        if result.overall_passed:
            return None
        
        # 收集所有失败的验证器
        failed_verifiers = result.get_failed_verifiers()
        error_verifiers = result.get_error_verifiers()
        
        # 从失败的验证器收集信息
        error_messages = []
        exception_types = []
        evidence_list = []
        
        for verifier in failed_verifiers + error_verifiers:
            if verifier.error:
                error_messages.append(verifier.error)
            if verifier.details.get("exception_type"):
                exception_types.append(verifier.details["exception_type"])
            
            # 从详情中提取证据
            if verifier.details.get("evidence"):
                for ev in verifier.details["evidence"]:
                    if isinstance(ev, VerificationEvidence):
                        evidence_list.append(ev)
        
        # 使用主要错误消息分类
        primary_error = error_messages[0] if error_messages else None
        primary_exception = exception_types[0] if exception_types else None
        
        return cls.classify_failure(
            task_id=result.task_id,
            error_message=primary_error,
            exception_type=primary_exception,
            execution_stage="verification",
            evidence=evidence_list,
            verifier_results=result.verifier_results,
        )
    
    @classmethod
    def _infer_failure_type(
        cls,
        error_message: Optional[str],
        exception_type: Optional[str],
        verifier_results: Optional[List[SingleVerifierResult]] = None,
    ) -> FailureType:
        """
        从错误信息推断失败类型
        
        Args:
            error_message: 错误消息
            exception_type: 异常类型
            verifier_results: 验证器结果
            
        Returns:
            FailureType: 推断的失败类型
        """
        # 合并所有文本内容进行搜索
        search_text = ""
        if error_message:
            search_text += error_message.lower()
        if exception_type:
            search_text += " " + exception_type.lower()
        
        # 从错误消息匹配关键字
        for keyword, failure_type in cls.ERROR_KEYWORD_MAPPING.items():
            if keyword in search_text:
                return failure_type
        
        # 如果有验证器结果，尝试从中推断
        if verifier_results:
            for result in verifier_results:
                if result.status == VerificationStatus.TIMEOUT:
                    return FailureType.EXECUTOR_TIMEOUT
                if result.status == VerificationStatus.ERROR:
                    if result.error:
                        search_text += " " + result.error.lower()
        
        # 再次尝试匹配（现在包括验证器错误）
        for keyword, failure_type in cls.ERROR_KEYWORD_MAPPING.items():
            if keyword in search_text:
                return failure_type
        
        # 默认为未知
        return FailureType.UNKNOWN
    
    @classmethod
    def _determine_root_cause(
        cls,
        failure_type: FailureType,
        error_message: Optional[str],
        exception_type: Optional[str],
    ) -> str:
        """
        确定根本原因描述
        
        Args:
            failure_type: 失败类型
            error_message: 错误消息
            exception_type: 异常类型
            
        Returns:
            str: 根本原因描述
        """
        # 从失败类型生成基础描述
        type_descriptions = {
            FailureType.EXECUTOR_CRASH: "执行器进程崩溃",
            FailureType.EXECUTOR_TIMEOUT: "执行器超出时间限制",
            FailureType.EXECUTOR_UNAVAILABLE: "执行器不可用或无法连接",
            FailureType.INCORRECT_OUTPUT: "输出不符合预期结果",
            FailureType.PARTIAL_OUTPUT: "执行器仅产生部分输出",
            FailureType.OUTPUT_QUALITY_LOW: "输出未达到质量标准",
            FailureType.MISSING_REQUIREMENT: "输出遗漏必需的功能",
            FailureType.OUT_OF_MEMORY: "系统内存不足",
            FailureType.DISK_FULL: "磁盘空间已满",
            FailureType.NETWORK_ERROR: "网络连接失败",
            FailureType.DEPENDENCY_FAILED: "依赖任务失败",
            FailureType.CIRCULAR_DEPENDENCY: "检测到循环依赖",
            FailureType.INVALID_INPUT: "提供的输入无效",
            FailureType.DATA_CORRUPTION: "检测到数据损坏",
            FailureType.UNKNOWN: "未知原因",
        }
        
        root_cause = type_descriptions.get(failure_type, "未分类的失败")
        
        # 如果有错误消息，附加详情
        if error_message:
            root_cause += f": {error_message[:100]}"
        
        return root_cause
    
    @classmethod
    def _extract_symptoms(
        cls,
        error_message: Optional[str],
        exception_type: Optional[str],
        verifier_results: Optional[List[SingleVerifierResult]] = None,
    ) -> List[str]:
        """
        从错误和验证结果中提取症状
        
        Args:
            error_message: 错误消息
            exception_type: 异常类型
            verifier_results: 验证器结果
            
        Returns:
            List[str]: 症状列表
        """
        symptoms = []
        
        if error_message:
            symptoms.append(f"错误消息: {error_message[:60]}")
        
        if exception_type:
            symptoms.append(f"异常类型: {exception_type}")
        
        if verifier_results:
            failed_count = sum(1 for r in verifier_results if not r.passed)
            error_count = sum(
                1 for r in verifier_results if r.status == VerificationStatus.ERROR
            )
            timeout_count = sum(
                1
                for r in verifier_results
                if r.status == VerificationStatus.TIMEOUT
            )
            
            if failed_count > 0:
                symptoms.append(f"{failed_count} 个验证器失败")
            if error_count > 0:
                symptoms.append(f"{error_count} 个验证器出错")
            if timeout_count > 0:
                symptoms.append(f"{timeout_count} 个验证器超时")
        
        return symptoms if symptoms else ["未知症状"]
    
    @classmethod
    def _calculate_priority(cls, severity: FailureSeverity) -> int:
        """
        根据严重程度计算优先级
        
        Args:
            severity: 严重程度
            
        Returns:
            int: 优先级 (1=紧急, 5=低)
        """
        priority_map = {
            FailureSeverity.CRITICAL: 1,
            FailureSeverity.HIGH: 2,
            FailureSeverity.MEDIUM: 3,
            FailureSeverity.LOW: 4,
            FailureSeverity.INFO: 5,
        }
        return priority_map.get(severity, 3)

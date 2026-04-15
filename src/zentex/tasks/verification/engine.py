"""
验证引擎 - Verification Engine

核心验证逻辑，负责协调多个验证器的执行、结果聚合和决策。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from zentex.tasks.models import ZentexTask
from zentex.tasks.verification.models import (
    SingleVerifierResult,
    VerificationConfig,
    VerificationResult,
    VerificationStatus,
)
from zentex.tasks.verification.registry import VerifierRegistry

# Phase C3: 失败分类集成
try:
    from zentex.tasks.verification.classifier import FailureClassifier
    CLASSIFIER_AVAILABLE = True
except ImportError:
    CLASSIFIER_AVAILABLE = False
    FailureClassifier = None

logger = logging.getLogger(__name__)


class VerificationEngine:
    """
    验证引擎
    
    工作流程：
    1. Worker声称完成任务
    2. 自动触发验证流程
    3. 并行/串行执行多个验证器
    4. 根据策略汇总结果
    5. 决定：接受/重试/升级/拒绝
    """

    def __init__(self, registry: VerifierRegistry):
        """
        初始化验证引擎
        
        Args:
            registry: 验证器注册表
        """
        self.registry = registry

    async def execute_verification(
        self, task: ZentexTask, result: Dict[str, Any]
    ) -> VerificationResult:
        """
        执行完整验证流程
        
        Args:
            task: 任务对象
            result: Worker提交的结果
            
        Returns:
            VerificationResult: 验证结果
        """
        config = task.contract.verification

        # 检查是否启用验证
        if not config.enabled:
            logger.debug(f"Verification disabled for task {task.task_id}")
            return VerificationResult(
                task_id=task.task_id,
                overall_status=VerificationStatus.PASSED,
                overall_passed=True,
                strategy="disabled",
                summary="验证已禁用",
                recommendation="accept",
                confidence_score=1.0,
            )

        logger.info(
            f"Starting verification for task {task.task_id} "
            f"with {len(config.verifiers)} verifiers"
        )

        start_time = datetime.now()
        verifier_results = []

        # 执行所有验证器
        for verifier_config in config.verifiers:
            try:
                # 获取验证器实例
                verifier = self.registry.get_verifier(
                    verifier_config.verifier_id,
                    verifier_config.verifier_type.value,
                    verifier_config.config,
                )

                # 执行验证（带重试）
                single_result = await self._execute_with_retry(
                    verifier, task, result, verifier_config
                )

                verifier_results.append(single_result)

                logger.debug(
                    f"Verifier {verifier_config.verifier_id} completed: "
                    f"{'PASSED' if single_result.passed else 'FAILED'}"
                )

            except Exception as e:
                logger.error(
                    f"Verifier {verifier_config.verifier_id} failed with exception: {e}"
                )
                verifier_results.append(
                    SingleVerifierResult(
                        verifier_id=verifier_config.verifier_id,
                        verifier_type=verifier_config.verifier_type.value,
                        status=VerificationStatus.ERROR,
                        passed=False,
                        confidence=0.0,
                        error=str(e),
                        summary="验证器执行异常",
                    )
                )

        # 汇总结果
        overall_result = self._aggregate_results(
            task.task_id, verifier_results, config.strategy.value
        )

        elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        overall_result.total_execution_time_ms = elapsed_ms

        # 生成建议动作
        overall_result.recommendation = self._generate_recommendation(
            overall_result, config
        )

        # Phase C3: 如果验证失败，自动进行失败分类
        if not overall_result.overall_passed and CLASSIFIER_AVAILABLE:
            self._classify_verification_failure(overall_result, task)

        logger.info(
            f"Verification completed for task {task.task_id}: "
            f"{'PASSED' if overall_result.overall_passed else 'FAILED'} "
            f"(confidence: {overall_result.confidence_score:.2f}, "
            f"time: {elapsed_ms}ms)"
        )

        return overall_result

    async def _execute_with_retry(
        self,
        verifier,
        task: ZentexTask,
        result: Dict[str, Any],
        config,
    ) -> SingleVerifierResult:
        """
        执行验证器，支持重试
        
        Args:
            verifier: 验证器实例
            task: 任务对象
            result: 任务结果
            config: 验证器配置
            
        Returns:
            SingleVerifierResult: 验证结果
        """
        last_result = None

        for attempt in range(config.max_retries + 1):
            try:
                single_result = await verifier.verify(task, result)
                single_result.retry_count = attempt

                # 如果通过或不需重试，直接返回
                if single_result.passed or not config.retry_on_failure:
                    return single_result

                last_result = single_result
                logger.warning(
                    f"Verifier {verifier.verifier_id} failed (attempt {attempt + 1}/{config.max_retries + 1}), "
                    f"retrying..."
                )

                # 指数退避：2^0, 2^1, 2^2...秒
                if attempt < config.max_retries:
                    wait_time = 2**attempt
                    logger.debug(f"Waiting {wait_time}s before retry")
                    await asyncio.sleep(wait_time)

            except Exception as e:
                logger.error(
                    f"Verifier execution error (attempt {attempt + 1}): {e}"
                )
                last_result = SingleVerifierResult(
                    verifier_id=verifier.verifier_id,
                    verifier_type=verifier.verifier_type,
                    status=VerificationStatus.ERROR,
                    passed=False,
                    confidence=0.0,
                    error=str(e),
                    summary="验证器执行异常",
                    retry_count=attempt,
                )

                # 如果是最后一次尝试，不再等待
                if attempt < config.max_retries:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)

        return last_result or SingleVerifierResult(
            verifier_id=verifier.verifier_id,
            verifier_type=verifier.verifier_type,
            status=VerificationStatus.ERROR,
            passed=False,
            confidence=0.0,
            error="所有重试均已耗尽",
            summary="验证失败且重试耗尽",
        )

    def _aggregate_results(
        self,
        task_id: str,
        results: List[SingleVerifierResult],
        strategy: str,
    ) -> VerificationResult:
        """
        根据策略汇总验证结果
        
        Args:
            task_id: 任务ID
            results: 所有验证器结果列表
            strategy: 验证策略
            
        Returns:
            VerificationResult: 汇总结果
        """
        if not results:
            return VerificationResult(
                task_id=task_id,
                overall_status=VerificationStatus.ERROR,
                overall_passed=False,
                strategy=strategy,
                summary="没有执行任何验证器",
                confidence_score=0.0,
            )

        # 根据不同策略计算结果
        if strategy == "all_must_pass":
            overall_passed = all(r.passed for r in results)
            overall_status = (
                VerificationStatus.PASSED
                if overall_passed
                else VerificationStatus.FAILED
            )
            # 置信度取最小值（木桶效应）
            confidence = min(r.confidence for r in results) if results else 0.0

        elif strategy == "majority_wins":
            passed_count = sum(1 for r in results if r.passed)
            total_count = len(results)
            overall_passed = passed_count > total_count / 2
            overall_status = (
                VerificationStatus.PASSED
                if overall_passed
                else (
                    VerificationStatus.PARTIAL
                    if passed_count > 0
                    else VerificationStatus.FAILED
                )
            )
            confidence = passed_count / total_count if total_count > 0 else 0.0

        elif strategy == "any_passes":
            overall_passed = any(r.passed for r in results)
            overall_status = (
                VerificationStatus.PASSED
                if overall_passed
                else VerificationStatus.FAILED
            )
            # 置信度取最大值
            confidence = max(r.confidence for r in results) if results else 0.0

        elif strategy == "weighted_vote":
            total_weight = sum(
                getattr(r, "weight", 1.0)
                for r in results
                if hasattr(r, "weight")
            )
            passed_weight = sum(
                (getattr(r, "weight", 1.0) if hasattr(r, "weight") else 1.0)
                for r in results
                if r.passed
            )
            overall_passed = (
                (passed_weight / total_weight) > 0.5 if total_weight > 0 else False
            )
            overall_status = (
                VerificationStatus.PASSED
                if overall_passed
                else (
                    VerificationStatus.PARTIAL
                    if passed_weight > 0
                    else VerificationStatus.FAILED
                )
            )
            confidence = passed_weight / total_weight if total_weight > 0 else 0.0

        else:
            # 默认使用ALL_MUST_PASS策略
            overall_passed = all(r.passed for r in results)
            overall_status = (
                VerificationStatus.PASSED
                if overall_passed
                else VerificationStatus.FAILED
            )
            confidence = min(r.confidence for r in results) if results else 0.0

        summary = self._generate_summary(results, overall_passed)

        return VerificationResult(
            task_id=task_id,
            overall_status=overall_status,
            overall_passed=overall_passed,
            strategy=strategy,
            verifier_results=results,
            summary=summary,
            confidence_score=confidence,
        )

    def _generate_summary(
        self, results: List[SingleVerifierResult], passed: bool
    ) -> str:
        """生成验证摘要"""
        passed_count = sum(1 for r in results if r.passed)
        total = len(results)

        if passed:
            return f"所有 {total} 个验证器均通过"
        else:
            failed_verifiers = [r.verifier_id for r in results if not r.passed]
            return f"{passed_count}/{total} 个验证器通过。失败的验证器: {', '.join(failed_verifiers)}"

    def _generate_recommendation(
        self, result: VerificationResult, config: VerificationConfig
    ) -> str:
        """
        生成建议动作
        
        Args:
            result: 验证结果
            config: 验证配置
            
        Returns:
            建议动作: accept/retry/escalate/reject
        """
        if result.overall_passed:
            return "accept"

        # 验证失败，根据配置决定下一步
        fallback_action = config.fallback_action

        if fallback_action == "retry":
            # 检查是否超过总重试次数
            max_retries = config.max_total_retries
            total_retries = sum(r.retry_count for r in result.verifier_results)
            if total_retries < max_retries:
                return "retry"
            else:
                return "escalate" if config.escalation_target else "reject"

        elif fallback_action == "escalate":
            return "escalate" if config.escalation_target else "reject"

        elif fallback_action == "fail":
            return "reject"

        else:
            # 默认行为：重试
            return "retry"
    
    def _classify_verification_failure(
        self,
        result: VerificationResult,
        task: ZentexTask,
    ) -> None:
        """
        Phase C3: 对验证失败进行自动分类
        
        从失败的验证结果中提取信息，
        自动分类失败原因，
        并将分类结果附加到 VerificationResult。
        
        Args:
            result: VerificationResult 对象
            task: ZentexTask 对象
        """
        if not CLASSIFIER_AVAILABLE or not FailureClassifier:
            logger.debug("Failure classifier not available, skipping classification")
            return
        
        try:
            # 从验证结果分类失败
            classification = FailureClassifier.classify_verification_result(result)
            
            if classification:
                result.failure_classification = classification
                
                logger.info(
                    f"Task {result.task_id} failure classified: "
                    f"{classification.failure_type.value} "
                    f"(severity: {classification.failure_severity.value}, "
                    f"action: {classification.recommended_action})"
                )
            else:
                logger.debug(f"No failure classification generated for {result.task_id}")
        
        except Exception as e:
            logger.error(
                f"Failed to classify verification failure for {result.task_id}: {e}",
                exc_info=True
            )

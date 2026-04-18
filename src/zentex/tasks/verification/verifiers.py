"""
验证器实现 - Verifier Implementations

提供多种类型的验证器实现，包括自动化测试、LLM评估和规则检查。
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict

from zentex.tasks.models import ZentexTask
from zentex.tasks.verification.models import SingleVerifierResult, VerificationStatus
from zentex.tasks.verification.llm_prompt import build_llm_evaluation_prompt

logger = logging.getLogger(__name__)


class BaseVerifier(ABC):
    """
    验证器基类
    
    所有验证器必须继承此类并实现verify方法。
    """

    def __init__(self, verifier_id: str, config: Dict[str, Any]):
        """
        初始化验证器
        
        Args:
            verifier_id: 验证器唯一标识
            config: 验证器配置参数
        """
        self.verifier_id = verifier_id
        self.config = config

    @abstractmethod
    async def verify(
        self, task: ZentexTask, result: Dict[str, Any]
    ) -> SingleVerifierResult:
        """
        执行验证
        
        Args:
            task: 任务对象（包含上下文信息）
            result: Worker提交的结果（output、metadata等）
            
        Returns:
            SingleVerifierResult: 验证结果
        """
        pass

    @property
    @abstractmethod
    def verifier_type(self) -> str:
        """验证器类型标识"""
        pass


class AutomatedTestVerifier(BaseVerifier):
    """
    自动化测试验证器
    
    执行shell命令或脚本来验证任务完成质量。
    适用于代码开发、脚本执行等可自动化测试的场景。
    
    配置示例：
    {
        "command": "pytest tests/ -v",
        "working_dir": "/path/to/project",
        "timeout_seconds": 120
    }
    """

    @property
    def verifier_type(self) -> str:
        return "automated_test"

    async def verify(
        self, task: ZentexTask, result: Dict[str, Any]
    ) -> SingleVerifierResult:
        start_time = datetime.now()

        try:
            command = self.config.get("command")
            if not command:
                return SingleVerifierResult(
                    verifier_id=self.verifier_id,
                    verifier_type=self.verifier_type,
                    status=VerificationStatus.ERROR,
                    passed=False,
                    confidence=0.0,
                    error="No verification command configured",
                    summary="验证命令未配置",
                )

            working_dir = self.config.get("working_dir", ".")
            timeout = self.config.get("timeout_seconds", 60)

            logger.info(
                f"Running automated test for task {task.task_id}: {command}"
            )

            # 执行验证命令
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )

                elapsed_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )

                if process.returncode == 0:
                    return SingleVerifierResult(
                        verifier_id=self.verifier_id,
                        verifier_type=self.verifier_type,
                        status=VerificationStatus.PASSED,
                        passed=True,
                        confidence=1.0,
                        summary="自动化测试通过",
                        details={
                            "stdout": stdout.decode("utf-8", errors="ignore")[:500],
                            "returncode": process.returncode,
                        },
                        execution_time_ms=elapsed_ms,
                    )
                else:
                    error_msg = stderr.decode("utf-8", errors="ignore")[:500]
                    return SingleVerifierResult(
                        verifier_id=self.verifier_id,
                        verifier_type=self.verifier_type,
                        status=VerificationStatus.FAILED,
                        passed=False,
                        confidence=0.0,
                        summary=f"测试失败 (退出码: {process.returncode})",
                        error=error_msg,
                        details={"returncode": process.returncode},
                        execution_time_ms=elapsed_ms,
                    )

            except asyncio.TimeoutError:
                # 终止超时进程
                try:
                    process.kill()
                except:
                    pass

                return SingleVerifierResult(
                    verifier_id=self.verifier_id,
                    verifier_type=self.verifier_type,
                    status=VerificationStatus.TIMEOUT,
                    passed=False,
                    confidence=0.0,
                    error=f"验证超时 ({timeout}秒)",
                    summary=f"验证执行超时，已超过{timeout}秒",
                )

        except Exception as e:
            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Automated test verifier failed: {e}")
            return SingleVerifierResult(
                verifier_id=self.verifier_id,
                verifier_type=self.verifier_type,
                status=VerificationStatus.ERROR,
                passed=False,
                confidence=0.0,
                error=str(e),
                summary="验证执行出错",
                execution_time_ms=elapsed_ms,
            )


class LLMEvaluationVerifier(BaseVerifier):
    """
    LLM评估验证器
    
    调用LLM服务对任务完成质量进行语义评估。
    适用于认知任务、分析报告、创作内容等需要主观判断的场景。
    
    配置示例：
    {
        "model": "gpt-4",
        "evaluation_criteria": [
            "内容准确无误",
            "结构清晰完整",
            "建议具有可操作性"
        ],
        "min_confidence": 0.8
    }
    """

    @property
    def verifier_type(self) -> str:
        return "llm_evaluation"

    async def verify(
        self, task: ZentexTask, result: Dict[str, Any]
    ) -> SingleVerifierResult:
        start_time = datetime.now()

        try:
            # 导入LLM服务
            try:
                from zentex.llm.service import get_llm_service

                llm_service = get_llm_service()
            except ImportError as e:
                logger.warning(f"LLM service not available: {e}")
                return SingleVerifierResult(
                    verifier_id=self.verifier_id,
                    verifier_type=self.verifier_type,
                    status=VerificationStatus.ERROR,
                    passed=False,
                    confidence=0.0,
                    error="LLM服务不可用",
                    summary="无法加载LLM服务",
                )

            # 构建评估prompt
            evaluation_prompt = self._build_evaluation_prompt(task, result)

            # 调用LLM进行评估
            model = self.config.get("model", "gpt-4")
            response = await llm_service.chat(
                messages=[{"role": "user", "content": evaluation_prompt}],
                model=model,
                temperature=0.1,  # 低温度确保一致性
            )

            # 解析评估结果
            parsed = self._parse_llm_response(response)

            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # 检查置信度阈值
            min_confidence = self.config.get("min_confidence", 0.0)
            if parsed["confidence"] < min_confidence:
                parsed["passed"] = False
                parsed["summary"] += f" (置信度低于阈值{min_confidence})"

            return SingleVerifierResult(
                verifier_id=self.verifier_id,
                verifier_type=self.verifier_type,
                status=(
                    VerificationStatus.PASSED
                    if parsed["passed"]
                    else VerificationStatus.FAILED
                ),
                passed=parsed["passed"],
                confidence=parsed.get("confidence", 0.5),
                summary=parsed.get("summary", ""),
                details={
                    "reasoning": parsed.get("reasoning", ""),
                    "criteria_met": parsed.get("criteria_met", []),
                    "criteria_failed": parsed.get("criteria_failed", []),
                    "llm_response": response[:1000],  # 保留原始响应片段
                },
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"LLM evaluation verifier failed: {e}")
            return SingleVerifierResult(
                verifier_id=self.verifier_id,
                verifier_type=self.verifier_type,
                status=VerificationStatus.ERROR,
                passed=False,
                confidence=0.0,
                error=str(e),
                summary="LLM评估执行出错",
                execution_time_ms=elapsed_ms,
            )

    def _build_evaluation_prompt(
        self, task: ZentexTask, result: Dict[str, Any]
    ) -> str:
        """构建评估prompt"""
        return build_llm_evaluation_prompt(
            task_title=task.title,
            task_type=task.task_type.value,
            task_remarks=task.remarks,
            result=result,
            criteria=self.config.get("evaluation_criteria", []),
        )["prompt"]

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析LLM响应"""
        import json

        try:
            # 尝试提取JSON
            if "{" in response:
                json_str = response[response.find("{") : response.rfind("}") + 1]
                parsed = json.loads(json_str)

                # 验证必需字段
                if "passed" in parsed and "confidence" in parsed:
                    return {
                        "passed": bool(parsed["passed"]),
                        "confidence": float(parsed.get("confidence", 0.5)),
                        "summary": parsed.get("summary", ""),
                        "reasoning": parsed.get("reasoning", ""),
                        "criteria_met": parsed.get("criteria_met", []),
                        "criteria_failed": parsed.get("criteria_failed", []),
                    }
        except Exception as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")

        # 默认返回（解析失败时）
        return {
            "passed": False,
            "confidence": 0.0,
            "summary": "无法解析LLM评估结果",
            "reasoning": "",
            "criteria_met": [],
            "criteria_failed": [],
        }


class RuleBasedVerifier(BaseVerifier):
    """
    规则检查验证器
    
    基于预定义规则检查任务结果的结构化字段。
    适用于需要验证输出格式、必填字段、数据范围等场景。
    
    支持的规则类型：
    - required_field: 必填字段检查
    - min_length: 最小长度检查
    - max_length: 最大长度检查
    - pattern_match: 正则表达式匹配
    - value_range: 数值范围检查
    - enum_value: 枚举值检查
    
    配置示例：
    {
        "rules": [
            {"type": "required_field", "field": "output"},
            {"type": "min_length", "field": "summary", "min_length": 100},
            {"type": "pattern_match", "field": "code", "pattern": "^def "}
        ]
    }
    """

    @property
    def verifier_type(self) -> str:
        return "rule_based"

    async def verify(
        self, task: ZentexTask, result: Dict[str, Any]
    ) -> SingleVerifierResult:
        start_time = datetime.now()

        try:
            rules = self.config.get("rules", [])
            if not rules:
                return SingleVerifierResult(
                    verifier_id=self.verifier_id,
                    verifier_type=self.verifier_type,
                    status=VerificationStatus.ERROR,
                    passed=False,
                    confidence=0.0,
                    error="未配置验证规则",
                    summary="验证规则列表为空",
                )

            # 执行规则检查
            rule_results = []
            for rule in rules:
                check_result = self._check_rule(rule, result)
                rule_results.append(check_result)

            # 统计结果
            passed_count = sum(1 for r in rule_results if r["passed"])
            total_count = len(rule_results)
            all_passed = passed_count == total_count

            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            return SingleVerifierResult(
                verifier_id=self.verifier_id,
                verifier_type=self.verifier_type,
                status=(
                    VerificationStatus.PASSED
                    if all_passed
                    else VerificationStatus.FAILED
                ),
                passed=all_passed,
                confidence=1.0 if all_passed else 0.0,
                summary=f"{passed_count}/{total_count} 条规则通过",
                details={"rule_results": rule_results},
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Rule-based verifier failed: {e}")
            return SingleVerifierResult(
                verifier_id=self.verifier_id,
                verifier_type=self.verifier_type,
                status=VerificationStatus.ERROR,
                passed=False,
                confidence=0.0,
                error=str(e),
                summary="规则检查执行出错",
                execution_time_ms=elapsed_ms,
            )

    def _check_rule(
        self, rule: Dict[str, Any], result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """检查单条规则"""
        rule_type = rule.get("type")

        try:
            if rule_type == "required_field":
                return self._check_required_field(rule, result)
            elif rule_type == "min_length":
                return self._check_min_length(rule, result)
            elif rule_type == "max_length":
                return self._check_max_length(rule, result)
            elif rule_type == "pattern_match":
                return self._check_pattern_match(rule, result)
            elif rule_type == "value_range":
                return self._check_value_range(rule, result)
            elif rule_type == "enum_value":
                return self._check_enum_value(rule, result)
            else:
                return {
                    "rule": rule,
                    "passed": False,
                    "error": f"未知的规则类型: {rule_type}",
                }
        except Exception as e:
            return {"rule": rule, "passed": False, "error": str(e)}

    def _check_required_field(
        self, rule: Dict[str, Any], result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """检查必填字段"""
        field = rule.get("field")
        passed = field in result and result[field] is not None
        return {
            "rule": rule,
            "passed": passed,
            "message": f"字段 '{field}' {'存在' if passed else '缺失'}",
        }

    def _check_min_length(
        self, rule: Dict[str, Any], result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """检查最小长度"""
        field = rule.get("field")
        min_len = rule.get("min_length", 0)
        value = result.get(field, "")
        passed = len(str(value)) >= min_len
        return {
            "rule": rule,
            "passed": passed,
            "message": f"字段 '{field}' 长度 {len(str(value))} {'≥' if passed else '<'} {min_len}",
        }

    def _check_max_length(
        self, rule: Dict[str, Any], result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """检查最大长度"""
        field = rule.get("field")
        max_len = rule.get("max_length", 0)
        value = result.get(field, "")
        passed = len(str(value)) <= max_len
        return {
            "rule": rule,
            "passed": passed,
            "message": f"字段 '{field}' 长度 {len(str(value))} {'≤' if passed else '>'} {max_len}",
        }

    def _check_pattern_match(
        self, rule: Dict[str, Any], result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """检查正则匹配"""
        field = rule.get("field")
        pattern = rule.get("pattern")
        value = str(result.get(field, ""))
        passed = bool(re.match(pattern, value))
        return {
            "rule": rule,
            "passed": passed,
            "message": f"字段 '{field}' {'匹配' if passed else '不匹配'} 模式 '{pattern}'",
        }

    def _check_value_range(
        self, rule: Dict[str, Any], result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """检查数值范围"""
        field = rule.get("field")
        min_val = rule.get("min", float("-inf"))
        max_val = rule.get("max", float("inf"))
        value = result.get(field, 0)

        try:
            value = float(value)
            passed = min_val <= value <= max_val
            return {
                "rule": rule,
                "passed": passed,
                "message": f"字段 '{field}' 值 {value} {'在' if passed else '不在'} 范围 [{min_val}, {max_val}]",
            }
        except (ValueError, TypeError):
            return {
                "rule": rule,
                "passed": False,
                "message": f"字段 '{field}' 的值 '{value}' 无法转换为数值",
            }

    def _check_enum_value(
        self, rule: Dict[str, Any], result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """检查枚举值"""
        field = rule.get("field")
        allowed_values = rule.get("allowed_values", [])
        value = result.get(field)
        passed = value in allowed_values
        return {
            "rule": rule,
            "passed": passed,
            "message": f"字段 '{field}' 值 '{value}' {'是' if passed else '不是'} 允许值之一 {allowed_values}",
        }

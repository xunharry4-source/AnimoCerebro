"""
验证器实现 - Verifier Implementations

提供多种类型的验证器实现，包括自动化测试、LLM评估和规则检查。
"""

import asyncio
import hashlib
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from zentex.tasks.models import ZentexTask
from zentex.tasks.verification.models import SingleVerifierResult, VerificationStatus
from zentex.tasks.verification.llm_prompt import build_llm_evaluation_prompt

logger = logging.getLogger(__name__)

_MISSING = object()


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
                except Exception as e:
                    logger.exception(f"Failed to kill timed-out verification process for task {task.task_id}")

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
            logger.exception(f"Error parsing LLM evaluation response: {e}")
            return {
                "passed": False,
                "confidence": 0.0,
                "summary": f"解析评估结果失败: {str(e)}",
                "reasoning": response[:500],
                "criteria_met": [],
                "criteria_failed": [],
            }

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
    - file_exists: 真实物理证据文件存在检查
    - non_empty_file: 真实物理证据文件非空检查
    - file_contains: 真实物理证据文件内容包含检查
    
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
            elif rule_type == "file_exists":
                return self._check_file_exists(rule, result, require_non_empty=False)
            elif rule_type == "non_empty_file":
                return self._check_file_exists(rule, result, require_non_empty=True)
            elif rule_type == "file_contains":
                return self._check_file_contains(rule, result)
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
        value = self._get_field_value(result, field)
        passed = value is not _MISSING and value is not None
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
        value = self._get_field_value(result, field, default="")
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
        value = self._get_field_value(result, field, default="")
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
        value = str(self._get_field_value(result, field, default=""))
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
        value = self._get_field_value(result, field, default=0)

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
        value = self._get_field_value(result, field)
        passed = value in allowed_values
        return {
            "rule": rule,
            "passed": passed,
            "message": f"字段 '{field}' 值 '{value}' {'是' if passed else '不是'} 允许值之一 {allowed_values}",
        }

    def _check_file_exists(
        self,
        rule: Dict[str, Any],
        result: Dict[str, Any],
        *,
        require_non_empty: bool,
    ) -> Dict[str, Any]:
        path_result = self._resolve_file_path(rule, result)
        if not path_result["passed"]:
            return path_result
        file_path = Path(path_result["path"])
        if not file_path.exists():
            return {
                "rule": rule,
                "passed": False,
                "path": str(file_path),
                "error_code": "EVIDENCE_FILE_MISSING",
                "message": f"物理证据文件不存在: {file_path}",
            }
        if not file_path.is_file():
            return {
                "rule": rule,
                "passed": False,
                "path": str(file_path),
                "error_code": "EVIDENCE_NOT_FILE",
                "message": f"物理证据路径不是文件: {file_path}",
            }
        size = file_path.stat().st_size
        if require_non_empty and size <= 0:
            return {
                "rule": rule,
                "passed": False,
                "path": str(file_path),
                "size_bytes": size,
                "error_code": "EVIDENCE_FILE_EMPTY",
                "message": f"物理证据文件为空: {file_path}",
            }
        return {
            "rule": rule,
            "passed": True,
            "path": str(file_path),
            "size_bytes": size,
            "sha256": self._file_sha256(file_path),
            "message": f"物理证据文件{'存在且非空' if require_non_empty else '存在'}: {file_path}",
        }

    def _check_file_contains(
        self, rule: Dict[str, Any], result: Dict[str, Any]
    ) -> Dict[str, Any]:
        exists_result = self._check_file_exists(rule, result, require_non_empty=True)
        if not exists_result["passed"]:
            return exists_result
        expected = (
            rule.get("contains")
            or rule.get("expected_text")
            or rule.get("expected_substring")
        )
        if expected is None or str(expected) == "":
            return {
                "rule": rule,
                "passed": False,
                "path": exists_result.get("path"),
                "error_code": "EVIDENCE_EXPECTED_TEXT_MISSING",
                "message": "file_contains 规则缺少 contains/expected_text/expected_substring",
            }
        file_path = Path(str(exists_result["path"]))
        encoding = str(rule.get("encoding") or "utf-8")
        content = file_path.read_text(encoding=encoding)
        passed = str(expected) in content
        return {
            "rule": rule,
            "passed": passed,
            "path": str(file_path),
            "size_bytes": exists_result.get("size_bytes"),
            "sha256": exists_result.get("sha256"),
            "expected_text": str(expected),
            "actual_preview": content[:500],
            "error_code": "" if passed else "EVIDENCE_TEXT_MISMATCH",
            "message": f"物理证据文件内容{'包含' if passed else '不包含'}期望文本",
        }

    def _resolve_file_path(
        self, rule: Dict[str, Any], result: Dict[str, Any]
    ) -> Dict[str, Any]:
        explicit_path = rule.get("path") or rule.get("file_path")
        path_field = rule.get("path_field") or rule.get("field")
        raw_path = explicit_path
        if not raw_path and path_field:
            raw_path = self._get_field_value(result, path_field)
        if raw_path is _MISSING or raw_path in (None, ""):
            return {
                "rule": rule,
                "passed": False,
                "field": path_field,
                "error_code": "EVIDENCE_PATH_MISSING",
                "message": "物理证据路径缺失",
            }
        return {"rule": rule, "passed": True, "path": str(Path(str(raw_path)).expanduser())}

    def _get_field_value(
        self,
        result: Dict[str, Any],
        field: Any,
        *,
        default: Any = _MISSING,
    ) -> Any:
        if not field:
            return default
        field_name = str(field)
        if isinstance(result, dict) and field_name in result:
            return result[field_name]
        value: Any = result
        normalized = field_name
        if normalized.startswith("$."):
            normalized = normalized[2:]
        elif normalized.startswith("$"):
            normalized = normalized[1:].lstrip(".")
        if not normalized:
            return value
        for token in normalized.split("."):
            if isinstance(value, dict) and token in value:
                value = value[token]
            else:
                return default
        return value

    def _file_sha256(self, file_path: Path) -> str:
        hasher = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()


class LogAuditVerifier(BaseVerifier):
    """
    日志审计验证器 (Phase C2 Hardening)
    
    物理检查系统日志文件，验证任务是否产生了真实的痕迹。
    用于防止“功能假实现”和“伪造测试数据”。
    
    配置示例：
    {
        "log_path": "data/app_data/logs/cognitive_tool_invocations.jsonl",
        "require_task_id": True,
        "min_log_entries": 1
    }
    """

    @property
    def verifier_type(self) -> str:
        return "log_audit"

    async def verify(
        self, task: ZentexTask, result: Dict[str, Any]
    ) -> SingleVerifierResult:
        start_time = datetime.now()
        default_log_path = None
        if "log_path" not in self.config:
            from zentex.common.storage_paths import get_storage_paths

            default_log_path = str(get_storage_paths().app_data_dir / "logs" / "cognitive_tool_invocations.jsonl")
        log_path = self.config.get("log_path", default_log_path)
        if log_path is None:
            raise RuntimeError("LogAuditVerifier requires a configured log_path")
        
        try:
            path = Path(log_path)
            if not path.exists():
                return SingleVerifierResult(
                    verifier_id=self.verifier_id,
                    verifier_type=self.verifier_type,
                    status=VerificationStatus.ERROR,
                    passed=False,
                    confidence=0.0,
                    error=f"Log file not found: {log_path}",
                    summary="日志文件缺失，无法进行物理审计",
                )

            # 物理扫描日志
            found_count = 0
            # 兼容 invocation_id 或 task_id
            search_terms = [task.task_id]
            if task.metadata.get("turn_id"):
                search_terms.append(task.metadata["turn_id"])

            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if any(term in line for term in search_terms):
                        found_count += 1

            min_entries = self.config.get("min_log_entries", 1)
            passed = found_count >= min_entries
            
            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            return SingleVerifierResult(
                verifier_id=self.verifier_id,
                verifier_type=self.verifier_type,
                status=VerificationStatus.PASSED if passed else VerificationStatus.FAILED,
                passed=passed,
                confidence=1.0 if passed else 0.0,
                summary=f"物理审计通过: 找到 {found_count} 条相关日志" if passed else f"物理审计失败: 仅找到 {found_count} 条日志 (预期 >= {min_entries})",
                details={
                    "found_entries": found_count,
                    "target_terms": search_terms,
                    "log_source": str(path)
                },
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            logger.exception(f"Log audit verifier failed: {e}")
            return SingleVerifierResult(
                verifier_id=self.verifier_id,
                verifier_type=self.verifier_type,
                status=VerificationStatus.ERROR,
                passed=False,
                confidence=0.0,
                error=str(e),
                summary="日志审计执行出错",
                execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
            )

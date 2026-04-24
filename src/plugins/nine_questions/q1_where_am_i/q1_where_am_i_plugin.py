from __future__ import annotations

import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q1
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q1_where_am_i.compression_budget import LocalCompressionBudget
from plugins.nine_questions.q1_where_am_i.llm_prompt import build_q1_llm_request
from plugins.nine_questions.q1_where_am_i.modules import (
    infer_host_runtime_type,
    normalize_dict,
    normalize_list_of_dicts,
)
from plugins.nine_questions.q1_where_am_i.llm_upgrade import build_q1_upgrade_payload
from plugins.nine_questions.q1_where_am_i.models import WorkspaceDomainInference
from zentex.plugins.service import (
    query_enabled_cognitive_plugin_functionals,
    unwrap_plugin_feedback_result,
)

QUESTION_REF = "我在哪"

UTC = timezone.utc

from zentex.common.nine_questions_shared import (
    build_nine_question_partial_failure,
    bind_module_runs,
    run_audit_integration,
    run_learning_integration,
    run_memory_integration,
    run_reflection_integration,
    build_caller_context,
    build_recovery_action,
    build_recovery_plan,
    build_model_context,
    persist_question_module_output,
    fail_module_run,
    finish_module_run,
    json_safe_payload,
    question_authenticity_judgment,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
    start_module_run,
)

logger = logging.getLogger(__name__)

TEXT_SAMPLE_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml",
    ".md", ".txt", ".toml", ".ini", ".cfg", ".conf", ".log", ".sh",
}
RISK_FILE_NAMES = {
    ".env", ".env.local", "secrets.json", "credentials.json", "id_rsa", "known_hosts",
}
MAX_SCAN_FILES = 400
MAX_SAMPLE_FILES = 8
MAX_SAMPLE_BYTES = 2048


def _resolve_workspace_root(context: Dict[str, Any], snapshot: Dict[str, Any]) -> str:
    return str(
        snapshot.get("workspace_root")
        or snapshot.get("cwd")
        or context.get("workspace_root")
        or context.get("cwd")
        or os.getcwd()
    )


def _is_non_empty_payload(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_is_non_empty_payload(item) for item in value.values())
    if isinstance(value, list):
        return any(_is_non_empty_payload(item) for item in value)
    return value not in (None, "", 0, False)


def _to_json_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(value, dict):
        return dict(value)
    return {}


def _normalize_inference_payload(raw: Any) -> dict[str, Any]:
    payload = _to_json_dict(raw)
    if not payload:
        return {}

    normalized = dict(payload)
    if not normalized.get("reasoning_summary") and isinstance(normalized.get("reasoning"), str):
        normalized["reasoning_summary"] = str(normalized["reasoning"]).strip()
    if not normalized.get("suggested_first_step") and isinstance(normalized.get("first_step"), str):
        normalized["suggested_first_step"] = str(normalized["first_step"]).strip()
    return normalized


def _build_q1_partial_failure_result(
    *,
    context: dict[str, Any],
    error_code: str,
    error_message: str,
    module_runs: List[dict[str, Any]],
    plugin_runs: List[dict[str, Any]],
    dependency_check: dict[str, Any],
    functional_chain_status: str,
    functional_chain_error: str,
    environment_service_status: str,
    snapshot_fallback_used: bool,
    overall_authenticity: str,
    structure_snapshot: dict[str, Any],
    samples_snapshot: dict[str, Any],
    sampled_file_summaries: List[dict[str, Any]],
    log_anomaly_snippets: List[str],
    environment_event: dict[str, Any],
    physical_host_state: dict[str, Any],
    sensory_audit: dict[str, Any],
    compression_snapshot: dict[str, Any],
) -> CognitiveToolResult:
    diagnosis = question_authenticity_judgment(
        module_runs=module_runs,
        upstream_dependencies=[],
        used_fallback=snapshot_fallback_used,
        diagnosis_code=error_code,
        diagnosis_message=error_message,
        required_modules=[
            "dependency_check",
            "functional_plugin_chain",
            "environment_scan",
            "workspace_structure_scan",
            "content_sampling",
            "domain_inference",
        ],
    )
    diagnosis["plugin_runs"] = plugin_runs
    diagnosis["recovery_plan"] = build_recovery_plan(
        question_id="q1",
        retriable=True,
        rollback_available=True,
        partial_retry_available=True,
        partial_replace_available=False,
        actions=[
            build_recovery_action(
                "q1-rerun-question",
                label="重跑 Q1",
                kind="retry",
                executable=True,
                scope="question_downstream",
                target="q1",
                reason="重新执行 Q1 的域推理阶段并保留已完成模块证据。",
                path="/api/web/nine-questions/q1/run",
            ),
            build_recovery_action(
                "q1-retry-domain-inference",
                label="局部重试域推理",
                kind="partial_retry",
                executable=False,
                scope="module",
                target="domain_inference",
                reason="当前执行器尚未支持模块级重试，但失败信息已经保留。",
            ),
            build_recovery_action(
                "q1-rollback-previous-success",
                label="沿用上一份 committed success",
                kind="rollback",
                executable=True,
                scope="record",
                target="q1",
                reason="当前失败不应覆盖上一份成功快照。",
            ),
        ],
    )

    execution_diagnosis = {
        "dependency_check": dependency_check,
        "functional_chain_status": functional_chain_status,
        "functional_chain_error": functional_chain_error,
        "environment_service_status": environment_service_status,
        "snapshot_fallback_used": snapshot_fallback_used,
        "overall_authenticity": overall_authenticity,
        "plugin_runs": plugin_runs,
        **diagnosis,
    }

    context_updates = {
        "workspace_structure_analysis": structure_snapshot,
        "workspace_content_samples": {
            **samples_snapshot,
            "sampled_file_summaries": sampled_file_summaries,
            "log_anomaly_snippets": log_anomaly_snippets,
        },
        "environment_event": environment_event,
        "physical_host_state": physical_host_state,
        "q1_sensory_audit": sensory_audit,
        "q1_compression_snapshot": compression_snapshot,
        "q1_execution_diagnosis": execution_diagnosis,
    }

    safe_context = dict(context)
    run_audit_integration(
        safe_context,
        question_id="q1",
        module_runs=module_runs,
        summary=f"Q1 partial failure audit: {error_message}",
        payload=context_updates,
    )
    run_memory_integration(
        safe_context,
        question_id="q1",
        module_runs=module_runs,
        title="Q1 Partial Failure",
        summary=f"Q1 encountered a partial failure: {error_message}",
        layer="episodic",
        payload=context_updates,
        tags=["nine-questions", "q1", "partial-failure"],
    )
    run_reflection_integration(
        safe_context,
        question_id="q1",
        module_runs=module_runs,
        subject="Q1 partial failure",
        summary="Q1 failure reflection recorded.",
        reflection_type="process_reflection",
        payload=context_updates,
    )
    run_learning_integration(
        safe_context,
        question_id="q1",
        module_runs=module_runs,
        learning_kind="anomaly_detection",
        summary="Q1 partial failure tracking.",
        payload=context_updates,
    )

    return CognitiveToolResult(
        tool_id=NINE_QUESTION_Q1,
        summary=f"Q1 partial failure: {error_message}",
        confidence=0.0,
        context_updates=context_updates,
        status="partial_failed",
        error=error_message,
        error_code=error_code,
        error_message=error_message,
    )


def _build_workspace_structure_analysis(workspace_root: str) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    if not root.exists() or not root.is_dir():
        return {}

    suffix_counter: Counter[str] = Counter()
    keyword_counter: Counter[str] = Counter()
    top_level_dirs: List[str] = []
    candidate_groups: List[str] = []
    risk_files: List[str] = []
    tree_rows: List[dict[str, Any]] = []
    group_details: List[dict[str, Any]] = []
    scanned_files = 0

    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".") and child.name not in {".github", ".vscode"}:
            continue
        if child.is_dir():
            top_level_dirs.append(child.name)
            file_count = 0
            for nested in child.rglob("*"):
                if scanned_files >= MAX_SCAN_FILES:
                    break
                if nested.is_file():
                    scanned_files += 1
                    file_count += 1
                    suffix = nested.suffix.lower()
                    if suffix:
                        suffix_counter[suffix] += 1
                    for token in re.findall(r"[A-Za-z]+", nested.stem.lower()):
                        if len(token) >= 4:
                            keyword_counter[token] += 1
                    if nested.name.lower() in RISK_FILE_NAMES:
                        risk_files.append(str(nested.relative_to(root)))
            tree_rows.append(
                {
                    "row_id": f"dir-{child.name}",
                    "path": child.name,
                    "label": child.name,
                    "depth": 0,
                    "kind": "directory",
                    "file_count": file_count,
                }
            )
        elif child.is_file():
            scanned_files += 1
            suffix = child.suffix.lower()
            if suffix:
                suffix_counter[suffix] += 1
            for token in re.findall(r"[A-Za-z]+", child.stem.lower()):
                if len(token) >= 4:
                    keyword_counter[token] += 1
            if child.name.lower() in RISK_FILE_NAMES:
                risk_files.append(child.name)

    top_suffixes = {suffix: count for suffix, count in suffix_counter.most_common(8)}
    top_keywords = {keyword: count for keyword, count in keyword_counter.most_common(8)}

    if any(ext in suffix_counter for ext in (".py", ".ts", ".tsx", ".js", ".jsx")):
        candidate_groups.append("application_code")
    if ".md" in suffix_counter:
        candidate_groups.append("documentation")
    if any(ext in suffix_counter for ext in (".log",)):
        candidate_groups.append("runtime_logs")
    if any(name in top_level_dirs for name in ("tests", "test")):
        candidate_groups.append("test_suite")

    for label in candidate_groups:
        group_details.append(
            {
                "group_id": label,
                "label": label,
                "summary": f"Detected from workspace structure: {label}",
            }
        )

    hierarchy_summary = (
        f"Workspace root '{root.name}' contains {len(top_level_dirs)} top-level directories; "
        f"dominant suffixes: {', '.join(top_suffixes.keys()) or 'unknown'}."
    )

    return {
        "directory_hierarchy_summary": hierarchy_summary,
        "top_level_dirs": top_level_dirs,
        "file_total_count": sum(suffix_counter.values()),
        "suffix_distribution": top_suffixes,
        "high_frequency_filename_keywords": top_keywords,
        "candidate_groups": candidate_groups,
        "obvious_risk_files": risk_files[:8],
        "directory_tree_rows": tree_rows,
        "candidate_group_details": group_details,
        "obvious_risk_file_details": [{"path": path, "severity": "medium"} for path in risk_files[:8]],
        "analyzer_snapshot": {
            "workspace_root": str(root),
            "scan_limited": scanned_files >= MAX_SCAN_FILES,
            "scanned_files": scanned_files,
        },
    }


def _build_workspace_content_samples(workspace_root: str) -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    if not root.exists() or not root.is_dir():
        return {}

    sampled: List[dict[str, Any]] = []
    anomalies: List[str] = []
    candidate_files: List[Path] = []

    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
        if len(candidate_files) >= MAX_SAMPLE_FILES:
            break
        if not path.is_file():
            continue
        if any(part.startswith(".") and part not in {".github", ".vscode"} for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SAMPLE_SUFFIXES:
            continue
        candidate_files.append(path)

    for path in candidate_files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:MAX_SAMPLE_BYTES]
        except Exception as exc:
            # 严禁吞掉采样器读文件异常并假装系统正常。
            # 这里允许跳过单个坏文件继续采样，但必须留下日志；否则真实 I/O 故障会被伪装成“没有异常样本”。
            logger.warning(
                "Q1 content sampler skipped unreadable file",
                extra={
                    "source_module": "plugins.nine_questions.q1_where_am_i",
                    "path": str(path),
                    "error": str(exc),
                },
            )
            continue
        stripped = text.strip()
        if not stripped:
            continue
        first_line = stripped.splitlines()[0][:160]
        summary = f"{path.suffix.lower() or 'text'} file under {path.parent.name or '.'}"
        sampled.append(
            {
                "path": str(path.relative_to(root)),
                "title": path.name,
                "summary": summary,
                "snippet": first_line,
                "first_lines": "\n".join(stripped.splitlines()[:6])[:400],
            }
        )
        if any(marker in stripped.lower() for marker in ("error", "exception", "traceback", "fatal", "critical")):
            anomalies.append(f"{path.relative_to(root)}: {first_line}")

    return {
        "sampled_file_summaries": sampled,
        "log_anomaly_snippets": anomalies[:8],
        "sampler_snapshot": {
            "workspace_root": str(root),
            "sampled_paths": [item["path"] for item in sampled],
            "sample_limit": MAX_SAMPLE_FILES,
        },
    }


def _build_dependency_check(
    *,
    plugin_service: Any,
    environment_service: Any,
    bound_plugins: List[dict],
) -> dict[str, Any]:
    enabled_bindings = [b for b in bound_plugins if b.get("enabled", True) is not False]
    return {
        "plugin_service_present": plugin_service is not None,
        "environment_service_present": environment_service is not None,
        "bound_functional_plugins": len(bound_plugins),
        "enabled_functional_plugins": len(enabled_bindings),
        "functional_chain_available": plugin_service is not None,
        "functional_bindings_missing": plugin_service is not None and len(enabled_bindings) == 0,
        "status": "ok" if plugin_service is not None else "functional_chain_unavailable",
    }


def _new_plugin_run(plugin_id: str, feature_code: str) -> dict[str, Any]:
    return {
        "plugin_id": plugin_id,
        "feature_code": feature_code,
        "binding_role": feature_code,
        "expected": True,
        "attempted": False,
        "status": "not_attempted",
        "input_summary": None,
        "output_summary": None,
        "error_code": None,
        "error_message": None,
        "duration_ms": None,
    }


class Q1WhereAmIPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q1
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q1"
    display_name: str = "Q1: Where am I?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Q1: 我在哪 (workspace domain inference)

    Absolute red lines (enforced here):
    - NEVER read raw file bodies.
    - Only consume pre-processed structured summaries from ContextSnapshot.
    - LLM is mandatory; fail-closed on any provider failure or schema mismatch.

    Plugin bus contract:
    - supports_multiple_plugins = True
    """

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)

        plugin_service = context.get("plugin_service")
        environment_service = context.get("environment_service")
        session_id = str(context.get("session_id") or "unknown-session")
        trace_id = str(context.get("trace_id") or f"q1-where-am-i:{uuid4().hex}")
        module_runs = bind_module_runs(context, "q1")
        plugin_runs: List[dict[str, Any]] = []
        upstream_dependencies: List[dict[str, Any]] = []

        # ------------------------------------------------------------------
        # Phase 1: Dependency check
        # ------------------------------------------------------------------
        dependency_run = start_module_run(
            module_runs, "dependency_check", source="plugins.nine_questions.q1"
        )
        bound_plugins: List[dict] = []
        if plugin_service is not None:
            try:
                bound_plugins = list(
                    query_enabled_cognitive_plugin_functionals(plugin_service, self.plugin_id, limit=200)
                )
            except Exception as exc:
                # 严禁吞掉绑定扫描异常并伪装成“只是当前没有插件绑定”。
                # 后台扫描失败必须留日志，否则监控层会把真实依赖故障误判成正常空配置。
                logger.exception(
                    "Q1 dependency binding scan failed session=%s trace=%s",
                    session_id, trace_id,
                )

        dependency_check = _build_dependency_check(
            plugin_service=plugin_service,
            environment_service=environment_service,
            bound_plugins=bound_plugins,
        )
        dependency_run["data"] = dict(dependency_check)

        logger.info(
            "q1.dependency_check.completed session=%s trace=%s status=%s "
            "plugin_service_present=%s env_service_present=%s bound=%d enabled=%d",
            session_id, trace_id,
            dependency_check["status"],
            dependency_check["plugin_service_present"],
            dependency_check["environment_service_present"],
            dependency_check["bound_functional_plugins"],
            dependency_check["enabled_functional_plugins"],
        )
        if dependency_check["status"] == "functional_chain_unavailable":
            fail_module_run(
                dependency_run,
                status="failed",
                error_code="plugin_service_missing",
                error_message="Q1 functional plugin chain not started because plugin_service is missing.",
                used_fallback=True,
            )
        elif dependency_check["functional_bindings_missing"]:
            fail_module_run(
                dependency_run,
                status="degraded",
                error_code="functional_bindings_missing",
                error_message="Q1 has no enabled functional bindings.",
                used_fallback=True,
            )
        else:
            finish_module_run(dependency_run)
        persist_question_module_output(
            context,
            question_id="q1",
            module_id="dependency_check",
            payload=dependency_check,
            status=str(dependency_run.get("status") or "completed"),
            output_kind="evidence",
        )

        # ------------------------------------------------------------------
        # Phase 2: Snapshot floor (always used as baseline)
        # ------------------------------------------------------------------
        snapshot = context.get("context_snapshot", {}) or {}
        structure = snapshot.get("workspace_structure_analysis", {}) or {}
        samples_block = snapshot.get("workspace_content_samples", {}) or {}
        workspace_root = _resolve_workspace_root(context, snapshot)
        local_inputs: Dict[str, Any] = {
            "structure": structure,
            "samples": samples_block,
            "environment_event": snapshot.get("environment_event", {}) or {},
            "physical_host_state": snapshot.get("physical_host_state", {}) or {},
            "interpretation_markers": None,
            "risk_markers": None,
        }
        producer_status = {
            "workspace_root": workspace_root,
            "structure_source": "snapshot" if _is_non_empty_payload(structure) else "missing",
            "samples_source": "snapshot" if _is_non_empty_payload(samples_block) else "missing",
        }

        if not _is_non_empty_payload(local_inputs["structure"]):
            generated_structure = _build_workspace_structure_analysis(workspace_root)
            if generated_structure:
                local_inputs["structure"] = generated_structure
                producer_status["structure_source"] = "runtime_workspace_scan"

        if not _is_non_empty_payload(local_inputs["samples"]):
            generated_samples = _build_workspace_content_samples(workspace_root)
            if generated_samples:
                local_inputs["samples"] = generated_samples
                producer_status["samples_source"] = "runtime_workspace_sampler"
        structure_run = start_module_run(
            module_runs, "workspace_structure_scan", source="plugins.nine_questions.q1"
        )
        structure_run["data"] = dict(local_inputs["structure"] or {})
        if _is_non_empty_payload(local_inputs["structure"]):
            finish_module_run(
                structure_run,
                status="completed",
                used_fallback=producer_status["structure_source"] != "snapshot",
            )
        else:
            fail_module_run(
                structure_run,
                status="missing",
                error_code="workspace_structure_missing",
                error_message="Q1 structure scan produced no usable structure evidence.",
                used_fallback=True,
            )
        persist_question_module_output(
            context,
            question_id="q1",
            module_id="workspace_structure_scan",
            payload=local_inputs["structure"],
            status=str(structure_run.get("status") or "completed"),
            output_kind="evidence",
        )

        content_run = start_module_run(
            module_runs, "content_sampling", source="plugins.nine_questions.q1"
        )
        content_run["data"] = dict(local_inputs["samples"] or {})
        if _is_non_empty_payload(local_inputs["samples"]):
            finish_module_run(
                content_run,
                status="completed",
                used_fallback=producer_status["samples_source"] != "snapshot",
            )
        else:
            fail_module_run(
                content_run,
                status="missing",
                error_code="workspace_samples_missing",
                error_message="Q1 content sampling produced no usable samples.",
                used_fallback=True,
            )
        persist_question_module_output(
            context,
            question_id="q1",
            module_id="content_sampling",
            payload=local_inputs["samples"],
            status=str(content_run.get("status") or "completed"),
            output_kind="evidence",
        )

        # ------------------------------------------------------------------
        # Phase 3: Functional plugin chain
        # ------------------------------------------------------------------
        chain_run = start_module_run(
            module_runs, "functional_plugin_chain", source="plugins.nine_questions.q1"
        )
        sensory_chain_ok = False
        functional_chain_status = "unavailable"
        functional_chain_error: Optional[str] = None

        if plugin_service is not None:
            functional_chain_status = "running"
            raw_signal: Any = None
            sanitized_signal: Any = None
            plugin_failure_detected = False

            try:
                for binding in bound_plugins:
                    functional_plugin_id = str(binding.get("plugin_id") or "")
                    feature_code = str(binding.get("feature_code") or "")
                    run_record = _new_plugin_run(functional_plugin_id, feature_code)
                    plugin_runs.append(run_record)

                    if feature_code == "sensory.ingest":
                        parameters: dict[str, Any] = {}
                    elif feature_code == "sensory.sanitize":
                        parameters = {"raw_signal": raw_signal or ""}
                    elif feature_code == "sensory.interpret":
                        parameters = {"signal": sanitized_signal}
                    else:
                        parameters = {
                            "workspace_root": (
                                (context.get("context_snapshot", {}) or {}).get("workspace_root")
                                or (context.get("context_snapshot", {}) or {}).get("cwd")
                                or context.get("workspace_root")
                            )
                        }

                    run_record["attempted"] = True
                    run_record["status"] = "running"
                    run_record["input_summary"] = list(parameters.keys())

                    plugin_started = perf_counter()
                    logger.info(
                        "q1.functional_plugin.invoke session=%s trace=%s plugin_id=%s feature=%s",
                        session_id, trace_id, functional_plugin_id, feature_code,
                    )
                    try:
                        feedback = plugin_service.execute_plugin_once_sync(
                            plugin_id=functional_plugin_id,
                            task_id=f"{trace_id}:{functional_plugin_id}",
                            parameters=parameters,
                            trace_id=trace_id,
                            originator_id=session_id,
                            caller_plugin_id=self.plugin_id,
                        )
                        run_record["duration_ms"] = int((perf_counter() - plugin_started) * 1000)

                        if getattr(feedback, "status", None) != "done":
                            run_record["status"] = "failed"
                            run_record["error_code"] = "non_done_status"
                            run_record["error_message"] = str(getattr(feedback, "status", "unknown"))
                            logger.warning(
                                "q1.functional_plugin.non_done session=%s trace=%s plugin_id=%s status=%s",
                                session_id, trace_id, functional_plugin_id, getattr(feedback, "status", None),
                            )
                            continue

                        result = unwrap_plugin_feedback_result(getattr(feedback, "result", None))

                        if feature_code == "sensory.ingest" and isinstance(result, str):
                            raw_signal = result
                            run_record["status"] = "completed"
                            run_record["output_summary"] = f"raw_signal len={len(result)}"
                        elif feature_code == "sensory.sanitize":
                            sanitized_signal = result
                            local_inputs["risk_markers"] = list(getattr(result, "redaction_evidence", []) or [])
                            run_record["status"] = "completed"
                            run_record["output_summary"] = "sanitized_signal produced"
                        elif feature_code == "sensory.interpret" and result is not None:
                            local_inputs["environment_event"] = {
                                "event_type": getattr(result, "event_type", None),
                                "summary": getattr(result, "summary", None),
                                "structured_payload": getattr(result, "structured_payload", {}),
                                "risk_flags": list(getattr(result, "risk_flags", []) or []),
                                "audit_evidence": list(getattr(result, "audit_evidence", []) or []),
                            }
                            local_inputs["interpretation_markers"] = list(getattr(result, "risk_flags", []) or [])
                            sensory_chain_ok = True
                            run_record["status"] = "completed"
                            run_record["output_summary"] = "environment_event updated"
                        elif isinstance(result, dict):
                            merged_host_state = dict(local_inputs.get("physical_host_state") or {})
                            merged_host_state.update(result)
                            local_inputs["physical_host_state"] = merged_host_state
                            if _is_non_empty_payload(result):
                                # Real structured host/runtime evidence from functional plugins
                                # must count as a successful sensory chain signal.
                                sensory_chain_ok = True
                            run_record["status"] = "completed"
                            run_record["output_summary"] = f"host_state keys={list(result.keys())}"
                        else:
                            run_record["status"] = "completed"
                            run_record["output_summary"] = "no structured output"

                        logger.info(
                            "q1.functional_plugin.completed session=%s trace=%s plugin_id=%s feature=%s",
                            session_id, trace_id, functional_plugin_id, feature_code,
                        )

                    except Exception as plugin_exc:
                        run_record["duration_ms"] = int((perf_counter() - plugin_started) * 1000)
                        run_record["status"] = "failed"
                        run_record["error_code"] = type(plugin_exc).__name__
                        run_record["error_message"] = str(plugin_exc)
                        plugin_failure_detected = True
                        # 严禁吞掉单个 functional plugin 异常后继续把整条链伪装成 completed。
                        # 这里只要任一插件真实失败，Q1 就必须显式暴露失败状态和异常堆栈，不能假装“核心证据还在所以整体正常”。
                        logger.exception(
                            "Q1 functional plugin failed session=%s trace=%s plugin_id=%s",
                            session_id, trace_id, functional_plugin_id,
                        )

                attempted = [r for r in plugin_runs if r["attempted"]]
                succeeded = [r for r in attempted if r["status"] == "completed"]
                if not attempted:
                    functional_chain_status = "no_bindings"
                elif plugin_failure_detected:
                    functional_chain_status = "failed"
                    functional_chain_error = "Q1 functional plugin failed."
                elif sensory_chain_ok:
                    functional_chain_status = "completed"
                elif succeeded:
                    functional_chain_status = "partial"
                else:
                    functional_chain_status = "failed"

                logger.info(
                    "q1.functional_plugin_chain.completed session=%s trace=%s "
                    "status=%s sensory_ok=%s plugins_attempted=%d succeeded=%d",
                    session_id, trace_id, functional_chain_status,
                    sensory_chain_ok, len(attempted), len(succeeded),
                )
                chain_run["data"] = {
                    "status": functional_chain_status,
                    "error": functional_chain_error,
                    "plugin_runs": plugin_runs,
                    "snapshot_fallback_used": not sensory_chain_ok,
                }
                if functional_chain_status == "completed":
                    finish_module_run(chain_run)
                elif functional_chain_status == "partial":
                    fail_module_run(
                        chain_run,
                        status="partial_failed",
                        error_code="functional_chain_partial",
                        error_message="Q1 functional chain produced only partial sensory evidence.",
                        used_fallback=True,
                    )
                elif functional_chain_status == "no_bindings":
                    fail_module_run(
                        chain_run,
                        status="missing",
                        error_code="functional_bindings_missing",
                        error_message="Q1 functional plugin chain found no enabled bindings.",
                        used_fallback=True,
                    )
                else:
                    fail_module_run(
                        chain_run,
                        status="failed",
                        error_code="functional_plugin_failed" if plugin_failure_detected else "functional_chain_failed",
                        error_message=functional_chain_error or "Q1 functional plugin chain failed.",
                        used_fallback=True,
                    )

            except Exception as exc:
                functional_chain_status = "failed"
                functional_chain_error = str(exc)
                chain_run["data"] = {
                    "status": functional_chain_status,
                    "error": functional_chain_error,
                    "plugin_runs": plugin_runs,
                    "snapshot_fallback_used": True,
                }
                fail_module_run(
                    chain_run,
                    status="failed",
                    error_code="functional_chain_exception",
                    error_message=str(exc),
                    used_fallback=True,
                )
                # 严禁吞掉 functional chain 级异常并继续伪装成普通降级。
                # 这里必须留下异常堆栈，否则后台链路故障会被监控页误判成普通无数据。
                logger.exception(
                    "Q1 functional plugin chain failed session=%s trace=%s",
                    session_id, trace_id,
                )
                raise RuntimeError(f"Q1 Functional Plugin Chain Failed: {exc}") from exc
        else:
            chain_run["data"] = {
                "status": functional_chain_status,
                "error": functional_chain_error,
                "plugin_runs": plugin_runs,
                "snapshot_fallback_used": True,
            }
            fail_module_run(
                chain_run,
                status="missing",
                error_code="plugin_service_missing",
                error_message="Q1 functional plugin chain not started because plugin_service is missing.",
                used_fallback=True,
            )
            logger.warning(
                "q1.snapshot_fallback.used session=%s trace=%s reason=plugin_service_unavailable",
                session_id, trace_id,
            )
        persist_question_module_output(
            context,
            question_id="q1",
            module_id="functional_plugin_chain",
            payload=chain_run.get("data") or {},
            status=str(chain_run.get("status") or "completed"),
            output_kind="evidence",
        )

        # ------------------------------------------------------------------
        # Phase 4: EnvironmentAwarenessService (explicit, separate)
        # ------------------------------------------------------------------
        environment_service_run = start_module_run(
            module_runs, "environment_service", source="plugins.nine_questions.q1"
        )
        environment_service_status = "unavailable"
        if environment_service is not None:
            try:
                logger.info("q1.environment_service.invoke session=%s trace=%s", session_id, trace_id)
                env_result = None
                host_state = None
                if callable(getattr(environment_service, "sample_host_state", None)):
                    host_state = environment_service.sample_host_state()
                    host_payload = _to_json_dict(host_state)
                    if host_payload:
                        merged_host_state = dict(local_inputs.get("physical_host_state") or {})
                        merged_host_state.update(host_payload)
                        local_inputs["physical_host_state"] = merged_host_state
                if callable(getattr(environment_service, "interpret_environment", None)) and host_state is not None:
                    env_result = environment_service.interpret_environment(host_state)
                elif callable(getattr(environment_service, "sample_and_interpret", None)):
                    sampled_host, env_result = environment_service.sample_and_interpret()
                    sampled_host_payload = _to_json_dict(sampled_host)
                    if sampled_host_payload:
                        merged_host_state = dict(local_inputs.get("physical_host_state") or {})
                        merged_host_state.update(sampled_host_payload)
                        local_inputs["physical_host_state"] = merged_host_state

                if env_result is not None:
                    env_payload = _to_json_dict(env_result)
                    local_inputs["environment_event"] = {
                        "event_type": str(env_payload.get("overall_assessment") or "environment.sampled"),
                        "summary": str(
                            env_payload.get("summary")
                            or env_payload.get("recommended_cognitive_mode")
                            or env_payload.get("overall_assessment")
                            or "Environment awareness sampled"
                        ),
                        "structured_payload": env_payload,
                        "risk_flags": list(env_payload.get("risk_flags") or []),
                        "audit_evidence": list(env_payload.get("recommendations") or []),
                    }
                    local_inputs["interpretation_markers"] = list(env_payload.get("risk_flags") or [])
                environment_service_status = (
                    "completed"
                    if _is_non_empty_payload(local_inputs.get("physical_host_state"))
                    or _is_non_empty_payload(local_inputs.get("environment_event"))
                    else "no_result"
                )
                environment_service_run["data"] = {"status": environment_service_status}
                logger.info(
                    "q1.environment_service.%s session=%s trace=%s",
                    "completed" if environment_service_status == "completed" else "no_result", session_id, trace_id,
                )
                if environment_service_status == "completed":
                    finish_module_run(environment_service_run)
                else:
                    fail_module_run(
                        environment_service_run,
                        status="missing",
                        error_code="environment_service_no_result",
                        error_message="Environment service returned no usable result.",
                        used_fallback=True,
                    )
            except Exception as env_exc:
                environment_service_status = "failed"
                environment_service_run["data"] = {"status": environment_service_status, "error": str(env_exc)}
                fail_module_run(
                    environment_service_run,
                    status="failed",
                    error_code="environment_service_failed",
                    error_message=str(env_exc),
                    used_fallback=True,
                )
                # 严禁吞掉 environment_service 异常后继续把 Q1 伪装成正常完成。
                # 环境感知后台一旦失败，结果必须保留失败状态和异常日志，不能假装只是“当前没采到环境数据”。
                logger.exception("Q1 environment service failed session=%s trace=%s", session_id, trace_id)
        else:
            environment_service_run["data"] = {"status": environment_service_status}
            fail_module_run(
                environment_service_run,
                status="missing",
                error_code="environment_service_missing",
                error_message="EnvironmentAwarenessService not available for Q1.",
                used_fallback=True,
            )
        persist_question_module_output(
            context,
            question_id="q1",
            module_id="environment_service",
            payload=environment_service_run.get("data") or {"status": environment_service_status},
            status=str(environment_service_run.get("status") or "completed"),
            output_kind="evidence",
        )

        environment_scan_run = start_module_run(
            module_runs, "environment_scan", source="plugins.nine_questions.q1"
        )
        environment_scan_run["data"] = {
            "environment_event": dict(local_inputs.get("environment_event") or {}),
            "physical_host_state": dict(local_inputs.get("physical_host_state") or {}),
        }
        if _is_non_empty_payload(local_inputs.get("environment_event")) or _is_non_empty_payload(local_inputs.get("physical_host_state")):
            finish_module_run(
                environment_scan_run,
                status="completed",
                used_fallback=not sensory_chain_ok,
            )
        else:
            fail_module_run(
                environment_scan_run,
                status="missing",
                error_code="environment_scan_missing",
                error_message="Q1 environment scan produced no host or environment evidence.",
                used_fallback=True,
            )
        persist_question_module_output(
            context,
            question_id="q1",
            module_id="environment_scan",
            payload=environment_scan_run.get("data") or {},
            status=str(environment_scan_run.get("status") or "completed"),
            output_kind="evidence",
        )

        # ------------------------------------------------------------------
        # Phase 5: Authenticity determination
        # ------------------------------------------------------------------
        snapshot_fallback_used = not (
            sensory_chain_ok
            or environment_service_status == "completed"
        )

        if sensory_chain_ok or environment_service_status == "completed":
            overall_authenticity = "real"
        elif plugin_service is None:
            overall_authenticity = "degraded_no_plugin_service"
        else:
            overall_authenticity = "degraded_chain_incomplete"

        if snapshot_fallback_used:
            logger.warning(
                "q1.snapshot_fallback.used session=%s trace=%s authenticity=%s functional_chain=%s",
                session_id, trace_id, overall_authenticity, functional_chain_status,
            )

        # ------------------------------------------------------------------
        # Phase 6: Compress + LLM
        # ------------------------------------------------------------------
        structure_snapshot = normalize_dict(local_inputs.get("structure"))
        samples_snapshot = normalize_dict(local_inputs.get("samples"))
        environment_event = normalize_dict(local_inputs.get("environment_event"))
        physical_host_state = normalize_dict(local_inputs.get("physical_host_state"))
        sampled_file_summaries = normalize_list_of_dicts(
            samples_snapshot.get("sampled_file_summaries") or samples_snapshot.get("file_samples")
        )
        log_anomaly_snippets = [
            str(item).strip()
            for item in (
                samples_snapshot.get("log_anomaly_snippets")
                or samples_snapshot.get("anomalies")
                or []
            )
            if str(item).strip()
        ] if isinstance(
            samples_snapshot.get("log_anomaly_snippets") or samples_snapshot.get("anomalies") or [],
            list,
        ) else []

        sensory_audit = {
            "sensory_chain_ok": sensory_chain_ok,
            "interpretation_markers": list(local_inputs.get("interpretation_markers") or []),
            "risk_markers": list(local_inputs.get("risk_markers") or []),
            "sampled_file_count": len(sampled_file_summaries),
            "anomaly_count": len(log_anomaly_snippets),
        }

        budget = LocalCompressionBudget()
        compressed = budget.compress(
            structure=structure_snapshot,
            samples=samples_snapshot,
            environment_event=environment_event,
            physical_host_state=physical_host_state,
        )

        llm_request = build_q1_llm_request(
            compressed=compressed,
            environment_event=environment_event,
            physical_host_state=physical_host_state,
            interpretation_markers=local_inputs.get("interpretation_markers"),
            risk_markers=local_inputs.get("risk_markers"),
            suffix_distribution=(local_inputs.get("structure") or {}).get("suffix_distribution"),
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q1_where_am_i")

        caller_context = build_caller_context(
            source_module="q1_where_am_i_plugin",
            invocation_phase="nine_question_q1_where_am_i",
            question_ref=QUESTION_REF,
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q1_where_am_i",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "system_prompt": system_prompt,
                "context": model_context,
            },
        )

        started = perf_counter()
        domain_inference_run = start_module_run(
            module_runs, "domain_inference", source="plugins.nine_questions.q1"
        )

        def _finalize_fallback_projection_modules(failure_reason: str) -> None:
            uncertainty_run = start_module_run(
                module_runs, "uncertainty_projection", source="plugins.nine_questions.q1"
            )
            uncertainty_run["data"] = {
                "risk_sources": [failure_reason],
                "uncertainty_intensity": 1.0,
                "sensory_chain_ok": sensory_chain_ok,
            }
            finish_module_run(
                uncertainty_run,
                status="partial_failed",
                used_fallback=True,
                error_code="domain_inference_unavailable",
                error_message="Q1 uncertainty projection used fallback because domain inference failed.",
            )
            persist_question_module_output(
                context,
                question_id="q1",
                module_id="uncertainty_projection",
                payload=uncertainty_run.get("data") or {},
                status=str(uncertainty_run.get("status") or "degraded"),
                output_kind="evidence",
            )

            state_write_run = start_module_run(
                module_runs, "state_write", source="plugins.nine_questions.q1"
            )
            state_write_run["data"] = {
                "overall_authenticity": overall_authenticity,
                "snapshot_fallback_used": True,
                "producer_status": producer_status,
                "failure_reason": failure_reason,
            }
            finish_module_run(
                state_write_run,
                status="partial_failed",
                used_fallback=True,
                error_code="domain_inference_unavailable",
                error_message="Q1 state write completed with degraded fallback due domain inference failure.",
            )
            persist_question_module_output(
                context,
                question_id="q1",
                module_id="state_write",
                payload=state_write_run.get("data") or {},
                status=str(state_write_run.get("status") or "degraded"),
                output_kind="integration",
            )

        try:
            raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{prompt}",
                context=model_context,
                caller_context=caller_context,
            )
        except Exception as exc:
            # 严禁吞掉模型调用异常并只返回一个无日志的 partial_failed。
            # Q1 域推理后台失败必须留下异常堆栈，否则系统会把真实推理故障误判成普通数据缺失。
            logger.exception(
                "Q1 domain inference provider failed session=%s trace=%s",
                session_id, trace_id,
            )
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q1_where_am_i",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            fail_module_run(
                domain_inference_run,
                status="partial_failed",
                error_code=exc.__class__.__name__,
                error_message=str(exc),
                used_fallback=True,
            )
            _finalize_fallback_projection_modules(str(exc))
            return _build_q1_partial_failure_result(
                context=context,
                error_code="model_provider_failed",
                error_message=str(exc),
                module_runs=module_runs,
                plugin_runs=plugin_runs,
                dependency_check=dependency_check,
                functional_chain_status=functional_chain_status,
                functional_chain_error=functional_chain_error,
                environment_service_status=environment_service_status,
                snapshot_fallback_used=snapshot_fallback_used,
                overall_authenticity=overall_authenticity,
                structure_snapshot=structure_snapshot,
                samples_snapshot=samples_snapshot,
                sampled_file_summaries=sampled_file_summaries,
                log_anomaly_snippets=log_anomaly_snippets,
                environment_event=environment_event,
                physical_host_state=physical_host_state,
                sensory_audit=sensory_audit,
                compression_snapshot={
                    "analysis_summary": compressed["analysis_summary"],
                    "sample_summary": compressed["sample_summary"],
                    "schema_summary": compressed["schema_summary"],
                    "uncertainty_summary": compressed["uncertainty_summary"],
                },
            )

        logger.info("q1.domain_inference.started session=%s trace=%s", session_id, trace_id)

        try:
            inference = WorkspaceDomainInference.model_validate(_normalize_inference_payload(raw))

            host_type, host_reason = infer_host_runtime_type(physical_host_state)
            host_line = f"当前运行主机类型判断：{host_type}（{host_reason}）。"
            updated_reasoning = f"{inference.reasoning_summary.strip()}\n\n{host_line}".strip()
            updated_uncertainties = list(inference.uncertainties)
            if host_type == "未知":
                updated_uncertainties.append("宿主机类型区分存在不确定性（server vs regular computer）")
            inference = inference.model_copy(
                update={
                    "reasoning_summary": updated_reasoning,
                    "uncertainties": updated_uncertainties,
                    "host_runtime_type": host_type,
                    "host_runtime_reason": host_reason,
                }
            )
            domain_inference_run["data"] = inference.model_dump(mode="json")
            upgrade_payload = build_q1_upgrade_payload(
                baseline_version=self.version,
                inference=inference,
                upgrade_service=context.get("llm_upgrade_service"),
                enable_candidate_planning=bool(context.get("enable_llm_upgrade_planning")),
            )
        except Exception as exc:
            # 严禁吞掉域推理结果校验/后处理异常并假装 Q1 只是普通降级。
            # 这里只要模型输出或后处理失败，就必须记录异常日志并显式 partial_failed。
            logger.exception(
                "Q1 domain inference post-processing failed session=%s trace=%s",
                session_id, trace_id,
            )
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q1_where_am_i",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            fail_module_run(
                domain_inference_run,
                status="partial_failed",
                error_code=exc.__class__.__name__,
                error_message=str(exc),
                used_fallback=True,
            )
            _finalize_fallback_projection_modules(str(exc))
            return _build_q1_partial_failure_result(
                context=context,
                error_code="domain_inference_validation_failed",
                error_message=str(exc),
                module_runs=module_runs,
                plugin_runs=plugin_runs,
                dependency_check=dependency_check,
                functional_chain_status=functional_chain_status,
                functional_chain_error=functional_chain_error,
                environment_service_status=environment_service_status,
                snapshot_fallback_used=snapshot_fallback_used,
                overall_authenticity=overall_authenticity,
                structure_snapshot=structure_snapshot,
                samples_snapshot=samples_snapshot,
                sampled_file_summaries=sampled_file_summaries,
                log_anomaly_snippets=log_anomaly_snippets,
                environment_event=environment_event,
                physical_host_state=physical_host_state,
                sensory_audit=sensory_audit,
                compression_snapshot={
                    "analysis_summary": compressed["analysis_summary"],
                    "sample_summary": compressed["sample_summary"],
                    "schema_summary": compressed["schema_summary"],
                    "uncertainty_summary": compressed["uncertainty_summary"],
                },
            )

        finish_module_run(domain_inference_run)
        persist_question_module_output(
            context,
            question_id="q1",
            module_id="domain_inference",
            payload=inference.model_dump(mode="json"),
            status=str(domain_inference_run.get("status") or "completed"),
            output_kind="inference",
        )

        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q1_where_am_i",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": inference.model_dump(mode="json"),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", {})),
                "model": json_safe_payload(
                    getattr(provider, "last_model_name", None) or getattr(provider, "default_model", None)
                ),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )

        logger.info(
            "q1.domain_inference.completed session=%s trace=%s domain=%s confidence=%.2f",
            session_id, trace_id, inference.primary_domain, inference.confidence,
        )

        # ------------------------------------------------------------------
        # Phase 7: Build execution diagnosis + return
        # ------------------------------------------------------------------
        uncertainty_run = start_module_run(
            module_runs, "uncertainty_projection", source="plugins.nine_questions.q1"
        )
        uncertainty_run["data"] = {
            "risk_sources": list(inference.uncertainties),
            "uncertainty_intensity": max(0.0, min(1.0, 1.0 - float(inference.confidence))),
            "sensory_chain_ok": sensory_chain_ok,
        }
        finish_module_run(
            uncertainty_run,
            status="partial_failed" if snapshot_fallback_used else "completed",
            used_fallback=snapshot_fallback_used,
            error_code="" if not snapshot_fallback_used else "snapshot_fallback_used",
            error_message="" if not snapshot_fallback_used else "Q1 uncertainty profile was derived with snapshot fallback.",
        )
        persist_question_module_output(
            context,
            question_id="q1",
            module_id="uncertainty_projection",
            payload=uncertainty_run.get("data") or {},
            status=str(uncertainty_run.get("status") or "completed"),
            output_kind="evidence",
        )
        state_write_run = start_module_run(
            module_runs, "state_write", source="plugins.nine_questions.q1"
        )
        state_write_run["data"] = {
            "overall_authenticity": overall_authenticity,
            "snapshot_fallback_used": snapshot_fallback_used,
            "producer_status": producer_status,
        }
        finish_module_run(
            state_write_run,
            status="partial_failed" if snapshot_fallback_used else "completed",
            used_fallback=snapshot_fallback_used,
            error_code="" if not snapshot_fallback_used else "snapshot_fallback_used",
            error_message="" if not snapshot_fallback_used else "Q1 state write completed with degraded authenticity.",
        )
        persist_question_module_output(
            context,
            question_id="q1",
            module_id="state_write",
            payload=state_write_run.get("data") or {},
            status=str(state_write_run.get("status") or "completed"),
            output_kind="integration",
        )

        failed_module = next((item for item in module_runs if str(item.get("status")) == "failed"), None)
        if failed_module is not None:
            diagnosis_code = str(failed_module.get("error_code") or "q1_module_failed")
            diagnosis_message = str(
                failed_module.get("error_message")
                or f"Q1 module failed: {failed_module.get('module_id') or 'unknown_module'}"
            )
        elif overall_authenticity == "real" and not snapshot_fallback_used:
            diagnosis_code = "completed"
            diagnosis_message = "Q1 completed with real environment evidence."
        elif snapshot_fallback_used:
            diagnosis_code = "q1_snapshot_fallback_degraded"
            diagnosis_message = "Q1 completed with degraded authenticity because snapshot fallback was used."
        elif plugin_service is None:
            diagnosis_code = "q1_authenticity_degraded"
            diagnosis_message = "Q1 used snapshot fallback because the functional chain was unavailable."
        else:
            diagnosis_code = "q1_authenticity_degraded"
            diagnosis_message = "Q1 completed with degraded authenticity because the functional chain was incomplete."

        diagnosis = question_authenticity_judgment(
            module_runs=module_runs,
            upstream_dependencies=upstream_dependencies,
            used_fallback=snapshot_fallback_used,
            diagnosis_code=diagnosis_code,
            diagnosis_message=diagnosis_message,
            required_modules=[
                "dependency_check",
                "functional_plugin_chain",
                "environment_scan",
                "workspace_structure_scan",
                "content_sampling",
                "domain_inference",
                "state_write",
            ],
        )
        if failed_module is not None and diagnosis["authenticity_status"] != "partial_failed":
            # 严禁让“缺模块导致 degraded”覆盖掉真实的 failed 模块。
            # 只要后台已有模块失败，Q1 对外必须显式 partial_failed，不能再伪装成普通降级。
            diagnosis["authenticity_status"] = "partial_failed"
        if snapshot_fallback_used and diagnosis["authenticity_status"] != "partial_failed":
            # 严禁把 fallback 运行伪装成 degraded/ready。
            # 只要 Q1 使用了 snapshot fallback，对外状态必须明确为 partial_failed。
            diagnosis["authenticity_status"] = "partial_failed"
        diagnosis["plugin_runs"] = plugin_runs
        diagnosis["recovery_plan"] = build_recovery_plan(
            question_id="q1",
            retriable=True,
            rollback_available=True,
            partial_retry_available=True,
            partial_replace_available=False,
            actions=[
                build_recovery_action(
                    "q1-rerun-question",
                    label="重跑 Q1",
                    kind="retry",
                    executable=True,
                    scope="question_downstream",
                    target="q1",
                    reason="重新执行 Q1 环境态势与域推理链。",
                    path="/api/web/nine-questions/q1/run",
                ),
                build_recovery_action(
                    "q1-rollback-previous-success",
                    label="沿用上一份 committed success",
                    kind="rollback",
                    executable=True,
                    scope="record",
                    target="q1",
                    reason="当前持久化层支持 Q1 在失败时沿用上一份 committed success。",
                ),
                build_recovery_action(
                    "q1-rerun-functional-chain",
                    label="局部重试功能插件链",
                    kind="partial_retry",
                    executable=False,
                    scope="module",
                    target="functional_plugin_chain",
                    reason="当前执行器尚未支持 Q1 模块级局部重试，需要先扩展模块执行器。",
                ),
            ],
        )

        execution_diagnosis = {
            "dependency_check": dependency_check,
            "functional_chain_status": functional_chain_status,
            "functional_chain_error": functional_chain_error,
            "environment_service_status": environment_service_status,
            "snapshot_fallback_used": snapshot_fallback_used,
            "overall_authenticity": overall_authenticity,
            "plugin_runs": plugin_runs,
            "producer_status": producer_status,
            "sensory_chain_ok": sensory_chain_ok,
        }
        execution_diagnosis.update(diagnosis)

        summary = (
            f"primary_domain={inference.primary_domain}; "
            f"secondary={inference.secondary_domains}; "
            f"confidence={inference.confidence:.2f}; "
            f"authenticity={overall_authenticity}; "
            f"status={diagnosis['authenticity_status']}"
        )

        logger.info(
            "q1.state_write.completed session=%s trace=%s status=%s authenticity=%s",
            session_id, trace_id,
            "degraded" if snapshot_fallback_used else "completed",
            overall_authenticity,
        )

        result_payload = {
            "tool_id": self.plugin_id,
            "summary": summary,
            "proposals": [
                {
                    "kind": "workspace_domain_inference",
                    "question_ref": QUESTION_REF,
                    **inference.model_dump(mode="json"),
                }
            ],
            "uncertainties": [{"kind": "uncertainties", "items": inference.uncertainties}],
            "context_updates": {
                "nine_questions": {QUESTION_REF: inference.primary_domain},
                "workspace_domain_inference": inference.model_dump(mode="json"),
                "workspace_structure_analysis": structure_snapshot,
                "workspace_content_samples": {
                    **samples_snapshot,
                    "sampled_file_summaries": sampled_file_summaries,
                    "log_anomaly_snippets": log_anomaly_snippets,
                },
                "environment_event": environment_event,
                "physical_host_state": physical_host_state,
                "q1_sensory_audit": sensory_audit,
                "q1_compression_snapshot": {
                    "analysis_summary": compressed["analysis_summary"],
                    "sample_summary": compressed["sample_summary"],
                    "schema_summary": compressed["schema_summary"],
                    "uncertainty_summary": compressed["uncertainty_summary"],
                },
                "q1_scene_model": {
                    "primary_domain": inference.primary_domain,
                    "secondary_domains": list(inference.secondary_domains),
                    "suggested_first_step": inference.suggested_first_step,
                    "host_runtime_type": host_type,
                },
                "q1_uncertainty_profile": {
                    "risk_sources": list(inference.uncertainties),
                    "risk_summary": inference.reasoning_summary,
                    "uncertainty_intensity": max(0.0, min(1.0, 1.0 - float(inference.confidence))),
                    "sensory_chain_ok": sensory_chain_ok,
                },
                "q1_llm_upgrade": upgrade_payload.model_dump(mode="json"),
                "q1_execution_diagnosis": execution_diagnosis,
            },
            "confidence": float(inference.confidence),
            # 严禁在模块已经 failed 时还返回一个没有状态字段的“正常结果”。
            # Q1 必须把真实执行状态显式暴露出来，避免监控页和上游把后台故障误判成成功。
            "status": diagnosis["authenticity_status"],
        }
        if diagnosis["authenticity_status"] == "partial_failed":
            result_payload["error"] = diagnosis["diagnosis_message"]
            result_payload["error_code"] = diagnosis["diagnosis_code"]
            result_payload["error_message"] = diagnosis["diagnosis_message"]

        q1_execution_diagnosis = result_payload["context_updates"]["q1_execution_diagnosis"]
        q1_module_runs = q1_execution_diagnosis.get("module_runs")
        q1_module_runs = q1_module_runs if isinstance(q1_module_runs, list) else []
        run_audit_integration(
            context,
            question_id="q1",
            module_runs=q1_module_runs,
            summary="Q1 场景识别审计已记录。",
            payload={
                "workspace_domain_inference": result_payload["context_updates"]["workspace_domain_inference"],
                "q1_scene_model": result_payload["context_updates"]["q1_scene_model"],
                "q1_sensory_audit": result_payload["context_updates"]["q1_sensory_audit"],
            },
        )
        run_memory_integration(
            context,
            question_id="q1",
            module_runs=q1_module_runs,
            title="Q1 Scene Model",
            summary="Q1 场景模型已写入记忆。",
            layer="episodic",
            payload={
                "workspace_domain_inference": result_payload["context_updates"]["workspace_domain_inference"],
                "q1_scene_model": result_payload["context_updates"]["q1_scene_model"],
            },
            tags=["nine-questions", "q1", "scene-model"],
        )
        run_reflection_integration(
            context,
            question_id="q1",
            module_runs=q1_module_runs,
            subject="Q1 sensory grounding",
            summary="Q1 感知质量与不确定性反思已记录。",
            reflection_type="process_reflection",
            payload={
                "q1_uncertainty_profile": result_payload["context_updates"]["q1_uncertainty_profile"],
                "q1_sensory_audit": result_payload["context_updates"]["q1_sensory_audit"],
            },
        )
        run_learning_integration(
            context,
            question_id="q1",
            module_runs=q1_module_runs,
            learning_kind="environment_grounding",
            summary="Q1 环境 grounding 学习记录已登记。",
            payload={
                "workspace_domain_inference": result_payload["context_updates"]["workspace_domain_inference"],
                "q1_scene_model": result_payload["context_updates"]["q1_scene_model"],
            },
        )
        q1_execution_diagnosis["module_runs"] = q1_module_runs

        return CognitiveToolResult(
            **result_payload,
        )


def build_q1_where_am_i_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q1,
    version: str = "1.0.0",
    lifecycle_status: Union[str, PluginLifecycleStatus] = PluginLifecycleStatus.ACTIVE,
) -> Q1WhereAmIPlugin:
    return Q1WhereAmIPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q1",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )

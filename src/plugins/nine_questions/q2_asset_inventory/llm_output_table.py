from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

from zentex.common.storage_paths import get_storage_paths

NQ_BASELINE_SESSION_ID = "nq-baseline"
Q2_SNAPSHOT_TABLE = "nine_question_q2_snapshots"


def _resolve_q2_state_db_path(db_path: str | Path | None = None) -> Path:
    if db_path not in (None, "", [], {}):
        return Path(str(db_path))
    return get_storage_paths().session_db


def _load_q2_llm_output_json_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q2_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q2_llm_output_table_missing: {resolved_db_path}")
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT llm_output_json
                FROM {Q2_SNAPSHOT_TABLE}
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q2_llm_output_table_missing") from exc
    if row is None:
        raise RuntimeError("q2_llm_output_row_missing")
    try:
        llm_output = json.loads(str(row["llm_output_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("q2_llm_output_json_invalid") from exc
    if not isinstance(llm_output, dict):
        raise RuntimeError("q2_llm_output_json_not_object")
    return llm_output


def _load_q2_context_updates_json_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    resolved_db_path = _resolve_q2_state_db_path(db_path)
    if not resolved_db_path.exists():
        raise RuntimeError(f"q2_context_updates_table_missing: {resolved_db_path}")
    try:
        with sqlite3.connect(str(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT context_updates_json
                FROM {Q2_SNAPSHOT_TABLE}
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("q2_context_updates_table_missing") from exc
    if row is None:
        raise RuntimeError("q2_context_updates_row_missing")
    try:
        context_updates = json.loads(str(row["context_updates_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("q2_context_updates_json_invalid") from exc
    if not isinstance(context_updates, dict):
        raise RuntimeError("q2_context_updates_json_not_object")
    return context_updates


def load_external_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    llm_output = _load_q2_llm_output_json_from_table(db_path=db_path, session_id=session_id)
    payload = llm_output.get("q2_external_tool_asset_inventory")
    if not isinstance(payload, dict) or payload in (None, "", [], {}):
        raise RuntimeError("q2_external_tool_asset_inventory_missing")
    return deepcopy(payload)


def load_external_function_signal_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    payload = load_external_llm_output_from_table(db_path=db_path, session_id=session_id)
    return {"functions": _function_name_description(payload)}


def load_q2_audit_id_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> str:
    context_updates = _load_q2_context_updates_json_from_table(db_path=db_path, session_id=session_id)
    audit_id = str(context_updates.get("q2_audit_id") or "").strip()
    if not audit_id:
        raise RuntimeError("q2_audit_id_missing")
    return audit_id


def load_internal_llm_output_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    llm_output = _load_q2_llm_output_json_from_table(db_path=db_path, session_id=session_id)
    payload = llm_output.get("q2_internal_tool_asset_inventory")
    if not isinstance(payload, dict) or payload in (None, "", [], {}):
        raise RuntimeError("q2_internal_tool_asset_inventory_missing")
    return deepcopy(payload)


def load_internal_function_signal_from_table(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    payload = load_internal_llm_output_from_table(db_path=db_path, session_id=session_id)
    return {"functions": _function_name_description(payload)}


def _function_name_description(payload: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw_items in payload.values():
        if not isinstance(raw_items, list):
            continue
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            description = _clean_text(
                raw.get("capability_summary")
                or raw.get("description")
                or raw.get("basic_capability_description")
                or raw.get("function_description")
                or raw.get("purpose")
                or ""
            )
            function_description = _operation_description(raw, description=description)
            raw_name = _clean_text(
                raw.get("display_name")
                or raw.get("name")
                or raw.get("tool_name")
                or raw.get("agent_name")
                or raw.get("connector_name")
                or raw.get("plugin_id")
                or raw.get("id")
                or ""
            )
            name = raw_name if _is_external_asset_row(raw) and raw_name else _human_function_name(raw_name, description)
            if name or description:
                items.append(
                    {
                        "function_name": name,
                        "description": description,
                        "function_description": function_description,
                    }
                )
    return items


def _clean_text(value: Any) -> str:
    if isinstance(value, list):
        return "；".join(_clean_text(item) for item in value if _clean_text(item))
    return str(value or "").strip()


def _operation_description(raw: dict[str, Any], *, description: str) -> str:
    explicit = _clean_text(raw.get("function_description"))
    if explicit and explicit != description:
        return explicit
    name = _clean_text(raw.get("display_name") or raw.get("name") or raw.get("tool_name") or raw.get("connector_name"))
    operation_object = _clean_text(
        raw.get("operation_object")
        or raw.get("target_app")
        or raw.get("server_name")
        or raw.get("connector_name")
    )
    capability_names = _clean_joined_list(raw.get("capability_names") or raw.get("tool_names"))
    routing = _clean_text(raw.get("task_routing_hints") or raw.get("applicable_scenario"))
    if operation_object and capability_names:
        return f"{name or operation_object} 能对 {operation_object} 执行 {capability_names} 等操作。"
    if operation_object and routing:
        return f"{name or operation_object} 能对 {operation_object} 执行相关操作：{routing}"
    if routing:
        return routing
    if operation_object:
        return f"{name or operation_object} 能对 {operation_object} 执行其注册说明中声明的操作。"
    if description:
        return description
    return f"{name} 能执行其注册说明中声明的操作。" if name else ""


def _clean_joined_list(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(_clean_text(item) for item in value if _clean_text(item))
    return _clean_text(value)


def _is_external_asset_row(raw: dict[str, Any]) -> bool:
    return any(
        key in raw
        for key in (
            "asset_type",
            "operation_object",
            "target_app",
            "verification_status",
            "external_agents",
            "connector_name",
            "server_name",
        )
    )


def _human_function_name(raw_name: str, description: str) -> str:
    known_names = {
        "cognitive_budget_conflict": "预算与资源分配冲突检测功能",
        "cognitive_expired_assumption": "过期假设检测与清理功能",
        "cognitive_failure_cluster": "重复失败模式聚类分析功能",
        "cognitive_semantic_conflict": "计划与输出语义冲突检测功能",
        "memory_extractor": "记忆候选提取功能",
        "reflection_generator": "反思与学习总结生成功能",
        "nine-question-q1-where-am-i": "九问第一问环境定位模块",
        "nine-question-q2-who-am-i": "九问第二问身份识别模块",
        "nine-question-q3-what-do-i-have": "九问第三问资产盘点模块",
        "nine-question-q4-what-can-i-do": "九问第四问目标候选生成模块",
        "nine-question-q5-what-am-i-allowed-to-do": "九问第五问授权边界判断模块",
        "nine-question-q6-what-should-i-not-do": "九问第六问后果约束与禁区识别模块",
        "nine-question-q7_alternatives": "九问第七问替代可能性探索模块",
        "nine_question_q8_decision": "九问第八问即时目标综合模块",
        "nine_question_q9_posture": "九问第九问行动方案设计模块",
        "nine-question-q2-asset-inventory": "九问第二问资产盘点模块",
        "nine-question-q3-who-am-i": "九问第三问身份推断模块",
        "execution_cloud_browser": "受控云浏览器执行功能",
        "execution_local_system": "受控本地系统执行功能",
        "oracle_alternative": "替代策略建议功能",
        "oracle_objective": "目标框架指导功能",
        "oracle_posture": "行动姿态调整建议功能",
        "oracle_redline": "红线与硬约束警告功能",
        "task_capability_matcher": "任务能力匹配评分功能",
        "task_compensation_workspace_cleanup": "任务临时工件清理补偿规划功能",
        "task_constraint_checker": "任务执行约束检查功能",
        "document_router": "文档任务路由功能",
        "task_evidence_extractor": "任务执行证据提取功能",
        "project_plan_document": "项目计划文档记录功能",
        "task_result_normalizer": "任务执行结果标准化功能",
        "task_verification_rule_based": "规则化任务结果验证功能",
    }
    lowered = raw_name.strip().lower()
    if lowered in known_names:
        return known_names[lowered]
    if raw_name and not _looks_like_code_identifier(raw_name):
        return raw_name.strip()
    description_text = description.strip().rstrip("。.")
    if description_text:
        return f"{description_text}功能"
    return ""


def _looks_like_code_identifier(value: str) -> bool:
    text = value.strip()
    return bool(text) and all(char.islower() or char.isdigit() or char in {"_", "-", ".", ":"} for char in text)

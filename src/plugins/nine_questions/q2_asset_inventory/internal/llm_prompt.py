from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from zentex.common.prompt_template_files import prompt_template_files, render_prompt_template
from zentex.common.plugin_ids import NINE_QUESTION_Q2

MAX_Q2_MEMORY_INPUTS = 10
_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")
_TEMPLATE_FILES = ["system_prompt.md", "user_prompt.md"]


def _render_template(name: str, values: dict[str, str] | None = None) -> str:
    return render_prompt_template(_TEMPLATE_DIR, name, values or {}, error_prefix="q2_internal")


def _json_block(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, indent=2, default=str)


Q2_INTERNAL_SYSTEM_PROMPT = _render_template("system_prompt.md")


def build_q2_internal_system_prompt() -> str:
    return Q2_INTERNAL_SYSTEM_PROMPT


def _text(value: Any) -> str:
    return str(value or "").strip()


def _brief(value: Any, *, limit: int = 260) -> str:
    text = _text(value).replace("\n", " ")
    return text[:limit].strip()


def collect_internal_cognitive_tools(plugin_service: Any) -> list[dict[str, Any]]:
    # 必须直接调用插件服务的认知插件查询方法，不能绕成快照或本地拼装。
    rows = plugin_service.query_plugins_by_operational_status(
        category="cognitive",
        operational_status="enabled",
        limit=200,
    )
    cognitive_tools: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        plugin_id = _text(row.get("plugin_id"))
        if not plugin_id:
            continue
        cognitive_tools.append(
            {
                "name": _text(row.get("display_name") or row.get("purpose") or plugin_id),
                "basic_capability_description": _brief(row.get("description") or row.get("purpose")),
            }
        )
    return cognitive_tools


def _plugin_asset_row(row: dict[str, Any], *, plugin_kind: str) -> dict[str, Any]:
    name = _text(row.get("display_name") or row.get("purpose") or row.get("description") or row.get("plugin_id"))
    description = _brief(row.get("description") or row.get("purpose") or name)
    routing_parts = [
        _text(row.get("role")),
        _text(row.get("feature_code")),
        _text(row.get("behavior_key")),
    ]
    return {
        "name": name,
        "plugin_kind": plugin_kind,
        "basic_capability_description": description,
        "task_routing_hints": "；".join(part for part in routing_parts if part),
        "lifecycle_status": _text(row.get("lifecycle_status")),
        "operational_status": _text(row.get("operational_status")),
    }


def collect_internal_functional_plugins(plugin_service: Any) -> list[dict[str, Any]]:
    # 必须直接调用插件服务的内部插件注册表查询方法。
    # Q2 内部 LLM 输入必须同时包含 Internal_Cognitive_Tools 和 Internal_Functional_Plugins，
    # 禁止只查某个认知插件的绑定关系；功能插件来自 service.py 维护的功能插件注册表。
    rows = plugin_service.query_plugins_by_operational_status(
        category="functional",
        operational_status="enabled",
        limit=200,
    )
    if not isinstance(rows, list):
        raise RuntimeError("Q2 内部资产盘点功能插件查询结果不是列表")
    functional_plugins: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _text(row.get("display_name") or row.get("purpose") or row.get("description") or row.get("plugin_id"))
        if not name:
            continue
        functional_plugins.append(_plugin_asset_row(row, plugin_kind="functional"))
    if not functional_plugins:
        raise RuntimeError(
            "Q2 内部资产盘点功能插件查询为空：Internal_Functional_Plugins 不能为空，"
            "禁止只把认知插件交给内部 LLM 分析。"
        )
    return functional_plugins


def normalize_memory_and_patches_context(memory_and_patches_context: dict[str, Any]) -> dict[str, Any]:
    source = memory_and_patches_context if isinstance(memory_and_patches_context, dict) else {}
    return {
        "long_term_memories": _normalize_memory_rows(
            source.get("long_term_memories")
            or source.get("memories")
            or source.get("recalled_memory_summaries")
        ),
        "reusable_strategy_patches": _normalize_strategy_patch_rows(
            source.get("reusable_strategy_patches")
            or source.get("strategy_patches")
            or source.get("patches")
        ),
    }


def _normalize_memory_rows(value: Any) -> list[dict[str, str]]:
    rows = value if isinstance(value, list) else []
    memories: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        summary_text = _brief(row.get("summary_text") or row.get("summary"), limit=500)
        if not summary_text or _is_low_value_memory(summary_text):
            continue
        dedupe_key = _memory_dedupe_key(summary_text)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        memories.append(
            {
                "memory_type": _text(row.get("memory_type")),
                "summary_text": summary_text,
                "updated_at": _text(row.get("updated_at")),
            }
        )
        if len(memories) >= MAX_Q2_MEMORY_INPUTS:
            break
    return memories


def _memory_dedupe_key(summary_text: str) -> str:
    text = re.sub(r"\s+", "", summary_text.lower())
    text = re.sub(r"[，。、“”‘’：:；;,.!?！？()\[\]{}<>《》`'\"\\/-]", "", text)
    return text[:180]


def _is_low_value_memory(summary_text: str) -> bool:
    text = summary_text.strip()
    if len(text) < 12:
        return True
    lowered = text.lower()
    low_value_markers = (
        "unknown",
        "none",
        "null",
        "todo",
        "n/a",
        "无",
        "暂无",
        "没有",
        "空",
        "测试",
        "占位",
        "placeholder",
        "lorem ipsum",
    )
    if lowered in low_value_markers:
        return True
    if any(marker in lowered for marker in ("placeholder", "lorem ipsum")):
        return True
    if len(set(re.sub(r"\s+", "", text))) <= 3:
        return True
    return False


def _normalize_strategy_patch_rows(value: Any) -> list[dict[str, str]]:
    rows = value if isinstance(value, list) else []
    patches: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = _text(row.get("status")).lower()
        if status not in {"active", "validated"}:
            continue
        patch_summary = _brief(row.get("patch_summary"), limit=500)
        if not patch_summary:
            continue
        patches.append(
            {
                "patch_type": _text(row.get("patch_type")),
                "patch_summary": patch_summary,
                "risk_level": _text(row.get("risk_level")),
                "status": status,
            }
        )
    return patches


def build_q2_internal_llm_request(
    *,
    plugin_service: Any,
    memory_and_patches_context: dict[str, Any],
    plugin_service_inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    internal_cognitive_tools = collect_internal_cognitive_tools(plugin_service)
    internal_functional_plugins = collect_internal_functional_plugins(plugin_service)
    model_context = {
        "Internal_Cognitive_Tools": internal_cognitive_tools,
        "Internal_Functional_Plugins": internal_functional_plugins,
        "Memory_&_Patches_Context": normalize_memory_and_patches_context(memory_and_patches_context),
    }
    template_values = {
        "INTERNAL_COGNITIVE_TOOLS_JSON": _json_block(model_context["Internal_Cognitive_Tools"]),
        "INTERNAL_FUNCTIONAL_PLUGINS_JSON": _json_block(model_context["Internal_Functional_Plugins"]),
        "MEMORY_AND_PATCHES_CONTEXT_JSON": _json_block(model_context["Memory_&_Patches_Context"]),
    }
    return {
        "system_prompt": build_q2_internal_system_prompt(),
        "prompt": _render_template("user_prompt.md", template_values),
        "model_context": model_context,
        "template_files": prompt_template_files(_TEMPLATE_DIR, _TEMPLATE_FILES),
    }


def build_deterministic_internal_asset_inventory(model_context: dict[str, Any]) -> dict[str, Any]:
    source = model_context if isinstance(model_context, dict) else {}
    memory_context = normalize_memory_and_patches_context(
        source.get("Memory_&_Patches_Context") if isinstance(source.get("Memory_&_Patches_Context"), dict) else {}
    )
    return {
        "internal_cognitive_tools": [
            _deterministic_internal_tool(row, fallback_kind="内部认知工具")
            for row in _dict_rows(source.get("Internal_Cognitive_Tools"))
        ],
        "internal_functional_plugins": [
            _deterministic_internal_tool(row, fallback_kind="内部功能插件")
            for row in _dict_rows(source.get("Internal_Functional_Plugins"))
        ],
        "long_term_memories": [
            {
                "summary": _text(row.get("summary_text") or row.get("summary")),
                "freshness": _freshness_label(row.get("updated_at")),
            }
            for row in _dict_rows(memory_context.get("long_term_memories"))
            if _text(row.get("summary_text") or row.get("summary"))
        ],
        "reusable_strategy_patches": [
            {
                "name": _brief(row.get("patch_summary"), limit=80) or _text(row.get("patch_type")) or "内部策略补丁",
                "applicable_scenario": _deterministic_patch_scenario(row),
            }
            for row in _dict_rows(memory_context.get("reusable_strategy_patches"))
        ],
    }


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _deterministic_internal_tool(row: dict[str, Any], *, fallback_kind: str) -> dict[str, str]:
    name = _text(row.get("name") or row.get("display_name") or row.get("purpose") or fallback_kind)
    description = _brief(row.get("basic_capability_description") or row.get("description") or row.get("purpose") or name)
    kind = _text(row.get("plugin_kind")) or fallback_kind
    capability_summary = f"这是一个{kind}。其核心功能是：{description or name}。"
    function_description = (
        _text(row.get("task_routing_hints"))
        or f"{name} 能执行其注册说明中声明的内部认知或功能操作。"
    )
    return {
        "name": name,
        "capability_summary": capability_summary,
        "description": capability_summary,
        "function_description": function_description,
        "task_routing_hints": _text(row.get("task_routing_hints")) or f"适用于需要调用{name}能力的内部认知任务。",
        "side_effects": "无外部副作用",
    }


def _freshness_label(updated_at: Any) -> str:
    return "近期更新" if _text(updated_at) else "时效未知"


def _deterministic_patch_scenario(row: dict[str, Any]) -> str:
    summary = _brief(row.get("patch_summary"), limit=260)
    risk = _text(row.get("risk_level"))
    if risk:
        return f"{summary}；风险等级：{risk}。"
    return summary or "适用于匹配该补丁条件的内部策略复用场景。"

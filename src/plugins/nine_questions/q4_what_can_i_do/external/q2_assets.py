from __future__ import annotations

import json
from typing import Any

from zentex.common.nine_questions_shared import json_safe_payload
from plugins.nine_questions.q2_asset_inventory.llm_output_table import (
    load_external_llm_output_from_table as load_q2_external_llm_output_from_table,
)


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _asset_identity_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _normalize_text(item.get("asset_name")).lower(),
        _normalize_text(item.get("source")).lower(),
        _normalize_text(item.get("plugin_category")).lower(),
        _normalize_text(item.get("description")).lower(),
    )


def _dedupe_asset_items(items: object) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = _asset_identity_key(item)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        unique.append(dict(item))
    return unique


def _normalize_q2_llm_asset_inventory(inventory: object) -> dict[str, Any]:
    if not isinstance(inventory, dict) or not inventory:
        return {}
    cognitive_and_functional_tools = _dedupe_asset_items(
        inventory.get("cognitive_and_functional_tools")
    )
    cognitive_and_functional_tools.extend(_dedupe_asset_items(inventory.get("internal_cognitive_tools")))
    cognitive_and_functional_tools.extend(_dedupe_asset_items(inventory.get("internal_functional_plugins")))
    cognitive_and_functional_tools.extend(_dedupe_asset_items(inventory.get("available_external_tools")))
    return {
        "inventory_summary": _normalize_text(inventory.get("inventory_summary")),
        "long_term_memory": _dedupe_asset_items(inventory.get("long_term_memory") or inventory.get("long_term_memories")),
        "cognitive_and_functional_tools": _dedupe_asset_items(cognitive_and_functional_tools),
        "connected_agents": _dedupe_asset_items(inventory.get("connected_agents") or inventory.get("external_agents")),
        "strategy_patches": _dedupe_asset_items(inventory.get("strategy_patches") or inventory.get("reusable_strategy_patches")),
    }


def load_external_q2_asset_inventory(context: dict[str, Any]) -> dict[str, Any]:
    return _normalize_q2_llm_asset_inventory(
        load_q2_external_llm_output_from_table(db_path=context.get("nine_question_state_db_path"))
    )


def render_external_q2_asset_inventory(context: dict[str, Any]) -> str:
    external_inventory = load_external_q2_asset_inventory(context)
    return (
        "Q2 外部功能资产清单（来自 Q2 external_tools LLM 输出）\n"
        f"{json.dumps(json_safe_payload({'q2_external_tool_asset_inventory': external_inventory}), ensure_ascii=False, indent=2)}"
    )


__all__ = [
    "load_external_q2_asset_inventory",
    "render_external_q2_asset_inventory",
]

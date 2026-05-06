from __future__ import annotations

import logging
from typing import Any

from plugins.nine_questions.q2_asset_inventory.llm_output_table import (
    load_external_llm_output_from_table as load_q2_external_llm_output_from_table,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.internal import (
    coerce_string_list,
    normalize_functional_authorization_inputs,
)
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals

logger = logging.getLogger(__name__)


def load_q2_external_connected_agents(context: dict[str, Any]) -> list[str]:
    q2_external_llm_output = load_q2_external_llm_output_from_table(
        db_path=context.get("nine_question_state_db_path")
    )
    return coerce_string_list(q2_external_llm_output.get("external_agents"))


def run_external_authorization_inputs(
    plugin_service: Any,
    *,
    plugin_id: str,
    feature_code: str,
    context: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        functional_authorization_inputs = execute_enabled_cognitive_plugin_functionals(
            plugin_service,
            plugin_id,
            default_parameters={"action_trace": dict(context)},
            trace_id=str(context.get("trace_id") or "q5"),
            originator_id=str(context.get("session_id") or "unknown-session"),
            caller_plugin_id=plugin_id,
        )
    except Exception as exc:
        logger.exception("Q5 external functional authorization chain failed")
        raise RuntimeError("q5_functional_authorization_chain_failed") from exc

    plugin_runs: list[dict[str, Any]] = []
    for item in functional_authorization_inputs:
        done = item.get("status") == "done"
        plugin_runs.append(
            {
                "plugin_id": str(item.get("plugin_id") or "unknown_plugin"),
                "feature_code": str(item.get("feature_code") or feature_code),
                "expected": True,
                "attempted": True,
                "status": "completed" if done else "failed",
                "error_code": "" if done else "functional_authorization_failed",
                "error_message": "" if done else str(item.get("error") or "functional authorization input failed"),
                "duration_ms": 0,
                "input_summary": {},
                "output_summary": item.get("result") if isinstance(item.get("result"), dict) else {},
            }
        )
        if not done:
            raise RuntimeError("q5_functional_authorization_chain_failed")
    return normalize_functional_authorization_inputs(functional_authorization_inputs), plugin_runs

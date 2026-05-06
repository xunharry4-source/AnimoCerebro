from __future__ import annotations

import logging
from typing import Any

from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals

logger = logging.getLogger(__name__)


def collect_external_redline_inputs(
    plugin_service: Any,
    *,
    plugin_id: str,
    feature_code: str,
    context: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]] | dict[str, Any]], list[dict[str, Any]]]:
    try:
        functional_inputs = execute_enabled_cognitive_plugin_functionals(
            plugin_service,
            plugin_id,
            default_parameters=dict(context),
            trace_id=str(context.get("trace_id") or "q6"),
            originator_id=str(context.get("session_id") or "unknown-session"),
            caller_plugin_id=plugin_id,
        )
    except Exception as exc:
        logger.exception("Q6 external redline functional chain failed")
        raise RuntimeError("q6_functional_redline_chain_failed") from exc

    global_constraints: list[dict[str, Any]] = []
    redline_hints: list[list[dict[str, Any]] | dict[str, Any]] = []
    plugin_runs: list[dict[str, Any]] = []
    for item in functional_inputs:
        done = item.get("status") == "done"
        plugin_runs.append(
            {
                "plugin_id": str(item.get("plugin_id") or "unknown_plugin"),
                "feature_code": str(item.get("feature_code") or feature_code),
                "expected": True,
                "attempted": True,
                "status": "completed" if done else "failed",
                "error_code": "" if done else "redline_plugin_failed",
                "error_message": "" if done else str(item.get("error") or "redline plugin failed"),
                "duration_ms": 0,
                "input_summary": {},
                "output_summary": item.get("result") if isinstance(item.get("result"), dict) else {},
            }
        )
        if not done:
            raise RuntimeError("q6_functional_redline_chain_failed")
        result = item.get("result")
        if not isinstance(result, (dict, list)):
            raise RuntimeError("q6_functional_redline_output_invalid")

        if isinstance(result, dict):
            is_redline_pack = result.get("pack_type") == "redline_pack"
            has_constraints = "non_bypassable_constraints" in result
            has_redline_hints = is_redline_pack or any(
                key in result
                for key in (
                    "zone",
                    "forbidden_actions",
                    "absolute_red_lines",
                    "performance_tradeoff_bans",
                    "prohibited_strategies",
                    "contamination_risks",
                )
            )

            if is_redline_pack or has_constraints:
                global_constraints.append(result)
            if has_redline_hints:
                redline_hints.append(result)
            if not (is_redline_pack or has_constraints or has_redline_hints):
                raise RuntimeError("q6_functional_redline_output_invalid")
        else:
            redline_hints.extend(result)

    return global_constraints, redline_hints, plugin_runs

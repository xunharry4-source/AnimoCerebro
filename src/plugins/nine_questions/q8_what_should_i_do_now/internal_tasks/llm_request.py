from __future__ import annotations

from pathlib import Path
from typing import Any

from zentex.common.prompt_template_files import prompt_template_files, render_prompt_template
from ..objective_profile_contract import build_q8_internal_objective_profile_prompt

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")
_TEMPLATE_FILES = ["final_stage.md"]


def _render_template(name: str, values: dict[str, str] | None = None) -> str:
    return render_prompt_template(_TEMPLATE_DIR, name, values or {}, error_prefix="q8_internal")


def _text(value: object) -> str:
    return str(value or "").strip()


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _strategic_mission_user_intent(
    *,
    snapshot: dict[str, Any],
    priority_baseline: dict[str, Any],
    allowed_tasks: list[dict[str, Any]],
    blocked_tasks: list[dict[str, Any]],
    q1_payload: dict[str, Any],
) -> dict[str, Any]:
    q3_payload = snapshot.get("q3") if isinstance(snapshot.get("q3"), dict) else {}
    q2_payload = snapshot.get("q2") if isinstance(snapshot.get("q2"), dict) else {}
    mission_payload = q2_payload.get("mission") if isinstance(q2_payload.get("mission"), dict) else {}
    q3_mission_payload = q3_payload.get("mission") if isinstance(q3_payload.get("mission"), dict) else {}

    mission_candidates = [
        mission_payload.get("current_mission"),
        q3_mission_payload.get("current_mission"),
        q3_payload.get("current_mission"),
        q3_payload.get("task_role"),
        q3_payload.get("active_role"),
        q1_payload.get("suggested_first_step"),
        q1_payload.get("environment_summary"),
    ]
    mission_candidates.extend(_string_list(priority_baseline.get("immediate_tasks")))
    mission_candidates.extend(_text(item.get("title") or item.get("task")) for item in allowed_tasks if isinstance(item, dict))

    current_total_goal = next((item for item in (_text(value) for value in mission_candidates) if item), "")
    if not current_total_goal:
        current_total_goal = "基于当前九问上下文生成服务于用户主线意图的内部认知目标"

    return {
        "current_total_goal": current_total_goal,
        "user_or_q3_mission_sources": [
            item
            for item in (
                _text(mission_payload.get("current_mission")),
                _text(q3_mission_payload.get("current_mission")),
                _text(q3_payload.get("task_role")),
                _text(q3_payload.get("active_role")),
            )
            if item
        ],
        "immediate_business_needs": _string_list(priority_baseline.get("immediate_tasks")),
        "allowed_candidate_intents": [
            _text(item.get("title") or item.get("task"))
            for item in allowed_tasks
            if isinstance(item, dict) and _text(item.get("title") or item.get("task"))
        ],
        "blocked_or_forbidden_intents": [
            _text(item.get("title") or item.get("task") or item.get("blocked_by"))
            for item in blocked_tasks
            if isinstance(item, dict) and _text(item.get("title") or item.get("task") or item.get("blocked_by"))
        ],
        "alignment_rule": "Q8 内部任务只能服务于 current_total_goal，必须解释 mission_rationale，禁止自行扩展新主线。",
    }


def build_q8_internal_staged_llm_request(
    *,
    system_prompt: str,
    priority_baseline: dict[str, Any],
    allowed_tasks: list[dict[str, Any]],
    blocked_tasks: list[dict[str, Any]],
    q1_llm_output: Any | None = None,
    q7_snapshot: Any,
    normalized_task_state: dict[str, list[dict[str, Any]]],
    request_timeout_seconds: float,
    q2_cognitive_plugins: list[str] | None = None,
    q2_functional_plugins: list[str] | None = None,
    q7_redlines: dict[str, Any] | None = None,
    q1_q7_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_stage_prompt = _render_template(
        "final_stage.md",
        {"OBJECTIVE_PROFILE_PROMPT": build_q8_internal_objective_profile_prompt()},
    )
    q2_cognitive_plugins = [
        str(item or "").strip()
        for item in (q2_cognitive_plugins or [])
        if str(item or "").strip()
    ]
    q7_redlines = q7_redlines if isinstance(q7_redlines, dict) else {}
    q7_redlines_converted = {
        "q7_raw_redlines": q7_redlines,
        "blocked_candidate_tasks": blocked_tasks,
        "conversion_rule": (
            "Convert Q7-blocked external or destructive intents only into read-only thought-sandbox, conflict-audit, "
            "reflection, learning, or memory-analysis tasks."
        ),
    }
    self_state_and_memory = {
        "priority_baseline": priority_baseline if isinstance(priority_baseline, dict) else {},
        "task_state": normalized_task_state if isinstance(normalized_task_state, dict) else {},
        "allowed_internal_candidates": allowed_tasks,
        "blocked_candidates_for_reflection": blocked_tasks,
    }
    snapshot = q1_q7_snapshot if isinstance(q1_q7_snapshot, dict) else {}
    q1_payload = snapshot.get("q1") if isinstance(snapshot.get("q1"), dict) else {}
    if not q1_payload and isinstance(q1_llm_output, dict):
        q1_payload = q1_llm_output
    q2_payload = snapshot.get("q2") if isinstance(snapshot.get("q2"), dict) else {}
    q3_payload = snapshot.get("q3") if isinstance(snapshot.get("q3"), dict) else {}
    q4_payload = snapshot.get("q4") if isinstance(snapshot.get("q4"), dict) else {}
    q5_payload = snapshot.get("q5") if isinstance(snapshot.get("q5"), dict) else {}
    q6_payload = snapshot.get("q6") if isinstance(snapshot.get("q6"), dict) else {}
    q7_payload = snapshot.get("q7") if isinstance(snapshot.get("q7"), dict) else {}
    if not q7_payload and isinstance(q7_snapshot, dict):
        q7_payload = q7_snapshot
    strategic_mission = _strategic_mission_user_intent(
        snapshot=snapshot,
        priority_baseline=priority_baseline if isinstance(priority_baseline, dict) else {},
        allowed_tasks=allowed_tasks,
        blocked_tasks=blocked_tasks,
        q1_payload=q1_payload,
    )
    context = {
        "request_timeout_seconds": request_timeout_seconds,
        "Strategic_Mission_&_User_Intent": strategic_mission,
        "Environment_State": q1_payload,
        "Role_Profile": q3_payload,
        "Internal_Cognitive_Assets": {
            "q2_asset_inventory": q2_payload,
            "q2_cognitive_capabilities": q2_cognitive_plugins,
        },
        "Internal_Brain_Organs_State": self_state_and_memory,
        "Q4_Capabilities": q4_payload,
        "Q5_AuthorizationBoundary": q5_payload,
        "Q6_ConsequenceProfile": q6_payload,
        "Q7_Redlines": q7_payload or q7_redlines,
        "Q2_Cognitive_Capabilities": q2_cognitive_plugins,
        "Q7_Redlines_Converted": q7_redlines_converted,
        "q8_priority_baseline": priority_baseline if isinstance(priority_baseline, dict) else {},
        "allowed_tasks": allowed_tasks,
        "blocked_tasks": blocked_tasks,
        "task_state": normalized_task_state if isinstance(normalized_task_state, dict) else {},
        "q8_request_scope": "internal",
    }
    return {
        "system_prompt": system_prompt,
        "prompt": f"{system_prompt}\n\n{final_stage_prompt}",
        "stage_prompt": final_stage_prompt,
        "context": context,
        "scope": "internal",
        "template_files": prompt_template_files(_TEMPLATE_DIR, _TEMPLATE_FILES),
    }

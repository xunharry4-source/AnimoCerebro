from __future__ import annotations

from pathlib import Path
from typing import Any

from zentex.common.prompt_template_files import prompt_template_files, render_prompt_template

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")
_TEMPLATE_FILES = ["final_stage.md"]


def _render_template(name: str, values: dict[str, str] | None = None) -> str:
    return render_prompt_template(_TEMPLATE_DIR, name, values or {}, error_prefix="q8_external")


def _text(value: object) -> str:
    return str(value or "").strip()


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _external_strategic_mission_user_intent(
    *,
    snapshot: dict[str, Any],
    priority_baseline: dict[str, Any],
    allowed_tasks: list[dict[str, Any]],
    blocked_tasks: list[dict[str, Any]],
    q1_payload: dict[str, Any],
) -> dict[str, Any]:
    q2_payload = snapshot.get("q2") if isinstance(snapshot.get("q2"), dict) else {}
    q3_payload = snapshot.get("q3") if isinstance(snapshot.get("q3"), dict) else {}
    q2_mission_payload = q2_payload.get("mission") if isinstance(q2_payload.get("mission"), dict) else {}
    q3_mission_payload = q3_payload.get("mission") if isinstance(q3_payload.get("mission"), dict) else {}

    mission_candidates = [
        q3_mission_payload.get("current_mission"),
        q3_payload.get("current_mission"),
        q2_mission_payload.get("current_mission"),
        q3_payload.get("task_role"),
        q3_payload.get("active_role"),
        q1_payload.get("suggested_first_step"),
        q1_payload.get("environment_summary"),
    ]
    mission_candidates.extend(_string_list(priority_baseline.get("immediate_tasks")))
    mission_candidates.extend(
        _text(item.get("title") or item.get("task")) for item in allowed_tasks if isinstance(item, dict)
    )
    current_total_goal = next((item for item in (_text(value) for value in mission_candidates) if item), "")
    return {
        "current_total_goal": current_total_goal,
        "q3_mission_sources": [
            item
            for item in (
                _text(q3_mission_payload.get("current_mission")),
                _text(q3_payload.get("current_mission")),
                _text(q3_payload.get("task_role")),
                _text(q3_payload.get("active_role")),
            )
            if item
        ],
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
        "alignment_rule": "Q8 外部 ObjectiveProfile.current_mission 必须继承 current_total_goal 或 Q3 主线使命，禁止留空或另造新主线。",
    }


def build_q8_external_staged_llm_request(
    *,
    system_prompt: str,
    priority_baseline: dict[str, Any],
    allowed_tasks: list[dict[str, Any]],
    blocked_tasks: list[dict[str, Any]],
    q1_llm_output: Any | None = None,
    q7_snapshot: Any,
    normalized_task_state: dict[str, list[dict[str, Any]]],
    request_timeout_seconds: float,
    q2_functional_plugins: list[str] | None = None,
    q2_cognitive_plugins: list[str] | None = None,
    q7_redlines: dict[str, Any] | None = None,
    q1_q7_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_stage_prompt = _render_template("final_stage.md")
    q2_functional_plugins = [
        str(item or "").strip()
        for item in (q2_functional_plugins or [])
        if str(item or "").strip()
    ]
    q7_redlines = q7_redlines if isinstance(q7_redlines, dict) else {}
    snapshot = q1_q7_snapshot if isinstance(q1_q7_snapshot, dict) else {}
    q1_payload = snapshot.get("q1") if isinstance(snapshot.get("q1"), dict) else {}
    if not q1_payload and isinstance(q1_llm_output, dict):
        q1_payload = q1_llm_output
    q2_payload = snapshot.get("q2") if isinstance(snapshot.get("q2"), dict) else {}
    q3_payload = snapshot.get("q3") if isinstance(snapshot.get("q3"), dict) else {}
    q7_payload = snapshot.get("q7") if isinstance(snapshot.get("q7"), dict) else {}
    if not q7_payload and isinstance(q7_snapshot, dict):
        q7_payload = q7_snapshot
    strategic_mission = _external_strategic_mission_user_intent(
        snapshot=snapshot,
        priority_baseline=priority_baseline if isinstance(priority_baseline, dict) else {},
        allowed_tasks=allowed_tasks,
        blocked_tasks=blocked_tasks,
        q1_payload=q1_payload,
    )
    context = {
        "request_timeout_seconds": request_timeout_seconds,
        "Strategic_Mission_&_User_Intent": strategic_mission,
        "Q1_Workspace_Domain_Inference": q1_payload,
        "Q2_AssetInventory": q2_payload,
        "Q3_RoleProfile": q3_payload,
        "Q7_External_Output": q7_payload or q7_redlines,
        "Q2_Functional_Capabilities": q2_functional_plugins,
        "q8_priority_baseline": priority_baseline if isinstance(priority_baseline, dict) else {},
        "allowed_tasks": allowed_tasks,
        "blocked_tasks": blocked_tasks,
        "task_state": normalized_task_state if isinstance(normalized_task_state, dict) else {},
        "q8_request_scope": "external",
    }
    return {
        "system_prompt": system_prompt,
        "prompt": f"{system_prompt}\n\n{final_stage_prompt}",
        "stage_prompt": final_stage_prompt,
        "context": context,
        "scope": "external",
        "template_files": prompt_template_files(_TEMPLATE_DIR, _TEMPLATE_FILES),
    }

from __future__ import annotations

from pathlib import Path
from typing import Any

from zentex.common.prompt_template_files import prompt_template_files, render_prompt_template

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")
_TEMPLATE_FILES = ["final_stage.md"]


def _render_template(name: str, values: dict[str, str] | None = None) -> str:
    return render_prompt_template(_TEMPLATE_DIR, name, values or {}, error_prefix="q8_external")


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
    q4_external_capabilities: dict[str, Any] | None = None,
    q7_redlines: dict[str, Any] | None = None,
    q1_q7_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_stage_prompt = _render_template("final_stage.md")
    q2_functional_plugins = [
        str(item or "").strip()
        for item in (q2_functional_plugins or [])
        if str(item or "").strip()
    ]
    q4_external_capabilities = q4_external_capabilities if isinstance(q4_external_capabilities, dict) else {}
    q7_redlines = q7_redlines if isinstance(q7_redlines, dict) else {}
    snapshot = q1_q7_snapshot if isinstance(q1_q7_snapshot, dict) else {}
    q1_payload = snapshot.get("q1") if isinstance(snapshot.get("q1"), dict) else {}
    if not q1_payload and isinstance(q1_llm_output, dict):
        q1_payload = q1_llm_output
    q2_payload = snapshot.get("q2") if isinstance(snapshot.get("q2"), dict) else {}
    q3_payload = snapshot.get("q3") if isinstance(snapshot.get("q3"), dict) else {}
    q4_payload = snapshot.get("q4") if isinstance(snapshot.get("q4"), dict) else {}
    if not q4_payload:
        q4_payload = q4_external_capabilities
    q5_payload = snapshot.get("q5") if isinstance(snapshot.get("q5"), dict) else {}
    q6_payload = snapshot.get("q6") if isinstance(snapshot.get("q6"), dict) else {}
    q7_payload = snapshot.get("q7") if isinstance(snapshot.get("q7"), dict) else {}
    if not q7_payload and isinstance(q7_snapshot, dict):
        q7_payload = q7_snapshot
    context = {
        "request_timeout_seconds": request_timeout_seconds,
        "Q1_Workspace_Domain_Inference": q1_payload,
        "Q2_AssetInventory": q2_payload,
        "Q3_RoleProfile": q3_payload,
        "Q4_External_Capabilities": q4_payload,
        "Q5_AuthorizationBoundary": q5_payload,
        "Q6_ConsequenceProfile": q6_payload,
        "Q7_Redlines": q7_payload or q7_redlines,
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

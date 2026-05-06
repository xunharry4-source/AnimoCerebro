from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import HTTPException, Request

from plugins.nine_questions.q9_how_should_i_act.llm_output_table import load_llm_output_from_table
from zentex.nine_questions.q9_tasks import sync_q9_tasks_to_task_service
from zentex.web_console.dependencies import get_plugin_service
from zentex.web_console.routers.nine_questions_impl.q_state import _get_nine_question_service

logger = logging.getLogger(__name__)
_nine_question_execution_guard = threading.Lock()

QUESTION_TITLES = {
    "q1": "我在那",
    "q2": "我有什么",
    "q3": "我是谁",
    "q4": "我能干什么",
    "q5": "我可以干什么",
    "q6": "我该如何进化",
    "q7": "我还可以做什么",
    "q8": "我应该干什么",
    "q9": "我应该怎么做",
}


def acquire_nine_question_execution_guard() -> None:
    if _nine_question_execution_guard.acquire(blocking=False):
        return
    raise HTTPException(
        status_code=409,
        detail={
            "error": "nine_question_execution_in_progress",
            "message": "九问执行正在进行中，请等待当前执行完成后再试。",
        },
    )


def stringify_timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def inject_app_runtime_context(request: Request, context: dict[str, Any]) -> dict[str, Any]:
    app_state = getattr(request.app, "state", None)
    enriched = dict(context)
    for key in (
        "foundation_service",
        "agent_service",
        "agent_coordination_service",
        "cli_service",
        "mcp_service",
        "external_connector_service",
        "task_service",
        "memory_service",
        "audit_service",
        "reflection_service",
        "learning_service",
        "cognitive_tool_registry_runtime",
        "managed_plugin_records",
        "workspace_store",
        "system_identity_store",
    ):
        if key not in enriched and app_state is not None and hasattr(app_state, key):
            enriched[key] = getattr(app_state, key)
    if "agent_service" not in enriched and "agent_coordination_service" in enriched:
        enriched["agent_service"] = enriched["agent_coordination_service"]
    plugin_service = get_plugin_service(request)
    if plugin_service is not None:
        enriched["plugin_service"] = plugin_service
    return enriched


def _merge_q9_context_updates(
    snapshot_map: dict[str, dict[str, Any]],
    context_updates: dict[str, Any],
) -> None:
    if not context_updates:
        return
    q9_snapshot = dict(snapshot_map.get("q9") or {})
    q9_context_updates = q9_snapshot.get("context_updates")
    q9_context_updates = q9_context_updates if isinstance(q9_context_updates, dict) else {}
    q9_snapshot["context_updates"] = {**q9_context_updates, **context_updates}
    snapshot_map["q9"] = q9_snapshot


async def sync_q9_postured_q8_tasks(
    request: Request,
    session_id: str,
    snapshot_map: dict[str, dict[str, Any]],
) -> None:
    if "q9" not in snapshot_map:
        raise HTTPException(status_code=409, detail="Q9 snapshot missing; task publication must happen from Q9")
    snapshot_map = {key: dict(value) for key, value in snapshot_map.items()}
    try:
        service = _get_nine_question_service(request)
        persisted_q9_snapshot = await service.get_question_snapshot("q9")
        if isinstance(persisted_q9_snapshot, dict) and persisted_q9_snapshot:
            current_q9_snapshot = snapshot_map.get("q9")
            current_q9_snapshot = current_q9_snapshot if isinstance(current_q9_snapshot, dict) else {}
            merged_q9_snapshot = {**current_q9_snapshot, **persisted_q9_snapshot}
            for field in ("context_updates", "result", "llm_output", "modules"):
                current_value = current_q9_snapshot.get(field)
                persisted_value = persisted_q9_snapshot.get(field)
                if isinstance(current_value, dict) or isinstance(persisted_value, dict):
                    merged_q9_snapshot[field] = {
                        **(current_value if isinstance(current_value, dict) else {}),
                        **(persisted_value if isinstance(persisted_value, dict) else {}),
                    }
            snapshot_map["q9"] = merged_q9_snapshot
        state_manager = getattr(service, "_state_manager", None)
        store = getattr(state_manager, "_store", None)
        q9_llm_output = load_llm_output_from_table(
            db_path=getattr(store, "db_path", None),
            session_id="nq-baseline",
        )
        q9_llm_context_updates = {
            key: value
            for key, value in q9_llm_output.items()
            if key
            in {
                "q9_internal_llm_input",
                "q9_internal_llm_output",
                "q9_external_llm_input",
                "q9_external_llm_output",
            }
            and isinstance(value, dict)
            and value
        }
        _merge_q9_context_updates(snapshot_map, q9_llm_context_updates)
        modules = await service.get_question_modules("q9")
        module_context_updates: dict[str, Any] = {}
        module_map = modules.get("modules") if isinstance(modules, dict) else {}
        if isinstance(module_map, dict):
            for module in module_map.values():
                if not isinstance(module, dict):
                    continue
                data = module.get("data")
                if isinstance(data, dict):
                    module_context_updates.update(data)
        if module_context_updates:
            _merge_q9_context_updates(snapshot_map, module_context_updates)
        _merge_q9_context_updates(snapshot_map, q9_llm_context_updates)
    except Exception:
        logger.exception("[nine-questions] failed to enrich q9 task sync from module outputs")
    await sync_q9_tasks_to_task_service(
        task_service=getattr(request.app.state, "task_service", None),
        session_id=session_id,
        snapshot_map=snapshot_map,
        logger=logger,
    )

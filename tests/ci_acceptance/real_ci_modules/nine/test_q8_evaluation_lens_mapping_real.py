from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.q8_evaluation_lens_mapper import (
    Q8EvaluationLensMappingError,
    map_evaluation_weights_to_meta_value_lenses,
)
from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service


def _snapshot(session_id: str, suffix: str) -> dict:
    q8_objective = {
        "current_mission": f"map evaluation lenses {suffix}",
        "primary_objectives": ["prove meta value lenses are queryable"],
        "completion_conditions": ["task stores mapped lens weights"],
    }
    q9_evaluation = {
        "role_context": "release executor",
        "resource_context": "real TaskService sync",
        "risk_level": "high",
        "evaluation_weights": {
            "accuracy": 0.25,
            "creativity": 0.15,
            "speed": 0.30,
            "continuity": 0.20,
            "risk_control": 0.10,
        },
        "conservative_mode_triggered": False,
        "evaluation_style": "lens_mapping_real",
        "action_rhythm_hint": "sync_then_query",
    }
    return {
        "q8": {
            "trace_id": f"trace-q8-lens-map-{suffix}",
            "summary": "Q8 lens mapping test",
            "context_updates": {
                "q8_objective_profile": q8_objective,
                "q8_task_queue": {
                    "next_self_tasks": [
                        {
                            "task_id": f"lens-map-task-{suffix}",
                            "title": "persist mapped meta value lens weights",
                            "priority": "medium",
                            "success_criteria": ["meta lens mapping is stored"],
                            "risk_assessment": {"risk_level": "low"},
                        }
                    ],
                    "blocked_self_tasks": [],
                    "proactive_actions": [],
                },
            },
            "result": {},
        },
        "q9": {
            "trace_id": f"trace-q9-lens-map-{suffix}",
            "summary": "Q9 lens mapping profile",
            "context_updates": {
                "q9_evaluation_profile": q9_evaluation,
                "q9_action_posture": {"evaluation_profile": q9_evaluation},
            },
            "result": {"evaluation_profile": q9_evaluation},
        },
    }


def test_q8_evaluation_lens_mapper_maps_configured_axes_exactly() -> None:
    report = map_evaluation_weights_to_meta_value_lenses(
        {
            "accuracy": 0.25,
            "creativity": 0.15,
            "speed": 0.30,
            "continuity": 0.20,
            "risk_control": 0.10,
        }
    )

    assert report["mapping_version"] == "1.0"
    assert report["lens_weights"] == {
        "system_capability_lens": 0.2,
        "user_efficiency_lens": 0.3,
        "user_value_lens": 0.4,
    }
    assert report["lens_axis_weights"]["user_value_lens"] == {"accuracy": 0.25, "creativity": 0.15}
    assert report["dominant_lenses"] == ["user_value_lens"]
    assert report["unmapped_source_weights"] == {"risk_control": 0.1}


def test_q8_evaluation_lens_mapper_rejects_invalid_weight_without_fallback() -> None:
    with pytest.raises(Q8EvaluationLensMappingError) as exc_info:
        map_evaluation_weights_to_meta_value_lenses({"accuracy": "not-a-number"})

    assert exc_info.value.failures == [
        {"reason": "evaluation_weight_invalid", "axis": "accuracy", "value": "not-a-number"}
    ]


@pytest.mark.asyncio
async def test_q8_sync_persists_meta_value_lens_mapping_and_query_matches_business_weights(real_ci_runtime) -> None:
    suffix = unique_suffix()
    session_id = f"q8-lens-map-{suffix}"

    await sync_q8_tasks_to_task_service(
        task_service=real_ci_runtime.task_service,
        session_id=session_id,
        snapshot_map=_snapshot(session_id, suffix),
    )

    tasks = real_ci_runtime.task_service.list_tasks(
        metadata_filters={"session_id": session_id, "queue_name": "next_self_tasks"}
    )
    assert len(tasks) == 1
    task = tasks[0]
    queried = real_ci_runtime.task_service.get_task(task.task_id)
    assert queried.metadata["evaluation_profile"]["source_trace_id"] == f"trace-q9-lens-map-{suffix}"
    assert queried.metadata["evaluation_profile"]["evaluation_weights"] == {
        "accuracy": 0.25,
        "creativity": 0.15,
        "speed": 0.30,
        "continuity": 0.20,
        "risk_control": 0.10,
    }
    assert queried.metadata["evaluation_profile"]["meta_value_lens_weights"] == {
        "system_capability_lens": 0.2,
        "user_efficiency_lens": 0.3,
        "user_value_lens": 0.4,
    }
    assert queried.metadata["evaluation_profile"]["dominant_meta_value_lenses"] == ["user_value_lens"]
    assert queried.metadata["phase_a_evaluation"]["meta_value_lens_weights"] == {
        "system_capability_lens": 0.2,
        "user_efficiency_lens": 0.3,
        "user_value_lens": 0.4,
    }
    assert queried.metadata["phase_a_evaluation"]["dominant_meta_value_lenses"] == ["user_value_lens"]

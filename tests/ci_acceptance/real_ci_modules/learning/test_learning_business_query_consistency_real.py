from __future__ import annotations

import json
import sqlite3

from zentex.reflection.models import ReflectionType
from zentex.learning.engine import LEARNING_SESSION_ID
from zentex.learning.store import LEARNING_OVERALL_EVENT_TYPE

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_learning_business_query_consistency_real(real_ci_runtime) -> None:
    """功能：真实 maintenance 写入后，service 查询结果必须与学习库原始事件一致。"""
    suffix = unique_suffix()
    memory_record = real_ci_runtime.memory_service.remember(
        title=f"learning-business-{suffix}",
        content=f"learning business maintenance content {suffix}",
        summary=f"learning business maintenance summary {suffix}",
        source="tests",
        tags=["learning-business", suffix],
    )
    real_ci_runtime.reflection_service.record_nine_question_reflection(
        subject=f"learning-business-reflection-{suffix}",
        reflection_type=ReflectionType.LEARNING_REFLECTION,
        context={
            "summary": f"learning business reflection summary {suffix}",
            "question_id": "q1",
        },
        trace_id=f"learning-business-reflection-trace-{suffix}",
    )

    result = real_ci_runtime.learning_service.trigger_memory_aware_maintenance(operator="ci")
    service_rows = real_ci_runtime.learning_service.query_overall_records(
        limit=20,
        trace_id=result.trace_id,
        status="completed",
    )
    assert service_rows, "expected service to return learning overall record"
    service_record = service_rows[0]

    db_path = real_ci_runtime.learning_service.store.db_path
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT trace_id, entry_type, payload, timestamp
            FROM learning_events
            WHERE session_id = ?
              AND entry_type = ?
              AND trace_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (LEARNING_SESSION_ID, LEARNING_OVERALL_EVENT_TYPE, result.trace_id),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "expected raw overall record in learning_events"
    payload = json.loads(str(row[2]))
    detail = dict(payload.get("detail") or {})

    assert str(row[0]) == result.trace_id
    assert str(row[1]) == LEARNING_OVERALL_EVENT_TYPE
    assert service_record.trace_id == result.trace_id
    assert service_record.direction == str(payload.get("direction"))
    assert service_record.status == str(payload.get("status"))
    assert service_record.summary == str(payload.get("summary"))
    assert service_record.detail == detail
    assert memory_record.memory_id in list(detail.get("source_memory_ids") or [])
    assert detail.get("used_memory_count") == result.used_memory_count
    assert detail.get("used_reflection_count") == result.used_reflection_count
    assert detail.get("cross_module_pressure") is not None

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

from zentex.reflection.models import ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_business_query_consistency_real(real_ci_runtime) -> None:
    """功能：真实 service 写入后，业务查询结果必须与库内 SQL 查询一致。"""
    suffix = unique_suffix()
    reflection_service = real_ci_runtime.reflection_service
    start_time = datetime.now(timezone.utc) - timedelta(seconds=1)

    inserted = []
    for question_id, index in [("q1", 1), ("q1", 2), ("q2", 3)]:
        trace_id = f"reflection-business-query:{suffix}:{question_id}:{index}"
        record = reflection_service.record_nine_question_reflection(
            subject=f"business-query-{suffix}-{question_id}-{index}",
            reflection_type=ReflectionType.LEARNING_REFLECTION,
            context={
                "summary": f"business query summary {suffix} {question_id} {index}",
                "question_id": question_id,
            },
            trace_id=trace_id,
        )
        inserted.append(record)

    end_time = datetime.now(timezone.utc) + timedelta(seconds=1)

    service_rows = reflection_service.list_reflections(
        {
            "question_id": "q1",
            "start_time": start_time,
            "end_time": end_time,
            "limit": 100,
        }
    )
    service_ids = {
        row.reflection_id
        for row in service_rows
        if suffix in row.subject
    }

    db_path = reflection_service._dao.db.db_path
    conn = sqlite3.connect(str(db_path))
    try:
        sql_rows = conn.execute(
            """
            SELECT reflection_id
            FROM reflections
            WHERE json_extract(context, '$.question_id') = ?
              AND created_at >= ?
              AND created_at <= ?
            ORDER BY created_at DESC
            """,
            ("q1", start_time.isoformat(), end_time.isoformat()),
        ).fetchall()
        sql_ids = {str(row[0]) for row in sql_rows}

        overall_rows = conn.execute(
            """
            SELECT reflection_id, trace_id, subject, summary, quality
            FROM reflection_overall_records
            WHERE trace_id = ?
            LIMIT 1
            """,
            (inserted[0].trace_id,),
        ).fetchone()
    finally:
        conn.close()

    expected_q1_ids = {
        record.reflection_id
        for record in inserted
        if record.context.get("question_id") == "q1"
    }

    assert service_ids == expected_q1_ids
    assert sql_ids >= expected_q1_ids
    assert overall_rows is not None, "expected mirrored row in reflection_overall_records"
    assert str(overall_rows[0]) == inserted[0].reflection_id
    assert str(overall_rows[1]) == inserted[0].trace_id
    assert str(overall_rows[2]) == inserted[0].subject
    assert suffix in str(overall_rows[3])
    assert str(overall_rows[4]) == inserted[0].quality.value

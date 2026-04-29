from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

from zentex.reflection.models import GovernanceStatus, ReflectionQuality, ReflectionType

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def _seed_reflection(
    reflection_service,
    *,
    suffix: str,
    group: str,
    index: int,
    text: str,
    quality: ReflectionQuality,
    created_at: datetime,
    confidence: float = 0.75,
    actionability: float = 0.65,
    archived: bool = False,
):
    trace_id = f"cleanup-cleanlab:{suffix}:{group}:{index}"
    record = reflection_service.record_nine_question_reflection(
        subject=f"cleanup-cleanlab-{suffix}-{group}-{index}",
        reflection_type=ReflectionType.LEARNING_REFLECTION,
        context={
            "summary": text,
            "question_id": "q1",
            "cleanup_group": group,
            "test_suffix": suffix,
        },
        trace_id=trace_id,
    )
    updated = reflection_service.update_reflection(
        record.reflection_id,
        {
            "quality": quality,
            "confidence": confidence,
            "actionability": actionability,
            "summary": text,
            "created_at": created_at,
            "updated_at": created_at,
            "reflection_timestamp": created_at,
            "tags": ["cleanup_cleanlab_real", group, suffix],
            "metadata": {
                "source": "cleanup_cleanlab_real",
                "test_suffix": suffix,
                "cleanup_group": group,
            },
        },
    )
    if archived:
        updated = reflection_service.archive_reflection(updated.reflection_id)
    return updated


def test_reflection_cleanup_cleanlab_protection_real(real_ci_runtime) -> None:
    """真实维护清理必须删除低价值旧记录，同时保护 CleanLab 判定可疑的误标记录。"""
    suffix = unique_suffix()
    reflection_service = real_ci_runtime.reflection_service
    now = datetime.now(timezone.utc)
    base_old = now - timedelta(days=7, hours=1)

    texts = {
        "poor": "deployment outage rollback failed incident blocked release repeated error unstable loss",
        "fair": "partial improvement mixed result moderate issue workaround needs review",
        "good": "stable reusable pattern successful workflow verified evidence repeatable improvement",
        "excellent": "excellent high confidence evidence backed optimization reliable repeatable result",
    }

    all_seeded_ids: list[str] = []
    for quality_name, base_text in texts.items():
        for index in range(30):
            quality = getattr(ReflectionQuality, quality_name.upper())
            record = _seed_reflection(
                reflection_service,
                suffix=suffix,
                group=quality_name,
                index=index,
                text=f"{base_text} {suffix} cohort {index}",
                quality=quality,
                created_at=base_old + timedelta(seconds=index),
            )
            all_seeded_ids.append(record.reflection_id)

    protected_records = [
        _seed_reflection(
            reflection_service,
            suffix=suffix,
            group="mislabeled_good_as_poor",
            index=index,
            text=f"{texts['good']} {suffix} cohort {index}",
            quality=ReflectionQuality.POOR,
            created_at=base_old + timedelta(minutes=2, seconds=index),
            confidence=0.18,
            actionability=0.08,
        )
        for index in range(10)
    ]
    expected_protected_by_trace = {
        f"cleanup-cleanlab:{suffix}:mislabeled_good_as_poor:{index}": record.reflection_id
        for index, record in enumerate(protected_records)
    }
    expected_protected_ids = set(expected_protected_by_trace.values())
    all_seeded_ids.extend(expected_protected_ids)

    archived_records = [
        _seed_reflection(
            reflection_service,
            suffix=suffix,
            group="archived_low_value",
            index=index,
            text=f"{texts['poor']} {suffix} archived deletion candidate {index}",
            quality=ReflectionQuality.POOR,
            created_at=base_old + timedelta(minutes=3, seconds=index),
            confidence=0.12,
            actionability=0.05,
            archived=True,
        )
        for index in range(5)
    ]
    expected_deleted_by_trace = {
        f"cleanup-cleanlab:{suffix}:archived_low_value:{index}": record.reflection_id
        for index, record in enumerate(archived_records)
    }
    expected_deleted_ids = set(expected_deleted_by_trace.values())
    all_seeded_ids.extend(expected_deleted_ids)

    db_path = reflection_service._dao.db.db_path
    oldest_seed_time = min(reflection_service.get_reflection(reflection_id).created_at for reflection_id in all_seeded_ids)
    conn = sqlite3.connect(str(db_path))
    try:
        rows_in_window = conn.execute(
            "SELECT COUNT(*) FROM reflections WHERE created_at >= ?",
            ((oldest_seed_time - timedelta(seconds=1)).isoformat(),),
        ).fetchone()[0]
    finally:
        conn.close()

    result = reflection_service.trigger_memory_aware_maintenance(
        operator=f"cleanup-cleanlab-real-{suffix}",
        memory_limit=1,
        reflection_limit=int(rows_in_window) + 20,
    )

    # Query each expected row by its true trace_id instead of relying on the maintenance aggregate count,
    # because the mixed real database may contain unrelated cleanup candidates in the same run.
    service_deleted_ids = set()
    for trace_id, reflection_id in expected_deleted_by_trace.items():
        rows = reflection_service.list_reflections({"trace_id": trace_id})
        if not rows:
            service_deleted_ids.add(reflection_id)

    protected_service_rows = {
        row.reflection_id: row
        for trace_id in expected_protected_by_trace
        for row in reflection_service.list_reflections(
            {"trace_id": trace_id}
        )
    }

    conn = sqlite3.connect(str(db_path))
    try:
        deleted_db_rows = conn.execute(
            f"""
            SELECT reflection_id
            FROM reflections
            WHERE reflection_id IN ({','.join('?' for _ in expected_deleted_ids)})
            """,
            tuple(expected_deleted_ids),
        ).fetchall()
        deleted_overall_rows = conn.execute(
            f"""
            SELECT reflection_id
            FROM reflection_overall_records
            WHERE reflection_id IN ({','.join('?' for _ in expected_deleted_ids)})
            """,
            tuple(expected_deleted_ids),
        ).fetchall()
        protected_db_rows = conn.execute(
            f"""
            SELECT reflection_id, governance_status, suspect_reason, quality, confidence, actionability
            FROM reflections
            WHERE reflection_id IN ({','.join('?' for _ in expected_protected_ids)})
            """,
            tuple(expected_protected_ids),
        ).fetchall()
    finally:
        conn.close()

    assert result.deleted_reflection_count >= len(expected_deleted_ids)
    assert service_deleted_ids == expected_deleted_ids
    assert deleted_db_rows == []
    assert deleted_overall_rows == []

    assert set(protected_service_rows) == expected_protected_ids
    for row in protected_service_rows.values():
        assert row.governance_status == GovernanceStatus.SUSPECT
        assert row.suspect_reason == "cleanlab_label_issue"

    protected_db_by_id = {str(row[0]): row for row in protected_db_rows}
    assert set(protected_db_by_id) == expected_protected_ids
    for row in protected_db_by_id.values():
        assert str(row[1]) == GovernanceStatus.SUSPECT.value
        assert str(row[2]) == "cleanlab_label_issue"
        assert str(row[3]) == ReflectionQuality.POOR.value
        assert float(row[4]) < 0.35
        assert float(row[5]) < 0.25

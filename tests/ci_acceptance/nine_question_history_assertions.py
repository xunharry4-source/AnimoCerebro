from __future__ import annotations

from typing import Any


HISTORY_FIELD_NAMES = {
    "history",
    "histories",
    "versions",
    "previous_versions",
    "historical_versions",
    "version_history",
    "snapshot_history",
    "snapshot_versions",
    "question_history",
    "question_versions",
    "question_snapshot_history",
    "question_snapshots_history",
}


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _has_payload(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_payload(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_payload(item) for item in value)
    return value not in (None, "", [], {})


def _history_entries_for_question(container: Any, question_id: str) -> list[Any]:
    if not _has_payload(container):
        return []
    if isinstance(container, dict):
        direct = container.get(question_id)
        if _has_payload(direct):
            return [direct]
        entries: list[Any] = []
        for key, value in container.items():
            key_text = str(key).lower()
            if key_text == question_id or key_text.startswith(f"{question_id}:") or key_text.startswith(f"{question_id}@"):
                if _has_payload(value):
                    entries.append(value)
        return entries
    if isinstance(container, list):
        entries = []
        for item in container:
            if not _has_payload(item):
                continue
            if not isinstance(item, dict):
                entries.append(item)
                continue
            item_qid = str(
                item.get("question_id")
                or item.get("qid")
                or item.get("question_ref")
                or item.get("id")
                or ""
            ).lower()
            if item_qid == question_id:
                entries.append(item)
        return entries
    return [container]


def assert_question_history_version_exists(state: Any, question_id: str) -> None:
    """Clinical gate: every q1..q9 rerun must persist a historical version."""
    qid = str(question_id).lower()
    payload = _as_dict(state)
    snapshots = payload.get("question_snapshots")
    snapshots = snapshots if isinstance(snapshots, dict) else {}
    snapshot = snapshots.get(qid) if isinstance(snapshots.get(qid), dict) else {}

    found_entries: list[Any] = []
    for key in HISTORY_FIELD_NAMES:
        found_entries.extend(_history_entries_for_question(payload.get(key), qid))
        found_entries.extend(_history_entries_for_question(snapshot.get(key), qid))

    for key, value in snapshots.items():
        key_text = str(key).lower()
        if key_text.startswith(f"{qid}:history") or key_text.startswith(f"{qid}@history"):
            if _has_payload(value):
                found_entries.append(value)

    assert found_entries, (
        f"{qid.upper()} historical version missing. "
        "Rerun must persist a history/version record instead of only overwriting the canonical snapshot."
    )

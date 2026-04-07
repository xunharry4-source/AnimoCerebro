from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.runtime.temporal import CognitiveTemporalEngine, TemporalAgendaState  # noqa: E402


def test_agenda_priority_shifts_with_age_and_risk() -> None:
    engine = CognitiveTemporalEngine()
    created_at = datetime(2026, 4, 3, 8, 0, tzinfo=timezone.utc)
    current_time = created_at + timedelta(hours=4)
    item = {
        "item_id": "risk-item-1",
        "status": "watching",
        "watching": True,
        "priority": 5,
        "created_at": created_at.isoformat(),
        "updated_at": created_at.isoformat(),
        "last_reviewed_at": (created_at + timedelta(minutes=5)).isoformat(),
        "review_count": 0,
        "impact_score": 0.95,
        "uncertainty_score": 0.9,
        "review_window": {
            "window_kind": "short_term",
            "review_interval_seconds": 300,
            "grace_period_seconds": 60,
            "expire_after_seconds": 20000,
        },
        "reminder_cooldown": {
            "cooldown_seconds": 30,
            "last_resurfaced_at": (created_at + timedelta(minutes=6)).isoformat(),
            "suppressed_count": 0,
        },
    }

    state = engine.tick_agenda(current_time=current_time, current_agenda_items=[item])

    assert isinstance(state, TemporalAgendaState)
    assert "risk-item-1" in state.review_now_item_ids
    assert "risk-item-1" in state.overdue_item_ids
    assert item["priority"] == 100
    assert item["status"] == "review_now"


def test_expired_assumptions_are_downgraded() -> None:
    engine = CognitiveTemporalEngine()
    created_at = datetime(2026, 4, 3, 8, 0, tzinfo=timezone.utc)
    current_time = created_at + timedelta(hours=2)
    item = {
        "item_id": "assumption-1",
        "status": "open",
        "priority": 10,
        "created_at": created_at.isoformat(),
        "updated_at": created_at.isoformat(),
        "review_window": {
            "window_kind": "immediate",
            "review_interval_seconds": 60,
            "grace_period_seconds": 30,
            "expire_after_seconds": 300,
        },
    }

    state = engine.tick_agenda(current_time=current_time, current_agenda_items=[item])

    assert "assumption-1" in state.expired_item_ids
    assert "assumption-1" not in state.open_item_ids
    assert item["expired"] is True
    assert item["status"] == "expired"


def test_reminder_cooldown_suppression() -> None:
    engine = CognitiveTemporalEngine()
    current_time = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    item = {
        "item_id": "cooldown-item-1",
        "status": "watching",
        "watching": True,
        "priority": 9,
        "created_at": (current_time - timedelta(hours=1)).isoformat(),
        "updated_at": (current_time - timedelta(hours=1)).isoformat(),
        "last_reviewed_at": (current_time - timedelta(minutes=30)).isoformat(),
        "impact_score": 0.98,
        "uncertainty_score": 0.95,
        "review_window": {
            "window_kind": "short_term",
            "review_interval_seconds": 60,
            "grace_period_seconds": 10,
            "expire_after_seconds": 10000,
        },
        "reminder_cooldown": {
            "cooldown_seconds": 600,
            "last_resurfaced_at": (current_time - timedelta(seconds=120)).isoformat(),
            "suppressed_count": 2,
        },
    }

    state = engine.tick_agenda(current_time=current_time, current_agenda_items=[item])

    assert "cooldown-item-1" not in state.review_now_item_ids
    assert item["reminder_cooldown"]["suppressed_count"] == 3
    assert item["status"] == "watching"


def test_strict_no_execution_boundary() -> None:
    engine = CognitiveTemporalEngine()
    action_router = Mock(name="action_router")
    webhook_sender = Mock(name="webhook_sender")

    now = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)
    item = {
        "item_id": "internal-item",
        "status": "open",
        "priority": 4,
        "created_at": (now - timedelta(hours=3)).isoformat(),
        "updated_at": (now - timedelta(hours=3)).isoformat(),
        "impact_score": 0.7,
        "uncertainty_score": 0.6,
        "review_window": {
            "window_kind": "mid_term",
            "review_interval_seconds": 60,
            "grace_period_seconds": 10,
            "expire_after_seconds": 10000,
        },
    }

    state = engine.tick_agenda(current_time=now, current_agenda_items=[item])

    assert isinstance(state, TemporalAgendaState)
    action_router.assert_not_called()
    webhook_sender.assert_not_called()


def test_no_llm_calls_made() -> None:
    engine = CognitiveTemporalEngine()
    model_provider = Mock(name="model_provider")
    llm_client = Mock(name="llm_client")

    now = datetime(2026, 4, 3, 13, 0, tzinfo=timezone.utc)
    item = {
        "item_id": "deterministic-item",
        "status": "open",
        "priority": 3,
        "created_at": (now - timedelta(minutes=10)).isoformat(),
        "updated_at": (now - timedelta(minutes=10)).isoformat(),
        "review_window": {
            "window_kind": "short_term",
            "review_interval_seconds": 120,
            "grace_period_seconds": 30,
            "expire_after_seconds": 1000,
        },
    }

    state = engine.tick_agenda(current_time=now, current_agenda_items=[item])

    assert isinstance(state, TemporalAgendaState)
    model_provider.assert_not_called()
    llm_client.assert_not_called()


def test_cluster_concurrency_state_serializable() -> None:
    engine = CognitiveTemporalEngine()
    now = datetime(2026, 4, 3, 14, 0, tzinfo=timezone.utc)
    items = [
        {
            "item_id": "serializable-a",
            "status": "open",
            "priority": 1,
            "created_at": (now - timedelta(minutes=15)).isoformat(),
            "updated_at": (now - timedelta(minutes=15)).isoformat(),
            "review_window": {
                "window_kind": "short_term",
                "review_interval_seconds": 120,
                "grace_period_seconds": 30,
                "expire_after_seconds": 1000,
            },
        },
        {
            "item_id": "serializable-b",
            "status": "watching",
            "watching": True,
            "priority": 2,
            "created_at": (now - timedelta(minutes=30)).isoformat(),
            "updated_at": (now - timedelta(minutes=30)).isoformat(),
            "review_window": {
                "window_kind": "mid_term",
                "review_interval_seconds": 300,
                "grace_period_seconds": 60,
                "expire_after_seconds": 2000,
            },
        },
    ]

    state = engine.tick_agenda(current_time=now, current_agenda_items=items)
    payload = state.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    restored = TemporalAgendaState.from_dict(decoded)

    assert restored == state
    assert restored.open_item_ids == state.open_item_ids
    assert restored.watching_item_ids == state.watching_item_ids
    assert restored.created_at == state.created_at
    assert restored.updated_at == state.updated_at

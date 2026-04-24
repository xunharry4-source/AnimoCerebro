from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[4]
if str(repo_root / "src") not in sys.path:
    sys.path.append(str(repo_root / "src"))
if str(repo_root / "tests/ci_acceptance") not in sys.path:
    sys.path.append(str(repo_root / "tests/ci_acceptance"))

from nine_question_history_assertions import assert_question_history_version_exists
from zentex.web_console.di_container import WebConsoleContainer


async def _assert_question_has_history_version(question_id: str) -> None:
    WebConsoleContainer.initialize()
    facade = WebConsoleContainer.get_kernel_service()
    state_mgr = facade.get_nine_question_state_manager()
    db_state = await state_mgr.get_state("nq-baseline")

    snapshots = getattr(db_state, "question_snapshots", {})
    assert isinstance(snapshots, dict), "nine-question state question_snapshots must be a dict"
    assert question_id in snapshots, f"{question_id.upper()} not found in authoritative database snapshots"
    assert_question_history_version_exists(db_state, question_id)


@pytest.mark.asyncio
async def test_q1_history_version_exists() -> None:
    await _assert_question_has_history_version("q1")


@pytest.mark.asyncio
async def test_q2_history_version_exists() -> None:
    await _assert_question_has_history_version("q2")


@pytest.mark.asyncio
async def test_q3_history_version_exists() -> None:
    await _assert_question_has_history_version("q3")


@pytest.mark.asyncio
async def test_q4_history_version_exists() -> None:
    await _assert_question_has_history_version("q4")


@pytest.mark.asyncio
async def test_q5_history_version_exists() -> None:
    await _assert_question_has_history_version("q5")


@pytest.mark.asyncio
async def test_q6_history_version_exists() -> None:
    await _assert_question_has_history_version("q6")


@pytest.mark.asyncio
async def test_q7_history_version_exists() -> None:
    await _assert_question_has_history_version("q7")


@pytest.mark.asyncio
async def test_q8_history_version_exists() -> None:
    await _assert_question_has_history_version("q8")


@pytest.mark.asyncio
async def test_q9_history_version_exists() -> None:
    await _assert_question_has_history_version("q9")

from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import Mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.tasks.registry import TaskRegistry  # noqa: E402
from zentex.tasks.service import TaskManagementService  # noqa: E402


def test_task_management_service_requires_explicit_decomposer_in_production() -> None:
    registry = TaskRegistry()
    transcript_store = Mock()

    with pytest.raises(RuntimeError, match="requires an explicit mission decomposer"):
        TaskManagementService(registry, transcript_store)

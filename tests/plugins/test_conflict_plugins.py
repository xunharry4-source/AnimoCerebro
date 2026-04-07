from __future__ import annotations

from pathlib import Path
import sys
from unittest import mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from plugins.cognitive import build_semantic_conflict_plugin  # noqa: E402
from zentex.core.model_provider_spec import ModelProviderRemoteError  # noqa: E402


def test_semantic_conflict_plugin_fail_closed_when_llm_remote_errors() -> None:
    plugin = build_semantic_conflict_plugin()
    model_provider = mock.Mock()
    model_provider.generate_json.side_effect = ModelProviderRemoteError("remote 500")

    with pytest.raises(ModelProviderRemoteError, match="remote 500"):
        plugin.detect_conflict(
            context={
                "goal": "Expand autonomous execution",
                "identity_constraints": ["avoid unsafe escalation"],
                "decision_id": "decision-1",
            },
            model_provider=model_provider,
        )

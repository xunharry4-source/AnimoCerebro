from __future__ import annotations

from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from plugins.model_providers.provider_tools_provider import (  # noqa: E402
    build_default_provider_tools_model_provider,
)
from zentex.core.model_provider_spec import (  # noqa: E402
    ModelProviderCallerContext,
    ModelProviderConfigError,
)


def test_default_provider_tools_model_provider_raises_when_current_config_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = build_default_provider_tools_model_provider(
        provider_name="openai",
        plugin_id="model-provider-openai",
    )
    monkeypatch.delenv(provider.api_key_env, raising=False)

    with pytest.raises(ModelProviderConfigError):
        provider.generate_json(
            prompt="return a json object",
            context={"topic": "missing credentials must fail closed"},
            caller_context=ModelProviderCallerContext(
                source_module="pytest",
                invocation_phase="fail_closed_verification",
                question_driver_refs=["我是谁"],
                decision_id="test:provider_tools_fail_closed",
            ),
        )

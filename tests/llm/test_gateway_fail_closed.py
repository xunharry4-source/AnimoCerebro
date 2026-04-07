from __future__ import annotations

from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from plugins.provider_tools import AuthError, ConfigError, RemoteServiceError, RemoteTimeoutError  # noqa: E402
from zentex.core.model_provider_spec import (  # noqa: E402
    ModelProviderAuthError,
    ModelProviderCallerContext,
    ModelProviderConfigError,
    ModelProviderRemoteError,
    ModelProviderTimeoutError,
)
from zentex.llm.gateway import LLMGateway  # noqa: E402


class _FakeToolConfig:
    default_model = "fake-model"


class _FailingTool:
    def __init__(self, exc: Exception) -> None:
        self.config = _FakeToolConfig()
        self._exc = exc

    def call(self, invocation):  # noqa: ANN001
        raise self._exc


def test_gateway_raises_config_error_when_provider_key_missing() -> None:
    gateway = LLMGateway(tools={"fake": _FailingTool(RemoteServiceError("unused"))})
    ctx = ModelProviderCallerContext(
        source_module="test",
        invocation_phase="unit",
        question_driver_refs=["q"],
        decision_id="d",
    )

    with pytest.raises(ModelProviderConfigError, match="provider_key must not be empty"):
        gateway.invoke_generate_json(prompt="x", context={}, caller_context=ctx, provider_key="  ")


def test_gateway_maps_auth_timeout_remote_errors_and_never_returns_fake_data() -> None:
    ctx = ModelProviderCallerContext(
        source_module="test",
        invocation_phase="unit",
        question_driver_refs=["q"],
        decision_id="d",
    )

    gateway = LLMGateway(tools={"fake": _FailingTool(AuthError("missing api key"))})
    with pytest.raises(ModelProviderAuthError, match="missing api key"):
        gateway.invoke_generate_json(prompt="x", context={}, caller_context=ctx, provider_key="fake")

    gateway = LLMGateway(tools={"fake": _FailingTool(RemoteTimeoutError("timeout"))})
    with pytest.raises(ModelProviderTimeoutError, match="timeout"):
        gateway.invoke_generate_json(prompt="x", context={}, caller_context=ctx, provider_key="fake")

    gateway = LLMGateway(tools={"fake": _FailingTool(RemoteServiceError("500"))})
    with pytest.raises(ModelProviderRemoteError, match="500"):
        gateway.invoke_generate_json(prompt="x", context={}, caller_context=ctx, provider_key="fake")


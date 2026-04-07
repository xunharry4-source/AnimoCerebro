from __future__ import annotations

import io
import json
from pathlib import Path
import sys
from urllib import error as urllib_error
from unittest.mock import patch

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from plugins.model_providers.gemini_provider import GeminiProvider  # noqa: E402
from zentex.core.model_provider_spec import (  # noqa: E402
    ModelProviderCallerContext,
    ModelProviderConfigError,
    ModelProviderParseError,
    ModelProviderRateLimitError,
    ModelProviderTimeoutError,
)
from zentex.core.plugin_base import (  # noqa: E402
    PluginHealthStatus,
    PluginLifecycleStatus,
)


class _FakeHTTPResponse:
    def __init__(self, body: str) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body.encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _build_provider() -> GeminiProvider:
    return GeminiProvider(
        plugin_id="gemini-provider",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        rollback_conditions=["provider_timeout_spike"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )


def test_missing_api_key_blocks_provider_startup() -> None:
    with patch.dict("os.environ", {}, clear=True):
        provider = _build_provider()
        with patch(
            "plugins.provider_tools.urllib_request.urlopen",
            side_effect=TimeoutError("socket stalled"),
        ):
            with pytest.raises(ModelProviderConfigError) as exc_info:
                provider.generate_json(
                    "return health",
                    {"topic": "missing-key"},
                    ModelProviderCallerContext(
                        source_module="ThinkLoop",
                        invocation_phase="phase_2_frame",
                        question_driver_refs=["我是谁"],
                    ),
                )

    assert "GEMINI_API_KEY" in str(exc_info.value) or "Missing API key" in str(exc_info.value)


def test_remote_failure_classification_timeout_and_rate_limit() -> None:
    provider = _build_provider()

    with patch.dict("os.environ", {"GEMINI_API_KEY": "secret"}, clear=False):
        with patch(
            "plugins.provider_tools.urllib_request.urlopen",
            side_effect=TimeoutError("socket stalled"),
        ):
            with pytest.raises(ModelProviderTimeoutError) as timeout_exc:
                provider.generate_json(
                    "return health",
                    {"topic": "timeout"},
                    ModelProviderCallerContext(
                        source_module="ThinkLoop",
                        invocation_phase="phase_2_frame",
                        question_driver_refs=["我是谁"],
                    ),
                )

    assert "timeout" in str(timeout_exc.value).lower()

    rate_limit_error = urllib_error.HTTPError(
        url="https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
        code=429,
        msg="quota exceeded",
        hdrs=None,
        fp=io.BytesIO(b'{"error":"quota exceeded"}'),
    )
    with patch.dict("os.environ", {"GEMINI_API_KEY": "secret"}, clear=False):
        with patch(
            "plugins.provider_tools.urllib_request.urlopen",
            side_effect=rate_limit_error,
        ):
            with pytest.raises(ModelProviderRateLimitError) as rate_exc:
                provider.generate_json(
                    "return health",
                    {"topic": "quota"},
                    ModelProviderCallerContext(
                        source_module="ThinkLoop",
                        invocation_phase="phase_2_frame",
                        question_driver_refs=["我是谁"],
                    ),
                )

    assert "rate" in str(rate_exc.value).lower()

    with patch.dict("os.environ", {"GEMINI_API_KEY": "secret"}, clear=False):
        with patch(
            "plugins.provider_tools.urllib_request.urlopen",
            side_effect=rate_limit_error,
        ):
            assert provider.health_probe() == PluginHealthStatus.DEGRADED


def test_invalid_json_raises_parse_error_without_fake_fallback() -> None:
    provider = _build_provider()

    invalid_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "{not-valid-json"},
                    ]
                }
            }
        ]
    }
    with patch.dict("os.environ", {"GEMINI_API_KEY": "secret"}, clear=False):
        with patch(
            "plugins.provider_tools.urllib_request.urlopen",
            return_value=_FakeHTTPResponse(json.dumps(invalid_payload)),
        ):
            with pytest.raises(ModelProviderParseError) as exc_info:
                provider.generate_json(
                    "return a decision object",
                    {"goal": "test"},
                    ModelProviderCallerContext(
                        source_module="ThinkLoop",
                        invocation_phase="phase_8_synthesize_decision",
                        question_driver_refs=["我现在应该做什么"],
                    ),
                )

    assert "json" in str(exc_info.value).lower()

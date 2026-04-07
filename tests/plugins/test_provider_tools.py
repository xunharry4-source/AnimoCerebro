from __future__ import annotations

import json
from pathlib import Path
from urllib import error as urllib_error
from unittest.mock import patch

import pytest

from plugins.provider_tools import (
    ChatGPTTool,
    ClaudeTool,
    ConfigError,
    GeminiTool,
    OpenAICompatibleGatewayTool,
    OpenAITool,
    ProviderToolConfig,
    load_provider_tool_configs,
    RemoteServiceError,
    RemoteTimeoutError,
    ResponseParseError,
    ToolInvocationRequest,
    build_default_provider_tools,
    resolve_provider_api_key,
)


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _build_config(provider_name: str, api_base: str, api_key_env: str, default_model: str) -> ProviderToolConfig:
    return ProviderToolConfig(
        provider_name=provider_name,
        api_base=api_base,
        api_key_env=api_key_env,
        default_model=default_model,
    )


def test_openai_tool_calls_responses_endpoint() -> None:
    tool = OpenAITool(
        _build_config("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-test")
    )
    invocation = ToolInvocationRequest(model="gpt-test", prompt="hello")

    with patch.dict("os.environ", {"OPENAI_API_KEY": "secret"}, clear=False):
        with patch("plugins.provider_tools.urllib_request.urlopen") as mocked_urlopen:
            mocked_urlopen.return_value = _FakeHTTPResponse(
                {
                    "output": [
                        {"content": [{"type": "output_text", "text": "openai-ok"}]}
                    ]
                }
            )
            response = tool.call(invocation)

    request_obj = mocked_urlopen.call_args.args[0]
    assert request_obj.full_url == "https://api.openai.com/v1/responses"
    assert request_obj.headers["Authorization"] == "Bearer secret"
    assert response.output_text == "openai-ok"


def test_gemini_tool_builds_generate_content_request() -> None:
    tool = GeminiTool(
        _build_config(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta",
            "GEMINI_API_KEY",
            "gemini-test",
        )
    )
    invocation = ToolInvocationRequest(model="ignored", prompt="hello", system_prompt="system")

    with patch.dict("os.environ", {"GEMINI_API_KEY": "gemini-secret"}, clear=False):
        with patch("plugins.provider_tools.urllib_request.urlopen") as mocked_urlopen:
            mocked_urlopen.return_value = _FakeHTTPResponse(
                {"candidates": [{"content": {"parts": [{"text": "gemini-ok"}]}}]}
            )
            response = tool.call(invocation)

    request_obj = mocked_urlopen.call_args.args[0]
    assert request_obj.full_url.endswith("/models/gemini-test:generateContent")
    assert request_obj.headers["X-goog-api-key"] == "gemini-secret"
    assert response.output_text == "gemini-ok"


def test_claude_tool_requires_api_key() -> None:
    tool = ClaudeTool(
        _build_config("claude", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", "claude-test")
    )

    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ConfigError) as exc_info:
            tool.call(ToolInvocationRequest(model="claude-test", prompt="hello"))

    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


def test_remote_timeout_is_classified_and_does_not_fallback() -> None:
    tool = OpenAITool(
        _build_config("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-test")
    )

    with patch.dict("os.environ", {"OPENAI_API_KEY": "secret"}, clear=False):
        with patch(
            "plugins.provider_tools.urllib_request.urlopen",
            side_effect=TimeoutError("network timed out"),
        ):
            with pytest.raises(RemoteTimeoutError) as exc_info:
                tool.call(ToolInvocationRequest(model="gpt-test", prompt="hello"))

    assert "openai" in str(exc_info.value)


def test_remote_500_is_classified_and_does_not_fallback() -> None:
    tool = GeminiTool(
        _build_config(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta",
            "GEMINI_API_KEY",
            "gemini-test",
        )
    )
    http_error = urllib_error.HTTPError(
        url="https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent",
        code=500,
        msg="internal error",
        hdrs=None,
        fp=None,
    )

    with patch.dict("os.environ", {"GEMINI_API_KEY": "secret"}, clear=False):
        with patch("plugins.provider_tools.urllib_request.urlopen", side_effect=http_error):
            with pytest.raises(RemoteServiceError) as exc_info:
                tool.call(ToolInvocationRequest(model="ignored", prompt="hello"))

    assert "status 500" in str(exc_info.value)


def test_invalid_json_raises_parse_error_and_never_falls_back_to_fake_ai() -> None:
    tool = OpenAITool(
        _build_config("openai", "https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-test")
    )

    class _InvalidJSONResponse:
        def read(self) -> bytes:
            return b'{"not-valid-json"'

        def __enter__(self) -> "_InvalidJSONResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    with patch.dict("os.environ", {"OPENAI_API_KEY": "secret"}, clear=False):
        with patch(
            "plugins.provider_tools.urllib_request.urlopen",
            return_value=_InvalidJSONResponse(),
        ):
            with pytest.raises(ResponseParseError) as exc_info:
                tool.call(ToolInvocationRequest(model="gpt-test", prompt="hello"))

    assert "invalid JSON" in str(exc_info.value)


def test_chatgpt_tool_uses_openai_transport_shape() -> None:
    tools = build_default_provider_tools()
    tool = tools["chatgpt"]
    assert isinstance(tool, ChatGPTTool)
    assert isinstance(tool, OpenAITool)


def test_openai_compatible_gateway_reads_local_gateway_config() -> None:
    tools = build_default_provider_tools()
    compat_tool = tools["openai_compat"]

    assert isinstance(compat_tool, OpenAICompatibleGatewayTool)
    assert compat_tool.config.api_base == "http://localhost:8317/v1"
    assert compat_tool.config.api_key_env == "your-api-key-1"
    assert compat_tool.config.default_model == "gemini-3-flash(auto)"


def test_load_provider_tool_configs_from_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "provider_tools.yml"
    config_file.write_text(
        "\n".join(
            [
                "providers:",
                "  openai_compat:",
                "    provider_name: openai_compat",
                "    api_base: http://localhost:9000/v1",
                "    api_key_env: LOCAL_GATEWAY_KEY",
                "    default_model: gemini-local(auto)",
                "    timeout_seconds: 15",
            ]
        ),
        encoding="utf-8",
    )

    configs = load_provider_tool_configs(config_file)

    assert configs["openai_compat"].api_base == "http://localhost:9000/v1"
    assert configs["openai_compat"].api_key_env == "LOCAL_GATEWAY_KEY"
    assert configs["openai_compat"].default_model == "gemini-local(auto)"
    assert configs["openai_compat"].timeout_seconds == 15


def test_literal_api_key_value_can_be_used_without_environment_variable() -> None:
    config = _build_config("openai_compat", "http://localhost:8317/v1", "your-api-key-1", "gemini-local(auto)")

    with patch.dict("os.environ", {}, clear=True):
        assert resolve_provider_api_key(config) == "your-api-key-1"

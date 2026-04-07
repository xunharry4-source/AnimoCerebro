from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure SRC_ROOT is in path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from zentex.core.model_provider_spec import ModelProviderCallerContext
from zentex.llm.gateway import LLMGateway
from plugins.provider_tools import (
    BaseProviderTool,
    ToolInvocationResponse,
    build_default_provider_tools,
)


def test_general_tool_methods_can_be_built() -> None:
    """Test that build_default_provider_tools returns the standard tool map."""
    tools = build_default_provider_tools()
    assert isinstance(tools, dict)
    assert "openai_compat" in tools
    assert "gemini" in tools
    assert "claude" in tools


def test_llm_gateway_invocation_with_mock_tool() -> None:
    """
    Test the general LLM gateway entrypoint using a mock provider tool.
    This verifies the high-level orchestration logic.
    """
    mock_tool = MagicMock(spec=BaseProviderTool)
    # Configure mock tool's nested config (required by LLMGateway)
    mock_tool.config = MagicMock()
    mock_tool.config.default_model = "mock-model"
    
    # Mock response
    mock_tool.call.return_value = ToolInvocationResponse(
        provider="mock",
        model="mock-model",
        output_text='{"status": "ok", "reasoning": "test"}',
        raw_response={},
    )

    gateway = LLMGateway(tools={"mock_provider": mock_tool})
    
    ctx = ModelProviderCallerContext(
        source_module="test_connectivity",
        invocation_phase="unit_test",
    )

    result = gateway.invoke_generate_json(
        prompt="Check connectivity",
        context={"ping": "pong"},
        caller_context=ctx,
        provider_key="mock_provider",
    )

    assert result.output == {"status": "ok", "reasoning": "test"}
    assert result.provider_key == "mock_provider"
    assert result.model == "mock-model"
    assert mock_tool.call.called


@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
def test_live_gateway_connectivity_gemini() -> None:
    """
    Real-world test case calling the general gateway with live Gemini provider.
    This fulfills the requirement of testing if the LLM can actually connect.
    """
    gateway = LLMGateway() # uses default tools including gemini
    
    ctx = ModelProviderCallerContext(
        source_module="test_connectivity",
        invocation_phase="integration_test",
    )

    # Use a very simple prompt to minimize token cost
    try:
        result = gateway.invoke_generate_json(
            prompt="Respond with exactly: {\"status\": \"connected\"}",
            context={},
            caller_context=ctx,
            provider_key="gemini",
        )
        assert result.output == {"status": "connected"}
        print("\n[SUCCESS] LLM Gateway is connected to Gemini API.")
    except Exception as exc:
        pytest.fail(f"LLM Gateway failed to connect to Gemini: {exc}")

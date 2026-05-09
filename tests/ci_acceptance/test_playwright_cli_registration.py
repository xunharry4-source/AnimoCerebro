from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any
from uuid import uuid4

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.cli.adapter import create_cli_adapter_plugin
from zentex.cli.service import PLAYWRIGHT_CLI_TOOL_CONFIG, CliIntegrationService, get_service
from zentex.tools.documentation_learning import ToolDocumentationLearningService
from zentex.web_console.routers.cli import router as cli_router


class _TestTranscriptStore:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def write_entry(self, **payload: Any) -> None:
        self.entries.append(payload)

    def list_entries(self, **_: Any) -> list[dict[str, Any]]:
        return list(self.entries)


class _StrictPlaywrightLearningLLM:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        context = kwargs.get("context")
        if not isinstance(context, dict):
            raise AssertionError("LLM context must be a JSON object")
        assert context.get("tool_type") == "cli"
        assert context.get("tool_name") == "playwright-cli"
        assert context.get("command_executable") == "npx"
        assert context.get("command_args") == ["--no-install", "playwright-cli"]
        assert context.get("help_doc_url") == "https://github.com/microsoft/playwright-cli"
        assert context.get("help_output") and "Usage:" in context["help_output"]
        assert context.get("version_output", "").strip()
        self.calls.append(kwargs)
        return {
            "usage_summary": "Playwright CLI automates browser actions from shell commands.",
            "supported_commands": ["open", "goto", "click", "screenshot", "show"],
            "supported_tools": [],
            "argument_schema": {"type": "array", "items": {"type": "string"}},
            "examples": [{"command": ["npx", "--no-install", "playwright-cli", "--help"]}],
            "side_effects": ["May launch browser sessions and write screenshots, traces, or storage state."],
            "auth_requirements": [],
            "risk_notes": ["Execution-domain browser automation tool."],
            "task_routing_hints": ["browser automation", "screenshots", "web UI testing"],
        }


class _StrictGenericCliLearningLLM:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        context = kwargs.get("context")
        if not isinstance(context, dict):
            raise AssertionError("LLM context must be a JSON object")
        assert context.get("tool_type") == "cli"
        assert context.get("tool_name", "").startswith("generic-pip-cli-")
        assert context.get("command_executable") == sys.executable
        assert context.get("command_args") == ["-m", "pip"]
        assert context.get("help_doc_url") == "https://pip.pypa.io/en/stable/cli/pip/"
        assert context.get("help_output") and "Usage:" in context["help_output"]
        self.calls.append(kwargs)
        return {
            "usage_summary": "Generic pip CLI exposes Python package management commands through argv.",
            "supported_commands": ["install", "download", "list", "show", "check"],
            "supported_tools": [],
            "argument_schema": {"type": "array", "items": {"type": "string"}},
            "examples": [{"command": [sys.executable, "-m", "pip", "list"]}],
            "side_effects": ["Some pip commands can install, remove, or modify Python packages."],
            "auth_requirements": [],
            "risk_notes": ["Package management CLI; mutating subcommands require explicit task-center dispatch."],
            "task_routing_hints": ["python package management", "pip package inspection"],
        }


def _playwright_cli_available() -> bool:
    if shutil.which("npx") is None:
        return False
    try:
        completed = subprocess.run(
            ["npx", "--no-install", "playwright-cli", "--version"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return False
    return completed.returncode == 0


def _build_app(llm: Any | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(cli_router, prefix="/api/web")
    transcript_store = _TestTranscriptStore()
    learning_service = ToolDocumentationLearningService(llm_service=llm) if llm is not None else None
    app.state.cli_service = CliIntegrationService(
        adapter=create_cli_adapter_plugin(transcript_store=transcript_store),
        transcript_store=transcript_store,
        documentation_learning_service=learning_service,
    )
    return app


def test_playwright_cli_registers_through_real_web_api() -> None:
    if not _playwright_cli_available():
        pytest.skip("playwright-cli is not installed locally; test avoids npm network install")

    llm = _StrictPlaywrightLearningLLM()
    app = _build_app(llm)

    with live_http_server(app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/cli-tools/register",
            json=PLAYWRIGHT_CLI_TOOL_CONFIG.model_dump(mode="json"),
            timeout=30,
        )
        assert response.status_code == 200
        playwright = response.json()

        tools = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert tools.status_code == 200
        matching_tools = [tool for tool in tools.json() if tool["command_name"] == "playwright-cli"]
        assert len(matching_tools) == 1
        assert matching_tools[0]["status"] == "active"

        duplicate = requests.post(
            f"{base_url}/api/web/cli-tools/register",
            json=PLAYWRIGHT_CLI_TOOL_CONFIG.model_dump(mode="json"),
            timeout=30,
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["command_name"] == "playwright-cli"
        assert duplicate.json()["status"] == "active"
        tools_after_duplicate = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert tools_after_duplicate.status_code == 200
        assert [tool["command_name"] for tool in tools_after_duplicate.json()].count("playwright-cli") == 1

        profile = requests.get(f"{base_url}/api/web/cli-tools/playwright-cli/usage-profile", timeout=10)
        assert profile.status_code == 200
        profile_payload = profile.json()
        assert profile_payload["source_type"] == "cli"
        assert profile_payload["learning_status"] == "learned"
        assert profile_payload["usage_summary"] == "Playwright CLI automates browser actions from shell commands."
        assert {"open", "goto", "click", "screenshot", "show"}.issubset(profile_payload["supported_commands"])
        assert profile_payload["argument_schema"] == {"type": "array", "items": {"type": "string"}}
        assert "https://github.com/microsoft/playwright-cli" in profile_payload["source_refs"]
        assert "browser automation" in profile_payload["task_routing_hints"]
        assert any("browser sessions" in item for item in profile_payload["side_effects"])
        assert any("Execution-domain" in item for item in profile_payload["risk_notes"])
        rendered_profile = str(profile_payload).lower()
        assert "authorization:" not in rendered_profile
        assert "cookie:" not in rendered_profile
        assert "token=" not in rendered_profile

        health = requests.get(f"{base_url}/api/web/cli-tools/playwright-cli/health", timeout=20)
        assert health.status_code == 200
        assert health.json()["healthy"] is True

        test_call = requests.post(
            f"{base_url}/api/web/cli-tools/playwright-cli/test-call",
            json={"arguments": ["--version"], "timeout_seconds": 20},
            timeout=30,
        )
        assert test_call.status_code == 200
        call_payload = test_call.json()
        assert call_payload["status"] == "success"
        assert call_payload["exit_code"] == 0
        assert call_payload["stdout"].strip()

        delete_response = requests.delete(f"{base_url}/api/web/cli-tools/playwright-cli", timeout=10)
        assert delete_response.status_code == 200
        assert delete_response.json() == {"success": True, "tool_name": "playwright-cli"}
        tools_after_delete = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert tools_after_delete.status_code == 200
        assert all(tool["command_name"] != "playwright-cli" for tool in tools_after_delete.json())
        assert requests.get(f"{base_url}/api/web/cli-tools/playwright-cli/detail", timeout=10).status_code == 404
        assert requests.get(f"{base_url}/api/web/cli-tools/playwright-cli/health", timeout=10).status_code == 404
        assert requests.get(f"{base_url}/api/web/cli-tools/playwright-cli/usage-profile", timeout=10).status_code == 404

    assert playwright["command_name"] == "playwright-cli"
    assert playwright["mapped_domain"] == "execution"
    assert playwright["execution_domain"] == "cli"
    assert playwright["read_only"] is False
    assert playwright["mutates_state"] is True
    assert playwright["requires_cloud_audit"] is True
    assert len(llm.calls) == 1


def test_playwright_cli_registered_by_web_api_can_be_invoked_by_cli_service() -> None:
    if not _playwright_cli_available():
        pytest.skip("playwright-cli is not installed locally; test avoids npm network install")

    app = _build_app(_StrictPlaywrightLearningLLM())

    with live_http_server(app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/cli-tools/register",
            json=PLAYWRIGHT_CLI_TOOL_CONFIG.model_dump(mode="json"),
            timeout=30,
        )
        assert response.status_code == 200
        profile = requests.get(f"{base_url}/api/web/cli-tools/playwright-cli/usage-profile", timeout=10)
        assert profile.status_code == 200

    call = app.state.cli_service.test_call(
        "playwright-cli",
        arguments=["--version"],
        timeout_seconds=20,
    )

    assert call.status == "ok"
    assert call.data.status == "success"
    assert call.data.exit_code == 0
    assert call.data.stdout.strip()


def test_execution_cli_registration_without_llm_fails_closed_through_real_web_api() -> None:
    app = _build_app(llm=None)
    payload = {
        "tool_name": "no-llm-exec",
        "command_executable": sys.executable,
        "command_args": ["-c", "print('usage output')"],
        "description": "Execution tool must not register without learned docs",
        "read_only_flag": False,
        "help_probe_args": [],
        "version_probe_args": [],
    }

    with live_http_server(app) as base_url:
        response = requests.post(f"{base_url}/api/web/cli-tools/register", json=payload, timeout=10)
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error_code"] == "INVALID_ARGUMENT"
        assert detail["error_stage"] == "cli_registration"
        assert "documentation learning failed" in detail["operator_message"]
        tools = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert tools.status_code == 200
        assert all(tool["command_name"] != "no-llm-exec" for tool in tools.json())
        assert requests.get(f"{base_url}/api/web/cli-tools/no-llm-exec/usage-profile", timeout=10).status_code == 404


def test_generic_cli_can_register_through_same_api_without_code_changes() -> None:
    tool_name = f"generic-pip-cli-{uuid4().hex[:8]}"
    llm = _StrictGenericCliLearningLLM()
    app = _build_app(llm)
    payload = {
        "tool_name": tool_name,
        "command_executable": sys.executable,
        "command_args": ["-m", "pip"],
        "description": "Generic Python pip CLI registered only through Web API payload.",
        "read_only_flag": False,
        "help_doc_url": "https://pip.pypa.io/en/stable/cli/pip/",
        "health_probe_args": ["--version"],
        "help_probe_args": ["--help"],
        "version_probe_args": ["--version"],
    }

    with live_http_server(app) as base_url:
        response = requests.post(f"{base_url}/api/web/cli-tools/register", json=payload, timeout=30)
        assert response.status_code == 200
        registered = response.json()
        assert registered["command_name"] == tool_name
        assert registered["help_doc_url"] == "https://pip.pypa.io/en/stable/cli/pip/"
        assert registered["mapped_domain"] == "execution"

        tools = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert tools.status_code == 200
        assert any(item["command_name"] == tool_name for item in tools.json())

        profile = requests.get(f"{base_url}/api/web/cli-tools/{tool_name}/usage-profile", timeout=10)
        assert profile.status_code == 200
        profile_payload = profile.json()
        assert profile_payload["usage_summary"].startswith("Generic pip CLI")
        assert {"install", "download", "list", "show", "check"}.issubset(profile_payload["supported_commands"])
        assert profile_payload["argument_schema"] == {"type": "array", "items": {"type": "string"}}
        assert "https://pip.pypa.io/en/stable/cli/pip/" in profile_payload["source_refs"]

        call = requests.post(
            f"{base_url}/api/web/cli-tools/{tool_name}/test-call",
            json={"arguments": ["--version"], "timeout_seconds": 20},
            timeout=30,
        )
        assert call.status_code == 200
        assert call.json()["status"] == "success"
        assert "pip" in call.json()["stdout"].lower()

        delete_response = requests.delete(f"{base_url}/api/web/cli-tools/{tool_name}", timeout=10)
        assert delete_response.status_code == 200
        assert delete_response.json()["success"] is True
        assert requests.get(f"{base_url}/api/web/cli-tools/{tool_name}/usage-profile", timeout=10).status_code == 404

    assert len(llm.calls) == 1


def test_playwright_cli_is_seeded_by_default_cli_service() -> None:
    if not _playwright_cli_available():
        pytest.skip("playwright-cli is not installed locally; test avoids npm network install")

    service = get_service(llm_service=_StrictPlaywrightLearningLLM())

    assert any(tool.command_name == "playwright-cli" for tool in service.list_tools())
    profile = service.get_usage_profile("playwright-cli")
    assert profile.argument_schema == {"type": "array", "items": {"type": "string"}}

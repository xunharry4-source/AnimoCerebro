from __future__ import annotations

import sys
from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


def _assert_read_only_cli_business_payload(payload: dict, tool_name: str) -> None:
    assert payload["command_name"] == tool_name
    assert payload["description"] == "Read-only Python inspection CLI"
    assert payload["cli_id"] == f"cli:{tool_name}"
    assert payload["feature_code"] == f"cli.{tool_name}"
    assert payload["mapped_domain"] == "cognitive"
    assert payload["status"] == "active"
    assert payload["read_only"] is True
    assert payload["side_effect_free"] is True
    assert payload["mutates_state"] is False
    assert payload["requires_cloud_audit"] is False
    assert payload["project_name"] == "feature45-real-test"
    assert "plugin_id" not in payload


def _assert_execution_cli_business_payload(payload: dict, tool_name: str) -> None:
    assert payload["command_name"] == tool_name
    assert payload["description"] == "Execution-domain Python CLI"
    assert payload["cli_id"] == f"cli:{tool_name}"
    assert payload["feature_code"] == f"cli.{tool_name}"
    assert payload["mapped_domain"] == "execution"
    assert payload["status"] == "active"
    assert payload["read_only"] is False
    assert payload["side_effect_free"] is False
    assert payload["mutates_state"] is True
    assert payload["requires_cloud_audit"] is True
    assert payload["execution_domain"] == "local_cli_write_guarded"
    assert "plugin_id" not in payload


def _assert_initial_cli_detail_metrics(payload: dict) -> None:
    credit_score = payload["credit_score"]
    assert 0.0 <= credit_score["total_score"] <= 100.0
    assert 0.0 <= credit_score["success_rate"] <= 1.0
    assert credit_score["total_executions"] == 0
    assert credit_score["successful_executions"] == 0
    assert credit_score["failed_executions"] == 0
    assert 0.0 <= credit_score["error_rate"] <= 1.0
    assert credit_score["usage_frequency"] in {"low", "medium", "high"}
    assert credit_score["credit_level"] in {"unrated", "excellent", "good", "fair", "poor"}
    assert isinstance(credit_score["last_updated"], str)
    assert payload["task_statistics"] == {
        "in_progress": 0,
        "pending": 0,
        "failed": 0,
        "completed": 0,
        "total": 0,
    }


def test_cli_asset_control_registers_queries_executes_and_audits_real_requests(acceptance_app: FastAPI) -> None:
    suffix = uuid4().hex[:8]
    read_only_tool = f"cli-readonly-{suffix}"
    execution_tool = f"cli-execution-{suffix}"
    transcript_before = len(acceptance_app.state.transcript_store.entries)

    with live_http_server(acceptance_app) as base_url:
        empty_adapters = requests.get(f"{base_url}/api/web/cli-adapters", timeout=10)
        assert empty_adapters.status_code == 200
        assert empty_adapters.json()["healthy"] is True
        baseline_adapter_payload = empty_adapters.json()
        baseline_total_tools = baseline_adapter_payload["total_tools"]
        baseline_cognitive_tools = baseline_adapter_payload["cognitive_tools"]
        baseline_execution_tools = baseline_adapter_payload["execution_tools"]

        read_only_register = requests.post(
            f"{base_url}/api/web/cli-tools/register",
            json={
                "tool_name": read_only_tool,
                "command_executable": sys.executable,
                "command_args": ["-c", "import sys; data=sys.stdin.read(); print('READONLY_OK:' + str(len(data)))"],
                "description": "Read-only Python inspection CLI",
                "read_only_flag": True,
                "project_name": "feature45-real-test",
            },
            timeout=10,
        )
        assert read_only_register.status_code == 200, read_only_register.text
        read_only_payload = read_only_register.json()
        _assert_read_only_cli_business_payload(read_only_payload, read_only_tool)

        execution_register = requests.post(
            f"{base_url}/api/web/cli-tools/register",
            json={
                "tool_name": execution_tool,
                "command_executable": sys.executable,
                "command_args": ["-c", "print('EXECUTION_DOMAIN_OK')"],
                "description": "Execution-domain Python CLI",
                "read_only_flag": False,
                "execution_domain": "local_cli_write_guarded",
            },
            timeout=10,
        )
        assert execution_register.status_code == 200, execution_register.text
        execution_payload = execution_register.json()
        _assert_execution_cli_business_payload(execution_payload, execution_tool)

        tools = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert tools.status_code == 200
        list_payload = tools.json()
        assert isinstance(list_payload, list)
        by_name = {item["command_name"]: item for item in list_payload}
        assert read_only_tool in by_name
        assert execution_tool in by_name
        _assert_read_only_cli_business_payload(by_name[read_only_tool], read_only_tool)
        _assert_execution_cli_business_payload(by_name[execution_tool], execution_tool)

        read_only_detail = requests.get(f"{base_url}/api/web/cli-tools/{read_only_tool}/detail", timeout=10)
        assert read_only_detail.status_code == 200
        read_only_detail_payload = read_only_detail.json()
        _assert_read_only_cli_business_payload(read_only_detail_payload, read_only_tool)
        _assert_initial_cli_detail_metrics(read_only_detail_payload)

        execution_detail = requests.get(f"{base_url}/api/web/cli-tools/{execution_tool}/detail", timeout=10)
        assert execution_detail.status_code == 200
        execution_detail_payload = execution_detail.json()
        _assert_execution_cli_business_payload(execution_detail_payload, execution_tool)
        _assert_initial_cli_detail_metrics(execution_detail_payload)

        duplicate_register = requests.post(
            f"{base_url}/api/web/cli-tools/register",
            json={
                "tool_name": read_only_tool,
                "command_executable": sys.executable,
                "command_args": ["-c", "print('duplicate must not register')"],
                "description": "Duplicate read-only Python inspection CLI",
                "read_only_flag": True,
            },
            timeout=10,
        )
        assert duplicate_register.status_code == 409, duplicate_register.text
        duplicate_detail = duplicate_register.json()["detail"]
        assert duplicate_detail == {
            "error_code": "STATE_CONFLICT",
            "error_stage": "cli_registration",
            "operator_message": (
                f"Failed to register CLI tool '{read_only_tool}': CLI tool '{read_only_tool}' is already registered"
            ),
            "message": (
                f"Failed to register CLI tool '{read_only_tool}': CLI tool '{read_only_tool}' is already registered"
            ),
        }
        tools_after_duplicate = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert tools_after_duplicate.status_code == 200
        duplicate_names = [item["command_name"] for item in tools_after_duplicate.json()]
        assert duplicate_names.count(read_only_tool) == 1
        assert duplicate_names.count(execution_tool) == 1

        adapters = requests.get(f"{base_url}/api/web/cli-adapters", timeout=10)
        assert adapters.status_code == 200
        adapter_payload = adapters.json()
        assert adapter_payload["total_tools"] == baseline_total_tools + 2
        assert adapter_payload["cognitive_tools"] == baseline_cognitive_tools + 1
        assert adapter_payload["execution_tools"] == baseline_execution_tools + 1
        assert adapter_payload["healthy"] is True
        adapter_tool_names = {item["command_name"] for item in adapter_payload["tools"]}
        assert {read_only_tool, execution_tool} <= adapter_tool_names

        health = requests.get(f"{base_url}/api/web/cli-tools/{read_only_tool}/health", timeout=10)
        assert health.status_code == 200
        assert health.json()["healthy"] is True
        assert health.json()["command_executable"] == sys.executable

        read_only_call = requests.post(
            f"{base_url}/api/web/cli-tools/{read_only_tool}/test-call",
            json={"stdin_input": "real request body", "timeout_seconds": 5},
            timeout=10,
        )
        assert read_only_call.status_code == 200, read_only_call.text
        read_only_result = read_only_call.json()
        assert read_only_result["status"] == "success"
        assert read_only_result["exit_code"] == 0
        assert "READONLY_OK:" in read_only_result["stdout"]
        assert read_only_result["trace_id"].startswith("cli-test:")

        execution_call = requests.post(
            f"{base_url}/api/web/cli-tools/{execution_tool}/test-call",
            json={"timeout_seconds": 5},
            timeout=10,
        )
        assert execution_call.status_code == 200, execution_call.text
        assert execution_call.json()["status"] == "success"
        assert "EXECUTION_DOMAIN_OK" in execution_call.json()["stdout"]

        history = requests.get(
            f"{base_url}/api/web/cli-tools/{read_only_tool}/execution-history",
            params={"limit": 10},
            timeout=10,
        )
        assert history.status_code == 200
        history_rows = history.json()
        assert history_rows
        assert history_rows[0]["tool_name"] == read_only_tool
        assert history_rows[0]["status"] == "success"
        assert "READONLY_OK:" in history_rows[0]["stdout"]

        disable = requests.post(f"{base_url}/api/web/cli-tools/{read_only_tool}/disable", timeout=10)
        assert disable.status_code == 200
        assert disable.json()["status"] == "stopped"
        stopped_call = requests.post(
            f"{base_url}/api/web/cli-tools/{read_only_tool}/test-call",
            json={"timeout_seconds": 5},
            timeout=10,
        )
        assert stopped_call.status_code == 200
        assert stopped_call.json()["status"] == "failed"
        assert "not active" in stopped_call.json()["stderr"]

        stopped_adapters = requests.get(f"{base_url}/api/web/cli-adapters", timeout=10)
        assert stopped_adapters.status_code == 200
        assert stopped_adapters.json()["healthy"] is False
        assert stopped_adapters.json()["stopped_tools"] == 1

        tools_after_disable = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert tools_after_disable.status_code == 200
        disabled_by_name = {item["command_name"]: item for item in tools_after_disable.json()}
        assert disabled_by_name[read_only_tool]["status"] == "stopped"
        assert disabled_by_name[execution_tool]["status"] == "active"

    assert len(acceptance_app.state.transcript_store.entries) >= transcript_before + 3
    audit_entries = [
        item
        for item in acceptance_app.state.transcript_store.entries
        if (item.get("payload") or {}).get("tool_name") in {read_only_tool, execution_tool}
    ]
    assert len(audit_entries) >= 3
    by_tool = {(item.get("payload") or {}).get("tool_name"): item.get("payload") or {} for item in audit_entries}
    assert by_tool[read_only_tool]["mapped_domain"] in {"cognitive", "inactive"}
    assert by_tool[execution_tool]["mapped_domain"] == "execution"
    assert by_tool[execution_tool]["requires_cloud_audit"] is True


def test_cli_asset_control_rejects_mutating_read_only_masquerade_real_requests(acceptance_app: FastAPI) -> None:
    tool_name = f"cli-mutating-masquerade-{uuid4().hex[:8]}"

    with live_http_server(acceptance_app) as base_url:
        response = requests.post(
            f"{base_url}/api/web/cli-tools/register",
            json={
                "tool_name": tool_name,
                "command_executable": sys.executable,
                "command_args": ["-c", "from pathlib import Path; Path('must_not_exist').write_text('bad')"],
                "description": "Mutating command pretending to be read-only",
                "read_only_flag": True,
            },
            timeout=10,
        )
        assert response.status_code == 400
        assert "read-only CLI tools cannot register mutating executables" in response.text

        tools = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert tools.status_code == 200
        assert all(item["command_name"] != tool_name for item in tools.json())


def test_cli_feature63_execution_defense_closure_real_requests(acceptance_app: FastAPI, tmp_path) -> None:
    suffix = uuid4().hex[:8]
    read_only_tool = f"feature63-readonly-{suffix}"
    nonzero_tool = f"feature63-nonzero-{suffix}"
    timeout_tool = f"feature63-timeout-{suffix}"
    execution_tool = f"feature63-execution-{suffix}"
    missing_tool = f"feature63-missing-{suffix}"
    output_file = tmp_path / f"feature63-{suffix}.txt"
    nonzero_script = tmp_path / f"feature63-nonzero-{suffix}.py"
    timeout_script = tmp_path / f"feature63-timeout-{suffix}.py"
    execution_script = tmp_path / f"feature63-execution-{suffix}.py"
    nonzero_script.write_text(
        "import sys\n"
        "if '--version' in sys.argv:\n"
        "    print('feature63-nonzero-health')\n"
        "    raise SystemExit(0)\n"
        "print('FEATURE63_NONZERO', file=sys.stderr)\n"
        "raise SystemExit(7)\n",
        encoding="utf-8",
    )
    timeout_script.write_text(
        "import sys, time\n"
        "if '--version' in sys.argv:\n"
        "    print('feature63-timeout-health')\n"
        "    raise SystemExit(0)\n"
        "time.sleep(2)\n",
        encoding="utf-8",
    )
    execution_script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "if len(sys.argv) < 2 or sys.argv[1].startswith('-'):\n"
        "    print('feature63-execution-health')\n"
        "    raise SystemExit(0)\n"
        "target = Path(sys.argv[1])\n"
        "target.write_text('feature63-written', encoding='utf-8')\n"
        "print(target.read_text(encoding='utf-8'))\n",
        encoding="utf-8",
    )

    with live_http_server(acceptance_app) as base_url:
        missing = requests.post(
            f"{base_url}/api/web/cli-tools/register",
            json={
                "tool_name": missing_tool,
                "command_executable": str(tmp_path / "definitely-missing-cli"),
                "command_args": ["--version"],
                "description": "Missing CLI command for feature 63",
                "read_only_flag": True,
            },
            timeout=10,
        )
        assert missing.status_code == 400
        assert "health probe failed" in missing.text

        registrations = [
            {
                "tool_name": read_only_tool,
                "command_executable": sys.executable,
                "command_args": [
                    "-c",
                    "import sys; print('FEATURE63_READONLY'); print('FEATURE63_STDERR', file=sys.stderr)",
                ],
                "description": "Feature 63 read-only stderr signal tool",
                "read_only_flag": True,
                "env": {"ZENTEX_CLI_FEATURE63": "locked"},
            },
            {
                "tool_name": nonzero_tool,
                "command_executable": sys.executable,
                "command_args": [str(nonzero_script)],
                "description": "Feature 63 non-zero exit tool",
                "read_only_flag": True,
                "health_probe_args": ["--version"],
            },
            {
                "tool_name": timeout_tool,
                "command_executable": sys.executable,
                "command_args": [str(timeout_script)],
                "description": "Feature 63 timeout tool",
                "read_only_flag": True,
                "health_probe_args": ["--version"],
            },
            {
                "tool_name": execution_tool,
                "command_executable": sys.executable,
                "command_args": [str(execution_script)],
                "description": "Feature 63 real execution side-effect tool",
                "read_only_flag": False,
                "execution_domain": "feature63_local_cli_write_guarded",
                "health_probe_args": ["--version"],
                "help_probe_args": ["--version"],
            },
        ]
        for payload in registrations:
            response = requests.post(f"{base_url}/api/web/cli-tools/register", json=payload, timeout=10)
            assert response.status_code == 200, response.text

        tools = requests.get(f"{base_url}/api/web/cli-tools", timeout=10)
        assert tools.status_code == 200
        feature63_tools = {
            item["command_name"]: item
            for item in tools.json()
            if item["command_name"]
            in {read_only_tool, nonzero_tool, timeout_tool, execution_tool, missing_tool}
        }
        assert set(feature63_tools) == {read_only_tool, nonzero_tool, timeout_tool, execution_tool}
        assert feature63_tools[read_only_tool]["mapped_domain"] == "cognitive"
        assert feature63_tools[execution_tool]["mapped_domain"] == "execution"
        assert feature63_tools[execution_tool]["requires_cloud_audit"] is True

        dangerous_call = requests.post(
            f"{base_url}/api/web/cli-tools/{read_only_tool}/test-call",
            json={"arguments": ["safe", ";", "touch", "blocked"], "timeout_seconds": 5},
            timeout=10,
        )
        assert dangerous_call.status_code == 200, dangerous_call.text
        dangerous_payload = dangerous_call.json()
        assert dangerous_payload["status"] == "failed"
        assert dangerous_payload["exit_code"] == -2
        assert dangerous_payload["failure_category"] == "dangerous_argument"
        assert dangerous_payload["preflight_blocked"] is True
        assert dangerous_payload["stdout"] == ""
        assert "dangerous CLI argument pattern blocked" in dangerous_payload["stderr"]

        read_only_call = requests.post(
            f"{base_url}/api/web/cli-tools/{read_only_tool}/test-call",
            json={"timeout_seconds": 5},
            timeout=10,
        )
        assert read_only_call.status_code == 200, read_only_call.text
        read_only_payload = read_only_call.json()
        assert read_only_payload["status"] == "success"
        assert read_only_payload["exit_code"] == 0
        assert read_only_payload["failure_category"] is None
        assert "FEATURE63_READONLY" in read_only_payload["stdout"]
        assert "FEATURE63_STDERR" in read_only_payload["stderr"]
        assert read_only_payload["duration_ms"] >= 0

        nonzero_call = requests.post(
            f"{base_url}/api/web/cli-tools/{nonzero_tool}/test-call",
            json={"timeout_seconds": 5},
            timeout=10,
        )
        assert nonzero_call.status_code == 200, nonzero_call.text
        nonzero_payload = nonzero_call.json()
        assert nonzero_payload["status"] == "failed"
        assert nonzero_payload["exit_code"] == 7
        assert nonzero_payload["failure_category"] == "non_zero_exit"
        assert "FEATURE63_NONZERO" in nonzero_payload["stderr"]

        timeout_call = requests.post(
            f"{base_url}/api/web/cli-tools/{timeout_tool}/test-call",
            json={"timeout_seconds": 1},
            timeout=10,
        )
        assert timeout_call.status_code == 200, timeout_call.text
        timeout_payload = timeout_call.json()
        assert timeout_payload["status"] == "timeout"
        assert timeout_payload["failure_category"] == "timeout"
        assert timeout_payload["exit_code"] == -1
        assert "timed out" in timeout_payload["stderr"]

        execution_call = requests.post(
            f"{base_url}/api/web/cli-tools/{execution_tool}/test-call",
            json={"arguments": [str(output_file)], "timeout_seconds": 5},
            timeout=10,
        )
        assert execution_call.status_code == 200, execution_call.text
        execution_payload = execution_call.json()
        assert execution_payload["status"] == "success"
        assert execution_payload["exit_code"] == 0
        assert execution_payload["failure_category"] is None
        assert execution_payload["stdout"].strip() == "feature63-written"
        assert output_file.read_text(encoding="utf-8") == "feature63-written"

        history = requests.get(
            f"{base_url}/api/web/cli-tools/{read_only_tool}/execution-history",
            params={"limit": 20},
            timeout=10,
        )
        assert history.status_code == 200
        read_only_history = history.json()
        assert {row["status"] for row in read_only_history} >= {"success", "failed"}
        assert any(row["failure_category"] == "dangerous_argument" and row["preflight_blocked"] for row in read_only_history)
        assert any(row["status"] == "success" and "FEATURE63_READONLY" in row["stdout"] for row in read_only_history)

        diagnostics = requests.get(f"{base_url}/api/web/cli-tools/closure/diagnostics", timeout=10)
        assert diagnostics.status_code == 200, diagnostics.text
        diagnostic_payload = diagnostics.json()
        check_map = {item["name"]: item for item in diagnostic_payload["checks"]}
        assert check_map["command_existence_detection"]["passed"] is True
        assert check_map["version_probe_detection"]["passed"] is True
        assert check_map["parameter_schema_validation"]["passed"] is True
        assert check_map["read_only_authenticity_detection"]["passed"] is True
        assert check_map["dangerous_argument_blocking"]["passed"] is True
        assert check_map["audit_field_completeness"]["passed"] is True
        assert check_map["runtime_failure_classification"]["passed"] is True
        assert diagnostic_payload["metrics"]["registration_rejection_count"] >= 1
        assert diagnostic_payload["metrics"]["preflight_blocked_invocations"] >= 1
        assert diagnostic_payload["completion"]["integration_complete"] is True
        assert diagnostic_payload["completion"]["audit_complete"] is True
        assert diagnostic_payload["completion"]["defense_complete"] is True
        assert diagnostic_payload["completion"]["real_completion"] is True
        issue_codes = {item["code"] for item in diagnostic_payload["issues"]}
        assert {"stderr_pollution", "non_zero_exit", "timeout", "dangerous_argument"}.issubset(issue_codes)

        fault_matrix = requests.post(f"{base_url}/api/web/cli-tools/closure/fault-injection", timeout=10)
        assert fault_matrix.status_code == 200, fault_matrix.text
        fault_payload = fault_matrix.json()
        assert fault_payload["passed"] is True
        fault_cases = {item["name"]: item for item in fault_payload["cases"]}
        assert fault_cases["command_missing_detector_ran"]["passed"] is True
        assert fault_cases["non_zero_exit_classified"]["passed"] is True
        assert fault_cases["read_only_or_shell_injection_blocked"]["passed"] is True
        assert fault_cases["timeout_killed_and_audited"]["passed"] is True
        assert fault_cases["stderr_pollution_detected"]["passed"] is True
        assert fault_cases["audit_completeness_verified"]["passed"] is True

    audit_events = [
        item.get("payload") or {}
        for item in acceptance_app.state.transcript_store.entries
        if (item.get("payload") or {}).get("tool_name")
        in {read_only_tool, nonzero_tool, timeout_tool, execution_tool, missing_tool}
    ]
    assert any(item.get("failure_category") == "command_missing" and item.get("status") == "rejected" for item in audit_events)
    assert any(item.get("failure_category") == "dangerous_argument" and item.get("preflight_blocked") for item in audit_events)
    assert any(item.get("failure_category") == "non_zero_exit" and item.get("exit_code") == 7 for item in audit_events)
    assert any(item.get("failure_category") == "timeout" and item.get("status") == "timeout" for item in audit_events)

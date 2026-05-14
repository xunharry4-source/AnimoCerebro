from __future__ import annotations

import asyncio
from typing import Any, Dict

from zentex.tasks.execution.executor_profiles import validate_dispatch_against_profile


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


async def run_preflight(context: Dict[str, Any], contract: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    dispatch = context.get("dispatch") if isinstance(context.get("dispatch"), dict) else {}
    profile = context.get("profile") if isinstance(context.get("profile"), dict) else {}
    missing = validate_dispatch_against_profile(dispatch, _profile_obj(profile))
    if missing:
        return {
            "passed": False,
            "failure_type": "contract_gap",
            "failure_code": "EXECUTOR_DISPATCH_FIELDS_MISSING",
            "message": f"Executor dispatch is missing required fields: {', '.join(missing)}",
            "retryable": False,
            "evidence": {"missing_fields": missing},
        }

    executor_type = str(context.get("executor_type") or "").strip()
    if executor_type == "cli":
        return _preflight_cli(dispatch, runtime)
    if executor_type == "mcp":
        return _preflight_mcp(dispatch, runtime)
    if executor_type == "external_connector":
        return _preflight_external_connector(dispatch, runtime)
    if executor_type == "agent":
        return await _preflight_agent(dispatch, runtime)
    if executor_type == "internal_plugin":
        return _preflight_internal_plugin(dispatch, runtime)
    return {
        "passed": False,
        "failure_type": "contract_gap",
        "failure_code": "UNSUPPORTED_EXECUTOR_TYPE",
        "message": f"Unsupported executor type: {executor_type}",
        "retryable": False,
        "evidence": {},
    }


def _profile_obj(profile: Dict[str, Any]) -> Any:
    class _Profile:
        required_dispatch_fields = list(profile.get("required_dispatch_fields") or [])
    return _Profile()


def _service_missing(name: str) -> Dict[str, Any]:
    return {
        "passed": False,
        "failure_type": "resource_unavailable",
        "failure_code": f"{name.upper()}_SERVICE_MISSING",
        "message": f"{name} service is not available through its service.py boundary",
        "retryable": False,
        "evidence": {},
    }


def _preflight_cli(dispatch: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    service = runtime.get("cli_service")
    if service is None:
        return _service_missing("cli")
    try:
        health = service.get_tool_health(dispatch["tool_name"])
    except Exception as exc:
        return {
            "passed": False,
            "failure_type": "resource_unavailable",
            "failure_code": "CLI_NOT_FOUND",
            "message": str(exc),
            "retryable": False,
            "evidence": {},
        }
    passed = health.get("status") == "active" and health.get("healthy") is True
    return {
        "passed": passed,
        "failure_type": "" if passed else "resource_unavailable",
        "failure_code": "" if passed else "CLI_UNHEALTHY",
        "message": "" if passed else f"CLI tool is not active and healthy: {health}",
        "retryable": False,
        "evidence": {"health": dict(health)},
    }


def _preflight_mcp(dispatch: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    service = runtime.get("mcp_service")
    if service is None:
        return _service_missing("mcp")
    try:
        health = service.get_server_health(dispatch["server_id"])
    except Exception as exc:
        return {
            "passed": False,
            "failure_type": "resource_unavailable",
            "failure_code": "MCP_SERVER_UNAVAILABLE",
            "message": str(exc),
            "retryable": False,
            "evidence": {},
        }
    if health.get("status") != "online" or health.get("healthy") is not True:
        return {
            "passed": False,
            "failure_type": "resource_unavailable",
            "failure_code": "MCP_UNHEALTHY",
            "message": f"MCP server is not online and healthy: {health}",
            "retryable": False,
            "evidence": {"health": dict(health)},
        }
    return {"passed": True, "failure_type": "", "failure_code": "", "message": "", "retryable": False, "evidence": {"health": dict(health)}}


def _preflight_external_connector(dispatch: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    service = runtime.get("external_connector_service")
    if service is None:
        return _service_missing("external_connector")
    if str(dispatch.get("capability") or "").lower() in {"mongodb_ping", "ping", "health_check", "health"}:
        return {
            "passed": False,
            "failure_type": "contract_gap",
            "failure_code": "CONNECTOR_CAPABILITY_MISMATCH",
            "message": "Health/probe connector capability cannot satisfy a business execution task",
            "retryable": False,
            "evidence": {"capability": dispatch.get("capability")},
        }
    try:
        connector = service.get_connector(dispatch["connector_id"])
        report = service.health_check(dispatch["connector_id"])
    except Exception as exc:
        return {
            "passed": False,
            "failure_type": "resource_unavailable",
            "failure_code": "CONNECTOR_UNHEALTHY",
            "message": str(exc),
            "retryable": False,
            "evidence": {},
        }
    status = _enum_value(getattr(connector, "status", None))
    health_status = _enum_value(getattr(report, "health_status", None))
    capability_names = [str(getattr(item, "name", "") or "") for item in getattr(connector, "capabilities", []) or []]
    if dispatch["capability"] not in capability_names:
        return {
            "passed": False,
            "failure_type": "contract_gap",
            "failure_code": "CONNECTOR_CAPABILITY_NOT_FOUND",
            "message": f"Connector capability {dispatch['capability']} is not declared by connector registry",
            "retryable": False,
            "evidence": {"declared_capabilities": capability_names},
        }
    passed = status == "active" and health_status == "healthy"
    return {
        "passed": passed,
        "failure_type": "" if passed else "resource_unavailable",
        "failure_code": "" if passed else "CONNECTOR_UNHEALTHY",
        "message": "" if passed else f"External connector is not active and healthy: status={status}, health_status={health_status}",
        "retryable": False,
        "evidence": {"status": status, "health_status": health_status, "declared_capabilities": capability_names},
    }


async def _preflight_agent(dispatch: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    service = runtime.get("agent_service")
    if service is None:
        return _service_missing("agent")
    asset = getattr(getattr(service, "manager", None), "get_asset", lambda _agent_id: None)(dispatch["agent_id"])
    if asset is None:
        return {
            "passed": False,
            "failure_type": "resource_unavailable",
            "failure_code": "AGENT_NOT_FOUND",
            "message": f"Agent {dispatch['agent_id']} not found",
            "retryable": False,
            "evidence": {},
        }
    block_reason = getattr(service, "get_dispatch_block_reason", None)
    if callable(block_reason):
        maybe = block_reason(dispatch["agent_id"], cli_service=runtime.get("cli_service"), mcp_service=runtime.get("mcp_service"))
        reason = await maybe if asyncio.iscoroutine(maybe) else maybe
        if reason:
            return {
                "passed": False,
                "failure_type": "resource_unavailable",
                "failure_code": "AGENT_BLOCKED",
                "message": str(reason),
                "retryable": False,
                "evidence": {},
            }
    status = _enum_value(getattr(asset, "status", None))
    return {
        "passed": status == "active",
        "failure_type": "" if status == "active" else "resource_unavailable",
        "failure_code": "" if status == "active" else "AGENT_OFFLINE",
        "message": "" if status == "active" else f"Agent is not active: status={status}",
        "retryable": False,
        "evidence": {"status": status},
    }


def _preflight_internal_plugin(dispatch: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    if runtime.get("internal_executor") is None:
        return _service_missing("internal_plugin")
    if not str(dispatch.get("plugin_id") or "").strip():
        return {
            "passed": False,
            "failure_type": "contract_gap",
            "failure_code": "INTERNAL_PLUGIN_ID_MISSING",
            "message": "Internal plugin execution requires a concrete plugin_id",
            "retryable": False,
            "evidence": {},
        }
    return {"passed": True, "failure_type": "", "failure_code": "", "message": "", "retryable": False, "evidence": {"plugin_id": dispatch["plugin_id"]}}

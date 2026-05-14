from __future__ import annotations

from typing import Any, Dict, List


def _schema_type_matches(expected: str, value: Any) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected in {"integer", "number"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def resolve_parameters(context: Dict[str, Any], contract: Dict[str, Any]) -> Dict[str, Any]:
    dispatch = context.get("dispatch") if isinstance(context.get("dispatch"), dict) else {}
    profile = context.get("profile") if isinstance(context.get("profile"), dict) else {}
    parameter_field = str(profile.get("parameter_field") or "arguments")
    arguments = dispatch.get(parameter_field)
    if arguments is None:
        arguments = dispatch.get("arguments")
    if arguments is None:
        arguments = {}

    required = [str(item) for item in contract.get("required_parameters") or [] if str(item).strip()]
    missing: List[str] = []
    invalid: List[Dict[str, Any]] = []
    if isinstance(arguments, dict):
        for field_name in required:
            if arguments.get(field_name) in (None, "", [], {}):
                missing.append(field_name)
    elif required:
        missing.extend(required)

    schema = contract.get("parameter_schema") if isinstance(contract.get("parameter_schema"), dict) else {}
    schema_type = str(schema.get("type") or "").strip()
    if schema_type and not _schema_type_matches(schema_type, arguments):
        invalid.append({"field": parameter_field, "expected_type": schema_type, "actual_type": type(arguments).__name__})
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    if isinstance(arguments, dict):
        for field_name, field_schema in properties.items():
            if not isinstance(field_schema, dict) or field_name not in arguments:
                continue
            expected_type = str(field_schema.get("type") or "").strip()
            if expected_type and not _schema_type_matches(expected_type, arguments[field_name]):
                invalid.append(
                    {
                        "field": field_name,
                        "expected_type": expected_type,
                        "actual_type": type(arguments[field_name]).__name__,
                    }
                )

    if missing:
        return {
            "status": "parameter_gap",
            "arguments": arguments,
            "missing_parameters": missing,
            "invalid_parameters": invalid,
            "parameter_sources": {key: f"dispatch.{parameter_field}.{key}" for key in (arguments.keys() if isinstance(arguments, dict) else [])},
        }
    if invalid:
        return {
            "status": "invalid_parameters",
            "arguments": arguments,
            "missing_parameters": [],
            "invalid_parameters": invalid,
            "parameter_sources": {},
        }
    return {
        "status": "resolved",
        "arguments": arguments,
        "missing_parameters": [],
        "invalid_parameters": [],
        "parameter_sources": {key: f"dispatch.{parameter_field}.{key}" for key in (arguments.keys() if isinstance(arguments, dict) else [])},
    }

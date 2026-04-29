from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from plugins.sensory.environment_interpreter.environment_interpreter_plugin import (
    build_default_environment_interpreter_plugin,
)
from plugins.sensory.prompt_injection_sanitizer.prompt_injection_sanitizer_plugin import (
    build_default_prompt_injection_sanitizer_plugin,
)
from plugins.sensory.webhook_ingest.webhook_ingest_plugin import (
    build_default_webhook_ingest_plugin,
)
from zentex.plugins.service.query import QueryService


@dataclass(frozen=True)
class SensoryChainStageSpec:
    stage_id: str
    feature_code: str
    plugin_kind: str
    plugin_id: str
    method_name: str


@dataclass(frozen=True)
class SensoryChainExecutionReport:
    audit_status: str
    chain_order: tuple[str, ...]
    raw_signal: str
    raw_fingerprint: str
    sanitized_signal: Any
    environment_event: Any
    stage_plugin_ids: dict[str, str]


class SensoryChainAuditError(RuntimeError):
    def __init__(self, message: str, issues: list[str] | None = None) -> None:
        super().__init__(message)
        self.issues = list(issues or [])


REQUIRED_SENSORY_CHAIN: tuple[SensoryChainStageSpec, ...] = (
    SensoryChainStageSpec(
        stage_id="ingest",
        feature_code="sensory.ingest",
        plugin_kind="signal_ingest",
        plugin_id="sensory_webhook",
        method_name="ingest_signal",
    ),
    SensoryChainStageSpec(
        stage_id="sanitize",
        feature_code="sensory.sanitize",
        plugin_kind="signal_sanitize",
        plugin_id="sensory_injection_sanitizer",
        method_name="sanitize_signal",
    ),
    SensoryChainStageSpec(
        stage_id="interpret",
        feature_code="sensory.interpret",
        plugin_kind="signal_interpret",
        plugin_id="sensory_environment",
        method_name="interpret_signal",
    ),
)


def audit_sensory_chain_catalog(catalog_items: list[Any] | None = None) -> dict[str, Any]:
    catalog = catalog_items
    if catalog is None:
        catalog = QueryService(
            storage=None,
            plugin_instances={},
            plugin_specs={},
            execution_stats={},
        ).get_feature_catalog()

    by_feature = {str(item.feature_code): item for item in catalog}
    issues: list[str] = []
    checked: list[dict[str, Any]] = []
    for spec in REQUIRED_SENSORY_CHAIN:
        item = by_feature.get(spec.feature_code)
        if item is None:
            issues.append(f"missing_feature:{spec.feature_code}")
            continue
        if item.plugin_kind != spec.plugin_kind:
            issues.append(
                f"plugin_kind_mismatch:{spec.feature_code}:{item.plugin_kind}!={spec.plugin_kind}"
            )
        if bool(item.supports_multiple_plugins):
            issues.append(f"unexpected_multi_plugin:{spec.feature_code}")
        checked.append(
            {
                "stage_id": spec.stage_id,
                "feature_code": item.feature_code,
                "plugin_kind": item.plugin_kind,
                "supports_multiple_plugins": bool(item.supports_multiple_plugins),
            }
        )

    if issues:
        raise SensoryChainAuditError("Sensory chain catalog audit failed.", issues)

    return {
        "audit_status": "passed",
        "chain_order": [spec.feature_code for spec in REQUIRED_SENSORY_CHAIN],
        "checked_features": checked,
    }


def run_default_sensory_chain_e2e(payload: str) -> SensoryChainExecutionReport:
    ingest_plugin = build_default_webhook_ingest_plugin()
    ingest_plugin.payload = payload
    return execute_sensory_chain(
        ingest_plugin=ingest_plugin,
        sanitizer_plugin=build_default_prompt_injection_sanitizer_plugin(),
        interpreter_plugin=build_default_environment_interpreter_plugin(),
    )


def execute_sensory_chain(
    *,
    ingest_plugin: Any,
    sanitizer_plugin: Any,
    interpreter_plugin: Any,
) -> SensoryChainExecutionReport:
    plugins = {
        "ingest": ingest_plugin,
        "sanitize": sanitizer_plugin,
        "interpret": interpreter_plugin,
    }
    _validate_plugin_contracts(plugins)

    raw_signal = ingest_plugin.ingest_signal()
    if not isinstance(raw_signal, str) or not raw_signal.strip():
        raise SensoryChainAuditError(
            "Sensory ingest stage returned an invalid raw signal.",
            ["invalid_raw_signal:sensory.ingest"],
        )

    sanitized_signal = sanitizer_plugin.sanitize_signal(raw_signal)
    raw_fingerprint = hashlib.sha256(raw_signal.encode("utf-8")).hexdigest()
    if getattr(sanitized_signal, "raw_fingerprint", None) != raw_fingerprint:
        raise SensoryChainAuditError(
            "Sensory sanitize stage did not preserve the raw signal fingerprint.",
            ["fingerprint_mismatch:sensory.sanitize"],
        )
    if not str(getattr(sanitized_signal, "sanitized_text", "") or "").strip():
        raise SensoryChainAuditError(
            "Sensory sanitize stage returned empty sanitized text.",
            ["empty_sanitized_text:sensory.sanitize"],
        )

    environment_event = interpreter_plugin.interpret_signal(sanitized_signal)
    event_fingerprint = (
        getattr(environment_event, "structured_payload", {}) or {}
    ).get("fingerprint")
    if event_fingerprint != raw_fingerprint:
        raise SensoryChainAuditError(
            "Sensory interpret stage did not consume the sanitized signal fingerprint.",
            ["fingerprint_mismatch:sensory.interpret"],
        )

    sanitize_evidence = list(getattr(sanitized_signal, "redaction_evidence", []) or [])
    interpret_evidence = list(getattr(environment_event, "audit_evidence", []) or [])
    if interpret_evidence != sanitize_evidence:
        raise SensoryChainAuditError(
            "Sensory interpret stage did not carry sanitizer audit evidence.",
            ["audit_evidence_mismatch:sensory.interpret"],
        )

    return SensoryChainExecutionReport(
        audit_status="passed",
        chain_order=tuple(spec.feature_code for spec in REQUIRED_SENSORY_CHAIN),
        raw_signal=raw_signal,
        raw_fingerprint=raw_fingerprint,
        sanitized_signal=sanitized_signal,
        environment_event=environment_event,
        stage_plugin_ids={
            spec.stage_id: str(getattr(plugins[spec.stage_id], "plugin_id", ""))
            for spec in REQUIRED_SENSORY_CHAIN
        },
    )


def _validate_plugin_contracts(plugins: dict[str, Any]) -> None:
    issues: list[str] = []
    for spec in REQUIRED_SENSORY_CHAIN:
        plugin = plugins.get(spec.stage_id)
        if plugin is None:
            issues.append(f"missing_stage:{spec.feature_code}")
            continue
        feature_code = str(getattr(plugin, "feature_code", "") or "")
        plugin_id = str(getattr(plugin, "plugin_id", "") or "")
        if feature_code != spec.feature_code:
            issues.append(f"invalid_stage_feature:{spec.feature_code}:{feature_code}")
        if plugin_id != spec.plugin_id:
            issues.append(f"invalid_stage_plugin:{spec.feature_code}:{plugin_id}")
        if not callable(getattr(plugin, spec.method_name, None)):
            issues.append(f"missing_stage_method:{spec.feature_code}:{spec.method_name}")
    if issues:
        raise SensoryChainAuditError("Sensory chain plugin contract audit failed.", issues)

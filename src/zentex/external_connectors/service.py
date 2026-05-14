from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from uuid import uuid4

from zentex.external_connectors.file_apps import (
    edit_pptx_slide,
    export_pseudo_pdf,
    file_evidence,
    read_office_text,
    render_preview,
    require_file,
    update_xlsx_cell,
    write_docx_text,
    write_json_summary,
)
from zentex.external_connectors.models import (
    ConnectorCapability,
    ConnectorError,
    ConnectorHealthReport,
    ConnectorHealthStatus,
    ConnectorInvocationRecord,
    ConnectorProfileLevel,
    ConnectorRegistrationRequest,
    ConnectorRiskLevel,
    ConnectorStatus,
    ConnectorTestCallRequest,
    ConnectorType,
    ConnectorUpdateRequest,
    ConnectorVerificationMode,
    ExternalConnectorRecord,
    utc_now,
)
from zentex.common.storage_paths import get_storage_paths
from zentex.external_capabilities import ExternalCapabilityRegistryStore
from zentex.module_logs import get_module_log_service, record_module_log

logger = logging.getLogger(__name__)


DEFAULT_FILE_APP_CAPABILITIES = [
    ConnectorCapability(
        name="read_document",
        description="Read text from a real document file.",
        read_only=True,
        profile_level=ConnectorProfileLevel.VERIFIABLE,
        verification_mode=ConnectorVerificationMode.EVIDENCE,
    ),
    ConnectorCapability(
        name="edit_document",
        description="Edit a real Word document body.",
        read_only=False,
        side_effect_type="writes_file",
        risk_level="writes_file",
        profile_level=ConnectorProfileLevel.VERIFIABLE,
        verification_mode=ConnectorVerificationMode.EVIDENCE,
    ),
    ConnectorCapability(
        name="export_pdf",
        description="Export a real document to a PDF artifact.",
        read_only=False,
        side_effect_type="writes_file",
        risk_level="writes_file",
        profile_level=ConnectorProfileLevel.VERIFIABLE,
        verification_mode=ConnectorVerificationMode.EVIDENCE,
    ),
    ConnectorCapability(
        name="render_preview",
        description="Render a text preview artifact from a real document file.",
        read_only=False,
        side_effect_type="writes_file",
        risk_level="writes_file",
        profile_level=ConnectorProfileLevel.VERIFIABLE,
        verification_mode=ConnectorVerificationMode.EVIDENCE,
    ),
    ConnectorCapability(
        name="read_workbook",
        description="Read text from a real workbook file.",
        read_only=True,
        profile_level=ConnectorProfileLevel.VERIFIABLE,
        verification_mode=ConnectorVerificationMode.EVIDENCE,
    ),
    ConnectorCapability(
        name="update_sheet",
        description="Update a real workbook sheet.",
        read_only=False,
        side_effect_type="writes_file",
        risk_level="writes_file",
        profile_level=ConnectorProfileLevel.VERIFIABLE,
        verification_mode=ConnectorVerificationMode.EVIDENCE,
    ),
    ConnectorCapability(
        name="read_deck",
        description="Read text from a real presentation deck.",
        read_only=True,
        profile_level=ConnectorProfileLevel.VERIFIABLE,
        verification_mode=ConnectorVerificationMode.EVIDENCE,
    ),
    ConnectorCapability(
        name="edit_slide",
        description="Edit a real presentation slide.",
        read_only=False,
        side_effect_type="writes_file",
        risk_level="writes_file",
        profile_level=ConnectorProfileLevel.VERIFIABLE,
        verification_mode=ConnectorVerificationMode.EVIDENCE,
    ),
]


PROFILE_ORDER = {
    ConnectorProfileLevel.MINIMAL: 0,
    ConnectorProfileLevel.DESCRIBED: 1,
    ConnectorProfileLevel.VERIFIABLE: 2,
    ConnectorProfileLevel.GOVERNED: 3,
}


class ExternalConnectorService:
    def __init__(
        self,
        transcript_store: Any = None,
        registry_path: Path | str | None = None,
        registry_store: ExternalCapabilityRegistryStore | None = None,
    ) -> None:
        started = time.monotonic()
        self._connectors: dict[str, ExternalConnectorRecord] = {}
        self._history: dict[str, list[ConnectorInvocationRecord]] = {}
        self._transcript_store = transcript_store
        self._registry_path = Path(registry_path) if registry_path is not None else get_storage_paths().runtime_data_dir / "external_connectors.json"
        self._registry_store = registry_store or ExternalCapabilityRegistryStore()
        self._module_log_service = get_module_log_service()
        self._restore_connectors()
        logger.info(
            "[external-connectors] service initialized connectors=%d registry_path=%s elapsed=%.3fs",
            len(self._connectors),
            self._registry_path,
            time.monotonic() - started,
        )

    def attach_transcript_store(self, transcript_store: Any) -> None:
        self._transcript_store = transcript_store

    def attach_module_log_service(self, module_log_service: Any) -> None:
        self._module_log_service = module_log_service

    def register_connector(self, payload: ConnectorRegistrationRequest) -> ExternalConnectorRecord:
        if payload.connector_id in self._connectors:
            raise ConnectorError(
                error_code="CONNECTOR_DUPLICATE",
                error_stage="connector_registration",
                operator_message=f"connector already registered: {payload.connector_id}",
                recovery_hint="Use a unique connector_id or update the existing connector.",
                status_code=409,
            )
        manifest_metadata = self._manifest_metadata_for_payload(payload)
        capabilities = payload.capabilities
        if not capabilities and payload.connector_type == ConnectorType.FILE_APP:
            capabilities = DEFAULT_FILE_APP_CAPABILITIES
        if not capabilities and manifest_metadata:
            capabilities = manifest_metadata["capabilities"]
        profile_level = payload.profile_level
        if payload.connector_type == ConnectorType.FILE_APP and profile_level == ConnectorProfileLevel.MINIMAL:
            profile_level = ConnectorProfileLevel.VERIFIABLE
        if manifest_metadata and PROFILE_ORDER[manifest_metadata["profile_level"]] > PROFILE_ORDER[profile_level]:
            profile_level = manifest_metadata["profile_level"]
        record = ExternalConnectorRecord(
            connector_id=payload.connector_id,
            connector_type=payload.connector_type,
            target_app=payload.target_app,
            display_name=payload.display_name,
            description=payload.description,
            connection_config=payload.connection_config,
            auth_config=payload.auth_config,
            permission_scope=payload.permission_scope,
            capabilities=capabilities,
            profile_level=profile_level,
            runtime=payload.runtime or (manifest_metadata or {}).get("runtime", ""),
            version=payload.version or (manifest_metadata or {}).get("version", ""),
            manifest_path=payload.manifest_path or (manifest_metadata or {}).get("manifest_path"),
            manifest_hash=payload.manifest_hash or (manifest_metadata or {}).get("manifest_hash"),
            status=ConnectorStatus.ACTIVE,
        )
        self._connectors[record.connector_id] = record
        self._history.setdefault(record.connector_id, [])
        self._persist_connectors()
        self._registry_store.upsert_current(
            "external_connector",
            record.connector_id,
            record.model_dump(mode="json"),
            status=record.status.value,
            display_name=record.display_name,
            action="register",
        )
        return record

    def list_plugin_manifests(self) -> list[dict[str, Any]]:
        manifests: list[dict[str, Any]] = []
        for manifest_path in sorted(self._plugins_root().glob("*/manifest.json")):
            manifests.append(self._read_manifest_card(manifest_path))
        return manifests

    def register_from_manifest(
        self,
        *,
        manifest_path: str | None = None,
        connector_id: str | None = None,
        connector_id_override: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        connection_config: dict[str, Any] | None = None,
        permission_scope: dict[str, Any] | None = None,
    ) -> ExternalConnectorRecord:
        card = self._manifest_card_by_path_or_id(manifest_path=manifest_path, connector_id=connector_id)
        if not card["valid"]:
            raise ConnectorError(
                error_code="CONNECTOR_MANIFEST_INVALID",
                error_stage="manifest_validation",
                operator_message="external connector manifest is invalid: " + "; ".join(card["errors"]),
                recovery_hint="Fix the manifest knowledge card or register the connector manually as minimal.",
                status_code=422,
            )
        manifest = card["manifest"]
        entrypoint = str(manifest["entrypoint"])
        payload = ConnectorRegistrationRequest(
            connector_id=connector_id_override or str(manifest["connector_id"]),
            connector_type=manifest.get("connector_type") or ConnectorType.SDK_APP,
            target_app=str(manifest.get("target_app") or manifest["connector_id"]),
            display_name=display_name or str(manifest.get("name") or manifest["connector_id"]),
            description=description or str(manifest.get("description") or ""),
            connection_config={
                "plugin_path": str(Path(card["relative_dir"]) / entrypoint),
                **(connection_config or {}),
            },
            permission_scope=permission_scope or {},
            capabilities=card["capabilities"],
            profile_level=card["profile_level"],
            runtime=str(manifest.get("runtime") or ""),
            version=str(manifest.get("version") or ""),
            manifest_path=card["relative_path"],
            manifest_hash=card["manifest_hash"],
        )
        return self.register_connector(payload)

    def list_connectors(self) -> list[ExternalConnectorRecord]:
        started = time.monotonic()
        self._refresh_connectors_from_registry_store()
        records = sorted(self._connectors.values(), key=lambda item: item.created_at)
        logger.debug(
            "[external-connectors] list_connectors count=%d elapsed=%.3fs",
            len(records),
            time.monotonic() - started,
        )
        return records

    def get_external_connector_statistics(self) -> dict[str, Any]:
        records = self.list_connectors()
        status_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        total_capabilities = 0
        read_only_capabilities = 0
        mutating_capabilities = 0
        for record in records:
            status = record.status.value
            connector_type = record.connector_type.value
            status_counts[status] = status_counts.get(status, 0) + 1
            type_counts[connector_type] = type_counts.get(connector_type, 0) + 1
            for capability in record.capabilities:
                total_capabilities += 1
                if capability.read_only:
                    read_only_capabilities += 1
                else:
                    mutating_capabilities += 1
        return {
            "asset_type": "external_connector",
            "total_connectors": len(records),
            "active_connectors": status_counts.get("active", 0),
            "degraded_connectors": status_counts.get("degraded", 0),
            "revoked_connectors": status_counts.get("revoked", 0),
            "total_capabilities": total_capabilities,
            "read_only_capabilities": read_only_capabilities,
            "mutating_capabilities": mutating_capabilities,
            "status_counts": status_counts,
            "type_counts": type_counts,
        }

    def get_connector(self, connector_id: str) -> ExternalConnectorRecord:
        self._refresh_connectors_from_registry_store()
        try:
            return self._connectors[connector_id]
        except KeyError as exc:
            raise ConnectorError(
                error_code="CONNECTOR_NOT_FOUND",
                error_stage="connector_query",
                operator_message=f"connector not found: {connector_id}",
                recovery_hint="Query the connector list and retry with an existing connector_id.",
                status_code=404,
            ) from exc

    def update_connector(self, connector_id: str, payload: ConnectorUpdateRequest) -> ExternalConnectorRecord:
        current = self.get_connector(connector_id)
        updated = current.model_copy(
            update={
                key: value
                for key, value in {
                    "display_name": payload.display_name,
                    "description": payload.description,
                    "connection_config": payload.connection_config,
                    "auth_config": payload.auth_config,
                    "permission_scope": payload.permission_scope,
                    "capabilities": payload.capabilities,
                    "status": payload.status,
                    "profile_level": payload.profile_level,
                    "updated_at": utc_now(),
                }.items()
                if value is not None
            }
        )
        self._connectors[connector_id] = updated
        self._persist_connectors()
        self._registry_store.upsert_current(
            "external_connector",
            connector_id,
            updated.model_dump(mode="json"),
            status=updated.status.value,
            display_name=updated.display_name,
            action="update",
        )
        return updated

    def activate_connector(self, connector_id: str) -> ExternalConnectorRecord:
        updated = self.update_connector(
            connector_id,
            ConnectorUpdateRequest(status=ConnectorStatus.ACTIVE),
        )
        report = self.health_check(connector_id)
        if report.health_status != ConnectorHealthStatus.HEALTHY:
            self.update_connector(
                connector_id,
                ConnectorUpdateRequest(status=ConnectorStatus.DEGRADED),
            )
            raise ConnectorError(
                error_code="CONNECTOR_ACTIVATION_HEALTH_CHECK_FAILED",
                error_stage="connector_activation",
                operator_message=f"connector health check failed during activation: {connector_id}",
                recovery_hint="Fix the connector target, plugin path, or capability declaration and retry activation.",
                status_code=409,
            )
        return updated

    def disable_connector(self, connector_id: str) -> ExternalConnectorRecord:
        return self.update_connector(
            connector_id,
            ConnectorUpdateRequest(status=ConnectorStatus.REVOKED),
        )

    def delete_connector(self, connector_id: str) -> dict[str, Any]:
        existing = self.get_connector(connector_id)
        del self._connectors[connector_id]
        self._persist_connectors()
        self._registry_store.delete_current(
            "external_connector",
            connector_id,
            payload=existing.model_dump(mode="json"),
        )
        return {"deleted": True, "connector_id": connector_id}

    def _restore_connectors(self) -> None:
        started = time.monotonic()
        logger.info("[external-connectors] restore start registry_path=%s", self._registry_path)
        db_rows = self._registry_store.list_current("external_connector")
        logger.info(
            "[external-connectors] restore db rows=%d elapsed=%.3fs",
            len(db_rows),
            time.monotonic() - started,
        )
        if db_rows:
            payload = [row["payload"] for row in db_rows]
        elif self._registry_path.exists():
            file_started = time.monotonic()
            try:
                payload = json.loads(self._registry_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("Failed to read external connector registry from %s: %s", self._registry_path, exc)
                raise RuntimeError(f"failed to read external connector registry: {exc}") from exc
            logger.info(
                "[external-connectors] restore json registry bytes=%d elapsed=%.3fs",
                self._registry_path.stat().st_size,
                time.monotonic() - file_started,
            )
        else:
            logger.info(
                "[external-connectors] restore skipped no persisted registry elapsed=%.3fs",
                time.monotonic() - started,
            )
            return
        if not isinstance(payload, list):
            raise RuntimeError("persisted external connector registry must be a list")
        for item in payload:
            record = ExternalConnectorRecord.model_validate(item)
            self._connectors[record.connector_id] = record
            self._history.setdefault(record.connector_id, [])
            if not db_rows:
                self._registry_store.upsert_current(
                    "external_connector",
                    record.connector_id,
                    record.model_dump(mode="json"),
                    status=record.status.value,
                    display_name=record.display_name,
                    action="import_json_registry",
                )
        logger.info(
            "[external-connectors] restore complete connectors=%d elapsed=%.3fs",
            len(self._connectors),
            time.monotonic() - started,
        )

    def _refresh_connectors_from_registry_store(self) -> None:
        db_rows = self._registry_store.list_current("external_connector")
        if not db_rows:
            if self._connectors:
                self._connectors = {}
                self._history = {}
            return
        refreshed: dict[str, ExternalConnectorRecord] = {}
        for row in db_rows:
            record = ExternalConnectorRecord.model_validate(row["payload"])
            refreshed[record.connector_id] = record
        self._connectors = refreshed
        for connector_id in refreshed:
            self._history.setdefault(connector_id, [])
        for connector_id in list(self._history.keys()):
            if connector_id not in refreshed:
                self._history.pop(connector_id, None)

    def _persist_connectors(self) -> None:
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        records = sorted(self._connectors.values(), key=lambda item: item.connector_id)
        payload = [record.model_dump(mode="json") for record in records]
        self._registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def health_check(self, connector_id: str, *, trace_id: str | None = None) -> ConnectorHealthReport:
        trace = trace_id or f"connector-health-{uuid4().hex}"
        record = self.get_connector(connector_id)
        checks: list[dict[str, Any]] = [
            {"name": "status_active", "passed": record.status == ConnectorStatus.ACTIVE, "status": record.status.value},
            {"name": "capabilities_present", "passed": bool(record.capabilities), "count": len(record.capabilities)},
            {"name": "profile_level_known", "passed": bool(record.profile_level), "profile_level": record.profile_level.value},
        ]
        if record.connector_type == ConnectorType.FILE_APP:
            base_path = record.connection_config.get("base_path")
            if base_path:
                base = Path(str(base_path)).expanduser()
                checks.append({"name": "base_path_exists", "passed": base.exists(), "path": str(base)})
                checks.append({"name": "base_path_is_directory", "passed": base.is_dir(), "path": str(base)})
        if record.connector_type == ConnectorType.SDK_APP:
            plugin_path = record.connection_config.get("plugin_path")
            try:
                script = self._resolve_external_plugin_script(plugin_path)
                checks.append({"name": "plugin_script_exists", "passed": script.exists(), "path": str(script)})
                checks.append({"name": "plugin_script_in_plugins_dir", "passed": True, "path": str(script)})
            except ConnectorError as exc:
                checks.append(
                    {
                        "name": "plugin_script_in_plugins_dir",
                        "passed": False,
                        "error_code": exc.error_code,
                        "operator_message": exc.operator_message,
                    }
                )
        healthy = all(item["passed"] for item in checks)
        report = ConnectorHealthReport(
            connector_id=record.connector_id,
            target_app=record.target_app,
            health_status=ConnectorHealthStatus.HEALTHY if healthy else ConnectorHealthStatus.UNHEALTHY,
            checks=checks,
            trace_id=trace,
            error_code=None if healthy else "CONNECTOR_HEALTH_CHECK_FAILED",
            error_stage=None if healthy else "connector_health",
            operator_message=None if healthy else "one or more connector health checks failed",
        )
        return report

    def test_call(self, connector_id: str, payload: ConnectorTestCallRequest) -> ConnectorInvocationRecord:
        trace_id = payload.trace_id or f"connector-trace-{uuid4().hex}"
        record = self.get_connector(connector_id)
        self._assert_active(record)
        self._assert_capability(record, payload.capability)
        before: dict[str, Any] = {}
        try:
            result = self._execute(record, payload, before)
            capability = self._get_capability(record, payload.capability)
            evidence_status = self._validate_evidence_for_capability(record, capability, result)
            invocation = ConnectorInvocationRecord(
                connector_id=record.connector_id,
                target_app=record.target_app,
                capability=payload.capability,
                trace_id=trace_id,
                status="success",
                input_summary=self._summarize_input(payload.arguments),
                output_summary=result.get("output_summary", result),
                before_evidence=result.get("before_evidence", before),
                after_evidence=result.get("after_evidence", {}),
                evidence_refs=result.get("evidence_refs", []),
                profile_level=self._effective_profile_level(record, capability),
                risk_level=capability.risk_level,
                verification_mode=capability.verification_mode,
                evidence_validation_status=evidence_status,
            )
        except ConnectorError as exc:
            capability = self._get_capability_or_none(record, payload.capability)
            invocation = ConnectorInvocationRecord(
                connector_id=record.connector_id,
                target_app=record.target_app,
                capability=payload.capability,
                trace_id=trace_id,
                status="failed",
                input_summary=self._summarize_input(payload.arguments),
                before_evidence=before,
                error_code=exc.error_code,
                error_stage=exc.error_stage,
                operator_message=exc.operator_message,
                recovery_hint=exc.recovery_hint,
                profile_level=self._effective_profile_level(record, capability),
                risk_level=capability.risk_level if capability else ConnectorRiskLevel.READ_ONLY,
                verification_mode=capability.verification_mode if capability else ConnectorVerificationMode.NONE,
                evidence_validation_status="failed",
            )
            self._record_invocation(invocation)
            raise
        self._record_invocation(invocation)
        return invocation

    def history(self, connector_id: str) -> list[ConnectorInvocationRecord]:
        self.get_connector(connector_id)
        return list(self._history.get(connector_id, []))

    def _assert_active(self, record: ExternalConnectorRecord) -> None:
        if record.status != ConnectorStatus.ACTIVE:
            raise ConnectorError(
                error_code="CONNECTOR_NOT_ACTIVE",
                error_stage="connector_preflight",
                operator_message=f"connector is not active: {record.connector_id}",
                recovery_hint="Reactivate or replace the connector before invoking it.",
                status_code=409,
            )

    def _assert_capability(self, record: ExternalConnectorRecord, capability: str) -> None:
        if self._get_capability_or_none(record, capability) is None:
            raise ConnectorError(
                error_code="CONNECTOR_CAPABILITY_NOT_FOUND",
                error_stage="connector_preflight",
                operator_message=f"capability {capability!r} is not declared by connector {record.connector_id}",
                recovery_hint="Query connector detail and call one of its declared capabilities.",
                status_code=404,
            )

    @staticmethod
    def _get_capability_or_none(record: ExternalConnectorRecord, capability: str) -> ConnectorCapability | None:
        for item in record.capabilities:
            if item.name == capability:
                return item
        return None

    def _get_capability(self, record: ExternalConnectorRecord, capability: str) -> ConnectorCapability:
        found = self._get_capability_or_none(record, capability)
        if found is None:
            self._assert_capability(record, capability)
            raise AssertionError("unreachable")
        return found

    @staticmethod
    def _effective_profile_level(
        record: ExternalConnectorRecord,
        capability: ConnectorCapability | None,
    ) -> ConnectorProfileLevel:
        if capability is None:
            return record.profile_level
        return max(record.profile_level, capability.profile_level, key=lambda level: PROFILE_ORDER[level])

    def _validate_evidence_for_capability(
        self,
        record: ExternalConnectorRecord,
        capability: ConnectorCapability,
        result: dict[str, Any],
    ) -> str:
        profile_level = self._effective_profile_level(record, capability)
        requires_verified_evidence = (
            not capability.read_only
            and capability.risk_level != ConnectorRiskLevel.READ_ONLY
            and profile_level in {ConnectorProfileLevel.VERIFIABLE, ConnectorProfileLevel.GOVERNED}
        )
        if result.get("evidence_refs") and result.get("after_evidence"):
            return "present"
        if not requires_verified_evidence:
            return "not_required"
        raise ConnectorError(
            error_code="CONNECTOR_EVIDENCE_REQUIRED",
            error_stage="post_validation",
            operator_message=(
                f"capability {capability.name!r} is {profile_level.value} and mutates external state "
                "but did not return after_evidence and evidence_refs"
            ),
            recovery_hint="Return real post-call evidence before marking this capability as completed.",
            status_code=502,
        )

    def _execute(
        self,
        record: ExternalConnectorRecord,
        payload: ConnectorTestCallRequest,
        before: dict[str, Any],
    ) -> dict[str, Any]:
        if record.connector_type == ConnectorType.SDK_APP:
            return self._execute_sdk_app(record, payload)
        if record.connector_type != ConnectorType.FILE_APP:
            raise ConnectorError(
                error_code="CONNECTOR_TYPE_NOT_IMPLEMENTED",
                error_stage="connector_dispatch",
                operator_message=f"connector_type {record.connector_type.value} has no runtime adapter yet",
                recovery_hint="Use file_app connector in this release or implement the requested adapter.",
                status_code=501,
            )
        path = require_file(payload.arguments.get("path"))
        self._assert_path_scope(record, path)
        self._assert_file_capability_match(path, payload.capability)
        before.update(file_evidence(path))
        capability = payload.capability
        if capability in {"read_document", "read_workbook", "read_deck"}:
            text = read_office_text(path)
            return {
                "output_summary": {"text": text, "text_length": len(text), "source_path": str(path)},
                "before_evidence": before,
                "after_evidence": file_evidence(path),
                "evidence_refs": [{"type": "file", "path": str(path), "sha256": before.get("sha256")}],
            }
        if payload.dry_run:
            raise ConnectorError(
                error_code="CONNECTOR_DRY_RUN_UNSUPPORTED",
                error_stage="connector_dispatch",
                operator_message="dry_run is not supported for file_app mutation verification",
                recovery_hint="Call read-only capabilities for dry inspection or execute a real test call.",
                status_code=422,
            )
        if capability == "edit_document":
            result = write_docx_text(path, str(payload.arguments.get("content") or ""))
        elif capability == "update_sheet":
            result = update_xlsx_cell(path, str(payload.arguments.get("value") or ""))
        elif capability == "edit_slide":
            result = edit_pptx_slide(path, str(payload.arguments.get("content") or ""))
        elif capability == "export_pdf":
            export_result = export_pseudo_pdf(path, payload.arguments.get("output_path"))
            return {
                "output_summary": export_result,
                "before_evidence": before,
                "after_evidence": file_evidence(path),
                "evidence_refs": [
                    {"type": "file", "path": str(path), "sha256": before.get("sha256")},
                    {"type": "export", **export_result["output_evidence"]},
                ],
            }
        elif capability == "render_preview":
            preview_result = render_preview(path, payload.arguments.get("output_path"))
            return {
                "output_summary": preview_result,
                "before_evidence": before,
                "after_evidence": file_evidence(path),
                "evidence_refs": [
                    {"type": "file", "path": str(path), "sha256": before.get("sha256")},
                    {"type": "preview", **preview_result["preview_evidence"]},
                ],
            }
        elif capability == "export_summary":
            text = read_office_text(path)
            summary = {"source_path": str(path), "text_length": len(text), "text_preview": text[:500]}
            export_result = write_json_summary(path, payload.arguments.get("output_path"), summary)
            return {
                "output_summary": export_result,
                "before_evidence": before,
                "after_evidence": file_evidence(path),
                "evidence_refs": [{"type": "export", **export_result["output_evidence"]}],
            }
        else:
            raise ConnectorError(
                error_code="CONNECTOR_CAPABILITY_UNSUPPORTED",
                error_stage="connector_dispatch",
                operator_message=f"capability {capability!r} is declared but unsupported by file_app runtime",
                recovery_hint="Implement this capability adapter or call a supported file_app capability.",
                status_code=501,
            )
        return {
            "output_summary": {k: v for k, v in result.items() if k not in {"before", "after"}},
            "before_evidence": result["before"],
            "after_evidence": result["after"],
            "evidence_refs": [
                {"type": "file_before", "path": str(path), "sha256": result["before"].get("sha256")},
                {"type": "file_after", "path": str(path), "sha256": result["after"].get("sha256")},
            ],
        }

    def _execute_sdk_app(
        self,
        record: ExternalConnectorRecord,
        payload: ConnectorTestCallRequest,
    ) -> dict[str, Any]:
        script = self._resolve_external_plugin_script(record.connection_config.get("plugin_path"))
        timeout_seconds = int(record.connection_config.get("timeout_seconds") or 15)
        request_payload = {
            "capability": payload.capability,
            "arguments": payload.arguments,
            "trace_id": payload.trace_id,
            "connector_id": record.connector_id,
        }
        try:
            completed = subprocess.run(
                [sys.executable, str(script)],
                input=json.dumps(request_payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
                cwd=str(script.parent),
            )
        except subprocess.TimeoutExpired as exc:
            raise ConnectorError(
                error_code="CONNECTOR_SDK_TIMEOUT",
                error_stage="sdk_app_runtime",
                operator_message=f"external plugin timed out after {timeout_seconds}s: {script}",
                recovery_hint="Increase connection_config.timeout_seconds or fix the external plugin runtime.",
                status_code=504,
            ) from exc
        except OSError as exc:
            raise ConnectorError(
                error_code="CONNECTOR_SDK_PROCESS_FAILED",
                error_stage="sdk_app_runtime",
                operator_message=f"failed to start external plugin: {exc}",
                recovery_hint="Check plugin_path, Python runtime, and file permissions.",
                status_code=500,
            ) from exc

        try:
            parsed = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise ConnectorError(
                error_code="CONNECTOR_SDK_BAD_JSON",
                error_stage="sdk_app_runtime",
                operator_message=f"external plugin returned invalid JSON; stderr={completed.stderr.strip()}",
                recovery_hint="Fix the external plugin stdout contract to return a JSON object.",
                status_code=502,
            ) from exc

        if completed.returncode != 0 or parsed.get("status") == "failed":
            raise ConnectorError(
                error_code=str(parsed.get("error_code") or "CONNECTOR_SDK_FAILED"),
                error_stage=str(parsed.get("error_stage") or "sdk_app_runtime"),
                operator_message=str(parsed.get("operator_message") or completed.stderr.strip() or "external plugin failed"),
                recovery_hint=str(parsed.get("recovery_hint") or "Inspect the external plugin failure and retry."),
                status_code=502,
            )

        required = {"output_summary", "before_evidence", "after_evidence", "evidence_refs"}
        if not required <= set(parsed):
            raise ConnectorError(
                error_code="CONNECTOR_SDK_SCHEMA_MISMATCH",
                error_stage="sdk_app_runtime",
                operator_message=f"external plugin response missing required fields: {sorted(required - set(parsed))}",
                recovery_hint="Return output_summary, before_evidence, after_evidence, and evidence_refs.",
                status_code=502,
            )
        return {
            "output_summary": parsed["output_summary"],
            "before_evidence": parsed["before_evidence"],
            "after_evidence": parsed["after_evidence"],
            "evidence_refs": parsed["evidence_refs"],
        }

    def _manifest_metadata_for_payload(self, payload: ConnectorRegistrationRequest) -> dict[str, Any] | None:
        if payload.manifest_path:
            card = self._read_manifest_card(self._resolve_manifest_path(payload.manifest_path))
        elif payload.connector_type == ConnectorType.SDK_APP and payload.connection_config.get("plugin_path"):
            try:
                script = self._resolve_external_plugin_script(payload.connection_config.get("plugin_path"))
            except ConnectorError:
                return None
            manifest_path = script.parent / "manifest.json"
            if not manifest_path.exists():
                return None
            card = self._read_manifest_card(manifest_path)
        else:
            return None
        if not card["valid"]:
            return None
        return {
            "profile_level": card["profile_level"],
            "capabilities": card["capabilities"],
            "runtime": str(card["manifest"].get("runtime") or ""),
            "version": str(card["manifest"].get("version") or ""),
            "manifest_path": card["relative_path"],
            "manifest_hash": card["manifest_hash"],
        }

    @staticmethod
    def _plugins_root() -> Path:
        return Path(__file__).resolve().parents[3] / "plugins"

    @classmethod
    def _resolve_manifest_path(cls, manifest_path: str) -> Path:
        root = cls._plugins_root().resolve()
        path = Path(str(manifest_path)).expanduser()
        if not path.is_absolute():
            path = root / path
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ConnectorError(
                error_code="CONNECTOR_MANIFEST_PATH_FORBIDDEN",
                error_stage="manifest_validation",
                operator_message=f"manifest_path must stay under root plugins directory: {manifest_path}",
                recovery_hint="Use a manifest under plugins/<connector>/manifest.json.",
                status_code=403,
            ) from exc
        return resolved

    def _manifest_card_by_path_or_id(
        self,
        *,
        manifest_path: str | None,
        connector_id: str | None,
    ) -> dict[str, Any]:
        if manifest_path:
            return self._read_manifest_card(self._resolve_manifest_path(manifest_path))
        if connector_id:
            for card in self.list_plugin_manifests():
                manifest = card.get("manifest") if isinstance(card.get("manifest"), dict) else {}
                if manifest.get("connector_id") == connector_id:
                    return card
            raise ConnectorError(
                error_code="CONNECTOR_MANIFEST_NOT_FOUND",
                error_stage="manifest_query",
                operator_message=f"external connector manifest not found for connector_id={connector_id}",
                recovery_hint="Register manually as minimal or add plugins/<connector>/manifest.json.",
                status_code=404,
            )
        raise ConnectorError(
            error_code="CONNECTOR_MANIFEST_QUERY_REQUIRED",
            error_stage="manifest_query",
            operator_message="manifest_path or connector_id is required.",
            recovery_hint="Provide a manifest path or connector_id.",
            status_code=422,
        )

    def _read_manifest_card(self, manifest_path: Path) -> dict[str, Any]:
        root = self._plugins_root().resolve()
        resolved = manifest_path.resolve()
        errors: list[str] = []
        manifest: dict[str, Any] = {}
        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append("manifest path is outside plugins directory")
        if not resolved.exists():
            errors.append("manifest file does not exist")
        else:
            try:
                manifest = json.loads(resolved.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"manifest is not valid JSON: {exc}")
        for field in ("connector_id", "name", "runtime", "entrypoint", "capabilities"):
            if field not in manifest:
                errors.append(f"missing field: {field}")
        if "capabilities" in manifest and not isinstance(manifest.get("capabilities"), list):
            errors.append("capabilities must be a list")
        entrypoint = manifest.get("entrypoint")
        if entrypoint:
            try:
                self._resolve_external_plugin_script(str(resolved.parent.relative_to(root) / str(entrypoint)))
            except ConnectorError as exc:
                errors.append(exc.operator_message)
        capabilities: list[ConnectorCapability] = []
        if not errors:
            try:
                capabilities = self._manifest_capabilities(manifest)
            except Exception as exc:
                errors.append(f"capabilities are invalid: {exc}")
        profile_level = self._profile_level_from_manifest(manifest)
        relative_path = str(resolved.relative_to(root)) if root in resolved.parents or resolved == root else str(resolved)
        return {
            "valid": not errors,
            "errors": errors,
            "manifest": manifest,
            "relative_path": relative_path,
            "relative_dir": str(resolved.parent.relative_to(root)) if not errors else str(resolved.parent),
            "manifest_hash": hashlib.sha256(resolved.read_bytes()).hexdigest() if resolved.exists() else None,
            "profile_level": profile_level,
            "capabilities": capabilities,
        }

    @staticmethod
    def _profile_level_from_manifest(manifest: dict[str, Any]) -> ConnectorProfileLevel:
        raw = str(manifest.get("profile_level") or "minimal").strip().lower()
        try:
            return ConnectorProfileLevel(raw)
        except ValueError:
            return ConnectorProfileLevel.MINIMAL

    def _manifest_capabilities(self, manifest: dict[str, Any]) -> list[ConnectorCapability]:
        default_profile = self._profile_level_from_manifest(manifest)
        capabilities: list[ConnectorCapability] = []
        for raw in manifest.get("capabilities") or []:
            if isinstance(raw, str):
                capabilities.append(ConnectorCapability(name=raw, profile_level=default_profile))
                continue
            if not isinstance(raw, dict):
                raise ConnectorError(
                    error_code="CONNECTOR_MANIFEST_INVALID",
                    error_stage="manifest_validation",
                    operator_message="manifest capability entries must be strings or objects",
                    recovery_hint="Use capability names or capability knowledge objects.",
                    status_code=422,
                )
            data = dict(raw)
            data.setdefault("profile_level", default_profile.value)
            if "verification" in data and "verification_mode" not in data:
                data["verification_mode"] = data.pop("verification")
            capabilities.append(ConnectorCapability.model_validate(data))
        return capabilities

    @classmethod
    def _resolve_external_plugin_script(cls, plugin_path: Any) -> Path:
        if not plugin_path:
            raise ConnectorError(
                error_code="CONNECTOR_SDK_PLUGIN_PATH_MISSING",
                error_stage="sdk_app_preflight",
                operator_message="connection_config.plugin_path is required for sdk_app connectors.",
                recovery_hint="Set plugin_path to a connector script under the repository root plugins/ directory.",
                status_code=422,
            )
        root = cls._plugins_root().resolve()
        script = Path(str(plugin_path)).expanduser()
        if not script.is_absolute():
            script = root / script
        resolved = script.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ConnectorError(
                error_code="CONNECTOR_SDK_PLUGIN_PATH_FORBIDDEN",
                error_stage="sdk_app_preflight",
                operator_message=f"sdk_app plugin_path must stay under root plugins directory: {plugin_path}",
                recovery_hint="Move the external connector under plugins/ and register that path.",
                status_code=403,
            ) from exc
        if not resolved.exists() or not resolved.is_file():
            raise ConnectorError(
                error_code="CONNECTOR_SDK_PLUGIN_NOT_FOUND",
                error_stage="sdk_app_preflight",
                operator_message=f"external plugin script not found: {resolved}",
                recovery_hint="Check connection_config.plugin_path and plugin installation.",
                status_code=404,
            )
        return resolved

    def _assert_path_scope(self, record: ExternalConnectorRecord, path: Path) -> None:
        allowed_roots = record.permission_scope.get("allowed_roots") or []
        if not allowed_roots:
            return
        resolved_path = path.resolve()
        for root_value in allowed_roots:
            root = Path(str(root_value)).expanduser().resolve()
            try:
                resolved_path.relative_to(root)
                return
            except ValueError:
                continue
        raise ConnectorError(
            error_code="CONNECTOR_PERMISSION_DENIED",
            error_stage="connector_permission_scope",
            operator_message=f"target path is outside connector allowed_roots: {path}",
            recovery_hint="Use a file inside the connector permission_scope.allowed_roots.",
            status_code=403,
        )

    @staticmethod
    def _assert_file_capability_match(path: Path, capability: str) -> None:
        suffix = path.suffix.lower()
        expected: dict[str, set[str]] = {
            ".docx": {"read_document", "edit_document", "export_pdf", "render_preview"},
            ".xlsx": {"read_workbook", "update_sheet", "export_summary", "render_preview"},
            ".pptx": {"read_deck", "edit_slide", "export_pdf", "render_preview"},
        }
        allowed = expected.get(suffix)
        if allowed is None:
            raise ConnectorError(
                error_code="CONNECTOR_UNSUPPORTED_FILE_TYPE",
                error_stage="file_app_preflight",
                operator_message=f"unsupported file extension for file_app connector: {suffix or '<none>'}",
                recovery_hint="Use a supported docx, xlsx, or pptx file.",
                status_code=422,
            )
        if capability not in allowed:
            raise ConnectorError(
                error_code="CONNECTOR_SCHEMA_MISMATCH",
                error_stage="file_app_preflight",
                operator_message=f"capability {capability!r} does not match file type {suffix}",
                recovery_hint="Call a capability that matches the target file type.",
                status_code=422,
            )

    @staticmethod
    def _summarize_input(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            key: (
                "[REDACTED]"
                if any(token in key.lower() for token in ("token", "secret", "password", "key", "uri", "connection_string"))
                else value
            )
            for key, value in arguments.items()
        }

    def _record_invocation(self, invocation: ConnectorInvocationRecord) -> None:
        self._history.setdefault(invocation.connector_id, []).append(invocation)
        self._registry_store.append_runtime_log(
            "external_connector",
            invocation.connector_id,
            capability_name=invocation.capability,
            invocation_type="test_call",
            status=invocation.status,
            request={"input_summary": invocation.input_summary},
            response=invocation.model_dump(mode="json"),
            error_message=invocation.operator_message,
            trace_id=invocation.trace_id,
            started_at=invocation.created_at.isoformat(),
        )
        record_module_log(
            self._module_log_service,
            source_module="connector",
            module_label="外部连接器",
            action="runtime_invocation",
            action_label="能力调用成功" if invocation.status == "success" else "能力调用失败",
            object_id=invocation.connector_id,
            object_label=invocation.connector_id,
            before_status=None,
            after_status=invocation.status,
            reason="外部连接器运行时能力调用已记录，供模块日志页查询",
            details={
                "invocation_id": invocation.invocation_id,
                "trace_id": invocation.trace_id,
                "target_app": invocation.target_app,
                "capability": invocation.capability,
                "profile_level": invocation.profile_level.value,
                "risk_level": invocation.risk_level.value,
                "verification_mode": invocation.verification_mode.value,
                "evidence_validation_status": invocation.evidence_validation_status,
                "evidence_refs": invocation.evidence_refs,
                "error_code": invocation.error_code,
                "error_stage": invocation.error_stage,
                "operator_message": invocation.operator_message,
                "recovery_hint": invocation.recovery_hint,
            },
            operator_id="task-worker",
            status=invocation.status,
            source="zentex.external_connectors.service",
        )
        transcript_store = self._transcript_store
        if transcript_store is None or not callable(getattr(transcript_store, "write_entry", None)):
            return
        transcript_store.write_entry(
            session_id="external-connectors",
            turn_id=invocation.invocation_id,
            entry_type="connector_audit_event",
            payload=invocation.model_dump(mode="json"),
            source="external_connectors.service",
            trace_id=invocation.trace_id,
        )


_SERVICE: ExternalConnectorService | None = None


def resolve_service(candidate: Any = None) -> ExternalConnectorService:
    global _SERVICE
    if candidate is not None and callable(getattr(candidate, "list_connectors", None)):
        _SERVICE = candidate
        return candidate
    return get_service()


def get_service() -> ExternalConnectorService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = ExternalConnectorService()
    return _SERVICE

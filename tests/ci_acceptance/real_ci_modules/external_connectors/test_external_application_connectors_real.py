from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import socket
import subprocess
import time
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


def _write_minimal_docx(path: Path, text: str) -> None:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types></Types>')
        archive.writestr("word/document.xml", document_xml)


def _write_minimal_xlsx(path: Path, text: str) -> None:
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>{text}</t></is></c></row></sheetData>'
        "</worksheet>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types></Types>')
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def _write_minimal_pptx(path: Path, text: str) -> None:
    slide_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f"<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types></Types>')
        archive.writestr("ppt/slides/slide1.xml", slide_xml)


def _read_docx_xml(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read("word/document.xml").decode("utf-8")


def _read_zip_member(path: Path, member: str) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read(member).decode("utf-8")


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _real_mongodb_container() -> Iterator[str]:
    port = _free_tcp_port()
    name = f"zentex-real-mongo-{uuid4().hex[:10]}"
    run = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{port}:27017",
            "mongo:7",
        ],
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if run.returncode != 0:
        pytest.fail(f"real MongoDB docker container failed to start: {run.stderr or run.stdout}")

    deadline = time.time() + 45
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.5)
    else:
        subprocess.run(["docker", "logs", name], text=True, capture_output=True, timeout=10, check=False)
        subprocess.run(["docker", "stop", name], text=True, capture_output=True, timeout=20, check=False)
        pytest.fail("real MongoDB docker container did not open its TCP port in time")

    try:
        yield f"mongodb://127.0.0.1:{port}/"
    finally:
        subprocess.run(["docker", "stop", name], text=True, capture_output=True, timeout=30, check=False)


def test_feature70_external_application_connector_real_api_file_office_flow(
    acceptance_app: FastAPI,
    tmp_path: Path,
) -> None:
    suffix = uuid4().hex[:8]
    connector_id = f"office-word-{suffix}"
    docx_path = tmp_path / "real_source.docx"
    xlsx_path = tmp_path / "real_sheet.xlsx"
    pptx_path = tmp_path / "real_deck.pptx"
    pdf_path = tmp_path / "real_export.pdf"
    preview_path = tmp_path / "real_preview.txt"
    forbidden_path = tmp_path.parent / f"outside-{suffix}.docx"
    _write_minimal_docx(docx_path, "Original Zentex connector text")
    _write_minimal_xlsx(xlsx_path, "Original Sheet Value")
    _write_minimal_pptx(pptx_path, "Original Slide Value")
    _write_minimal_docx(forbidden_path, "Forbidden path text")
    before_audit_count = len(acceptance_app.state.transcript_store.entries)

    with live_http_server(acceptance_app) as base_url:
        initial_list = requests.get(f"{base_url}/api/web/external-connectors", timeout=10)
        assert initial_list.status_code == 200
        assert all(item["connector_id"] != connector_id for item in initial_list.json())

        register_payload = {
            "connector_id": connector_id,
            "connector_type": "file_app",
            "target_app": "office.word",
            "display_name": "Word Connector Real Test",
            "description": "Reads, edits, and exports real docx files.",
            "connection_config": {"base_path": str(tmp_path)},
            "auth_config": {},
            "permission_scope": {"allowed_roots": [str(tmp_path)]},
            "capabilities": [],
        }
        registered = requests.post(
            f"{base_url}/api/web/external-connectors",
            json=register_payload,
            timeout=10,
        )
        assert registered.status_code == 200, registered.text
        registered_payload = registered.json()
        assert registered_payload["connector_id"] == connector_id
        assert registered_payload["connector_type"] == "file_app"
        assert registered_payload["target_app"] == "office.word"
        assert registered_payload["status"] == "active"
        assert registered_payload["profile_level"] == "verifiable"
        capability_names = {item["name"] for item in registered_payload["capabilities"]}
        assert {"read_document", "edit_document", "export_pdf", "render_preview", "read_workbook", "update_sheet", "read_deck", "edit_slide"} <= capability_names
        assert all(item["profile_level"] == "verifiable" for item in registered_payload["capabilities"])

        listed_after_register = requests.get(f"{base_url}/api/web/external-connectors", timeout=10)
        assert listed_after_register.status_code == 200
        assert any(item["connector_id"] == connector_id for item in listed_after_register.json())
        listed_row = next(item for item in listed_after_register.json() if item["connector_id"] == connector_id)
        assert listed_row["connector_id"] == connector_id
        assert listed_row["connector_type"] == "file_app"
        assert listed_row["target_app"] == "office.word"
        assert listed_row["display_name"] == "Word Connector Real Test"
        assert listed_row["description"] == "Reads, edits, and exports real docx files."
        assert listed_row["status"] == "active"
        assert listed_row["profile_level"] == "verifiable"
        assert listed_row["connection_config"]["base_path"] == str(tmp_path)
        assert listed_row["permission_scope"]["allowed_roots"] == [str(tmp_path)]
        listed_capabilities = {item["name"]: item for item in listed_row["capabilities"]}
        assert {"read_document", "edit_document", "export_pdf", "render_preview", "read_workbook", "update_sheet", "read_deck", "edit_slide"} <= set(listed_capabilities)
        assert listed_capabilities["edit_document"]["read_only"] is False
        assert listed_capabilities["edit_document"]["risk_level"] == "writes_file"
        assert listed_capabilities["edit_document"]["verification_mode"] == "evidence"

        duplicate = requests.post(
            f"{base_url}/api/web/external-connectors",
            json=register_payload,
            timeout=10,
        )
        assert duplicate.status_code == 409
        duplicate_detail = duplicate.json()["detail"]
        assert duplicate_detail["error_code"] == "CONNECTOR_DUPLICATE"
        assert duplicate_detail["error_stage"] == "connector_registration"
        assert duplicate_detail["operator_message"].startswith("connector already registered")

        detail = requests.get(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
        assert detail.status_code == 200
        detail_payload = detail.json()
        assert detail_payload["display_name"] == "Word Connector Real Test"
        assert detail_payload["connection_config"]["base_path"] == str(tmp_path)

        health = requests.get(f"{base_url}/api/web/external-connectors/{connector_id}/health", timeout=10)
        assert health.status_code == 200
        health_payload = health.json()
        assert health_payload["health_status"] == "healthy"
        checks = {item["name"]: item for item in health_payload["checks"]}
        assert checks["status_active"]["passed"] is True
        assert checks["capabilities_present"]["passed"] is True
        assert checks["base_path_exists"]["passed"] is True
        assert checks["base_path_is_directory"]["passed"] is True
        assert health_payload["trace_id"].startswith("connector-health-")

        read_response = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "read_document",
                "arguments": {"path": str(docx_path)},
                "trace_id": f"feature70-read-{suffix}",
            },
            timeout=10,
        )
        assert read_response.status_code == 200, read_response.text
        read_payload = read_response.json()
        assert read_payload["status"] == "success"
        assert read_payload["trace_id"] == f"feature70-read-{suffix}"
        assert read_payload["connector_id"] == connector_id
        assert read_payload["target_app"] == "office.word"
        assert read_payload["capability"] == "read_document"
        assert "Original Zentex connector text" in read_payload["output_summary"]["text"]
        assert read_payload["before_evidence"]["exists"] is True
        assert read_payload["after_evidence"]["sha256"] == read_payload["before_evidence"]["sha256"]
        assert read_payload["evidence_refs"][0]["type"] == "file"

        edit_response = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "edit_document",
                "arguments": {"path": str(docx_path), "content": "Updated Zentex connector text"},
                "trace_id": f"feature70-edit-{suffix}",
            },
            timeout=10,
        )
        assert edit_response.status_code == 200, edit_response.text
        edit_payload = edit_response.json()
        assert edit_payload["status"] == "success"
        assert edit_payload["capability"] == "edit_document"
        assert edit_payload["before_evidence"]["sha256"] != edit_payload["after_evidence"]["sha256"]
        assert "Updated Zentex connector text" in _read_docx_xml(docx_path)

        preview_response = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "render_preview",
                "arguments": {"path": str(docx_path), "output_path": str(preview_path)},
                "trace_id": f"feature70-preview-{suffix}",
            },
            timeout=10,
        )
        assert preview_response.status_code == 200, preview_response.text
        preview_payload = preview_response.json()
        assert preview_payload["status"] == "success"
        assert preview_path.exists()
        assert "Updated Zentex connector text" in preview_path.read_text(encoding="utf-8")
        preview_refs = {item["type"]: item for item in preview_payload["evidence_refs"]}
        assert preview_refs["preview"]["exists"] is True
        assert preview_refs["preview"]["sha256"]

        reread_response = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "read_document",
                "arguments": {"path": str(docx_path)},
                "trace_id": f"feature70-reread-{suffix}",
            },
            timeout=10,
        )
        assert reread_response.status_code == 200
        assert "Updated Zentex connector text" in reread_response.json()["output_summary"]["text"]

        export_response = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "export_pdf",
                "arguments": {"path": str(docx_path), "output_path": str(pdf_path)},
                "trace_id": f"feature70-export-{suffix}",
            },
            timeout=10,
        )
        assert export_response.status_code == 200, export_response.text
        export_payload = export_response.json()
        assert export_payload["status"] == "success"
        assert pdf_path.exists()
        assert pdf_path.read_bytes().startswith(b"%PDF-1.4")
        assert b"startxref" in pdf_path.read_bytes()
        export_refs = {item["type"]: item for item in export_payload["evidence_refs"]}
        assert export_refs["export"]["exists"] is True
        assert export_refs["export"]["sha256"]

        workbook_read = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "read_workbook",
                "arguments": {"path": str(xlsx_path)},
                "trace_id": f"feature70-xlsx-read-{suffix}",
            },
            timeout=10,
        )
        assert workbook_read.status_code == 200, workbook_read.text
        assert "Original Sheet Value" in workbook_read.json()["output_summary"]["text"]

        workbook_update = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "update_sheet",
                "arguments": {"path": str(xlsx_path), "value": "Updated Sheet Value"},
                "trace_id": f"feature70-xlsx-update-{suffix}",
            },
            timeout=10,
        )
        assert workbook_update.status_code == 200, workbook_update.text
        assert workbook_update.json()["before_evidence"]["sha256"] != workbook_update.json()["after_evidence"]["sha256"]
        assert "Updated Sheet Value" in _read_zip_member(xlsx_path, "xl/worksheets/sheet1.xml")

        deck_read = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "read_deck",
                "arguments": {"path": str(pptx_path)},
                "trace_id": f"feature70-pptx-read-{suffix}",
            },
            timeout=10,
        )
        assert deck_read.status_code == 200, deck_read.text
        assert "Original Slide Value" in deck_read.json()["output_summary"]["text"]

        deck_edit = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "edit_slide",
                "arguments": {"path": str(pptx_path), "content": "Updated Slide Value"},
                "trace_id": f"feature70-pptx-edit-{suffix}",
            },
            timeout=10,
        )
        assert deck_edit.status_code == 200, deck_edit.text
        assert deck_edit.json()["before_evidence"]["sha256"] != deck_edit.json()["after_evidence"]["sha256"]
        assert "Updated Slide Value" in _read_zip_member(pptx_path, "ppt/slides/slide1.xml")

        mismatch_response = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "edit_document",
                "arguments": {"path": str(xlsx_path), "content": "Wrong capability"},
                "trace_id": f"feature70-mismatch-{suffix}",
            },
            timeout=10,
        )
        assert mismatch_response.status_code == 422
        mismatch_detail = mismatch_response.json()["detail"]
        assert mismatch_detail["error_code"] == "CONNECTOR_SCHEMA_MISMATCH"
        assert mismatch_detail["error_stage"] == "file_app_preflight"
        assert "does not match file type" in mismatch_detail["operator_message"]

        permission_response = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "read_document",
                "arguments": {"path": str(forbidden_path)},
                "trace_id": f"feature70-permission-{suffix}",
            },
            timeout=10,
        )
        assert permission_response.status_code == 403
        permission_detail = permission_response.json()["detail"]
        assert permission_detail["error_code"] == "CONNECTOR_PERMISSION_DENIED"
        assert permission_detail["error_stage"] == "connector_permission_scope"
        assert "allowed_roots" in permission_detail["recovery_hint"]

        unsupported_payload = dict(register_payload)
        unsupported_payload["connector_id"] = f"api-connector-{suffix}"
        unsupported_payload["connector_type"] = "api_app"
        unsupported_payload["target_app"] = "example.api"
        unsupported_payload["display_name"] = "API Connector Unsupported Runtime"
        unsupported_payload["profile_level"] = "minimal"
        unsupported_payload["capabilities"] = [
            {
                "name": "create_ticket",
                "description": "Create ticket through remote API",
                "read_only": False,
                "side_effect_type": "mutates_remote",
                "risk_level": "mutates_remote",
                "requires_confirmation": False,
                "evidence_required": True,
            }
        ]
        unsupported_register = requests.post(
            f"{base_url}/api/web/external-connectors",
            json=unsupported_payload,
            timeout=10,
        )
        assert unsupported_register.status_code == 200, unsupported_register.text
        unsupported_call = requests.post(
            f"{base_url}/api/web/external-connectors/{unsupported_payload['connector_id']}/test-call",
            json={
                "capability": "create_ticket",
                "arguments": {"title": "real unsupported adapter check"},
                "trace_id": f"feature70-unsupported-{suffix}",
            },
            timeout=10,
        )
        assert unsupported_call.status_code == 501
        unsupported_detail = unsupported_call.json()["detail"]
        assert unsupported_detail["error_code"] == "CONNECTOR_TYPE_NOT_IMPLEMENTED"
        assert unsupported_detail["error_stage"] == "connector_dispatch"
        assert "no runtime adapter yet" in unsupported_detail["operator_message"]

        missing_response = requests.post(
            f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
            json={
                "capability": "read_document",
                "arguments": {"path": str(tmp_path / "missing.docx")},
                "trace_id": f"feature70-missing-{suffix}",
            },
            timeout=10,
        )
        assert missing_response.status_code == 404
        missing_detail = missing_response.json()["detail"]
        assert missing_detail["error_code"] == "CONNECTOR_FILE_NOT_FOUND"
        assert missing_detail["error_stage"] == "file_app_preflight"
        assert "operator_message" in missing_detail
        assert "recovery_hint" in missing_detail

        history = requests.get(f"{base_url}/api/web/external-connectors/{connector_id}/history", timeout=10)
        assert history.status_code == 200
        history_payload = history.json()
        assert len(history_payload) == 12
        by_trace = {item["trace_id"]: item for item in history_payload}
        assert by_trace[f"feature70-edit-{suffix}"]["status"] == "success"
        assert by_trace[f"feature70-export-{suffix}"]["evidence_refs"][1]["type"] == "export"
        assert by_trace[f"feature70-preview-{suffix}"]["evidence_refs"][1]["type"] == "preview"
        assert by_trace[f"feature70-xlsx-update-{suffix}"]["status"] == "success"
        assert by_trace[f"feature70-pptx-edit-{suffix}"]["status"] == "success"
        assert by_trace[f"feature70-mismatch-{suffix}"]["status"] == "failed"
        assert by_trace[f"feature70-mismatch-{suffix}"]["error_code"] == "CONNECTOR_SCHEMA_MISMATCH"
        assert by_trace[f"feature70-permission-{suffix}"]["status"] == "failed"
        assert by_trace[f"feature70-permission-{suffix}"]["error_code"] == "CONNECTOR_PERMISSION_DENIED"
        assert by_trace[f"feature70-missing-{suffix}"]["status"] == "failed"
        assert by_trace[f"feature70-missing-{suffix}"]["error_code"] == "CONNECTOR_FILE_NOT_FOUND"

        unsupported_history = requests.get(
            f"{base_url}/api/web/external-connectors/{unsupported_payload['connector_id']}/history",
            timeout=10,
        )
        assert unsupported_history.status_code == 200
        unsupported_history_payload = unsupported_history.json()
        assert len(unsupported_history_payload) == 1
        assert unsupported_history_payload[0]["trace_id"] == f"feature70-unsupported-{suffix}"
        assert unsupported_history_payload[0]["status"] == "failed"
        assert unsupported_history_payload[0]["error_code"] == "CONNECTOR_TYPE_NOT_IMPLEMENTED"

        update_response = requests.put(
            f"{base_url}/api/web/external-connectors/{connector_id}",
            json={"display_name": "Word Connector Renamed"},
            timeout=10,
        )
        assert update_response.status_code == 200, update_response.text
        assert update_response.json()["display_name"] == "Word Connector Renamed"
        detail_after_update = requests.get(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
        assert detail_after_update.status_code == 200
        assert detail_after_update.json()["display_name"] == "Word Connector Renamed"

        delete_response = requests.delete(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
        assert delete_response.status_code == 200
        assert delete_response.json() == {"deleted": True, "connector_id": connector_id}
        listed_after_delete = requests.get(f"{base_url}/api/web/external-connectors", timeout=10)
        assert listed_after_delete.status_code == 200
        assert all(item["connector_id"] != connector_id for item in listed_after_delete.json())
        detail_after_delete = requests.get(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
        assert detail_after_delete.status_code == 404
        assert detail_after_delete.json()["detail"]["error_code"] == "CONNECTOR_NOT_FOUND"

        delete_unsupported = requests.delete(
            f"{base_url}/api/web/external-connectors/{unsupported_payload['connector_id']}",
            timeout=10,
        )
        assert delete_unsupported.status_code == 200

    new_audits = acceptance_app.state.transcript_store.entries[before_audit_count:]
    connector_audits = [entry for entry in new_audits if entry.get("entry_type") == "connector_audit_event"]
    assert len(connector_audits) >= 5
    payloads = [entry["payload"] for entry in connector_audits]
    assert any(
        payload["connector_id"] == connector_id
        and payload["trace_id"] == f"feature70-edit-{suffix}"
        and payload["status"] == "success"
        and payload["before_evidence"]["sha256"] != payload["after_evidence"]["sha256"]
        for payload in payloads
    )
    assert any(
        payload["connector_id"] == connector_id
        and payload["trace_id"] == f"feature70-missing-{suffix}"
        and payload["status"] == "failed"
        and payload["error_code"] == "CONNECTOR_FILE_NOT_FOUND"
        for payload in payloads
    )
    assert any(
        payload["connector_id"] == connector_id
        and payload["trace_id"] == f"feature70-permission-{suffix}"
        and payload["status"] == "failed"
        and payload["error_code"] == "CONNECTOR_PERMISSION_DENIED"
        for payload in payloads
    )


def test_feature70_external_connector_minimal_profile_manual_registration_and_manifest_boundaries(
    acceptance_app: FastAPI,
) -> None:
    suffix = uuid4().hex[:8]
    connector_id = f"minimal-readonly-{suffix}"

    with live_http_server(acceptance_app) as base_url:
        register = requests.post(
            f"{base_url}/api/web/external-connectors",
            json={
                "connector_id": connector_id,
                "connector_type": "api_app",
                "target_app": "readonly.example",
                "display_name": "Minimal Readonly Connector",
                "description": "Manual minimal connector without manifest knowledge card.",
                "connection_config": {},
                "auth_config": {},
                "permission_scope": {},
                "capabilities": [
                    {
                        "name": "readonly_lookup",
                        "description": "A lightweight read-only lookup capability.",
                        "read_only": True,
                        "side_effect_type": "none",
                        "risk_level": "read_only",
                    }
                ],
            },
            timeout=10,
        )
        assert register.status_code == 200, register.text
        payload = register.json()
        assert payload["profile_level"] == "minimal"
        assert payload["manifest_path"] is None
        assert payload["capabilities"][0]["profile_level"] == "minimal"
        assert payload["capabilities"][0]["verification_mode"] == "none"

        detail = requests.get(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
        assert detail.status_code == 200
        assert detail.json()["profile_level"] == "minimal"

        forbidden_manifest = requests.post(
            f"{base_url}/api/web/external-connectors/register-from-manifest",
            json={"manifest_path": "../README.md"},
            timeout=10,
        )
        assert forbidden_manifest.status_code == 403
        assert forbidden_manifest.json()["detail"]["error_code"] == "CONNECTOR_MANIFEST_PATH_FORBIDDEN"

        delete_response = requests.delete(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
        assert delete_response.status_code == 200


def test_external_connector_manifest_registration_is_visible_in_real_list_api(
    acceptance_app: FastAPI,
) -> None:
    suffix = uuid4().hex[:8]
    connector_id = f"mongodb-visible-{suffix}"

    with live_http_server(acceptance_app) as base_url:
        manifests = requests.get(f"{base_url}/api/web/external-connectors/plugin-manifests", timeout=10)
        assert manifests.status_code == 200, manifests.text
        mongo_manifest = next(
            item for item in manifests.json()
            if item["manifest"].get("connector_id") == "mongodb_crud_connector"
        )
        assert mongo_manifest["valid"] is True
        assert mongo_manifest["manifest_hash"]

        registered = requests.post(
            f"{base_url}/api/web/external-connectors/register-from-manifest",
            json={
                "manifest_path": "mongodb_crud_connector/manifest.json",
                "connector_id_override": connector_id,
                "display_name": "MongoDB Visible Connector",
                "description": "Registered from manifest and verified by list query.",
                "connection_config": {"timeout_seconds": 20},
                "permission_scope": {
                    "allowed_operations": [
                        "mongodb_ping",
                        "mongodb_create",
                        "mongodb_read",
                        "mongodb_update",
                        "mongodb_delete",
                    ]
                },
            },
            timeout=10,
        )
        assert registered.status_code == 200, registered.text
        registered_payload = registered.json()
        assert registered_payload["connector_id"] == connector_id
        assert registered_payload["connector_type"] == "sdk_app"
        assert registered_payload["target_app"] == "mongodb"
        assert registered_payload["display_name"] == "MongoDB Visible Connector"
        assert registered_payload["description"] == "Registered from manifest and verified by list query."
        assert registered_payload["status"] == "active"
        assert registered_payload["profile_level"] == "verifiable"
        assert registered_payload["manifest_path"] == "mongodb_crud_connector/manifest.json"
        assert registered_payload["manifest_hash"] == mongo_manifest["manifest_hash"]

        listed = requests.get(f"{base_url}/api/web/external-connectors", timeout=10)
        assert listed.status_code == 200, listed.text
        listed_by_id = {item["connector_id"]: item for item in listed.json()}
        assert connector_id in listed_by_id
        listed_payload = listed_by_id[connector_id]
        assert listed_payload["connector_id"] == connector_id
        assert listed_payload["connector_type"] == registered_payload["connector_type"]
        assert listed_payload["target_app"] == registered_payload["target_app"]
        assert listed_payload["display_name"] == registered_payload["display_name"]
        assert listed_payload["description"] == registered_payload["description"]
        assert listed_payload["status"] == registered_payload["status"]
        assert listed_payload["profile_level"] == registered_payload["profile_level"]
        assert listed_payload["manifest_path"] == registered_payload["manifest_path"]
        assert listed_payload["manifest_hash"] == registered_payload["manifest_hash"]
        assert listed_payload["connection_config"]["plugin_path"] == "mongodb_crud_connector/connector.py"
        assert listed_payload["connection_config"]["timeout_seconds"] == 20
        assert listed_payload["permission_scope"]["allowed_operations"] == [
            "mongodb_ping",
            "mongodb_create",
            "mongodb_read",
            "mongodb_update",
            "mongodb_delete",
        ]
        assert {item["name"] for item in listed_payload["capabilities"]} == {
            "mongodb_ping",
            "mongodb_create",
            "mongodb_read",
            "mongodb_update",
            "mongodb_delete",
        }

        detail = requests.get(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
        assert detail.status_code == 200
        assert detail.json()["connector_id"] == connector_id
        assert detail.json()["manifest_hash"] == mongo_manifest["manifest_hash"]

        deleted = requests.delete(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True, "connector_id": connector_id}
        listed_after_delete = requests.get(f"{base_url}/api/web/external-connectors", timeout=10)
        assert listed_after_delete.status_code == 200
        assert connector_id not in {item["connector_id"] for item in listed_after_delete.json()}


def test_feature70_external_connector_real_api_root_plugins_mongodb_crud(
    acceptance_app: FastAPI,
) -> None:
    suffix = uuid4().hex[:8]
    connector_id = f"mongodb-crud-{suffix}"
    database = f"zentex_feature70_{suffix}"
    collection = "accounts"
    before_audit_count = len(acceptance_app.state.transcript_store.entries)

    with _real_mongodb_container() as mongo_uri:
        with live_http_server(acceptance_app) as base_url:
            manifests = requests.get(f"{base_url}/api/web/external-connectors/plugin-manifests", timeout=10)
            assert manifests.status_code == 200, manifests.text
            mongo_manifest = next(
                item for item in manifests.json()
                if item["manifest"].get("connector_id") == "mongodb_crud_connector"
            )
            assert mongo_manifest["valid"] is True
            assert mongo_manifest["manifest"]["profile_level"] == "verifiable"
            assert mongo_manifest["manifest_hash"]

            registered = requests.post(
                f"{base_url}/api/web/external-connectors/register-from-manifest",
                json={
                    "manifest_path": "mongodb_crud_connector/manifest.json",
                    "connector_id_override": connector_id,
                    "display_name": "MongoDB CRUD Root Plugin",
                    "description": "Calls the standalone root plugins/mongodb_crud_connector tool.",
                    "connection_config": {"timeout_seconds": 20},
                    "permission_scope": {
                        "allowed_operations": [
                            "mongodb_ping",
                            "mongodb_create",
                            "mongodb_read",
                            "mongodb_update",
                            "mongodb_delete",
                        ]
                    },
                },
                timeout=10,
            )
            assert registered.status_code == 200, registered.text
            registered_payload = registered.json()
            assert registered_payload["connector_id"] == connector_id
            assert registered_payload["connector_type"] == "sdk_app"
            assert registered_payload["target_app"] == "mongodb"
            assert registered_payload["connection_config"]["plugin_path"] == "mongodb_crud_connector/connector.py"
            assert registered_payload["profile_level"] == "verifiable"
            assert registered_payload["manifest_path"] == "mongodb_crud_connector/manifest.json"
            assert registered_payload["manifest_hash"] == mongo_manifest["manifest_hash"]
            assert {item["name"] for item in registered_payload["capabilities"]} == {
                "mongodb_ping",
                "mongodb_create",
                "mongodb_read",
                "mongodb_update",
                "mongodb_delete",
            }
            assert registered_payload["capabilities"][1]["verification_mode"] == "read_after_write"

            listed_after_manifest_register = requests.get(f"{base_url}/api/web/external-connectors", timeout=10)
            assert listed_after_manifest_register.status_code == 200
            listed_by_id = {item["connector_id"]: item for item in listed_after_manifest_register.json()}
            assert connector_id in listed_by_id
            listed_payload = listed_by_id[connector_id]
            assert listed_payload["connector_id"] == connector_id
            assert listed_payload["connector_type"] == "sdk_app"
            assert listed_payload["target_app"] == "mongodb"
            assert listed_payload["display_name"] == "MongoDB CRUD Root Plugin"
            assert listed_payload["description"] == "Calls the standalone root plugins/mongodb_crud_connector tool."
            assert listed_payload["status"] == "active"
            assert listed_payload["profile_level"] == "verifiable"
            assert listed_payload["manifest_path"] == "mongodb_crud_connector/manifest.json"
            assert listed_payload["manifest_hash"] == mongo_manifest["manifest_hash"]
            assert listed_payload["connection_config"]["plugin_path"] == "mongodb_crud_connector/connector.py"
            assert listed_payload["connection_config"]["timeout_seconds"] == 20
            assert listed_payload["permission_scope"]["allowed_operations"] == [
                "mongodb_ping",
                "mongodb_create",
                "mongodb_read",
                "mongodb_update",
                "mongodb_delete",
            ]
            listed_capability_map = {item["name"]: item for item in listed_payload["capabilities"]}
            assert set(listed_capability_map) == {
                "mongodb_ping",
                "mongodb_create",
                "mongodb_read",
                "mongodb_update",
                "mongodb_delete",
            }
            assert listed_capability_map["mongodb_create"]["read_only"] is False
            assert listed_capability_map["mongodb_create"]["verification_mode"] == "read_after_write"

            detail = requests.get(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
            assert detail.status_code == 200
            assert detail.json()["status"] == "active"

            health = requests.get(f"{base_url}/api/web/external-connectors/{connector_id}/health", timeout=10)
            assert health.status_code == 200, health.text
            health_payload = health.json()
            assert health_payload["health_status"] == "healthy"
            health_checks = {item["name"]: item for item in health_payload["checks"]}
            assert health_checks["status_active"]["passed"] is True
            assert health_checks["capabilities_present"]["count"] == 5
            assert health_checks["plugin_script_exists"]["passed"] is True
            assert health_checks["plugin_script_in_plugins_dir"]["passed"] is True

            common_args = {
                "mongo_uri": mongo_uri,
                "database": database,
                "collection": collection,
                "server_selection_timeout_ms": 5000,
            }
            ping = requests.post(
                f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
                json={
                    "capability": "mongodb_ping",
                    "arguments": common_args,
                    "trace_id": f"feature70-mongo-ping-{suffix}",
                },
                timeout=30,
            )
            assert ping.status_code == 200, ping.text
            assert ping.json()["output_summary"]["ping"] == "ok"
            assert ping.json()["after_evidence"]["database"] == database

            create = requests.post(
                f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
                json={
                    "capability": "mongodb_create",
                    "arguments": {
                        **common_args,
                        "document": {
                            "account_id": f"acct-{suffix}",
                            "owner": "Zentex",
                            "status": "active",
                            "balance": 100,
                        },
                    },
                    "trace_id": f"feature70-mongo-create-{suffix}",
                },
                timeout=30,
            )
            assert create.status_code == 200, create.text
            create_payload = create.json()
            assert create_payload["status"] == "success"
            assert create_payload["profile_level"] == "verifiable"
            assert create_payload["risk_level"] == "mutates_remote"
            assert create_payload["verification_mode"] == "read_after_write"
            assert create_payload["evidence_validation_status"] == "present"
            assert create_payload["output_summary"]["post_query_count"] == 1
            assert create_payload["output_summary"]["document"]["account_id"] == f"acct-{suffix}"
            assert create_payload["after_evidence"]["estimated_count"] == 1

            read_after_create = requests.post(
                f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
                json={
                    "capability": "mongodb_read",
                    "arguments": {**common_args, "filter": {"account_id": f"acct-{suffix}"}},
                    "trace_id": f"feature70-mongo-read-create-{suffix}",
                },
                timeout=30,
            )
            assert read_after_create.status_code == 200, read_after_create.text
            read_create_payload = read_after_create.json()["output_summary"]
            assert read_create_payload["matched_total"] == 1
            assert read_create_payload["documents"][0]["status"] == "active"
            assert read_create_payload["documents"][0]["balance"] == 100

            update = requests.post(
                f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
                json={
                    "capability": "mongodb_update",
                    "arguments": {
                        **common_args,
                        "filter": {"account_id": f"acct-{suffix}"},
                        "update": {"status": "closed", "balance": 75},
                    },
                    "trace_id": f"feature70-mongo-update-{suffix}",
                },
                timeout=30,
            )
            assert update.status_code == 200, update.text
            update_summary = update.json()["output_summary"]
            assert update_summary["matched_count"] == 1
            assert update_summary["modified_count"] == 1
            assert update_summary["post_update_documents"][0]["status"] == "closed"
            assert update_summary["post_update_documents"][0]["balance"] == 75

            read_after_update = requests.post(
                f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
                json={
                    "capability": "mongodb_read",
                    "arguments": {**common_args, "filter": {"account_id": f"acct-{suffix}", "status": "closed"}},
                    "trace_id": f"feature70-mongo-read-update-{suffix}",
                },
                timeout=30,
            )
            assert read_after_update.status_code == 200, read_after_update.text
            read_update_summary = read_after_update.json()["output_summary"]
            assert read_update_summary["matched_total"] == 1
            assert read_update_summary["documents"][0]["balance"] == 75

            delete = requests.post(
                f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
                json={
                    "capability": "mongodb_delete",
                    "arguments": {**common_args, "filter": {"account_id": f"acct-{suffix}"}},
                    "trace_id": f"feature70-mongo-delete-{suffix}",
                },
                timeout=30,
            )
            assert delete.status_code == 200, delete.text
            delete_summary = delete.json()["output_summary"]
            assert delete_summary["matched_before_delete"] == 1
            assert delete_summary["deleted_count"] == 1
            assert delete_summary["post_query_count"] == 0

            read_after_delete = requests.post(
                f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
                json={
                    "capability": "mongodb_read",
                    "arguments": {**common_args, "filter": {"account_id": f"acct-{suffix}"}},
                    "trace_id": f"feature70-mongo-read-delete-{suffix}",
                },
                timeout=30,
            )
            assert read_after_delete.status_code == 200, read_after_delete.text
            assert read_after_delete.json()["output_summary"]["matched_total"] == 0
            assert read_after_delete.json()["output_summary"]["documents"] == []

            invalid_update = requests.post(
                f"{base_url}/api/web/external-connectors/{connector_id}/test-call",
                json={
                    "capability": "mongodb_update",
                    "arguments": {**common_args, "update": {"status": "bad"}},
                    "trace_id": f"feature70-mongo-invalid-{suffix}",
                },
                timeout=30,
            )
            assert invalid_update.status_code == 502
            invalid_detail = invalid_update.json()["detail"]
            assert invalid_detail["error_code"] == "MONGODB_CONNECTOR_FAILED"
            assert invalid_detail["error_stage"] == "mongodb_connector_runtime"
            assert "filter" in invalid_detail["operator_message"]
            assert "recovery_hint" in invalid_detail

            history = requests.get(f"{base_url}/api/web/external-connectors/{connector_id}/history", timeout=10)
            assert history.status_code == 200
            history_payload = history.json()
            assert len(history_payload) == 8
            by_trace = {item["trace_id"]: item for item in history_payload}
            assert by_trace[f"feature70-mongo-create-{suffix}"]["status"] == "success"
            assert by_trace[f"feature70-mongo-create-{suffix}"]["output_summary"]["post_query_count"] == 1
            assert by_trace[f"feature70-mongo-update-{suffix}"]["output_summary"]["modified_count"] == 1
            assert by_trace[f"feature70-mongo-delete-{suffix}"]["output_summary"]["deleted_count"] == 1
            assert by_trace[f"feature70-mongo-read-delete-{suffix}"]["output_summary"]["matched_total"] == 0
            assert by_trace[f"feature70-mongo-invalid-{suffix}"]["status"] == "failed"
            assert by_trace[f"feature70-mongo-invalid-{suffix}"]["error_code"] == "MONGODB_CONNECTOR_FAILED"
            assert by_trace[f"feature70-mongo-create-{suffix}"]["evidence_refs"][0]["type"] == "mongodb_collection"
            assert by_trace[f"feature70-mongo-create-{suffix}"]["evidence_refs"][0]["operation"] == "create"

            delete_connector = requests.delete(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
            assert delete_connector.status_code == 200
            assert delete_connector.json() == {"deleted": True, "connector_id": connector_id}
            detail_after_delete = requests.get(f"{base_url}/api/web/external-connectors/{connector_id}", timeout=10)
            assert detail_after_delete.status_code == 404

    new_audits = acceptance_app.state.transcript_store.entries[before_audit_count:]
    mongo_audits = [
        entry["payload"]
        for entry in new_audits
        if entry.get("entry_type") == "connector_audit_event"
        and entry["payload"].get("connector_id") == connector_id
    ]
    assert len(mongo_audits) == 8
    assert any(
        payload["trace_id"] == f"feature70-mongo-delete-{suffix}"
        and payload["status"] == "success"
        and payload["output_summary"]["post_query_count"] == 0
        for payload in mongo_audits
    )
    assert any(
        payload["trace_id"] == f"feature70-mongo-invalid-{suffix}"
        and payload["status"] == "failed"
        and payload["error_code"] == "MONGODB_CONNECTOR_FAILED"
        for payload in mongo_audits
    )

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from zentex.external_connectors.models import ConnectorError


def file_evidence(path: Path) -> dict[str, Any]:
    exists = path.exists()
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
    }
    if not exists:
        return payload
    data = path.read_bytes()
    payload.update(
        {
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "mtime": path.stat().st_mtime,
        }
    )
    return payload


def require_file(path_value: Any) -> Path:
    path = Path(str(path_value or "")).expanduser()
    if not path.exists():
        raise ConnectorError(
            error_code="CONNECTOR_FILE_NOT_FOUND",
            error_stage="file_app_preflight",
            operator_message=f"target file does not exist: {path}",
            recovery_hint="Provide an existing file path and repeat the connector call.",
            status_code=404,
        )
    if not path.is_file():
        raise ConnectorError(
            error_code="CONNECTOR_TARGET_NOT_FILE",
            error_stage="file_app_preflight",
            operator_message=f"target path is not a file: {path}",
            recovery_hint="Provide a file path, not a directory.",
            status_code=422,
        )
    return path


def assert_writable(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    if not path.stat().st_mode & 0o200:
        raise ConnectorError(
            error_code="CONNECTOR_PERMISSION_DENIED",
            error_stage="file_app_preflight",
            operator_message=f"target file is not writable: {path}",
            recovery_hint="Grant write permission or use a writable copy.",
            status_code=403,
        )


def read_office_text(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix == ".docx":
            with zipfile.ZipFile(path) as archive:
                return _xml_to_text(archive.read("word/document.xml").decode("utf-8", errors="replace"))
        if suffix == ".xlsx":
            with zipfile.ZipFile(path) as archive:
                parts: list[str] = []
                for name in archive.namelist():
                    if name == "xl/sharedStrings.xml" or name.startswith("xl/worksheets/"):
                        parts.append(_xml_to_text(archive.read(name).decode("utf-8", errors="replace")))
                return "\n".join(part for part in parts if part)
        if suffix == ".pptx":
            with zipfile.ZipFile(path) as archive:
                parts = [
                    _xml_to_text(archive.read(name).decode("utf-8", errors="replace"))
                    for name in archive.namelist()
                    if name.startswith("ppt/slides/") and name.endswith(".xml")
                ]
                return "\n".join(part for part in parts if part)
        return path.read_text(encoding="utf-8", errors="replace")
    except zipfile.BadZipFile as exc:
        raise ConnectorError(
            error_code="CONNECTOR_BAD_FORMAT",
            error_stage="file_app_read",
            operator_message=f"file is not a valid office zip package: {path}",
            recovery_hint="Use a valid docx/xlsx/pptx file.",
            status_code=422,
        ) from exc
    except KeyError as exc:
        raise ConnectorError(
            error_code="CONNECTOR_SCHEMA_MISMATCH",
            error_stage="file_app_read",
            operator_message=f"required office document part is missing: {exc}",
            recovery_hint="Use a standard Office document package.",
            status_code=422,
        ) from exc


def write_docx_text(path: Path, content: str) -> dict[str, Any]:
    assert_writable(path)
    before = file_evidence(path)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{html.escape(content)}</w:t></w:r></w:p></w:body></w:document>"
    )
    _replace_zip_member(path, {"word/document.xml": xml.encode("utf-8")})
    after = file_evidence(path)
    _assert_changed(before, after, path)
    return {"text": content, "before": before, "after": after}


def update_xlsx_cell(path: Path, value: str) -> dict[str, Any]:
    assert_writable(path)
    before = file_evidence(path)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>{html.escape(value)}</t></is></c></row></sheetData>'
        "</worksheet>"
    )
    _replace_zip_member(path, {"xl/worksheets/sheet1.xml": xml.encode("utf-8")})
    after = file_evidence(path)
    _assert_changed(before, after, path)
    return {"cell": "A1", "value": value, "before": before, "after": after}


def edit_pptx_slide(path: Path, content: str) -> dict[str, Any]:
    assert_writable(path)
    before = file_evidence(path)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f"<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{html.escape(content)}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
    )
    _replace_zip_member(path, {"ppt/slides/slide1.xml": xml.encode("utf-8")})
    after = file_evidence(path)
    _assert_changed(before, after, path)
    return {"slide": "slide1", "text": content, "before": before, "after": after}


def export_pseudo_pdf(path: Path, output_path_value: Any, text: str | None = None) -> dict[str, Any]:
    output_path = Path(str(output_path_value or "")).expanduser()
    if not output_path:
        raise ConnectorError(
            error_code="CONNECTOR_OUTPUT_PATH_REQUIRED",
            error_stage="file_app_export",
            operator_message="output_path is required for export_pdf",
            recovery_hint="Provide output_path in connector call arguments.",
            status_code=422,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    body = text if text is not None else read_office_text(path)
    output_path.write_bytes(_build_text_pdf(f"Zentex export: {path.name}\n{body[:1600]}"))
    evidence = file_evidence(output_path)
    if not evidence.get("exists") or evidence.get("size_bytes", 0) <= 0:
        raise ConnectorError(
            error_code="CONNECTOR_EXPORT_FAILED",
            error_stage="file_app_export",
            operator_message=f"export did not create a non-empty file: {output_path}",
            recovery_hint="Check output path permissions and retry.",
            status_code=500,
        )
    return {"output_path": str(output_path), "output_evidence": evidence}


def render_preview(path: Path, output_path_value: Any) -> dict[str, Any]:
    text = read_office_text(path)
    output_path = Path(str(output_path_value or "")).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text[:5000], encoding="utf-8")
    evidence = file_evidence(output_path)
    return {
        "preview_path": str(output_path),
        "text_preview": text[:500],
        "preview_evidence": evidence,
    }


def write_json_summary(path: Path, output_path_value: Any, summary: dict[str, Any]) -> dict[str, Any]:
    output_path = Path(str(output_path_value or "")).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence = file_evidence(output_path)
    return {"output_path": str(output_path), "output_evidence": evidence}


def _xml_to_text(xml: str) -> str:
    text = re.sub(r"<[^>]+>", " ", xml)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def _build_text_pdf(text: str) -> bytes:
    safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    lines = safe_text.splitlines()[:40] or [""]
    text_ops = ["BT", "/F1 11 Tf", "50 760 Td"]
    for index, line in enumerate(lines):
        if index:
            text_ops.append("0 -16 Td")
        text_ops.append(f"({line[:110]}) Tj")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("utf-8")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        b"5 0 obj\n<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream\nendobj\n",
    ]
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(output))
        output.extend(obj)
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _replace_zip_member(path: Path, replacements: dict[str, bytes]) -> None:
    try:
        with zipfile.ZipFile(path, "r") as source:
            existing = {name: source.read(name) for name in source.namelist()}
    except zipfile.BadZipFile as exc:
        raise ConnectorError(
            error_code="CONNECTOR_BAD_FORMAT",
            error_stage="file_app_write",
            operator_message=f"file is not a valid office zip package: {path}",
            recovery_hint="Use a valid docx/xlsx/pptx file.",
            status_code=422,
        ) from exc

    existing.update(replacements)
    with NamedTemporaryFile(delete=False, suffix=path.suffix) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name, data in existing.items():
                target.writestr(name, data)
        shutil.move(str(tmp_path), path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _assert_changed(before: dict[str, Any], after: dict[str, Any], path: Path) -> None:
    if before.get("sha256") == after.get("sha256"):
        raise ConnectorError(
            error_code="CONNECTOR_NO_EFFECT",
            error_stage="file_app_write",
            operator_message=f"write operation did not change target file: {path}",
            recovery_hint="Check input content and target file permissions.",
            status_code=409,
        )

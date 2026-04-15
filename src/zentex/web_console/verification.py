from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path


LEGACY_RUNTIME_PATTERN = re.compile(r"zentex\.(?:core|runtime)|\bruntime\.")


@dataclass(frozen=True)
class LegacyImportFinding:
    file_path: str
    line_number: int
    line_text: str
    match_text: str


@dataclass(frozen=True)
class SmokeImportResult:
    module_name: str
    ok: bool
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class MigrationAuditRecord:
    file_path: str
    legacy_imports: list[str]
    replacement_imports: list[str]
    rationale: str
    verification: str


def scan_legacy_runtime_imports(root: Path) -> list[LegacyImportFinding]:
    findings: list[LegacyImportFinding] = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for line_number, line_text in enumerate(text.splitlines(), start=1):
            for match in LEGACY_RUNTIME_PATTERN.finditer(line_text):
                findings.append(
                    LegacyImportFinding(
                        file_path=str(path),
                        line_number=line_number,
                        line_text=line_text.strip(),
                        match_text=match.group(0),
                    )
                )
    return findings


def smoke_import_module(module_name: str) -> SmokeImportResult:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        return SmokeImportResult(
            module_name=module_name,
            ok=False,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    return SmokeImportResult(module_name=module_name, ok=True)


def build_migration_audit_record(
    *,
    file_path: str,
    legacy_imports: list[str],
    replacement_imports: list[str],
    rationale: str,
    verification: str,
) -> MigrationAuditRecord:
    return MigrationAuditRecord(
        file_path=file_path,
        legacy_imports=list(legacy_imports),
        replacement_imports=list(replacement_imports),
        rationale=rationale,
        verification=verification,
    )


def render_verification_report_markdown(
    *,
    scan_findings: list[LegacyImportFinding],
    smoke_results: list[SmokeImportResult],
) -> str:
    lines = ["# Web Console Verification Report", "", "## Legacy Runtime Import Scan"]
    if not scan_findings:
        lines.append("- No legacy runtime/core references detected.")
    else:
        for finding in scan_findings:
            lines.append(
                f"- `{finding.file_path}:{finding.line_number}` matched `{finding.match_text}`: `{finding.line_text}`"
            )

    lines.extend(["", "## Smoke Imports"])
    if not smoke_results:
        lines.append("- No smoke import results recorded.")
    else:
        for result in smoke_results:
            if result.ok:
                lines.append(f"- `{result.module_name}`: OK")
            else:
                lines.append(
                    f"- `{result.module_name}`: {result.error_type or 'Error'} - {result.error_message or ''}"
                )
    return "\n".join(lines)

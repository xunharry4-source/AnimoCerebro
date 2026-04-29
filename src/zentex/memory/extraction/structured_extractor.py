from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

StructuredMemoryKind = Literal["fact", "event", "case", "lesson", "constraint"]


class StructuredExtractionIssue(BaseModel):
    """Validation issue for an explicit structured memory fragment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class StructuredExtractionError(RuntimeError):
    """Raised when explicit structured memory input is malformed."""

    def __init__(self, message: str, *, issues: list[StructuredExtractionIssue]) -> None:
        self.issues = issues
        details = "; ".join(f"{issue.path}: {issue.reason}" for issue in issues)
        super().__init__(f"{message}: {details}" if details else message)


class StructuredMemoryItem(BaseModel):
    """One deterministic fact/event/case/lesson/constraint extraction result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str = Field(min_length=1)
    kind: StructuredMemoryKind
    content: str = Field(min_length=1)
    source_memory_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    evidence_path: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)


class StructuredExtractionReport(BaseModel):
    """Structured extraction report with explicit empty/extracted status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_memory_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    extraction_status: Literal["empty", "extracted"]
    counts_by_kind: dict[StructuredMemoryKind, int]
    items: list[StructuredMemoryItem] = Field(default_factory=list)

    @property
    def item_count(self) -> int:
        return len(self.items)


_PLURAL_TO_KIND: dict[str, StructuredMemoryKind] = {
    "facts": "fact",
    "events": "event",
    "cases": "case",
    "lessons": "lesson",
    "constraints": "constraint",
}


def extract_structured_memory_items(
    memory_record: Any,
    *,
    trace_id: str | None = None,
    source_memory_id: str | None = None,
) -> StructuredExtractionReport:
    """
    Extract explicit fact/event/case/lesson/constraint fragments from a memory record.

    This function is intentionally deterministic: it reads explicit structured
    payload fields only and does not infer semantics from free text.
    """

    record = _to_mapping(memory_record)
    payload = _require_mapping(record.get("payload", {}), "payload")
    resolved_trace_id = _non_empty_string(
        trace_id or record.get("trace_id") or payload.get("trace_id"),
        "trace_id",
    )
    resolved_source_memory_id = _non_empty_string(
        source_memory_id or record.get("memory_id") or payload.get("source_memory_id"),
        "source_memory_id",
    )

    roots = _structured_roots(payload)
    issues: list[StructuredExtractionIssue] = []
    items: list[StructuredMemoryItem] = []

    for root_path, root in roots:
        for plural_key, kind in _PLURAL_TO_KIND.items():
            if plural_key not in root:
                continue
            raw_entries = root[plural_key]
            if not isinstance(raw_entries, list):
                issues.append(
                    StructuredExtractionIssue(
                        path=f"{root_path}.{plural_key}",
                        reason="must be a list",
                    )
                )
                continue
            for index, raw_entry in enumerate(raw_entries):
                entry_path = f"{root_path}.{plural_key}[{index}]"
                if not isinstance(raw_entry, Mapping):
                    issues.append(
                        StructuredExtractionIssue(
                            path=entry_path,
                            reason="must be an object",
                        )
                    )
                    continue
                item = _extract_item(
                    kind=kind,
                    entry=dict(raw_entry),
                    source_memory_id=resolved_source_memory_id,
                    trace_id=resolved_trace_id,
                    entry_path=entry_path,
                    sequence=len(items),
                    issues=issues,
                )
                if item is not None:
                    items.append(item)

    if issues:
        raise StructuredExtractionError("structured memory extraction failed", issues=issues)

    counts_by_kind: dict[StructuredMemoryKind, int] = {
        "fact": 0,
        "event": 0,
        "case": 0,
        "lesson": 0,
        "constraint": 0,
    }
    for item in items:
        counts_by_kind[item.kind] += 1

    return StructuredExtractionReport(
        source_memory_id=resolved_source_memory_id,
        trace_id=resolved_trace_id,
        extraction_status="extracted" if items else "empty",
        counts_by_kind=counts_by_kind,
        items=items,
    )


def _to_mapping(memory_record: Any) -> dict[str, Any]:
    if isinstance(memory_record, Mapping):
        return dict(memory_record)
    model_dump = getattr(memory_record, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        if isinstance(dumped, Mapping):
            return dict(dumped)
    raise TypeError("memory_record must be a mapping or pydantic model")


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    raise StructuredExtractionError(
        "structured memory extraction failed",
        issues=[
            StructuredExtractionIssue(
                path=path,
                reason="must be an object",
            )
        ],
    )


def _non_empty_string(value: Any, path: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise StructuredExtractionError(
        "structured memory extraction failed",
        issues=[
            StructuredExtractionIssue(
                path=path,
                reason="must be a non-empty string",
            )
        ],
    )


def _structured_roots(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    roots: list[tuple[str, dict[str, Any]]] = []
    structured_memory = payload.get("structured_memory")
    if structured_memory is not None:
        roots.append(
            (
                "payload.structured_memory",
                _require_mapping(structured_memory, "payload.structured_memory"),
            )
        )

    direct_keys = set(_PLURAL_TO_KIND).intersection(payload)
    if direct_keys:
        roots.append(("payload", payload))

    return roots


def _extract_item(
    *,
    kind: StructuredMemoryKind,
    entry: dict[str, Any],
    source_memory_id: str,
    trace_id: str,
    entry_path: str,
    sequence: int,
    issues: list[StructuredExtractionIssue],
) -> StructuredMemoryItem | None:
    if kind == "fact":
        return _build_simple_item(
            kind=kind,
            required_field="statement",
            entry=entry,
            source_memory_id=source_memory_id,
            trace_id=trace_id,
            entry_path=entry_path,
            sequence=sequence,
            issues=issues,
        )
    if kind == "event":
        return _build_event_item(
            entry=entry,
            source_memory_id=source_memory_id,
            trace_id=trace_id,
            entry_path=entry_path,
            sequence=sequence,
            issues=issues,
        )
    if kind == "case":
        return _build_case_item(
            entry=entry,
            source_memory_id=source_memory_id,
            trace_id=trace_id,
            entry_path=entry_path,
            sequence=sequence,
            issues=issues,
        )
    if kind == "lesson":
        return _build_simple_item(
            kind=kind,
            required_field="lesson",
            entry=entry,
            source_memory_id=source_memory_id,
            trace_id=trace_id,
            entry_path=entry_path,
            sequence=sequence,
            issues=issues,
        )
    return _build_constraint_item(
        entry=entry,
        source_memory_id=source_memory_id,
        trace_id=trace_id,
        entry_path=entry_path,
        sequence=sequence,
        issues=issues,
    )


def _build_simple_item(
    *,
    kind: StructuredMemoryKind,
    required_field: str,
    entry: dict[str, Any],
    source_memory_id: str,
    trace_id: str,
    entry_path: str,
    sequence: int,
    issues: list[StructuredExtractionIssue],
) -> StructuredMemoryItem | None:
    content = _read_required_text(entry, required_field, entry_path, issues)
    if content is None:
        return None
    return _item(
        kind=kind,
        content=content,
        attributes=entry,
        source_memory_id=source_memory_id,
        trace_id=trace_id,
        evidence_path=f"{entry_path}.{required_field}",
        sequence=sequence,
    )


def _build_event_item(
    *,
    entry: dict[str, Any],
    source_memory_id: str,
    trace_id: str,
    entry_path: str,
    sequence: int,
    issues: list[StructuredExtractionIssue],
) -> StructuredMemoryItem | None:
    event_type = _read_required_text(entry, "event_type", entry_path, issues)
    description = _read_required_text(entry, "description", entry_path, issues)
    if event_type is None or description is None:
        return None
    return _item(
        kind="event",
        content=description,
        attributes=entry,
        source_memory_id=source_memory_id,
        trace_id=trace_id,
        evidence_path=f"{entry_path}.description",
        sequence=sequence,
    )


def _build_case_item(
    *,
    entry: dict[str, Any],
    source_memory_id: str,
    trace_id: str,
    entry_path: str,
    sequence: int,
    issues: list[StructuredExtractionIssue],
) -> StructuredMemoryItem | None:
    case_id = _read_required_text(entry, "case_id", entry_path, issues)
    condition = _read_required_text(entry, "condition", entry_path, issues)
    action = _read_required_text(entry, "action", entry_path, issues)
    outcome = _read_required_text(entry, "outcome", entry_path, issues)
    if None in {case_id, condition, action, outcome}:
        return None
    return _item(
        kind="case",
        content=f"{condition} -> {action} -> {outcome}",
        attributes=entry,
        source_memory_id=source_memory_id,
        trace_id=trace_id,
        evidence_path=f"{entry_path}.outcome",
        sequence=sequence,
    )


def _build_constraint_item(
    *,
    entry: dict[str, Any],
    source_memory_id: str,
    trace_id: str,
    entry_path: str,
    sequence: int,
    issues: list[StructuredExtractionIssue],
) -> StructuredMemoryItem | None:
    rule = _read_required_text(entry, "rule", entry_path, issues)
    scope = _read_required_text(entry, "scope", entry_path, issues)
    if not isinstance(entry.get("non_bypassable"), bool):
        issues.append(
            StructuredExtractionIssue(
                path=f"{entry_path}.non_bypassable",
                reason="must be a boolean",
            )
        )
    if rule is None or scope is None or not isinstance(entry.get("non_bypassable"), bool):
        return None
    return _item(
        kind="constraint",
        content=rule,
        attributes=entry,
        source_memory_id=source_memory_id,
        trace_id=trace_id,
        evidence_path=f"{entry_path}.rule",
        sequence=sequence,
    )


def _read_required_text(
    entry: dict[str, Any],
    field_name: str,
    entry_path: str,
    issues: list[StructuredExtractionIssue],
) -> str | None:
    value = entry.get(field_name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    issues.append(
        StructuredExtractionIssue(
            path=f"{entry_path}.{field_name}",
            reason="must be a non-empty string",
        )
    )
    return None


def _item(
    *,
    kind: StructuredMemoryKind,
    content: str,
    attributes: dict[str, Any],
    source_memory_id: str,
    trace_id: str,
    evidence_path: str,
    sequence: int,
) -> StructuredMemoryItem:
    return StructuredMemoryItem(
        item_id=f"{source_memory_id}:{kind}:{sequence}",
        kind=kind,
        content=content,
        source_memory_id=source_memory_id,
        trace_id=trace_id,
        evidence_path=evidence_path,
        attributes=dict(attributes),
    )

"""
Social posting ledger.

Purpose:
    Persist posting workflow outcomes to JSON and a small Markdown status table.

Main responsibilities:
    - Record platform, status, URL, title/content summary, and evidence.
    - Update a human-readable status document after successful or failed posts.

Not responsible for:
    - Deciding whether a post succeeded.
    - Editing source code documentation.
    - Hiding failed or unverified posting attempts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.state import utc_now_iso


class SocialPostingLedger:
    """Append-only social posting evidence ledger."""

    def __init__(self, ledger_path: Path, status_doc_path: Path) -> None:
        self.ledger_path = Path(ledger_path)
        self.status_doc_path = Path(status_doc_path)

    def record(self, *, platform: str, status: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Append a ledger row and refresh the Markdown table."""
        record = {
            "timestamp": utc_now_iso(),
            "platform": platform,
            "status": status,
            "data": data,
        }
        records = self._load_records()
        records.append(record)
        self._write_records(records)
        self._write_status_doc(records)
        return record

    def _load_records(self) -> List[Dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        try:
            raw = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise PostingWorkflowError(
                f"Could not read posting ledger: {exc}",
                node="update_document",
                code="ledger_read_failed",
                details={"path": str(self.ledger_path)},
            ) from exc
        if not isinstance(raw, list):
            raise PostingWorkflowError(
                "Posting ledger must be a JSON array",
                node="update_document",
                code="ledger_invalid_format",
                details={"path": str(self.ledger_path)},
            )
        return raw

    def _write_records(self, records: List[Dict[str, Any]]) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_status_doc(self, records: List[Dict[str, Any]]) -> None:
        self.status_doc_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Social Posting Status",
            "",
            "| Time | Platform | Status | Target | URL |",
            "| --- | --- | --- | --- | --- |",
        ]
        for record in records[-50:]:
            data = record.get("data") if isinstance(record.get("data"), dict) else {}
            target = data.get("subreddit") or data.get("repository") or data.get("topic") or data.get("target") or ""
            url = data.get("post_url") or data.get("url") or ""
            lines.append(
                "| {time} | {platform} | {status} | {target} | {url} |".format(
                    time=record.get("timestamp", ""),
                    platform=record.get("platform", ""),
                    status=record.get("status", ""),
                    target=str(target).replace("|", "/"),
                    url=str(url).replace("|", "/"),
                )
            )
        self.status_doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

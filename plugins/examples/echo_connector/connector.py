from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any


def _main() -> int:
    try:
        request = json.loads(sys.stdin.read() or "{}")
        capability = str(request.get("capability") or "").strip()
        if capability != "echo":
            raise ValueError(f"unsupported capability: {capability}")
        arguments = request.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be an object")
        message = str(arguments.get("message") or "")
        now = datetime.now(timezone.utc).isoformat()
        response: dict[str, Any] = {
            "status": "success",
            "output_summary": {
                "message": message,
                "message_length": len(message),
                "trace_id": request.get("trace_id"),
            },
            "before_evidence": {
                "received_at": now,
            },
            "after_evidence": {
                "completed_at": now,
                "echoed": True,
            },
            "evidence_refs": [
                {
                    "type": "process_echo",
                    "connector_id": request.get("connector_id"),
                    "capability": capability,
                }
            ],
        }
        sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "status": "failed",
                    "error_code": "ECHO_CONNECTOR_FAILED",
                    "error_stage": "runtime",
                    "operator_message": str(exc),
                    "recovery_hint": "Call capability 'echo' with arguments.message.",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())

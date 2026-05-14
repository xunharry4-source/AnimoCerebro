from __future__ import annotations

import json
import logging
from typing import Any


def observable_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    component: str,
    **fields: Any,
) -> None:
    """Emit a single-line JSON event that remains searchable with plain logs."""
    payload = {
        "event": str(event),
        "component": str(component),
        **{key: value for key, value in fields.items() if value not in (None, "", [], {})},
    }
    logger.log(
        level,
        "[OBSERVABILITY] %s",
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
    )

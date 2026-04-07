from __future__ import annotations

"""
Compatibility exports for the Zentex web console.

Historically this module contained the entire FastAPI implementation. It is now
split across:
- `zentex.web_console.app` (FastAPI app factory)
- `zentex.web_console.router` (API router wiring)
- `zentex.web_console.routers.*` (route modules)
- `zentex.web_console.services.*` (payload builders)
- `zentex.web_console.contracts.*` (pydantic schemas)
"""

from zentex.web_console.app import create_web_console_app
from zentex.web_console.contracts.plugins import PluginFeatureCatalogItem
from zentex.web_console.routers.nine_questions import get_latest_nine_questions_report
from zentex.web_console.services.plugins import build_managed_plugin_record

__all__ = [
    "PluginFeatureCatalogItem",
    "build_managed_plugin_record",
    "create_web_console_app",
    "get_latest_nine_questions_report",
]

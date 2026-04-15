from __future__ import annotations

"""Canonical lightweight facade for the Zentex web console.

Note: Direct factory import via this module is deprecated.
Use: from zentex.web_console.app import create_app
"""

from zentex.web_console.routers.nine_questions import get_latest_nine_questions_report
from zentex.plugins.service.utils import build_managed_plugin_record
from zentex.plugins.service import PluginFeatureCatalogItem

__all__ = [
    "PluginFeatureCatalogItem",
    "build_managed_plugin_record",
    "get_latest_nine_questions_report",
]

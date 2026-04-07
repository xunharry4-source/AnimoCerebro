from __future__ import annotations

import os
from typing import Any, Dict, List
from zentex.core.plugin_base import PluginLifecycleStatus, PluginHealthStatus
from zentex.core.plugin_family import SensoryPluginSpec


class WorkspaceSensoryPlugin(SensoryPluginSpec):
    """
    G14 Sensory Plugin for Workspace analysis.
    Implements the three-stage chain: ingest -> sanitize -> interpret.
    """
    
    plugin_id: str = "sensory_workspace_default"
    signal_type: str = "workspace_snapshot"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["io_failure"]
    revocation_reasons: List[str] = []

    def ingest(self, source: Any) -> Any:
        """
        Capture the raw skeleton of the workspace.
        In this context, 'source' is expected to be a directory path or a pre-fetched list.
        """
        # Logic to list files, check git status, etc.
        # This replaces the ad-hoc 'extract_q1_local_inputs' partially.
        return source # Simulation: returns the raw snapshot data

    def sanitize(self, raw_signal: Any) -> Any:
        """
        G14 requirement: Non-bypassable sanitization.
        Remove sensitive paths, normalize separators, etc.
        """
        if not isinstance(raw_signal, dict):
            return {}
        
        # Strip absolute paths, keep relative context only
        sanitized = {
            "structure": raw_signal.get("structure", {}),
            "events": raw_signal.get("events", []),
            "metadata_only": True
        }
        return sanitized

    def interpret(self, clean_signal: Any) -> Dict[str, Any]:
        """
        G14 requirement: Semantic interpretation.
        Identify file distributions, primary languages, and obvious risk markers.
        """
        structure = clean_signal.get("structure", {})
        files = structure.get("files", [])
        
        interpretations = {
            "has_git": ".git" in files,
            "primary_extension": self._guess_primary_ext(files),
            "is_complex": len(files) > 100,
            "risk_markers": [f for f in files if "config" in f.lower() or "key" in f.lower()]
        }
        return interpretations

    def _guess_primary_ext(self, files: List[str]) -> str:
        exts = {}
        for f in files:
            _, ext = os.path.splitext(f)
            if ext:
                exts[ext] = exts.get(ext, 0) + 1
        return max(exts, key=exts.get) if exts else "unknown"

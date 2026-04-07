from __future__ import annotations

"""
Runtime helpers for real plugin evolution filesystem operations.

This module performs the concrete copy, scaffold, and cleanup steps used by
plugin evolution jobs. It is intentionally limited to filesystem work and does
not pretend to execute OpenHands itself.
"""

from pathlib import Path
import shutil


class PluginEvolutionRuntime:
    """Concrete filesystem runtime for plugin candidate preparation and cleanup."""

    def copy_plugin_candidate(
        self,
        *,
        source_plugin_path: str,
        candidate_plugin_path: str,
    ) -> str:
        source_path = Path(source_plugin_path)
        candidate_path = Path(candidate_plugin_path)

        if not source_path.exists():
            raise FileNotFoundError(
                f"Source plugin path does not exist: {source_plugin_path}"
            )
        if candidate_path.exists():
            raise FileExistsError(
                f"Candidate plugin path already exists: {candidate_plugin_path}"
            )

        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(source_path, candidate_path)
        else:
            shutil.copy2(source_path, candidate_path)
        return str(candidate_path)

    def scaffold_new_plugin_candidate(
        self,
        *,
        candidate_plugin_path: str,
    ) -> str:
        candidate_path = Path(candidate_plugin_path)
        if candidate_path.exists():
            raise FileExistsError(
                f"Candidate plugin path already exists: {candidate_plugin_path}"
            )
        candidate_path.mkdir(parents=True, exist_ok=False)
        return str(candidate_path)

    def cleanup_candidate_path(
        self,
        *,
        candidate_plugin_path: str,
    ) -> bool:
        candidate_path = Path(candidate_plugin_path)
        if not candidate_path.exists():
            return False
        if candidate_path.is_dir():
            shutil.rmtree(candidate_path)
        else:
            candidate_path.unlink()
        return True

from __future__ import annotations

"""
Runtime helpers for real plugin evolution filesystem operations.

This module performs the concrete copy, scaffold, and cleanup steps used by
plugin evolution jobs. It is intentionally limited to filesystem work and does
not pretend to execute OpenHands itself.
"""

import logging
from pathlib import Path
import shutil
import subprocess
import ast
import json
import re
from typing import Any

logger = logging.getLogger(__name__)


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

    def update_plugin_metadata(self, candidate_path: str, new_version: str) -> bool:
        """Update version metadata inside an isolated plugin candidate."""
        path = Path(candidate_path)
        metadata_file = path / "plugin.json"
        if metadata_file.exists():
            try:
                data = json.loads(metadata_file.read_text(encoding="utf-8"))
                data["version"] = new_version
                metadata_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return True
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to update plugin.json version at {metadata_file}: {exc}"
                ) from exc

        init_file = path / "__init__.py"
        if init_file.exists():
            content = init_file.read_text(encoding="utf-8")
            new_content = re.sub(
                r'__version__\s*=\s*["\'].*["\']',
                f'__version__ = "{new_version}"',
                content,
            )
            if new_content != content:
                init_file.write_text(new_content, encoding="utf-8")
                return True

        return False

    def run_verification_suite(self, candidate_path: str, commands: list[str]) -> dict[str, Any]:
        """Automated lint/test/typecheck/build verification (Sub-function 1.3)."""
        results = {}
        path_obj = Path(candidate_path)
        cwd = str(path_obj if path_obj.is_dir() else path_obj.parent)

        for cmd in commands:
            try:
                # Basic execution logic. In production, this would use a real containerized sandbox.
                process = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=cwd
                )
                results[cmd] = {
                    "success": process.returncode == 0,
                    "stdout": process.stdout,
                    "stderr": process.stderr,
                    "exit_code": process.returncode
                }
            except Exception as e:
                results[cmd] = {"success": False, "error": str(e)}
        return results

    def scan_for_forbidden_calls(self, candidate_path: str) -> list[str]:
        """Automated AST-based code scanning for unauthorized access (Sub-function 58.3)."""
        violations = []
        forbidden_imports = {"socket", "requests", "urllib", "http.client", "os", "subprocess"}
        
        path = Path(candidate_path)
        files = list(path.rglob("*.py")) if path.is_dir() else [path if str(path).endswith(".py") else None]
        
        for file in files:
            if file is None or not file.is_file(): continue
            try:
                tree = ast.parse(file.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.split('.')[0] in forbidden_imports:
                                violations.append(f"Forbidden import '{alias.name}' in {file.name}")
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.module.split('.')[0] in forbidden_imports:
                             violations.append(f"Forbidden from-import '{node.module}' in {file.name}")
                    elif isinstance(node, ast.Call):
                        # Detect syscalls hidden in getattr or similar
                        if isinstance(node.func, ast.Attribute) and node.func.attr in {"system", "popen", "spawn"}:
                            violations.append(f"Dangeous call '.{node.func.attr}()' in {file.name}")
            except Exception as e:
                violations.append(f"AST Parse Error in {file.name}: {str(e)}")
        return violations

    def detect_side_effects(self, candidate_path: str) -> list[str]:
        """Detect side effects using AST-based analysis (Sub-function 58.1)."""
        side_effects = []
        path = Path(candidate_path)
        files = list(path.rglob("*.py")) if path.is_dir() else [path if str(path).endswith(".py") else None]

        for file in files:
            if file is None or not file.is_file(): continue
            try:
                tree = ast.parse(file.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Attribute):
                             if node.func.attr in {"remove", "rmtree", "mkdir", "write", "unlink"}:
                                  side_effects.append(f"Side-effect call '.{node.func.attr}()' in {file.name}")
            except Exception:
                # POLICY[no-silent-except]: log unparseable files and skip them.
                logger.debug("Could not parse %s for side-effect analysis — skipping", file, exc_info=True)
                continue
        return side_effects

    def validate_worker_evidence(
        self,
        *,
        worker_result: dict[str, Any],
        candidate_path: str,
        commands: list[str],
    ) -> dict[str, Any]:
        """Validate worker output, command results, permission scan, and health probes."""
        verification_results = self.run_verification_suite(candidate_path, commands)
        failed_commands = [
            command
            for command, result in verification_results.items()
            if not bool(result.get("success"))
        ]
        forbidden_calls = self.scan_for_forbidden_calls(candidate_path)
        side_effects = self.detect_side_effects(candidate_path)
        health_probe_results = worker_result.get("health_probe_results")
        if health_probe_results is None:
            health_probe_results = []
        if not isinstance(health_probe_results, list):
            raise RuntimeError("Plugin worker evidence must report health_probe_results as a list.")
        failed_health_probes = [
            item
            for item in health_probe_results
            if isinstance(item, dict) and not bool(item.get("success"))
        ]
        if failed_commands or forbidden_calls or side_effects or failed_health_probes:
            raise RuntimeError(
                "Plugin candidate verification failed: "
                f"failed_commands={failed_commands}, "
                f"forbidden_calls={forbidden_calls}, "
                f"side_effects={side_effects}, "
                f"failed_health_probes={failed_health_probes}"
            )
        return {
            "validation_results": verification_results,
            "permission_scan": {
                "forbidden_calls": forbidden_calls,
                "side_effects": side_effects,
            },
            "health_probe_results": health_probe_results,
        }

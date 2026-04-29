from __future__ import annotations

import ast
import difflib
import json
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from zentex.kernel.state_domain import TranscriptEntry, TranscriptEntryType


UTC = timezone.utc
PROTECTED_PATH_PARTS = (
    "src/zentex/safety",
    "src/zentex/kernel/safety_gate.py",
    "src/zentex/kernel/identity_kernel.py",
    "src/zentex/supervision",
    "identity",
    "guardrail",
)
FORBIDDEN_PATCH_TOKENS = (
    "os.system",
    "subprocess.Popen",
    "eval(",
    "exec(",
    "socket.",
    "requests.",
    "urllib.",
    "rm -rf",
)


@dataclass(frozen=True)
class ProtectedModulePolicy:
    """Fail-closed policy for self-upgrade candidate patch targets."""

    protected_path_parts: tuple[str, ...] = PROTECTED_PATH_PARTS
    forbidden_patch_tokens: tuple[str, ...] = FORBIDDEN_PATCH_TOKENS

    def is_protected_relative(self, relative_path: str) -> bool:
        lowered = str(relative_path).replace("\\", "/").lower()
        return any(part in lowered for part in self.protected_path_parts)

    def target_rejection_reason(self, workspace: Path, relative_path: str) -> str | None:
        normalized = str(relative_path).replace("\\", "/")
        path = Path(normalized)
        if path.is_absolute() or ".." in path.parts:
            return "invalid_patch_target_path"
        if self.is_protected_relative(normalized):
            return f"protected_module:{normalized}"
        target = workspace / normalized
        if not _is_relative_to(target.resolve(), workspace):
            return "patch_target_escapes_workspace"
        return None

    def content_rejection_reason(self, change: dict[str, Any]) -> str | None:
        combined = f"{change.get('find', '')}\n{change.get('replace', '')}"
        for token in self.forbidden_patch_tokens:
            if token in combined:
                return f"forbidden_patch_token:{token}"
        return None

    def rejection_reason(self, workspace: Path, change: dict[str, Any]) -> str | None:
        target_reason = self.target_rejection_reason(workspace, str(change["relative_path"]))
        if target_reason:
            return target_reason
        return self.content_rejection_reason(change)


DEFAULT_PROTECTED_MODULE_POLICY = ProtectedModulePolicy()


def run_self_coding_cycle(
    kernel: Any,
    *,
    session_id: str,
    workspace_root: str,
    candidate_root: str,
    capability_gap: dict[str, Any],
    patch_plan: dict[str, Any],
    verification_commands: list[list[str]],
) -> dict[str, Any]:
    if not session_id:
        raise ValueError("session_id is required")
    if not capability_gap:
        raise ValueError("capability_gap is required")
    if not patch_plan:
        raise ValueError("patch_plan is required")
    if not verification_commands:
        raise ValueError("verification_commands is required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")

    workspace = Path(workspace_root).expanduser().resolve()
    candidate_base = Path(candidate_root).expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise ValueError(f"workspace_root must be an existing directory: {workspace}")
    if _is_relative_to(candidate_base, workspace):
        raise ValueError("candidate_root must not be inside workspace_root")

    patch_id = f"g15-candidate-{uuid4().hex}"
    workspace_analysis = _analyze_workspace(workspace, patch_plan)
    original_hashes = _collect_target_hashes(workspace, patch_plan)
    rejection = _rejection_reason(workspace, patch_plan)
    record = {
        "feature_code": "G15",
        "session_id": session_id,
        "patch_id": patch_id,
        "capability_gap": capability_gap,
        "workspace_analysis": workspace_analysis,
        "patch_plan": patch_plan,
        "candidate_workspace": str(candidate_base / patch_id),
        "verification_commands": verification_commands,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "created",
        "diffs": [],
        "verification_bundle": None,
        "promotion_decision": None,
        "main_workspace_integrity": {},
        "evidence_refs": [],
    }
    if rejection:
        record["status"] = "rejected"
        record["promotion_decision"] = {
            "status": "rejected",
            "reason": rejection,
            "main_chain_write_allowed": False,
        }
        record["main_workspace_integrity"] = _verify_main_workspace_unchanged(workspace, original_hashes)
        return _finalize(kernel, state, record, "g15_self_coding_rejected")

    candidate_workspace = candidate_base / patch_id
    if candidate_workspace.exists():
        raise FileExistsError(f"candidate workspace already exists: {candidate_workspace}")
    candidate_base.mkdir(parents=True, exist_ok=True)
    shutil.copytree(workspace, candidate_workspace)
    applied = _apply_candidate_patch(candidate_workspace, patch_plan)
    record["diffs"] = applied["diffs"]
    record["candidate_files"] = applied["candidate_files"]
    verification_bundle = _run_verification(candidate_workspace, verification_commands)
    record["verification_bundle"] = verification_bundle
    record["main_workspace_integrity"] = _verify_main_workspace_unchanged(workspace, original_hashes)

    if not record["main_workspace_integrity"]["unchanged"]:
        raise RuntimeError("G15 main workspace integrity check failed; candidate patch touched main chain")
    if verification_bundle["status"] == "passed":
        record["status"] = "approved_for_review"
        record["promotion_decision"] = {
            "status": "approved_for_review",
            "reason": "candidate_patch_verified_in_isolation",
            "main_chain_write_allowed": False,
            "next_step": "manual_review_or_self_refactor_pipeline",
        }
    else:
        record["status"] = "rejected"
        record["promotion_decision"] = {
            "status": "rejected",
            "reason": "verification_failed",
            "main_chain_write_allowed": False,
            "next_step": "rollback_or_replan",
        }
    return _finalize(kernel, state, record, "g15_self_coding_cycle_completed")


def query_self_coding_patch(kernel: Any, *, session_id: str, patch_id: str) -> dict[str, Any]:
    if not session_id or not patch_id:
        raise ValueError("session_id and patch_id are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    record = getattr(kernel, "_self_coding_patches", {}).get(patch_id)
    if not record or record["session_id"] != session_id:
        raise KeyError(f"G15 self-coding patch not found: {patch_id}")
    _append_transcript(state, record, "g15_self_coding_patch_queried")
    return {**record, "query_visible": True}


def _analyze_workspace(workspace: Path, patch_plan: dict[str, Any]) -> dict[str, Any]:
    files: list[Path] = []
    suffix_counts: Counter[str] = Counter()
    risk_files: list[str] = []
    for path in workspace.rglob("*"):
        if not path.is_file() or _skip_path(path):
            continue
        files.append(path)
        suffix_counts[path.suffix or "<none>"] += 1
        relative = str(path.relative_to(workspace)).replace("\\", "/")
        if _is_protected_relative(relative):
            risk_files.append(relative)

    search_terms = [str(item) for item in patch_plan.get("search_terms", []) if str(item).strip()]
    search_hits: list[dict[str, Any]] = []
    for term in search_terms:
        for path in files:
            if path.suffix not in {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml"}:
                continue
            text = path.read_text(encoding="utf-8")
            if term in text:
                search_hits.append({"term": term, "path": str(path.relative_to(workspace))})

    references = [_python_reference_summary(path, workspace) for path in files if path.suffix == ".py"]
    return {
        "file_count": len(files),
        "suffix_distribution": dict(sorted(suffix_counts.items())),
        "risk_files": sorted(risk_files),
        "search_hits": search_hits,
        "code_reference_graph": [item for item in references if item["symbols"] or item["imports"]],
    }


def _python_reference_summary(path: Path, workspace: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    symbols: list[dict[str, str]] = []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append({"name": node.name, "kind": node.__class__.__name__})
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return {"path": str(path.relative_to(workspace)), "symbols": symbols, "imports": sorted(set(imports))}


def _collect_target_hashes(workspace: Path, patch_plan: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for change in _changes(patch_plan):
        path = workspace / change["relative_path"]
        if not path.exists() or not path.is_file():
            raise ValueError(f"patch target does not exist: {change['relative_path']}")
        hashes[change["relative_path"]] = _sha256(path.read_text(encoding="utf-8"))
    return hashes


def _rejection_reason(workspace: Path, patch_plan: dict[str, Any]) -> str | None:
    for change in _changes(patch_plan):
        reason = DEFAULT_PROTECTED_MODULE_POLICY.rejection_reason(workspace, change)
        if reason:
            return reason
    return None


def _apply_candidate_patch(candidate_workspace: Path, patch_plan: dict[str, Any]) -> dict[str, Any]:
    diffs: list[dict[str, Any]] = []
    candidate_files: list[dict[str, Any]] = []
    for change in _changes(patch_plan):
        relative = str(change["relative_path"]).replace("\\", "/")
        path = candidate_workspace / relative
        original = path.read_text(encoding="utf-8")
        find = str(change.get("find") or "")
        replace = str(change.get("replace") or "")
        if not find:
            raise ValueError("patch change find must not be empty")
        if find not in original:
            raise ValueError(f"patch find text is not present in candidate file: {relative}")
        updated = original.replace(find, replace, 1)
        path.write_text(updated, encoding="utf-8")
        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(),
                updated.splitlines(),
                fromfile=f"main/{relative}",
                tofile=f"candidate/{relative}",
                lineterm="",
            )
        )
        diffs.append({"relative_path": relative, "unified_diff": "\n".join(diff_lines)})
        candidate_files.append(
            {
                "relative_path": relative,
                "content_sha256": _sha256(updated),
                "contains_replacement": replace in updated,
            }
        )
    return {"diffs": diffs, "candidate_files": candidate_files}


def _run_verification(candidate_workspace: Path, commands: list[list[str]]) -> dict[str, Any]:
    receipts: list[dict[str, Any]] = []
    for command in commands:
        if not command or not all(isinstance(part, str) and part for part in command):
            raise ValueError("verification command must be a non-empty list of strings")
        completed = subprocess.run(command, cwd=str(candidate_workspace), text=True, capture_output=True, timeout=30, check=False)
        receipt = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
            "passed": completed.returncode == 0,
        }
        receipts.append(receipt)
        if completed.returncode != 0:
            return {"status": "failed", "receipts": receipts}
    return {"status": "passed", "receipts": receipts}


def _verify_main_workspace_unchanged(workspace: Path, original_hashes: dict[str, str]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for relative, before in original_hashes.items():
        path = workspace / relative
        after = _sha256(path.read_text(encoding="utf-8"))
        checks.append({"relative_path": relative, "before_sha256": before, "after_sha256": after, "unchanged": before == after})
    return {"unchanged": all(item["unchanged"] for item in checks), "checks": checks}


def _changes(patch_plan: dict[str, Any]) -> list[dict[str, Any]]:
    changes = patch_plan.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ValueError("patch_plan.changes is required")
    return changes


def _finalize(kernel: Any, state: Any, record: dict[str, Any], entry_type: str) -> dict[str, Any]:
    memory_id = _persist_memory(kernel, record)
    record["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    _cache_record(kernel, "_self_coding_patches", record["patch_id"], record)
    _append_transcript(state, record, entry_type)
    return record


def _persist_memory(kernel: Any, record: dict[str, Any]) -> str:
    memory_service = getattr(kernel, "_memory_service", None)
    if memory_service is None or not callable(getattr(memory_service, "remember", None)):
        raise RuntimeError("G15 requires MemoryService evidence persistence")
    memory = memory_service.remember(
        title=f"G15 self-coding patch {record['patch_id']}",
        summary=f"G15 {record['status']} {record['promotion_decision']['status']}",
        content=json.dumps(record, ensure_ascii=False, sort_keys=True),
        layer="procedural",
        source="g15_self_coding",
        trace_id=record["patch_id"],
        target_id=record["patch_id"],
        tags=["G15", "self_coding", record["status"]],
        self_coding_record=record,
    )
    memory_id = str(getattr(memory, "memory_id", "") or "")
    if not memory_id or getattr(memory_service.get_record(memory_id), "memory_id", None) != memory_id:
        raise RuntimeError(f"G15 memory writeback query verification failed: {memory_id}")
    return memory_id


def _cache_record(kernel: Any, attr: str, key: str, record: dict[str, Any]) -> None:
    if not hasattr(kernel, attr):
        setattr(kernel, attr, {})
    getattr(kernel, attr)[key] = record


def _append_transcript(state: Any, record: dict[str, Any], entry_type: str) -> None:
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=record["session_id"],
            payload={"feature_code": "G15", "entry_type": entry_type, **record},
        )
    )


def _is_protected_relative(relative: str) -> bool:
    return DEFAULT_PROTECTED_MODULE_POLICY.is_protected_relative(relative)


def _skip_path(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts.intersection({".git", "__pycache__", ".pytest_cache", "node_modules"}))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()

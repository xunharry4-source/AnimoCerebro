from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

"""
Memory versioning and rollback for profile-mode records.

职责:
  - 为 profile 类记忆维护版本链（v1 → v2 → v3），支持完整历史回溯。
  - 提供 rollback API：将某个 profile 回退到指定版本。
  - 记录版本间 diff（新增/修改/删除的 content 片段）。
  - 支持实验性"分支"：在沙箱中创建 profile 分支，确认后再合并到主链。

不负责:
  - 非 profile 类记忆（collection 模式）的版本管理。
  - 物理写入主存储（所有回滚操作都通过 MemoryAuditEvent 记录，由 EnhancedMemoryService 执行）。
"""

import difflib
import json
import logging
import threading
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class MemoryVersion(BaseModel):
    """One immutable snapshot of a profile record at a point in time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version_id: str = Field(default_factory=lambda: str(uuid4()))
    version_number: int = Field(ge=1)
    memory_id: str       # ID of the EnhancedMemoryRecord this version snapshots
    profile_key: str     # Canonical key: "{memory_layer}::{title}::{source_kind}"
    content: str
    summary: str
    content_hash: str    # From EnhancedMemoryRecord.content_hash
    operator: str = Field(default="system")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    change_note: str = Field(default="")


class VersionDiff(BaseModel):
    """Unified diff between two consecutive versions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    from_version: int
    to_version: int
    diff_lines: list[str]
    added_lines: int
    removed_lines: int


class VersionChain(BaseModel):
    """Ordered version history for one profile key."""

    model_config = ConfigDict(extra="forbid")

    profile_key: str
    versions: list[MemoryVersion] = Field(default_factory=list)
    # ID of the memory_id currently considered "active" (usually latest).
    active_memory_id: str = ""

    def latest(self) -> Optional[MemoryVersion]:
        return self.versions[-1] if self.versions else None

    def get_version(self, version_number: int) -> Optional[MemoryVersion]:
        for v in self.versions:
            if v.version_number == version_number:
                return v
        return None

    def diff(self, from_v: int, to_v: int) -> Optional[VersionDiff]:
        a = self.get_version(from_v)
        b = self.get_version(to_v)
        if not a or not b:
            return None
        diff = list(difflib.unified_diff(
            a.content.splitlines(),
            b.content.splitlines(),
            fromfile=f"v{from_v}",
            tofile=f"v{to_v}",
            lineterm="",
        ))
        added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
        return VersionDiff(
            from_version=from_v,
            to_version=to_v,
            diff_lines=diff,
            added_lines=added,
            removed_lines=removed,
        )


# ---------------------------------------------------------------------------
# Branch
# ---------------------------------------------------------------------------

class VersionBranch(BaseModel):
    """
    An experimental branch derived from a specific version of a profile.

    Branches allow testing new strategy patches without affecting the main chain.
    Merge → updates main chain; Discard → branch is deleted.
    """

    model_config = ConfigDict(extra="forbid")

    branch_id: str = Field(default_factory=lambda: str(uuid4()))
    profile_key: str
    base_version_number: int
    branch_name: str
    versions: list[MemoryVersion] = Field(default_factory=list)
    merged: bool = False
    discarded: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Versioned memory store
# ---------------------------------------------------------------------------

class VersionedMemoryStore:
    """
    Stores and manages version chains for all profile-mode memory records.

    Thread-safe.  Persists to a single JSON file.
    """

    def __init__(self, store_path: Union[str, Path]) -> None:
        self._path = Path(store_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # profile_key → VersionChain
        self._chains: dict[str, VersionChain] = {}
        # branch_id → VersionBranch
        self._branches: dict[str, VersionBranch] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text("utf-8"))
            for chain_data in raw.get("chains", {}).values():
                chain = VersionChain(**chain_data)
                self._chains[chain.profile_key] = chain
            for branch_data in raw.get("branches", {}).values():
                branch = VersionBranch(**branch_data)
                self._branches[branch.branch_id] = branch
        except Exception as exc:
            logger.error("Failed to load version store from %s: %s", self._path, exc)

    def _save(self) -> None:
        data = {
            "chains": {k: v.model_dump(mode="json") for k, v in self._chains.items()},
            "branches": {k: v.model_dump(mode="json") for k, v in self._branches.items()},
        }
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

    # ── version recording ─────────────────────────────────────────────────

    @staticmethod
    def make_profile_key(memory_layer: str, title: str, source_kind: str) -> str:
        return f"{memory_layer}::{title}::{source_kind}"

    def record_version(
        self,
        memory_layer: str,
        title: str,
        source_kind: str,
        memory_id: str,
        content: str,
        summary: str,
        content_hash: str,
        operator: str = "system",
        change_note: str = "",
    ) -> MemoryVersion:
        """Append a new version to the chain for a profile key."""
        key = self.make_profile_key(memory_layer, title, source_kind)
        with self._lock:
            chain = self._chains.setdefault(key, VersionChain(profile_key=key))
            next_num = (chain.latest().version_number + 1) if chain.versions else 1
            version = MemoryVersion(
                version_number=next_num,
                memory_id=memory_id,
                profile_key=key,
                content=content,
                summary=summary,
                content_hash=content_hash,
                operator=operator,
                change_note=change_note,
            )
            chain.versions.append(version)
            chain.active_memory_id = memory_id
            self._save()
        return version

    # ── rollback ─────────────────────────────────────────────────────────

    def rollback(
        self,
        memory_layer: str,
        title: str,
        source_kind: str,
        to_version: int,
    ) -> Optional[MemoryVersion]:
        """
        Mark an older version as the rollback target.

        Returns the target MemoryVersion so the caller can re-ingest it
        through EnhancedMemoryService.  Does NOT modify main storage directly.
        """
        key = self.make_profile_key(memory_layer, title, source_kind)
        with self._lock:
            chain = self._chains.get(key)
            if not chain:
                logger.warning("No version chain found for %s", key)
                return None
            target = chain.get_version(to_version)
            if not target:
                logger.warning("Version %d not found in chain %s", to_version, key)
                return None
            # The active_memory_id should be updated by the caller after re-ingestion.
        logger.info("Rollback requested: %s → version %d (memory_id=%s)", key, to_version, target.memory_id)
        return target

    # ── diff ─────────────────────────────────────────────────────────────

    def diff(
        self,
        memory_layer: str,
        title: str,
        source_kind: str,
        from_v: int,
        to_v: int,
    ) -> Optional[VersionDiff]:
        key = self.make_profile_key(memory_layer, title, source_kind)
        with self._lock:
            chain = self._chains.get(key)
        return chain.diff(from_v, to_v) if chain else None

    # ── branching ────────────────────────────────────────────────────────

    def create_branch(
        self,
        memory_layer: str,
        title: str,
        source_kind: str,
        branch_name: str,
    ) -> Optional[VersionBranch]:
        key = self.make_profile_key(memory_layer, title, source_kind)
        with self._lock:
            chain = self._chains.get(key)
            if not chain or not chain.versions:
                return None
            base = chain.latest()
            branch = VersionBranch(
                profile_key=key,
                base_version_number=base.version_number,
                branch_name=branch_name,
            )
            self._branches[branch.branch_id] = branch
            self._save()
        return branch

    def merge_branch(self, branch_id: str, operator: str = "system") -> bool:
        """Merge a branch's latest version into the main chain."""
        with self._lock:
            branch = self._branches.get(branch_id)
            if not branch or branch.discarded or branch.merged:
                return False
            if not branch.versions:
                return False
            latest_branch_v = branch.versions[-1]
            chain = self._chains.get(branch.profile_key)
            if not chain:
                return False
            next_num = (chain.latest().version_number + 1) if chain.versions else 1
            merged_v = latest_branch_v.model_copy(update={
                "version_number": next_num,
                "change_note": f"Merged from branch '{branch.branch_name}'",
                "operator": operator,
            })
            chain.versions.append(merged_v)
            chain.active_memory_id = merged_v.memory_id
            branch.merged = True
            self._save()
        return True

    def discard_branch(self, branch_id: str) -> bool:
        with self._lock:
            branch = self._branches.get(branch_id)
            if not branch:
                return False
            branch.discarded = True
            self._save()
        return True

    # ── queries ──────────────────────────────────────────────────────────

    def get_chain(self, memory_layer: str, title: str, source_kind: str) -> Optional[VersionChain]:
        key = self.make_profile_key(memory_layer, title, source_kind)
        with self._lock:
            return self._chains.get(key)

    def list_profile_keys(self) -> list[str]:
        with self._lock:
            return list(self._chains.keys())

    def stats(self) -> dict:
        with self._lock:
            chains = len(self._chains)
            total_versions = sum(len(c.versions) for c in self._chains.values())
            branches = len(self._branches)
        return {
            "profile_chains": chains,
            "total_versions": total_versions,
            "branches": branches,
        }

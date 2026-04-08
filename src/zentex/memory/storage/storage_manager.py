from __future__ import annotations

"""
Hierarchical memory storage manager.

职责:
  - 将各类记忆按命名空间、层级、时间分片组织到多个 JSONL 文件，解决单文件瓶颈。
  - 提供分区注册、文件轮转、冷存档迁移等基础设施。

不负责:
  - 记忆内容的语义理解或分类（由 classification.py 负责）。
  - 记忆的治理状态管理（由 enhanced.py 负责）。

Directory structure:
    memory_root/
    ├── partitions.json          # partition registry
    ├── semantic/
    │   ├── user_prefs/
    │   │   ├── collection_001.jsonl
    │   │   └── collection_002.jsonl
    │   └── profiles/
    │       └── profile_001.jsonl
    ├── procedural/
    │   └── workflows/
    ├── episodic/
    │   ├── 2026-04/
    │   └── 2026-03/
    ├── quarantine/
    └── cold_storage/
        └── archived_2025/
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_DEFAULT_MAX_FILE_SIZE_MB = 50.0
_DEFAULT_MAX_RECORDS_PER_FILE = 10_000


class StoragePartition(BaseModel):
    """Logical partition in the memory storage hierarchy."""

    model_config = ConfigDict(extra="forbid")

    partition_id: str = Field(default_factory=lambda: str(uuid4()))
    # Namespace tuple serialised as list for JSON round-trip.
    namespace: list[str]
    storage_mode: str = Field(default="collection")  # "collection" | "profile"
    max_records_per_file: int = Field(default=_DEFAULT_MAX_RECORDS_PER_FILE, ge=100)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_path_segment(self) -> str:
        return "/".join(self.namespace)


class RotationPolicy(BaseModel):
    """Controls when a storage file is rotated to a new shard."""

    model_config = ConfigDict(extra="forbid")

    max_size_mb: float = Field(default=_DEFAULT_MAX_FILE_SIZE_MB, gt=0)
    max_records: int = Field(default=_DEFAULT_MAX_RECORDS_PER_FILE, ge=100)


class HierarchicalMemoryStorage:
    """
    Namespace-based hierarchical storage manager inspired by LangMem.

    每个 (namespace, storage_mode) 组合对应一个目录分区；写入时按大小/记录数
    自动轮转到新文件，避免单文件无限膨胀。
    """

    def __init__(
        self,
        root_path: str | Path,
        *,
        rotation_policy: RotationPolicy | None = None,
    ) -> None:
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        self._rotation = rotation_policy or RotationPolicy()
        self._partitions: dict[tuple[str, ...], StoragePartition] = {}
        self._lock = threading.Lock()
        self._load_partitions()

    # ── partition registry ───────────────────────────────────────────────

    def _partition_registry_path(self) -> Path:
        return self.root_path / "partitions.json"

    def _load_partitions(self) -> None:
        path = self._partition_registry_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text("utf-8"))
            for item in data.get("partitions", []):
                p = StoragePartition(**item)
                key = tuple(p.namespace)
                self._partitions[key] = p
        except Exception as exc:
            logger.warning("Failed to load partition registry: %s", exc)

    def _save_partitions(self) -> None:
        path = self._partition_registry_path()
        data = {"partitions": [p.model_dump(mode="json") for p in self._partitions.values()]}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

    def get_or_create_partition(
        self,
        namespace: tuple[str, ...],
        storage_mode: str = "collection",
    ) -> StoragePartition:
        with self._lock:
            if namespace not in self._partitions:
                p = StoragePartition(namespace=list(namespace), storage_mode=storage_mode)
                self._partitions[namespace] = p
                self._save_partitions()
                (self.root_path / p.to_path_segment()).mkdir(parents=True, exist_ok=True)
            return self._partitions[namespace]

    # ── path resolution ──────────────────────────────────────────────────

    def partition_dir(self, namespace: tuple[str, ...]) -> Path:
        p = self.get_or_create_partition(namespace)
        return self.root_path / p.to_path_segment()

    def active_file(self, namespace: tuple[str, ...], prefix: str = "collection") -> Path:
        """Return the path of the current active shard file for a namespace."""
        d = self.partition_dir(namespace)
        shards = sorted(d.glob(f"{prefix}_*.jsonl"))
        if not shards:
            return d / f"{prefix}_001.jsonl"
        latest = shards[-1]
        # Rotate if needed.
        if self._needs_rotation(latest):
            return self._next_shard(d, prefix, len(shards) + 1)
        return latest

    def _needs_rotation(self, path: Path) -> bool:
        if not path.exists():
            return False
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb >= self._rotation.max_size_mb:
            return True
        # Count lines as a proxy for record count.
        try:
            lines = sum(1 for _ in path.open("r", encoding="utf-8"))
            return lines >= self._rotation.max_records
        except Exception:
            return False

    @staticmethod
    def _next_shard(directory: Path, prefix: str, index: int) -> Path:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return directory / f"{prefix}_{index:03d}_{ts}.jsonl"

    # ── temporal episodic sharding ───────────────────────────────────────

    def episodic_file_for(self, namespace: tuple[str, ...], dt: datetime | None = None) -> Path:
        """Return the episodic shard file for a given month (YYYY-MM)."""
        dt = dt or datetime.utcnow()
        month_dir = self.partition_dir(namespace) / dt.strftime("%Y-%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        shard = month_dir / "episodes_001.jsonl"
        if self._needs_rotation(shard):
            shards = sorted(month_dir.glob("episodes_*.jsonl"))
            shard = self._next_shard(month_dir, "episodes", len(shards) + 1)
        return shard

    # ── bulk iteration ───────────────────────────────────────────────────

    def iter_all_records(
        self,
        namespace: tuple[str, ...],
        *,
        pattern: str = "*.jsonl",
    ) -> Iterator[dict]:
        """Iterate every JSON record across all shards in a partition."""
        d = self.partition_dir(namespace)
        for shard in sorted(d.rglob(pattern)):
            try:
                for line in shard.open("r", encoding="utf-8"):
                    line = line.strip()
                    if line:
                        yield json.loads(line)
            except Exception as exc:
                logger.warning("Skipping corrupt shard %s: %s", shard, exc)

    def list_shards(self, namespace: tuple[str, ...]) -> list[Path]:
        return sorted(self.partition_dir(namespace).rglob("*.jsonl"))

    # ── cold-storage archival ────────────────────────────────────────────

    def archive_to_cold_storage(
        self,
        namespace: tuple[str, ...],
        year: int,
        *,
        dry_run: bool = False,
    ) -> list[Path]:
        """
        Move all shards older than the given year into cold_storage/archived_{year}/.

        只移动文件名中包含年份前缀且年份 < year 的分片，避免误移活跃数据。
        """
        archive_root = self.root_path / "cold_storage" / f"archived_{year}"
        moved: list[Path] = []
        for shard in self.list_shards(namespace):
            # Extract year from filename or parent directory.
            try:
                shard_year = int(shard.parent.name[:4])
            except (ValueError, IndexError):
                continue
            if shard_year < year:
                if not dry_run:
                    archive_root.mkdir(parents=True, exist_ok=True)
                    dest = archive_root / shard.name
                    shard.rename(dest)
                    logger.info("Archived %s → %s", shard, dest)
                moved.append(shard)
        return moved

    # ── maintenance ──────────────────────────────────────────────────────

    def cleanup_empty_partitions(self) -> list[tuple[str, ...]]:
        """Remove partition registry entries whose directories are empty."""
        removed: list[tuple[str, ...]] = []
        with self._lock:
            for ns, p in list(self._partitions.items()):
                d = self.root_path / p.to_path_segment()
                if d.exists() and not any(d.iterdir()):
                    try:
                        d.rmdir()
                    except OSError:
                        pass
                    del self._partitions[ns]
                    removed.append(ns)
            if removed:
                self._save_partitions()
        return removed

    def stats(self) -> dict:
        """Return a summary of all partitions and their shard counts."""
        result: dict = {"root": str(self.root_path), "partitions": {}}
        for ns, p in self._partitions.items():
            shards = self.list_shards(ns)
            total_bytes = sum(s.stat().st_size for s in shards if s.exists())
            result["partitions"]["/".join(ns)] = {
                "mode": p.storage_mode,
                "shard_count": len(shards),
                "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            }
        return result

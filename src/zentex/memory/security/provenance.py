from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

"""
Memory provenance and lineage tracking.

职责:
  - 记录每条记忆的完整来源链：原始 transcript 事件 → reflection → consolidation → 最终记忆。
  - 支持"我为什么相信这件事？"（why do I believe this?）溯源查询。
  - 提供有向无环图（DAG）表示记忆推导路径。

不负责:
  - 记忆内容的语义分析。
  - 物理存储管理（由 storage_manager.py 负责）。
  - 与 Kuzu 图数据库直接交互（由 kuzu_backend.py 负责）。
"""

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
# Node & Edge types
# ---------------------------------------------------------------------------

class ProvenanceNodeKind(str):
    """Type constants for provenance graph nodes."""
    TRANSCRIPT = "transcript"         # Raw runtime event
    REFLECTION = "reflection"         # Processed reflection output
    CONSOLIDATION = "consolidation"   # B8 consolidation cycle output
    MEMORY = "memory"                 # Final EnhancedMemoryRecord
    EXTRACTION = "extraction"         # Intermediate extracted fact


class ProvenanceNode(BaseModel):
    """A node in the memory derivation graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: str  # One of ProvenanceNodeKind constants
    ref_id: str  # External ID this node refers to (trace_id, memory_id, cycle_id, etc.)
    label: str  # Human-readable description
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict = Field(default_factory=dict)


class ProvenanceEdge(BaseModel):
    """A directed derivation link: source produced target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: str = Field(default_factory=lambda: str(uuid4()))
    source_node_id: str
    target_node_id: str
    # Transform type: "extracted_from" | "reflected_from" | "consolidated_from"
    # | "compressed_from" | "supersedes"
    transform: str = Field(default="extracted_from")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Lineage graph
# ---------------------------------------------------------------------------

class MemoryLineageGraph:
    """
    In-memory directed acyclic graph recording memory derivation chains.

    Thread-safe.  Nodes keyed by node_id; edges stored as adjacency lists in
    both directions for fast ancestor / descendant traversal.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nodes: dict[str, ProvenanceNode] = {}
        # node_id → list of outgoing edges (source → targets)
        self._out_edges: dict[str, list[ProvenanceEdge]] = {}
        # node_id → list of incoming edges (targets ← sources)
        self._in_edges: dict[str, list[ProvenanceEdge]] = {}

    def add_node(self, node: ProvenanceNode) -> ProvenanceNode:
        with self._lock:
            if node.node_id not in self._nodes:
                self._nodes[node.node_id] = node
        return node

    def add_edge(self, edge: ProvenanceEdge) -> ProvenanceEdge:
        with self._lock:
            self._out_edges.setdefault(edge.source_node_id, []).append(edge)
            self._in_edges.setdefault(edge.target_node_id, []).append(edge)
        return edge

    def find_node_by_ref(self, ref_id: str) -> Optional[ProvenanceNode]:
        with self._lock:
            for node in self._nodes.values():
                if node.ref_id == ref_id:
                    return node
        return None

    # ── traversal ────────────────────────────────────────────────────────

    def ancestors(self, node_id: str) -> list[ProvenanceNode]:
        """Return all ancestor nodes (transitively) for a given node_id."""
        visited: set[str] = set()
        result: list[ProvenanceNode] = []
        queue = [node_id]
        while queue:
            nid = queue.pop()
            if nid in visited:
                continue
            visited.add(nid)
            for edge in self._in_edges.get(nid, []):
                src = edge.source_node_id
                if src not in visited:
                    with self._lock:
                        node = self._nodes.get(src)
                    if node:
                        result.append(node)
                    queue.append(src)
        return result

    def descendants(self, node_id: str) -> list[ProvenanceNode]:
        """Return all descendant nodes (transitively) for a given node_id."""
        visited: set[str] = set()
        result: list[ProvenanceNode] = []
        queue = [node_id]
        while queue:
            nid = queue.pop()
            if nid in visited:
                continue
            visited.add(nid)
            for edge in self._out_edges.get(nid, []):
                tgt = edge.target_node_id
                if tgt not in visited:
                    with self._lock:
                        node = self._nodes.get(tgt)
                    if node:
                        result.append(node)
                    queue.append(tgt)
        return result

    def derivation_path(self, memory_id: str) -> list[ProvenanceNode]:
        """
        Return the ordered derivation chain that led to a memory record.

        Starts from the oldest ancestor (raw transcript) and ends at the memory node.
        """
        target = self.find_node_by_ref(memory_id)
        if not target:
            return []
        chain = self.ancestors(target.node_id)
        # Sort by creation time (oldest first) and append the memory node at end.
        chain.sort(key=lambda n: n.created_at)
        chain.append(target)
        return chain

    def why_do_i_believe(self, memory_id: str) -> str:
        """
        Return a human-readable explanation of a memory's derivation.

        格式: "Derived from transcript[trace_id] → reflection[ref] → consolidation[cycle_id]"
        """
        path = self.derivation_path(memory_id)
        if not path:
            return f"No lineage found for memory {memory_id}."
        parts = [f"{n.kind}[{n.ref_id[:8]}]" for n in path]
        return " → ".join(parts)

    # ── persistence ──────────────────────────────────────────────────────

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = {
                "nodes": [n.model_dump(mode="json") for n in self._nodes.values()],
                "out_edges": {
                    nid: [e.model_dump(mode="json") for e in edges]
                    for nid, edges in self._out_edges.items()
                },
            }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        data = json.loads(path.read_text("utf-8"))
        for n in data.get("nodes", []):
            self.add_node(ProvenanceNode(**n))
        for edges in data.get("out_edges", {}).values():
            for e in edges:
                self.add_edge(ProvenanceEdge(**e))

    def stats(self) -> dict:
        with self._lock:
            return {
                "node_count": len(self._nodes),
                "edge_count": sum(len(v) for v in self._out_edges.values()),
            }


# ---------------------------------------------------------------------------
# Provenance tracker facade
# ---------------------------------------------------------------------------

class ProvenanceTracker:
    """
    High-level facade for recording lineage events during memory ingestion.

    用法:
        tracker.record_transcript(trace_id="abc123", label="decision_synthesized")
        tracker.record_extraction(source_trace_id="abc123", extracted_memory_id="m-456")
        tracker.explain(memory_id="m-456")  # → "transcript[abc123] → memory[m-456]"
    """

    def __init__(self, graph: Optional[MemoryLineageGraph] = None) -> None:
        self._graph = graph or MemoryLineageGraph()

    @property
    def graph(self) -> MemoryLineageGraph:
        return self._graph

    def _ensure_node(self, kind: str, ref_id: str, label: str, **meta) -> ProvenanceNode:
        existing = self._graph.find_node_by_ref(ref_id)
        if existing:
            return existing
        node = ProvenanceNode(kind=kind, ref_id=ref_id, label=label, metadata=meta)
        return self._graph.add_node(node)

    def record_transcript(self, trace_id: str, label: str = "", **meta) -> ProvenanceNode:
        return self._ensure_node(ProvenanceNodeKind.TRANSCRIPT, trace_id, label or f"transcript:{trace_id}", **meta)

    def record_reflection(self, reflection_id: str, source_trace_id: str, label: str = "") -> ProvenanceNode:
        src = self._ensure_node(ProvenanceNodeKind.TRANSCRIPT, source_trace_id, source_trace_id)
        tgt = self._ensure_node(ProvenanceNodeKind.REFLECTION, reflection_id, label or f"reflection:{reflection_id}")
        self._graph.add_edge(ProvenanceEdge(
            source_node_id=src.node_id,
            target_node_id=tgt.node_id,
            transform="reflected_from",
        ))
        return tgt

    def record_consolidation(self, cycle_id: str, source_ids: list[str], label: str = "") -> ProvenanceNode:
        tgt = self._ensure_node(ProvenanceNodeKind.CONSOLIDATION, cycle_id, label or f"consolidation:{cycle_id}")
        for src_id in source_ids:
            src = self._graph.find_node_by_ref(src_id)
            if src:
                self._graph.add_edge(ProvenanceEdge(
                    source_node_id=src.node_id,
                    target_node_id=tgt.node_id,
                    transform="consolidated_from",
                ))
        return tgt

    def record_memory(
        self,
        memory_id: str,
        source_id: str,
        transform: str = "extracted_from",
        label: str = "",
    ) -> ProvenanceNode:
        """Link a final memory record to its immediate source node."""
        src = self._graph.find_node_by_ref(source_id)
        if not src:
            # Create a minimal source node if not already tracked.
            src = self._ensure_node(ProvenanceNodeKind.EXTRACTION, source_id, source_id)
        tgt = self._ensure_node(ProvenanceNodeKind.MEMORY, memory_id, label or f"memory:{memory_id}")
        self._graph.add_edge(ProvenanceEdge(
            source_node_id=src.node_id,
            target_node_id=tgt.node_id,
            transform=transform,
        ))
        return tgt

    def explain(self, memory_id: str) -> str:
        return self._graph.why_do_i_believe(memory_id)

    def save(self, path: Path) -> None:
        self._graph.save(path)

    def load(self, path: Path) -> None:
        self._graph.load(path)

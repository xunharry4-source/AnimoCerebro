"""
Deep Recall Engine
-----------------
Provides a lightweight in‑memory knowledge‑graph built from memory records.
Supports BFS, DFS and shortest‑path queries with optional path‑explanation.
"""

from __future__ import annotations

import collections
import heapq
from datetime import datetime
from typing import Iterable, List, Dict, Tuple, Set

from pydantic import BaseModel, Field, ConfigDict

# ---------------------------------------------------------------------------
# Graph models
# ---------------------------------------------------------------------------

class MemoryNode(BaseModel):
    """Immutable representation of a memory node in the graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str = Field(..., min_length=1)
    # Additional optional metadata can be added here (title, tags, etc.)

class MemoryEdge(BaseModel):
    """Directed edge between two memory nodes.

    weight: optional numeric value used for ranking (default 1.0).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(..., min_length=1)
    target_id: str = Field(..., min_length=1)
    weight: float = Field(default=1.0, ge=0.0)
    created_at: datetime | None = None

# ---------------------------------------------------------------------------
# Engine implementation
# ---------------------------------------------------------------------------

class DeepRecallEngine:
    """Builds and queries a memory graph.

    The engine is deliberately lightweight – it stores adjacency lists in plain
    Python dicts, which is sufficient for the required ≤ 100 K node graphs.
    """

    def __init__(self) -> None:
        # memory_id → MemoryNode
        self._nodes: Dict[str, MemoryNode] = {}
        # adjacency list: source_id → list[MemoryEdge]
        self._out_edges: Dict[str, List[MemoryEdge]] = collections.defaultdict(list)
        # reverse adjacency: target_id → list[MemoryEdge]
        self._in_edges: Dict[str, List[MemoryEdge]] = collections.defaultdict(list)

    # ---------------------------------------------------------------------
    # Public construction API
    # ---------------------------------------------------------------------
    def add_node(self, node: MemoryNode) -> None:
        self._nodes[node.memory_id] = node

    def add_edge(self, edge: MemoryEdge) -> None:
        if edge.source_id not in self._nodes or edge.target_id not in self._nodes:
            # silently ignore edges referencing unknown nodes – they will be
            # filtered out during traversal.
            return
        self._out_edges[edge.source_id].append(edge)
        self._in_edges[edge.target_id].append(edge)

    def bulk_load(self, records: Iterable[dict]) -> None:
        """Populate the graph from a collection of memory records.

        Expected dict keys:
            - ``memory_id`` (str)
            - ``source_refs`` (list[str]) – outgoing references
            - ``target_refs`` (list[str]) – incoming references (optional)
        """
        for rec in records:
            mid = str(rec.get("memory_id"))
            node = MemoryNode(memory_id=mid)
            self.add_node(node)
        for rec in records:
            src = str(rec.get("memory_id"))
            for tgt in rec.get("source_refs", []):
                edge = MemoryEdge(source_id=src, target_id=str(tgt))
                self.add_edge(edge)
            # also handle explicit ``target_refs`` if present
            for tgt in rec.get("target_refs", []):
                edge = MemoryEdge(source_id=str(tgt), target_id=src)
                self.add_edge(edge)

    # ---------------------------------------------------------------------
    # Traversal APIs
    # ---------------------------------------------------------------------
    def bfs(self, start_id: str, max_hops: int = 3) -> List[List[str]]:
        """Breadth‑first search returning all paths up to ``max_hops``.

        Each path is a list of memory IDs beginning with ``start_id``.
        """
        if start_id not in self._nodes:
            return []
        results: List[List[str]] = []
        queue: collections.deque[Tuple[List[str], Set[str]]] = collections.deque()
        queue.append(([start_id], {start_id}))
        while queue:
            path, visited = queue.popleft()
            current = path[-1]
            if len(path) - 1 >= max_hops:
                continue
            for edge in self._out_edges.get(current, []):
                nxt = edge.target_id
                if nxt in visited:
                    continue
                new_path = path + [nxt]
                results.append(new_path)
                queue.append((new_path, visited | {nxt}))
        return results

    def dfs(self, start_id: str, max_hops: int = 3) -> List[List[str]]:
        """Depth‑first search returning all paths up to ``max_hops``."""
        if start_id not in self._nodes:
            return []
        results: List[List[str]] = []
        stack: List[Tuple[List[str], Set[str]]] = []
        stack.append(([start_id], {start_id}))
        while stack:
            path, visited = stack.pop()
            current = path[-1]
            if len(path) - 1 >= max_hops:
                continue
            for edge in self._out_edges.get(current, []):
                nxt = edge.target_id
                if nxt in visited:
                    continue
                new_path = path + [nxt]
                results.append(new_path)
                stack.append((new_path, visited | {nxt}))
        return results

    def shortest_path(self, start_id: str, goal_id: str) -> List[str] | None:
        """Dijkstra‑style shortest‑weight path.

        Returns a list of memory IDs from ``start_id`` to ``goal_id`` or ``None``
        if no path exists.
        """
        if start_id not in self._nodes or goal_id not in self._nodes:
            return None
        # priority queue of (cumulative_weight, current_id, path_so_far)
        heap: List[Tuple[float, str, List[str]]] = [(0.0, start_id, [start_id])]
        visited: Set[str] = set()
        while heap:
            cum_w, cur, path = heapq.heappop(heap)
            if cur == goal_id:
                return path
            if cur in visited:
                continue
            visited.add(cur)
            for edge in self._out_edges.get(cur, []):
                if edge.target_id in visited:
                    continue
                heapq.heappush(heap, (cum_w + edge.weight, edge.target_id, path + [edge.target_id]))
        return None

    # ---------------------------------------------------------------------
    # Explanation helper
    # ---------------------------------------------------------------------
    def explain_path(self, path: List[str]) -> str:
        """Return a human‑readable explanation for a given path.

        Example output:
            "Memory A → (ref) → Memory B → (ref) → Memory C"
        """
        if not path:
            return ""
        parts = []
        for i, mid in enumerate(path):
            parts.append(f"Memory {mid}")
            if i < len(path) - 1:
                parts.append("→ (ref) →")
        return " ".join(parts)

# ---------------------------------------------------------------------------
# Convenience factory used by the retrieval router
# ---------------------------------------------------------------------------

def build_engine_from_service(service) -> DeepRecallEngine:
    """Utility to build a graph from an ``EnhancedMemoryService`` instance.

    The service must implement ``list_all_records()`` returning an iterable of
    dict‑like objects with ``memory_id`` and ``source_refs`` keys.
    """
    engine = DeepRecallEngine()
    records = service.list_all_records()
    engine.bulk_load(records)
    return engine

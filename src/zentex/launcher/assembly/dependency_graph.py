from __future__ import annotations
"""
ServiceDependencyGraph — canonical startup dependency order for zentex services.

Uses Kahn's algorithm for topological sort and includes cycle detection.
"""


from collections import deque
from dataclasses import dataclass, field


@dataclass
class ServiceNode:
    """A single node in the dependency graph."""

    name: str
    dependencies: list[str] = field(default_factory=list)


class ServiceDependencyGraph:
    """Encodes the canonical service dependency graph and provides ordering utilities."""

    # Canonical dependency definitions — order within this list is irrelevant;
    # topological_sort() determines the correct startup sequence.
    NODES: list[ServiceNode] = [
        ServiceNode("foundation", []),
        ServiceNode("environment", ["foundation"]),
        ServiceNode("llm", ["foundation"]),
        ServiceNode("memory", ["foundation"]),
        ServiceNode("audit", ["foundation"]),
        ServiceNode("safety", ["foundation", "memory"]),
        ServiceNode("plugins", ["foundation"]),
        ServiceNode("cognition", ["foundation", "llm", "memory"]),
        ServiceNode("tasks", ["foundation", "memory"]),
        ServiceNode("reflection", ["foundation", "memory", "tasks"]),
        ServiceNode("learning", ["foundation", "llm", "memory"]),
        ServiceNode("agents", ["foundation", "kernel"]),
        ServiceNode("kernel", ["foundation"]),
        ServiceNode("mcp", ["foundation", "llm"]),
        ServiceNode("cli", ["foundation", "memory", "llm"]),
        ServiceNode("web_console", ["kernel", "foundation"]),
    ]

    def __init__(self) -> None:
        # Build a lookup dict for fast access.
        self._nodes: dict[str, ServiceNode] = {n.name: n for n in self.NODES}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def topological_sort(self) -> list[str]:
        """Return service names in a valid startup order (Kahn's algorithm).

        Raises RuntimeError if the graph contains a cycle (use detect_cycles()
        to inspect before sorting if you want a clean error message).
        """
        # in-degree map
        in_degree: dict[str, int] = {n: 0 for n in self._nodes}
        adjacency: dict[str, list[str]] = {n: [] for n in self._nodes}

        for node in self._nodes.values():
            for dep in node.dependencies:
                if dep in adjacency:
                    adjacency[dep].append(node.name)
                    in_degree[node.name] += 1

        queue: deque[str] = deque(
            name for name, deg in in_degree.items() if deg == 0
        )
        result: list[str] = []

        while queue:
            current = queue.popleft()
            result.append(current)
            for successor in adjacency[current]:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if len(result) != len(self._nodes):
            remaining = [n for n in self._nodes if n not in result]
            raise RuntimeError(
                f"Cycle detected in service dependency graph. "
                f"Unresolvable nodes: {remaining}"
            )

        return result

    def detect_cycles(self) -> list[str]:
        """Return the names of nodes involved in a cycle, or an empty list if none."""
        try:
            self.topological_sort()
            return []
        except RuntimeError:
            # Identify nodes that would not appear in a complete sort.
            in_degree: dict[str, int] = {n: 0 for n in self._nodes}
            adjacency: dict[str, list[str]] = {n: [] for n in self._nodes}

            for node in self._nodes.values():
                for dep in node.dependencies:
                    if dep in adjacency:
                        adjacency[dep].append(node.name)
                        in_degree[node.name] += 1

            queue: deque[str] = deque(
                name for name, deg in in_degree.items() if deg == 0
            )
            visited: set[str] = set()

            while queue:
                current = queue.popleft()
                visited.add(current)
                for successor in adjacency[current]:
                    in_degree[successor] -= 1
                    if in_degree[successor] == 0:
                        queue.append(successor)

            return [n for n in self._nodes if n not in visited]

    def dependencies_of(self, name: str) -> list[str]:
        """Return the direct dependencies of a named service."""
        node = self._nodes.get(name)
        return node.dependencies if node is not None else []

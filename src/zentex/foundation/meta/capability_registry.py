"""Capability entry definitions and the default capability directory."""

from pydantic import BaseModel, ConfigDict

from zentex.foundation.meta.feature_family import FeatureFamily


class CapabilityEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    family: FeatureFamily
    protocol_version: str
    required: bool = True
    description: str = ""


class CapabilityDirectory:
    """In-memory registry of capability entries."""

    def __init__(self, entries: list[CapabilityEntry]) -> None:
        self._entries: list[CapabilityEntry] = list(entries)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def by_family(self, family: FeatureFamily) -> list[CapabilityEntry]:
        return [e for e in self._entries if e.family == family]

    def all_entries(self) -> list[CapabilityEntry]:
        return list(self._entries)

    def required_entries(self) -> list[CapabilityEntry]:
        return [e for e in self._entries if e.required]

    def to_dict(self) -> dict:
        return {
            "entries": [
                {
                    "name": e.name,
                    "family": e.family.value,
                    "protocol_version": e.protocol_version,
                    "required": e.required,
                    "description": e.description,
                }
                for e in self._entries
            ]
        }

    def version_diff(self, other: "CapabilityDirectory") -> dict:
        """Return which entries were added or removed comparing self to other.

        Added   = present in *other* but not in self.
        Removed = present in self but not in *other*.
        """
        self_names: set[str] = {e.name for e in self._entries}
        other_names: set[str] = {e.name for e in other._entries}

        added = [e.name for e in other._entries if e.name not in self_names]
        removed = [e.name for e in self._entries if e.name not in other_names]
        return {"added": added, "removed": removed}

    def __repr__(self) -> str:  # pragma: no cover
        return f"CapabilityDirectory(entries={len(self._entries)})"


# ---------------------------------------------------------------------------
# Default capability directory — at least one entry per FeatureFamily
# ---------------------------------------------------------------------------

DEFAULT_CAPABILITY_DIRECTORY: CapabilityDirectory = CapabilityDirectory(
    entries=[
        CapabilityEntry(
            name="execution.core",
            family=FeatureFamily.execution,
            protocol_version="1.0",
            required=True,
            description="Core action dispatch and execution orchestration.",
        ),
        CapabilityEntry(
            name="sensory.ingest",
            family=FeatureFamily.sensory,
            protocol_version="1.0",
            required=True,
            description="Raw signal ingestion from environment adapters.",
        ),
        CapabilityEntry(
            name="simulation.counterfactual",
            family=FeatureFamily.simulation,
            protocol_version="1.0",
            required=False,
            description="Counterfactual branch simulation before committing actions.",
        ),
        CapabilityEntry(
            name="cognition.reasoning",
            family=FeatureFamily.cognition,
            protocol_version="1.0",
            required=True,
            description="Higher-order reasoning and plan generation.",
        ),
        CapabilityEntry(
            name="memory.working",
            family=FeatureFamily.memory,
            protocol_version="1.0",
            required=True,
            description="Short-term working memory slot management.",
        ),
        CapabilityEntry(
            name="safety.policy",
            family=FeatureFamily.safety,
            protocol_version="1.0",
            required=True,
            description="Safety policy evaluation and action blocking.",
        ),
        CapabilityEntry(
            name="reflection.self_monitor",
            family=FeatureFamily.reflection,
            protocol_version="1.0",
            required=False,
            description="Introspective monitoring of system state and calibration.",
        ),
        CapabilityEntry(
            name="task.scheduler",
            family=FeatureFamily.task,
            protocol_version="1.0",
            required=True,
            description="Task decomposition and scheduling.",
        ),
        CapabilityEntry(
            name="learning.online",
            family=FeatureFamily.learning,
            protocol_version="1.0",
            required=False,
            description="Online adaptation from interaction feedback.",
        ),
        CapabilityEntry(
            name="agent.coordinator",
            family=FeatureFamily.agent,
            protocol_version="1.0",
            required=False,
            description="Sub-agent creation and lifecycle coordination.",
        ),
        CapabilityEntry(
            name="tool.registry",
            family=FeatureFamily.tool,
            protocol_version="1.0",
            required=True,
            description="External tool registration and invocation.",
        ),
        CapabilityEntry(
            name="audit.logger",
            family=FeatureFamily.audit,
            protocol_version="1.0",
            required=True,
            description="Immutable audit log persistence.",
        ),
    ]
)

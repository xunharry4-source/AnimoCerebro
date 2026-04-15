"""PhaseRegistry — ordered configuration for the 9 processing phases."""

from dataclasses import dataclass, field


@dataclass
class PhaseConfig:
    """Configuration for a single processing phase."""

    name: str
    timeout_seconds: int = 30
    skippable: bool = False
    degradable: bool = True


NINE_PHASES: list[PhaseConfig] = [
    PhaseConfig(name="observe",            timeout_seconds=20, skippable=False, degradable=True),
    PhaseConfig(name="frame",              timeout_seconds=15, skippable=False, degradable=True),
    PhaseConfig(name="working_state",      timeout_seconds=10, skippable=True,  degradable=True),
    PhaseConfig(name="cognitive_risks",    timeout_seconds=20, skippable=True,  degradable=True),
    PhaseConfig(name="simulate",           timeout_seconds=30, skippable=True,  degradable=True),
    PhaseConfig(name="metacognition",      timeout_seconds=15, skippable=True,  degradable=True),
    PhaseConfig(name="cognitive_tools",    timeout_seconds=30, skippable=True,  degradable=True),
    PhaseConfig(name="decision_synthesis", timeout_seconds=30, skippable=False, degradable=True),
    PhaseConfig(name="consolidate",        timeout_seconds=20, skippable=True,  degradable=True),
]


class PhaseRegistry:
    """Registry of ordered phase configurations."""

    def __init__(self) -> None:
        self._phases: dict[str, PhaseConfig] = {p.name: p for p in NINE_PHASES}

    def get(self, name: str) -> PhaseConfig | None:
        """Return the PhaseConfig for *name*, or None if not registered."""
        return self._phases.get(name)

    def ordered(self) -> list[PhaseConfig]:
        """Return the phases in canonical execution order."""
        return list(NINE_PHASES)

    def names(self) -> list[str]:
        """Return phase names in canonical execution order."""
        return [p.name for p in NINE_PHASES]

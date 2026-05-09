"""FeatureFamily enum and associated metadata registry."""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class FeatureFamily(str, Enum):
    execution = "execution"
    sensory = "sensory"
    simulation = "simulation"
    cognition = "cognition"
    memory = "memory"
    safety = "safety"
    reflection = "reflection"
    task = "task"
    learning = "learning"
    agent = "agent"
    tool = "tool"
    audit = "audit"


class FeatureFamilyMeta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    family: FeatureFamily
    display_name: str
    description: str
    max_plugins: int
    priority: int  # 1 = highest priority


FEATURE_FAMILY_REGISTRY: dict[FeatureFamily, FeatureFamilyMeta] = {
    FeatureFamily.execution: FeatureFamilyMeta(
        family=FeatureFamily.execution,
        display_name="Execution",
        description="Handles action dispatch, orchestration and execution of operations.",
        max_plugins=10,
        priority=1,
    ),
    FeatureFamily.sensory: FeatureFamilyMeta(
        family=FeatureFamily.sensory,
        display_name="Sensory",
        description="Ingests and sanitises signals from the environment.",
        max_plugins=8,
        priority=2,
    ),
    FeatureFamily.simulation: FeatureFamilyMeta(
        family=FeatureFamily.simulation,
        display_name="Simulation",
        description="Runs counterfactual and predictive simulations before action.",
        max_plugins=6,
        priority=2,
    ),
    FeatureFamily.cognition: FeatureFamilyMeta(
        family=FeatureFamily.cognition,
        display_name="Cognition",
        description="Higher-order reasoning, planning and decision-making.",
        max_plugins=8,
        priority=1,
    ),
    FeatureFamily.memory: FeatureFamilyMeta(
        family=FeatureFamily.memory,
        display_name="Memory",
        description="Working, episodic and semantic memory management.",
        max_plugins=20,
        priority=2,
    ),
    FeatureFamily.safety: FeatureFamilyMeta(
        family=FeatureFamily.safety,
        display_name="Safety",
        description="Enforces safety policies and blocks unsafe actions.",
        max_plugins=5,
        priority=1,
    ),
    FeatureFamily.reflection: FeatureFamilyMeta(
        family=FeatureFamily.reflection,
        display_name="Reflection",
        description="Self-monitoring, introspection and calibration loops.",
        max_plugins=6,
        priority=3,
    ),
    FeatureFamily.task: FeatureFamilyMeta(
        family=FeatureFamily.task,
        display_name="Task",
        description="Task decomposition, scheduling and lifecycle management.",
        max_plugins=12,
        priority=2,
    ),
    FeatureFamily.learning: FeatureFamilyMeta(
        family=FeatureFamily.learning,
        display_name="Learning",
        description="Online and offline adaptation from experience.",
        max_plugins=8,
        priority=3,
    ),
    FeatureFamily.agent: FeatureFamilyMeta(
        family=FeatureFamily.agent,
        display_name="Agent",
        description="Sub-agent creation, management and coordination.",
        max_plugins=10,
        priority=2,
    ),
    FeatureFamily.tool: FeatureFamilyMeta(
        family=FeatureFamily.tool,
        display_name="Tool",
        description="External tool integrations and plugin wrappers.",
        max_plugins=50,
        priority=3,
    ),
    FeatureFamily.audit: FeatureFamilyMeta(
        family=FeatureFamily.audit,
        display_name="Audit",
        description="Immutable audit logging and compliance recording.",
        max_plugins=5,
        priority=1,
    ),
}


def get_family_meta(family: FeatureFamily) -> FeatureFamilyMeta:
    """Return the FeatureFamilyMeta for a given FeatureFamily."""
    return FEATURE_FAMILY_REGISTRY[family]

"""Specifications package — exports all abstract spec types."""

from zentex.foundation.specs.cognitive_tool_spec import (
    CognitiveToolSpec,
    LogicalCognitiveToolSpec,
)
from zentex.foundation.specs.execution_spec import (
    ExecutionDomainLevel,
    ExecutionDomainSpec,
    ExecutionPluginSpec,
)
from zentex.foundation.specs.plugin_spec import (
    PluginCapabilitySpec,
    PluginIsolationSpec,
    PluginLifecycleSpec,
)
from zentex.foundation.specs.sensory_spec import (
    SignalIngestSpec,
    SignalInterpretSpec,
    SignalSanitizeSpec,
)
from zentex.foundation.specs.simulation_spec import SimulationPluginSpec

__all__ = [
    # plugin_spec
    "PluginLifecycleSpec",
    "PluginCapabilitySpec",
    "PluginIsolationSpec",
    # execution_spec
    "ExecutionDomainLevel",
    "ExecutionPluginSpec",
    "ExecutionDomainSpec",
    # sensory_spec
    "SignalIngestSpec",
    "SignalSanitizeSpec",
    "SignalInterpretSpec",
    # simulation_spec
    "SimulationPluginSpec",
    # cognitive_tool_spec
    "CognitiveToolSpec",
    "LogicalCognitiveToolSpec",
]

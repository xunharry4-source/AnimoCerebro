from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from typing import Any


UTC = timezone.utc

CORE_MODULES: tuple[dict[str, Any], ...] = (
    {
        "module_id": "cognition",
        "module_name": "核心认知中枢",
        "responsibilities": ["single_turn_thinking", "working_memory", "metacognitive_dispatch"],
        "service_boundary": "zentex.cognition.service.CognitionService",
    },
    {
        "module_id": "memory",
        "module_name": "记忆与自我演化",
        "responsibilities": ["identity_anchor", "experience_persistence", "layered_memory"],
        "service_boundary": "zentex.memory.service.MemoryService",
    },
    {
        "module_id": "bridge",
        "module_name": "宿主桥接与感知执行",
        "responsibilities": ["host_bridge", "sensory_adaptation", "execution_routing", "safety_gate_entry"],
        "service_boundary": "zentex.environment.service.EnvironmentAwarenessService",
    },
    {
        "module_id": "safety",
        "module_name": "安全风控与人类监督",
        "responsibilities": ["cloud_audit", "human_intervention", "supervision_channel"],
        "service_boundary": "zentex.safety.service.SafetyService",
    },
    {
        "module_id": "network",
        "module_name": "组织协作网络",
        "responsibilities": ["agent_coordination", "mcp_integration", "cli_integration", "experience_exchange"],
        "service_boundary": "zentex.agents.service.AgentCoordinationService",
    },
    {
        "module_id": "runtime",
        "module_name": "弹性运行时底座",
        "responsibilities": ["session_lifecycle", "background_queue", "runtime_snapshot", "transcript_persistence"],
        "service_boundary": "zentex.kernel.service.KernelService",
    },
)


def build_core_architecture_snapshot(kernel_service: Any) -> dict[str, Any]:
    phase_registry = getattr(kernel_service, "_phase_registry", None)
    phase_names = phase_registry.names() if callable(getattr(phase_registry, "names", None)) else []
    active_sessions = (
        kernel_service.list_active_sessions()
        if callable(getattr(kernel_service, "list_active_sessions", None))
        else []
    )

    modules = [_module_record(module) for module in CORE_MODULES]
    required_component_status = _required_component_status(kernel_service, phase_names=phase_names)

    return {
        "feature_code": "G2",
        "status": "complete" if all(item["present"] for item in required_component_status) else "incomplete",
        "created_at": datetime.now(UTC).isoformat(),
        "module_count": len(modules),
        "modules": modules,
        "runtime_container": {
            "name": "BrainRuntime",
            "implementation": "zentex.kernel.service.KernelService",
            "holds_shared_dependencies": True,
            "injected_dependency_slots": [
                "_environment_service",
                "_cognition_service",
                "_safety_service",
                "_plugins_service",
                "_memory_service",
                "_audit_service",
                "_llm_service",
                "_foundation_service",
                "_agent_service",
                "_cli_service",
                "_mcp_service",
                "_reflection_service",
                "_learning_service",
                "_task_service",
            ],
        },
        "session_container": {
            "name": "BrainSession",
            "implementation": "zentex.kernel.session_domain.KernelSession",
            "state_container": "zentex.kernel.service._SessionState",
            "active_session_count": len(active_sessions),
            "active_session_ids": list(active_sessions),
            "cross_turn_continuity": True,
        },
        "think_loop": {
            "name": "ThinkLoop",
            "implementation": "zentex.kernel.flow_domain.think_loop.ThinkLoop",
            "stateless": True,
            "phase_names": phase_names,
            "registered_phase_count": len(phase_names),
            "nominal_nine_stage_contract": True,
            "supplemental_subphases": [name for name in phase_names if name == "drive"],
        },
        "cognitive_tool_orchestrator": {
            "name": "CognitiveToolOrchestrator",
            "implementation": "plugins.service.invoke_cognitive_tools",
            "kernel_bridge_method": "invoke_cognitive_tools",
            "service_boundary_only": True,
        },
        "transcript_store": {
            "name": "BrainTranscriptStore",
            "implementation": "zentex.kernel.state_domain.TranscriptStore",
            "session_scoped": True,
            "continuity_foundation": True,
        },
        "required_components": required_component_status,
        "architecture_rules": {
            "models_in_core": True,
            "external_modules_use_service_boundary": True,
            "think_loop_persists_no_long_term_state": True,
            "web_console_business_logic": False,
        },
    }


def _module_record(module: dict[str, Any]) -> dict[str, Any]:
    service_boundary = str(module["service_boundary"])
    return {
        **module,
        "service_boundary_importable": _is_importable(service_boundary),
    }


def _is_importable(path: str) -> bool:
    module_name, _, attr = path.rpartition(".")
    if not module_name or not attr:
        return False
    module = import_module(module_name)
    return hasattr(module, attr)


def _required_component_status(kernel_service: Any, *, phase_names: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "component": "BrainRuntime",
            "present": kernel_service.__class__.__name__ == "KernelService",
            "evidence": kernel_service.__class__.__module__,
        },
        {
            "component": "BrainSession",
            "present": hasattr(kernel_service, "_lifecycle") and hasattr(kernel_service, "_session_states"),
            "evidence": "SessionLifecycleManager + _SessionState",
        },
        {
            "component": "ThinkLoop",
            "present": hasattr(kernel_service, "_think_loop") and "observe" in phase_names and "decision_synthesis" in phase_names,
            "evidence": ",".join(phase_names),
        },
        {
            "component": "CognitiveToolOrchestrator",
            "present": callable(getattr(kernel_service, "invoke_cognitive_tools", None)),
            "evidence": "KernelService.invoke_cognitive_tools",
        },
        {
            "component": "BrainTranscriptStore",
            "present": hasattr(kernel_service, "transcript_store"),
            "evidence": kernel_service.transcript_store.__class__.__name__,
        },
    ]

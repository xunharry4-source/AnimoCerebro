from __future__ import annotations

"""
Situation Interpreter / 态势解释器

Translates environmental changes into meaningful impacts on the agent's role, goals,
and cognitive strategy. Implements the situation interpretation layer from G8 specification.

将环境变化翻译为对代理角色、目标和认知策略的有意义影响。
实现 G8 规范中的态势解释层。
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.environment.models import (
    HealthStatus,
    MemoryPressureLevel,
    NetworkHealthStatus,
    PhysicalHostState,
    SituationImpact,
)


class SituationInterpreter:
    """
    Interprets environmental state and translates it into actionable insights.
    
    态势解释器，解释环境状态并将其转化为可操作的洞察。
    
    Analyzes physical host states and determines their impact on the agent's
    current role, active goals, and recommended cognitive modes. Provides
    risk assessments and action recommendations.
    
    分析物理宿主状态并确定其对代理当前角色、活动目标和推荐认知模式的影响。
    提供风险评估和行动建议。
    """
    
    def __init__(self) -> None:
        """Initialize the SituationInterpreter."""
        pass
    
    def interpret_host_state(
        self,
        host_state: PhysicalHostState,
        current_role: Optional[str] = None,
        active_goals: list[Optional[str]] = None,
        identity: Optional[dict[str, Any]] = None,
        nine_question_state: Optional[dict[str, Any]] = None,
    ) -> SituationImpact:
        """
        Interpret physical host state and determine impacts.
        
        解释物理宿主状态并确定影响。
        
        Args:
            host_state: Current physical host state
            current_role: Agent's current role (optional)
            active_goals: List of currently active goal IDs (optional)
            identity: Agent's identity kernel (optional)
            nine_question_state: Nine-Question baseline (optional)
            
        Returns:
            SituationImpact: Interpreted impacts and recommendations
            
        Logic:
            1. Assess resource constraints and their implications
            2. Determine if cognitive mode adjustment is needed
            3. Identify risks that require rational audit (G25)
            4. Generate specific recommendations for each detected issue
        """
        recommendations = []
        goal_impacts = []
        risk_level = "low"
        requires_audit = False
        reasoning_parts = []
        
        # AUTHENTIC GROUNDING: Incorporate cognitive risk from 9-questions
        if nine_question_state:
            nq_risk = nine_question_state.get("risk_level", 0.0)
            if nq_risk > 0.7:
                 risk_level = "high"
                 reasoning_parts.append(f"Cognitive baseline risk is elevated ({nq_risk:.2f}).")
                 requires_audit = True
                 recommendations.append("Prioritize cognitive integrity check (Audit)")
        
        # Analyze memory pressure
        if host_state.memory_pressure == MemoryPressureLevel.CRITICAL:
            recommendations.append("Switch to low-power cognitive mode immediately")
            recommendations.append("Suspend non-critical background tasks")
            goal_impacts.append("Memory critical: defer memory-intensive operations")
            risk_level = "critical"
            requires_audit = True
            reasoning_parts.append(
                f"Memory pressure is CRITICAL ({host_state.memory_used_ratio:.1%} used). "
                "System must reduce cognitive load to prevent failures."
            )
        elif host_state.memory_pressure == MemoryPressureLevel.HIGH:
            recommendations.append("Consider switching to shallow thinking mode")
            recommendations.append("Monitor memory usage closely")
            goal_impacts.append("Memory high: prefer lightweight operations")
            if risk_level != "critical":
                risk_level = "high"
            reasoning_parts.append(
                f"Memory pressure is HIGH ({host_state.memory_used_ratio:.1%} used). "
                "System should reduce resource consumption."
            )
        
        # Analyze network health
        if host_state.network_health == NetworkHealthStatus.OFFLINE:
            recommendations.append("Network offline: cannot perform external operations")
            recommendations.append("Queue network-dependent tasks for later execution")
            goal_impacts.append("Network unavailable: pause external communications")
            risk_level = "critical"
            requires_audit = True
            reasoning_parts.append(
                "Network is OFFLINE. External operations are impossible. "
                "System must operate in disconnected mode."
            )
        elif host_state.network_health == NetworkHealthStatus.DEGRADED:
            recommendations.append("Network degraded: expect intermittent connectivity")
            recommendations.append("Implement retry logic for network operations")
            goal_impacts.append("Network unstable: use cautious communication strategy")
            if risk_level not in ("critical", "high"):
                risk_level = "medium"
            reasoning_parts.append(
                "Network is DEGRADED. Connectivity may be unreliable. "
                "System should prepare for connection failures."
            )
        
        # Analyze CPU load
        if host_state.cpu_load_percent is not None and host_state.cpu_load_percent > 90:
            recommendations.append("CPU overloaded: reduce computational intensity")
            recommendations.append("Defer non-urgent processing tasks")
            goal_impacts.append("CPU saturated: minimize compute-heavy operations")
            if risk_level not in ("critical",):
                risk_level = "high"
            reasoning_parts.append(
                f"CPU load is very high ({host_state.cpu_load_percent:.1f}%). "
                "System should avoid additional computational burden."
            )
        elif host_state.cpu_load_percent is not None and host_state.cpu_load_percent > 70:
            recommendations.append("CPU load elevated: monitor for further increases")
            if risk_level == "low":
                risk_level = "medium"
            reasoning_parts.append(
                f"CPU load is elevated ({host_state.cpu_load_percent:.1f}%). "
                "System should be prepared to scale back if load increases."
            )
        
        # Analyze disk space
        if host_state.disk_usage_percent is not None and host_state.disk_usage_percent > 90:
            recommendations.append("Disk nearly full: clean up temporary files")
            recommendations.append("Avoid writing large files")
            goal_impacts.append("Disk space critical: limit file operations")
            if risk_level not in ("critical",):
                risk_level = "high"
            requires_audit = True
            reasoning_parts.append(
                f"Disk usage is critical ({host_state.disk_usage_percent:.1f}%). "
                "System must avoid operations that consume significant disk space."
            )
        elif host_state.disk_usage_percent is not None and host_state.disk_usage_percent > 80:
            recommendations.append("Disk usage high: plan cleanup operations")
            if risk_level == "low":
                risk_level = "medium"
            reasoning_parts.append(
                f"Disk usage is high ({host_state.disk_usage_percent:.1f}%). "
                "System should prepare for potential storage limitations."
            )
        
        # Determine recommended cognitive mode
        recommended_mode = self._determine_cognitive_mode(host_state)
        if recommended_mode != "standard":
            recommendations.append(f"Switch cognitive mode to: {recommended_mode}")
        
        # Build role impact assessment
        role_impact = self._assess_role_impact(host_state, current_role)
        
        # Compile reasoning
        reasoning = " | ".join(reasoning_parts) if reasoning_parts else "No significant issues detected."
        
        return SituationImpact(
            interpretation_id=str(uuid4()),
            source_host_state=host_state,
            role_impact=role_impact,
            goal_impacts=goal_impacts,
            recommended_cognitive_mode=recommended_mode,
            recommended_actions=recommendations,
            risk_level=risk_level,
            requires_rational_audit=requires_audit,
            reasoning=reasoning,
        )
    
    def _determine_cognitive_mode(self, host_state: PhysicalHostState) -> str:
        """
        Determine appropriate cognitive mode based on host state.
        
        根据宿主状态确定适当的认知模式。
        
        Returns:
            Cognitive mode recommendation: 'emergency', 'shallow', 'standard', or 'deep'
        """
        # Emergency mode for critical conditions
        if (
            host_state.memory_pressure == MemoryPressureLevel.CRITICAL
            or host_state.network_health == NetworkHealthStatus.OFFLINE
            or host_state.overall_health == HealthStatus.CRITICAL
        ):
            return "emergency"
        
        # Shallow mode for degraded conditions
        if (
            host_state.memory_pressure in (MemoryPressureLevel.HIGH, MemoryPressureLevel.MEDIUM)
            or host_state.network_health == NetworkHealthStatus.DEGRADED
            or (host_state.cpu_load_percent is not None and host_state.cpu_load_percent > 80)
        ):
            return "shallow"
        
        # Deep mode only when resources are abundant
        if (
            host_state.memory_pressure == MemoryPressureLevel.NORMAL
            and host_state.network_health == NetworkHealthStatus.HEALTHY
            and (host_state.cpu_load_percent is None or host_state.cpu_load_percent < 50)
        ):
            return "deep"
        
        # Standard mode for normal conditions
        return "standard"
    
    def _assess_role_impact(
        self,
        host_state: PhysicalHostState,
        current_role: Optional[str],
        identity: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Assess how environmental state impacts the agent's current role.
        
        评估环境状态如何影响代理的当前角色。
        
        Args:
            host_state: Current physical host state
            current_role: Agent's current role
            identity: Agent's identity kernel (optional)
            
        Returns:
            Description of role impact, or None if no significant impact
        """
        if current_role is None:
            return None
        
        impacts = []
        
        # AUTHENTIC GROUNDING: check if context matches mission
        if identity and identity.get("mission_baseline"):
             impacts.append(f"Mission Check: Active mission '{identity['mission_baseline']}' is the primary driver for role '{current_role}'.")
        
        if host_state.is_degraded():
            impacts.append(
                f"Role '{current_role}' execution may be impaired due to degraded system state"
            )
        
        if host_state.should_switch_to_low_power_mode():
            impacts.append(
                f"Role '{current_role}' should operate in reduced-capacity mode"
            )
        
        if host_state.network_health == NetworkHealthStatus.OFFLINE:
            impacts.append(
                f"Role '{current_role}' cannot perform network-dependent activities"
            )
        
        return "; ".join(impacts) if impacts else None

from __future__ import annotations

"""
Environment Awareness Data Models / 环境感知数据模型

Defines all data structures for environment perception, including physical host states,
context snapshots, situation interpretations, and sensory signals.

定义环境感知的所有数据结构，包括物理宿主状态、上下文快照、态势解释和感官信号。
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


class HealthStatus(str, Enum):
    """Health status enumeration for various system components."""
    
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    OFFLINE = "offline"


class MemoryPressureLevel(str, Enum):
    """Memory pressure classification levels."""
    
    NORMAL = "normal"       # < 65% used
    MEDIUM = "medium"       # 65-80% used
    HIGH = "high"           # 80-90% used
    CRITICAL = "critical"   # >= 90% used
    UNKNOWN = "unknown"


class NetworkHealthStatus(str, Enum):
    """Network connectivity health status."""
    
    HEALTHY = "healthy"     # Active non-loopback interface
    DEGRADED = "degraded"   # Configured but inactive
    OFFLINE = "offline"     # No configured interfaces
    UNKNOWN = "unknown"


class PhysicalHostState(BaseModel):
    """
    Physical host state snapshot capturing machine resource and environment health.
    
    物理宿主状态快照，记录机器资源与环境健康情况。
    
    This model represents a point-in-time view of the physical host's resource utilization
    and health metrics. It is sampled by EnvironmentScouter and used for decision-making
    about cognitive modes and resource allocation.
    """
    
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    timestamp: datetime = Field(default_factory=utc_now)
    hostname: str = Field(min_length=1, description="Host machine name")
    platform: str = Field(min_length=1, description="Operating system platform")
    python_version: str = Field(min_length=1, description="Python runtime version")
    
    # Memory metrics
    memory_pressure: MemoryPressureLevel = Field(
        default=MemoryPressureLevel.UNKNOWN,
        description="Memory usage pressure level"
    )
    memory_used_ratio: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Memory usage ratio (0.0-1.0)"
    )
    memory_total_bytes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Total memory in bytes"
    )
    memory_available_bytes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Available memory in bytes"
    )
    
    # CPU metrics
    cpu_load_percent: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="CPU load percentage (0-100+)"
    )
    cpu_count: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of CPU cores"
    )
    
    # Disk metrics
    disk_usage_percent: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Disk usage percentage"
    )
    disk_free_bytes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Free disk space in bytes"
    )
    
    # Network metrics
    network_health: NetworkHealthStatus = Field(
        default=NetworkHealthStatus.UNKNOWN,
        description="Network connectivity health status"
    )
    network_interfaces_configured: bool = Field(
        default=False,
        description="Whether non-loopback interfaces are configured"
    )
    network_interfaces_active: bool = Field(
        default=False,
        description="Whether any non-loopback interfaces are active"
    )
    
    # Overall assessment
    overall_health: HealthStatus = Field(
        default=HealthStatus.UNKNOWN,
        description="Overall host health assessment"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="List of warning messages"
    )
    sampling_source: str = Field(
        default="local_host",
        description="Source of the sampling data"
    )
    
    def is_degraded(self) -> bool:
        """Check if host is in degraded state."""
        return self.overall_health in (
            HealthStatus.DEGRADED,
            HealthStatus.CRITICAL,
            HealthStatus.OFFLINE
        )
    
    def should_switch_to_low_power_mode(self) -> bool:
        """Determine if cognitive mode should switch to low-power."""
        return (
            self.memory_pressure in (MemoryPressureLevel.HIGH, MemoryPressureLevel.CRITICAL)
            or self.overall_health == HealthStatus.CRITICAL
        )


class WorkspaceChange(BaseModel):
    """
    Represents a detected change in the workspace environment.
    
    表示在工作区环境中检测到的变化。
    """
    
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    change_id: str = Field(min_length=1, description="Unique change identifier")
    timestamp: datetime = Field(default_factory=utc_now)
    change_type: str = Field(
        min_length=1,
        description="Type of change: file_created, file_modified, file_deleted, etc."
    )
    path: str = Field(min_length=1, description="Affected file or directory path")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the change"
    )
    significance_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Significance score of this change (0-1)"
    )


class ContextSnapshot(BaseModel):
    """
    Context snapshot recording comprehensive state at a point in time.
    
    上下文快照，记录某一时刻环境、任务、角色和记忆的综合状态。
    
    Extends over time to form a time-series record of the brain's operational context.
    """
    
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    snapshot_id: str = Field(min_length=1, description="Unique snapshot identifier")
    timestamp: datetime = Field(default_factory=utc_now)
    session_id: Optional[str] = Field(default=None, description="Associated session ID")
    turn_id: Optional[str] = Field(default=None, description="Associated think loop turn ID")
    
    # Environmental state
    host_state: Optional[PhysicalHostState] = Field(
        default=None,
        description="Physical host state at snapshot time"
    )
    workspace_changes: list[WorkspaceChange] = Field(
        default_factory=list,
        description="Recent workspace changes"
    )
    
    # Cognitive state references
    active_goals: list[str] = Field(
        default_factory=list,
        description="IDs of currently active goals"
    )
    working_memory_summary: Optional[str] = Field(
        default=None,
        description="Summary of working memory state"
    )
    
    # Role and identity context
    current_role: Optional[str] = Field(
        default=None,
        description="Current agent role"
    )
    identity_anchor_ref: Optional[str] = Field(
        default=None,
        description="Reference to identity kernel"
    )
    
    # Metadata
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for categorization and search"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional contextual metadata"
    )


class SituationImpact(BaseModel):
    """
    Interpreted impact of environmental changes on role and goals.
    
    环境变化对角色和目标的解释性影响。
    
    The SituationInterpreter translates raw environmental data into meaningful
    impacts on the agent's current role, goals, and cognitive strategy.
    """
    
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    interpretation_id: str = Field(min_length=1, description="Unique interpretation ID")
    timestamp: datetime = Field(default_factory=utc_now)
    
    # Source reference
    source_snapshot_id: Optional[str] = Field(
        default=None,
        description="Reference to source context snapshot"
    )
    source_host_state: Optional[PhysicalHostState] = Field(
        default=None,
        description="Reference to source host state"
    )
    
    # Impact assessments
    role_impact: Optional[str] = Field(
        default=None,
        description="How environment affects current role execution"
    )
    goal_impacts: list[str] = Field(
        default_factory=list,
        description="Impacts on current goals"
    )
    
    # Recommendations
    recommended_cognitive_mode: Optional[str] = Field(
        default=None,
        description="Suggested cognitive mode (e.g., 'shallow', 'deep', 'emergency')"
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="Recommended actions to take"
    )
    
    # Risk assessment
    risk_level: str = Field(
        default="low",
        description="Risk level: low, medium, high, critical"
    )
    requires_rational_audit: bool = Field(
        default=False,
        description="Whether rational audit (G25) should be triggered"
    )
    
    # Explanation
    reasoning: Optional[str] = Field(
        default=None,
        description="Explanation of the interpretation logic"
    )


class SanitizedSignal(BaseModel):
    """
    Sanitized sensory signal after injection filtering.
    
    经过注入过滤后的清洗感官信号。
    """
    
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    signal_id: str = Field(min_length=1, description="Unique signal identifier")
    timestamp: datetime = Field(default_factory=utc_now)
    
    original_fingerprint: str = Field(
        min_length=1,
        description="SHA256 fingerprint of original signal"
    )
    sanitized_content: str = Field(
        min_length=1,
        description="Sanitized signal content"
    )
    
    # Security assessment
    injection_risk: bool = Field(
        default=False,
        description="Whether prompt injection risk was detected"
    )
    redaction_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence of redacted content"
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in sanitization quality"
    )
    
    # Source tracking
    source_plugin_id: Optional[str] = Field(
        default=None,
        description="ID of the plugin that provided this signal"
    )
    source_kind: Optional[str] = Field(
        default=None,
        description="Kind of source (webhook, file, api, etc.)"
    )


class SourceConflictScore(BaseModel):
    """
    Conflict score between multiple information sources.
    
    多信息源之间的冲突评分。
    """
    
    model_config = ConfigDict(extra="forbid", frozen=True)
    
    conflict_id: str = Field(min_length=1, description="Unique conflict identifier")
    timestamp: datetime = Field(default_factory=utc_now)
    
    # Conflicting sources
    source_a: str = Field(min_length=1, description="First source identifier")
    source_b: str = Field(min_length=1, description="Second source identifier")
    
    # Conflict details
    conflict_type: str = Field(
        min_length=1,
        description="Type of conflict (value_mismatch, timing_conflict, etc.)"
    )
    conflict_field: str = Field(
        min_length=1,
        description="Field or metric where conflict occurred"
    )
    value_a: Any = Field(description="Value from source A")
    value_b: Any = Field(description="Value from source B")
    
    # Scoring
    conflict_severity: float = Field(
        ge=0.0,
        le=1.0,
        description="Severity of conflict (0-1)"
    )
    confidence_in_conflict: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that this is a real conflict"
    )
    
    # Resolution guidance
    suggested_resolution: Optional[str] = Field(
        default=None,
        description="Suggested resolution approach"
    )
    requires_human_review: bool = Field(
        default=False,
        description="Whether human review is needed"
    )

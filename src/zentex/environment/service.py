"""
Environment Awareness Service / 环境感知服务

Unified external service interface for the Environment Awareness module.
Provides a clean API for other modules to access environment perception capabilities.

环境感知模块的统一对外服务接口。
为其他模块提供访问环境感知能力的清晰 API。

This is the ONLY entry point that external modules should use to interact
with the environment awareness system. All other classes in this module
are internal implementation details.

这是外部模块与环境感知系统交互的唯一入口点。
此模块中的所有其他类都是内部实现细节。
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.environment.cleaner import SensoryDataCleaner
from zentex.environment.comparator import MultiSourceComparator
from zentex.environment.interpreter import SituationInterpreter
from zentex.environment.models import (
    ContextSnapshot,
    PhysicalHostState,
    SanitizedSignal,
    SituationImpact,
    SourceConflictScore,
)
from zentex.environment.scouter import EnvironmentScouter
from zentex.environment.snapshot import ContextSnapshotStore


class EnvironmentAwarenessService:
    """
    Unified service interface for environment awareness capabilities.
    
    环境感知能力的统一服务接口。
    
    This service provides a single entry point for all environment awareness
    operations including host state sampling, situation interpretation,
    signal sanitization, context snapshotting, and multi-source comparison.
    
    External modules should ONLY interact with environment awareness through
    this service interface to maintain proper module boundaries.
    
    该服务为所有环境感知操作提供单一入口点，包括宿主状态采样、
    态势解释、信号清洗、上下文快照和多源比较。
    
    外部模块应仅通过此服务接口与环境感知交互，以保持适当的模块边界。
    
    Usage Example:
        ```python
        from zentex.environment import EnvironmentAwarenessService
        
        # Create service instance
        env_service = EnvironmentAwarenessService()
        
        # Sample current host state
        host_state = env_service.sample_host_state()
        
        # Interpret the state
        impact = env_service.interpret_environment(host_state)
        
        # Sanitize external signal
        clean_signal = env_service.sanitize_signal("raw signal content")
        
        # Create context snapshot
        snapshot = env_service.create_context_snapshot(host_state=host_state)
        ```
    """
    
    def __init__(
        self,
        *,
        scouter_debounce_seconds: float = 5.0,
        snapshot_storage_path: str | None = None,
        max_snapshots_in_memory: int = 1000,
        sanitizer_max_length: int = 10000,
        enable_injection_detection: bool = True,
    ) -> None:
        """
        Initialize the EnvironmentAwarenessService.
        
        Args:
            scouter_debounce_seconds: Debounce window for host state sampling
            snapshot_storage_path: Path to persist context snapshots (optional)
            max_snapshots_in_memory: Maximum snapshots to keep in memory
            sanitizer_max_length: Maximum length for sanitized signals
            enable_injection_detection: Whether to enable prompt injection detection
        """
        # Initialize internal components
        self._scouter = EnvironmentScouter(
            debounce_window_seconds=scouter_debounce_seconds
        )
        self._interpreter = SituationInterpreter()
        self._cleaner = SensoryDataCleaner(
            max_signal_length=sanitizer_max_length,
            enable_injection_detection=enable_injection_detection,
        )
        self._snapshot_store = ContextSnapshotStore(
            storage_path=snapshot_storage_path,
            max_in_memory_snapshots=max_snapshots_in_memory,
        )
        self._comparator = MultiSourceComparator()
    
    # =========================================================================
    # Public API - Host State Sampling / 宿主状态采样
    # =========================================================================
    
    def sample_host_state(self) -> PhysicalHostState:
        """
        Sample current physical host state.
        
        采样当前物理宿主状态。
        
        Returns:
            PhysicalHostState: Current host state with CPU, memory, disk, network metrics
            
        This method samples the physical host's resource utilization and health.
        Results are debounced to prevent rapid oscillations.
        
        该方法采样物理主机的资源利用率和健康状况。
        结果经过去抖处理以防止快速振荡。
        """
        return self._scouter.sample_host_state()
    
    def get_last_host_state(self) -> PhysicalHostState | None:
        """
        Get the last sampled host state without triggering a new sample.
        
        获取上次采样的宿主状态而不触发新采样。
        
        Returns:
            Last sampled state, or None if no sampling has occurred
        """
        return self._scouter.get_last_state()
    
    # =========================================================================
    # Public API - Situation Interpretation / 态势解释
    # =========================================================================
    
    def interpret_environment(
        self,
        host_state: PhysicalHostState,
        current_role: str | None = None,
        active_goals: list[str] | None = None,
    ) -> SituationImpact:
        """
        Interpret environmental state and determine impacts on agent operations.
        
        解释环境状态并确定对代理操作的影响。
        
        Args:
            host_state: Current physical host state
            current_role: Agent's current role (optional)
            active_goals: List of currently active goal IDs (optional)
            
        Returns:
            SituationImpact: Interpreted impacts, recommendations, and risk assessment
            
        This method analyzes the host state and provides actionable insights
        including cognitive mode recommendations and risk assessments.
        
        该方法分析宿主状态并提供可操作的洞察，
        包括认知模式建议和风险评估。
        """
        return self._interpreter.interpret_host_state(
            host_state=host_state,
            current_role=current_role,
            active_goals=active_goals,
        )
    
    # =========================================================================
    # Public API - Signal Sanitization / 信号清洗
    # =========================================================================
    
    def sanitize_signal(
        self,
        raw_signal: str,
        source_plugin_id: str | None = None,
        source_kind: str | None = None,
    ) -> SanitizedSignal:
        """
        Sanitize a raw sensory signal from external sources.
        
        清洗来自外部源的原始感官信号。
        
        Args:
            raw_signal: The raw signal content to sanitize
            source_plugin_id: ID of the plugin that provided this signal
            source_kind: Type of source (webhook, file, api, etc.)
            
        Returns:
            SanitizedSignal: Cleaned signal with security assessment
            
        This method applies injection filtering and content sanitization
        to protect the cognitive system from malicious inputs.
        
        该方法应用注入过滤和内容清洗，
        保护认知系统免受恶意输入的影响。
        """
        return self._cleaner.sanitize_signal(
            raw_signal=raw_signal,
            source_plugin_id=source_plugin_id,
            source_kind=source_kind,
        )
    
    def sanitize_multiple_signals(
        self,
        signals: list[str],
        source_plugin_id: str | None = None,
        source_kind: str | None = None,
    ) -> list[SanitizedSignal]:
        """
        Sanitize multiple signals in batch.
        
        批量清洗多个信号。
        
        Args:
            signals: List of raw signal strings
            source_plugin_id: ID of the plugin that provided these signals
            source_kind: Type of source
            
        Returns:
            List of sanitized signals
        """
        return self._cleaner.batch_sanitize(
            signals=signals,
            source_plugin_id=source_plugin_id,
            source_kind=source_kind,
        )
    
    # =========================================================================
    # Public API - Context Snapshots / 上下文快照
    # =========================================================================
    
    def create_context_snapshot(
        self,
        host_state: PhysicalHostState | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        active_goals: list[str] | None = None,
        working_memory_summary: str | None = None,
        current_role: str | None = None,
        identity_anchor_ref: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextSnapshot:
        """
        Create and store a new context snapshot.
        
        创建并存储新的上下文快照。
        
        Args:
            host_state: Physical host state at snapshot time
            session_id: Associated session ID
            turn_id: Associated think loop turn ID
            active_goals: List of active goal IDs
            working_memory_summary: Summary of working memory
            current_role: Current agent role
            identity_anchor_ref: Reference to identity kernel
            tags: Tags for categorization
            metadata: Additional metadata
            
        Returns:
            The created ContextSnapshot
            
        Context snapshots provide point-in-time records of the system state
        for historical analysis and state recovery.
        
        上下文快照提供系统状态的时间点记录，
        用于历史分析和状态恢复。
        """
        return self._snapshot_store.create_snapshot(
            host_state=host_state,
            session_id=session_id,
            turn_id=turn_id,
            active_goals=active_goals,
            working_memory_summary=working_memory_summary,
            current_role=current_role,
            identity_anchor_ref=identity_anchor_ref,
            tags=tags,
            metadata=metadata,
        )
    
    def get_recent_snapshots(
        self,
        count: int = 10,
        before_timestamp: datetime | None = None,
    ) -> list[ContextSnapshot]:
        """
        Get the most recent context snapshots.
        
        获取最近的上下文快照。
        
        Args:
            count: Number of snapshots to retrieve
            before_timestamp: Only return snapshots before this time
            
        Returns:
            List of recent snapshots, ordered newest first
        """
        return self._snapshot_store.get_recent_snapshots(
            count=count,
            before_timestamp=before_timestamp,
        )
    
    def query_snapshots(
        self,
        session_id: str | None = None,
        turn_id: str | None = None,
        tag: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[ContextSnapshot]:
        """
        Query context snapshots with various filters.
        
        使用各种过滤器查询上下文快照。
        
        Args:
            session_id: Filter by session ID
            turn_id: Filter by turn ID
            tag: Filter by tag (must be present in snapshot's tags)
            start_time: Only return snapshots after this time
            end_time: Only return snapshots before this time
            
        Returns:
            List of matching snapshots
        """
        return self._snapshot_store.query_snapshots(
            session_id=session_id,
            turn_id=turn_id,
            tag=tag,
            start_time=start_time,
            end_time=end_time,
        )
    
    # =========================================================================
    # Public API - Multi-Source Comparison / 多源比较
    # =========================================================================
    
    def compare_sources(
        self,
        source_a_id: str,
        source_b_id: str,
        field_name: str,
        value_a: Any,
        value_b: Any,
        conflict_type: str = "value_mismatch",
    ) -> SourceConflictScore | None:
        """
        Compare values from two sources to detect conflicts.
        
        比较两个来源的值以检测冲突。
        
        Args:
            source_a_id: Identifier for source A
            source_b_id: Identifier for source B
            field_name: Name of the field being compared
            value_a: Value from source A
            value_b: Value from source B
            conflict_type: Type of conflict being detected
            
        Returns:
            SourceConflictScore if conflict detected, None otherwise
            
        This method is useful for validating sensor readings and detecting
        inconsistencies between different information sources.
        
        该方法用于验证传感器读数并检测不同信息源之间的不一致。
        """
        return self._comparator.compare_sources(
            source_a_id=source_a_id,
            source_b_id=source_b_id,
            field_name=field_name,
            value_a=value_a,
            value_b=value_b,
            conflict_type=conflict_type,
        )
    
    def compare_multiple_sources(
        self,
        field_name: str,
        sources: dict[str, Any],
    ) -> list[SourceConflictScore]:
        """
        Compare values from multiple sources pairwise.
        
        成对比较多个来源的值。
        
        Args:
            field_name: Name of the field being compared
            sources: Dictionary mapping source IDs to their values
            
        Returns:
            List of detected conflicts
        """
        return self._comparator.compare_multiple_sources(
            field_name=field_name,
            sources=sources,
        )
    
    # =========================================================================
    # Convenience Methods / 便捷方法
    # =========================================================================
    
    def sample_and_interpret(
        self,
        current_role: str | None = None,
        active_goals: list[str] | None = None,
    ) -> tuple[PhysicalHostState, SituationImpact]:
        """
        Convenience method to sample host state and interpret it in one call.
        
        便捷方法，在一次调用中采样宿主状态并解释它。
        
        Args:
            current_role: Agent's current role (optional)
            active_goals: List of currently active goal IDs (optional)
            
        Returns:
            Tuple of (host_state, situation_impact)
        """
        host_state = self.sample_host_state()
        impact = self.interpret_environment(
            host_state=host_state,
            current_role=current_role,
            active_goals=active_goals,
        )
        return host_state, impact
    
    def sample_and_snapshot(
        self,
        session_id: str | None = None,
        turn_id: str | None = None,
        **snapshot_kwargs: Any,
    ) -> tuple[PhysicalHostState, ContextSnapshot]:
        """
        Convenience method to sample host state and create a snapshot.
        
        便捷方法，采样宿主状态并创建快照。
        
        Args:
            session_id: Associated session ID
            turn_id: Associated think loop turn ID
            **snapshot_kwargs: Additional arguments for snapshot creation
            
        Returns:
            Tuple of (host_state, context_snapshot)
        """
        host_state = self.sample_host_state()
        snapshot = self.create_context_snapshot(
            host_state=host_state,
            session_id=session_id,
            turn_id=turn_id,
            **snapshot_kwargs,
        )
        return host_state, snapshot

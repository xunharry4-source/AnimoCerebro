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
import logging
from typing import Any, Optional
from uuid import uuid4

from zentex.environment.cleaner import SensoryDataCleaner
from zentex.environment.comparator import MultiSourceComparator
from zentex.environment.interpreter import SituationInterpreter
from zentex.environment.models import (
    HealthStatus,
    ContextSnapshot,
    PhysicalHostState,
    SanitizedSignal,
    SituationImpact,
    SourceConflictScore,
)
from zentex.environment.scouter import EnvironmentScouter
from zentex.environment.snapshot import ContextSnapshotStore

# G19 - 用户偏好辨析与意图对齐 (v1.0)
from zentex.environment.preference_engine import PreferenceEngine
from zentex.environment.preference_manager import PreferenceManager
from zentex.environment.extreme_signal_interceptor import ExtremeSignalInterceptor
from zentex.environment.attack_sample_marker import AttackSampleMarker
from zentex.environment.preference_storage import PreferenceStore

# G19 v2.0 - 新技术栈组件
from zentex.environment.g19_settings import G19Settings, get_g19_settings
from zentex.environment.g19_database import G19Database, get_g19_database
from zentex.environment.g19_judgment_engine import HybridJudgmentEngine

logger = logging.getLogger(__name__)


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
        # G19 - 用户偏好辨析配置
        preference_db_path: str | None = None,
        auto_confirm_threshold: float = 0.9,
        confirmation_timeout_hours: int = 24,
    ) -> None:
        """
        Initialize the EnvironmentAwarenessService.
        
        Args:
            scouter_debounce_seconds: Debounce window for host state sampling
            snapshot_storage_path: Path to persist context snapshots (optional)
            max_snapshots_in_memory: Maximum snapshots to keep in memory
            sanitizer_max_length: Maximum length for sanitized signals
            enable_injection_detection: Whether to enable prompt injection detection
            preference_db_path: Path to preference database (G19)
            auto_confirm_threshold: Confidence threshold for auto-confirming preferences (G19)
            confirmation_timeout_hours: Hours before confirmation expires (G19)
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
        
        # G19 - 初始化偏好辨析组件
        self._preference_store = PreferenceStore(
            db_path=preference_db_path
        )
        self._preference_engine = PreferenceEngine(store=self._preference_store)
        self._preference_engine.auto_confirm_threshold = auto_confirm_threshold
        self._preference_engine.confirmation_timeout_hours = confirmation_timeout_hours
        self._preference_manager = PreferenceManager(store=self._preference_store)
        self._extreme_signal_interceptor = ExtremeSignalInterceptor()
        self._attack_sample_marker = AttackSampleMarker(store=self._preference_store)
    
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
        source_plugin_id: Optional[str] = None,
        source_kind: Optional[str] = None,
    ) -> SanitizedSignal:
        """Submit a raw signal for sanitization and normalization."""
        return self._cleaner.sanitize_signal(
            raw_signal=raw_signal,
            source_plugin_id=source_plugin_id,
            source_kind=source_kind
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

    def ingest_sensory_signal(self, session: Any) -> str:
        """
        Ingest a raw signal from the currently active ingestion plugin.
        
        This method encapsulates the internal plugin resolution logic,
        allowing the caller (e.g., ThinkLoop) to remain agnostic of the 
        underlying plugin management.
        """
        # In a real implementation, this would look up the active plugin 
        # from the runtime/registry. For now, we delegate to the registry
        # attached to the session's runtime if available.
        runtime = getattr(session, "runtime", None)
        if not runtime:
            return "system_idle_signal"
            
        # Note: This logic is moved from ThinkLoop to here to maintain isolation.
        # We use a simplified version for the facade.
        return "simulated_raw_signal_from_facade"

    def interpret_signal(
        self,
        sanitized_signal: SanitizedSignal,
        current_role: Optional[str] = None,
        active_goals: Optional[list[str]] = None,
    ) -> SituationImpact:
        """Interpret a sanitized signal into a cognitive situation impact."""
        # For now, we map this to the host state interpreter
        # In a full implementation, this would handle broader sensory events
        host_state = self._scouter.sample_host_state()
        return self._interpreter.interpret_host_state(
            host_state=host_state,
            current_role=current_role,
            active_goals=active_goals
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

    def get_status(self) -> dict[str, Any]:
        """Return diagnostic host metrics and snapshot storage status."""
        last_state = self.get_last_host_state()
        return {
            "host_metrics": last_state.model_dump() if last_state else "not_sampled",
            "snapshot_count": self._snapshot_store.get_snapshot_count(),
            "storage_enabled": self._snapshot_store.storage_path is not None,
        }

    # =========================================================================
    # Public API - G19 User Preference & Intent Alignment / 用户偏好辨析与意图对齐
    # =========================================================================
    
    async def execute_preference_judgment(
        self,
        detected_state: dict[str, Any],
        detection_source: str,
        context: dict[str, Any] | None = None,
    ) -> Any:
        """
        Execute the three-step preference judgment process.
        
        执行三步偏好判断流程。
        
        Args:
            detected_state: The detected anomalous state
            detection_source: Source of the detection (e.g., 'environment_scouter')
            context: Additional context information
            
        Returns:
            JudgmentResult with conclusion and required actions
            
        This is the main entry point for G19 preference discrimination.
        It follows the flow: Anomaly Candidate -> Preference Candidate -> Confirmation Required.
        
        这是 G19 偏好辨析的主要入口点。
        遵循流程：异常候选 -> 偏好候选 -> 需要确认。
        """
        return await self._preference_engine.execute_three_step_judgment(
            detected_state=detected_state,
            detection_source=detection_source,
            context=context
        )
    
    async def confirm_user_preference(
        self,
        ambiguity_case_id: str,
        user_decision: str,
        user_id: str,
        confirmation_context: dict[str, Any] | None = None,
    ) -> Any | None:
        """
        Confirm a user preference from an ambiguity case.
        
        从歧义案例中确认用户偏好。
        
        Args:
            ambiguity_case_id: ID of the intent ambiguity case
            user_decision: User's decision ('confirm_as_preference', 'mark_as_anomaly', 'needs_investigation')
            user_id: ID of the user making the decision
            confirmation_context: Additional context for the confirmation
            
        Returns:
            UserPreference object if confirmed as preference, None otherwise
        """
        from zentex.environment.preference_models import UserDecision
        
        decision_enum = UserDecision(user_decision)
        return await self._preference_manager.confirm_preference(
            ambiguity_case_id=ambiguity_case_id,
            user_decision=decision_enum,
            user_id=user_id,
            confirmation_context=confirmation_context
        )
    
    async def revoke_preference(
        self,
        preference_id: str,
        reason: str,
        user_id: str,
    ) -> None:
        """
        Revoke a previously confirmed preference.
        
        撤销之前确认的偏好。
        
        Args:
            preference_id: ID of the preference to revoke
            reason: Reason for revocation
            user_id: ID of the user revoking the preference
        """
        await self._preference_manager.revoke_preference(
            preference_id=preference_id,
            reason=reason,
            user_id=user_id
        )
    
    async def query_preferences(
        self,
        scope_filter: dict[str, Any] | None = None,
        source_filter: str | None = None,
        status_filter: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        """
        Query user preferences with filters.
        
        查询用户偏好（带过滤器）。
        
        Args:
            scope_filter: Filter by applicable scope
            source_filter: Filter by source
            status_filter: Filter by status
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of UserPreference objects
        """
        from zentex.environment.preference_models import PreferenceStatus
        
        status_enum = PreferenceStatus(status_filter) if status_filter else None
        return await self._preference_manager.query_preferences(
            scope_filter=scope_filter,
            source_filter=source_filter,
            status_filter=status_enum,
            limit=limit,
            offset=offset
        )
    
    async def assess_signal_risk(
        self,
        signal_content: str,
        signal_source: str,
        context: dict[str, Any] | None = None,
    ) -> Any:
        """
        Assess the risk level of an external signal.
        
        评估外部信号的风险等级。
        
        Args:
            signal_content: Content of the signal
            signal_source: Source of the signal
            context: Additional context (e.g., physical_state, is_trusted_source)
            
        Returns:
            RiskAssessment with risk score and indicators
        """
        return await self._extreme_signal_interceptor.assess_signal_risk(
            signal_content=signal_content,
            signal_source=signal_source,
            context=context
        )
    
    async def intercept_extreme_signal(
        self,
        signal_content: str,
        signal_source: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[Any, Any]:
        """
        Intercept and handle extreme/high-risk signals.
        
        拦截并处理极端/高风险信号。
        
        Args:
            signal_content: Content of the signal
            signal_source: Source of the signal
            context: Additional context
            
        Returns:
            Tuple of (ExtremeSignalRecord, ConfirmationRequest)
        """
        # Assess risk
        risk_assessment = await self.assess_signal_risk(
            signal_content=signal_content,
            signal_source=signal_source,
            context=context
        )
        
        # Create signal record
        signal_record = self._extreme_signal_interceptor.create_extreme_signal_record(
            signal_content=signal_content,
            signal_source=signal_source,
            risk_assessment=risk_assessment
        )
        
        # Force secondary confirmation if needed
        if risk_assessment.requires_confirmation:
            confirmation_request = await self._extreme_signal_interceptor.force_secondary_confirmation(
                signal_record=signal_record
            )
        else:
            from zentex.environment.preference_models import ConfirmationRequest
            confirmation_request = None
        
        return signal_record, confirmation_request
    
    async def mark_attack_sample(
        self,
        signal_record_id: str,
        attack_type: str,
        confidence: float,
        analyst_id: str | None = None,
    ) -> Any:
        """
        Mark a signal as a malicious attack sample.
        
        标记信号为恶意攻击样本。
        
        Args:
            signal_record_id: ID of the extreme signal record
            attack_type: Type of attack (injection/spoofing/manipulation/other)
            confidence: Confidence level (0.0-1.0)
            analyst_id: ID of the analyst (or 'auto' for automatic)
            
        Returns:
            AttackSample object
        """
        # Note: In production, we'd fetch the signal_record from storage
        # For now, create a minimal record for demonstration
        from zentex.environment.preference_models import ExtremeSignalRecord
        
        signal_record = ExtremeSignalRecord(
            record_id=signal_record_id,
            signal_content="[REDACTED]",
            signal_source="unknown",
            risk_score=confidence
        )
        
        return await self._attack_sample_marker.mark_malicious_signal(
            signal_record=signal_record,
            attack_type=attack_type,
            confidence=confidence,
            analyst_id=analyst_id
        )
    
    async def detect_similar_attack(
        self,
        new_signal: str,
        similarity_threshold: float = 0.85,
    ) -> Any | None:
        """
        Detect if a new signal matches known attack patterns.
        
        检测新信号是否匹配已知攻击模式。
        
        Args:
            new_signal: Content of the new signal
            similarity_threshold: Minimum similarity score to consider a match
            
        Returns:
            AttackMatch if found, None otherwise
        """
        return await self._attack_sample_marker.detect_similar_attack(
            new_signal=new_signal,
            similarity_threshold=similarity_threshold
        )
    
    async def get_unresolved_cases(
        self,
        risk_level_filter: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        """
        Get unresolved intent ambiguity cases.
        
        获取未解决的意图歧义案例。
        
        Args:
            risk_level_filter: Filter by risk level (low/medium/high/critical)
            limit: Maximum number of results
            
        Returns:
            List of IntentAmbiguityCase objects
        """
        from zentex.environment.preference_models import RiskLevel
        
        risk_enum = RiskLevel(risk_level_filter) if risk_level_filter else None
        return await self._preference_manager.get_unresolved_cases(
            risk_level_filter=risk_enum,
            limit=limit
        )


# Global singleton instance
_default_service: EnvironmentAwarenessService | None = None


def get_environment_service() -> EnvironmentAwarenessService:
    """Return the global default EnvironmentAwarenessService instance."""
    global _default_service
    if _default_service is None:
        _default_service = EnvironmentAwarenessService()
    return _default_service


def get_service() -> EnvironmentAwarenessService:
    """Standard service factory function for launcher assembly.
    
    Alias for get_environment_service() to maintain compatibility
    with the SystemAssembler's expectation of a get_service() function.
    """
    return get_environment_service()

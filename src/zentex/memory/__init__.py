from __future__ import annotations

"""
Memory domain exports / 记忆功能域导出。

该包只承载长期记忆、离线巩固、遗忘与沉淀机制。运行时调度逻辑不得继续
堆在这里之外的 `runtime/` 目录中。
"""

from zentex.memory.consolidation import (
    ConsolidationCycle,
    ConsolidationPluginOutput,
    ConsolidationQueue,
    ConsolidationTaskHandle,
    ConsolidationTaskRequest,
    ConsolidationTaskRejectedError,
    ForgettableNoiseRule,
    MemoryPromotionCandidate,
    PatternStabilityScore,
    StaleWriteError,
    ConsolidationEngine,
)
from zentex.memory.enhanced import (
    EnhancedMemoryRecord,
    EnhancedMemoryService,
    ManagedEnhancedMemoryRecord,
    MemoryAuditEvent,
    MemoryManagementState,
    MemoryRecallHit,
)

__all__ = [
    "ConsolidationCycle",
    "ConsolidationPluginOutput",
    "ConsolidationQueue",
    "ConsolidationTaskHandle",
    "ConsolidationTaskRequest",
    "ConsolidationTaskRejectedError",
    "ForgettableNoiseRule",
    "MemoryPromotionCandidate",
    "PatternStabilityScore",
    "StaleWriteError",
    "ConsolidationEngine",
    "EnhancedMemoryRecord",
    "EnhancedMemoryService",
    "ManagedEnhancedMemoryRecord",
    "MemoryAuditEvent",
    "MemoryManagementState",
    "MemoryRecallHit",
]

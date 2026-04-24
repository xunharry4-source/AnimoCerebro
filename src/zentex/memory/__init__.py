from __future__ import annotations

"""
Zentex Memory Engine - Common Interface / 统一对外接口

This module serves as the primary entry point for the Zentex memory domain. 
Internally reorganized into 6 sub-domains (storage, query, consolidation, security, management, plugins).
"""

# ── 1. Service Facade (Primary Entry Point) ───────────────────────────────
from zentex.memory.service import MemoryService, build_default_episode_graph_adapter, get_memory_service

# ── 2. Management & Coordination ──────────────────────────────────────────
from zentex.memory.management.classification import (
    EmotionalValence,
    MemoryTier,
    MEMORY_WORTHY_EVENTS,
    compute_content_hash,
    tier_for_source,
    valence_for_transcript_event,
    valence_for_upgrade_outcome,
)
from zentex.memory.management.enhanced import (
    EnhancedMemoryRecord,
    EnhancedMemoryService,
    EpisodeGraphMemoryAdapter,
    ManagedEnhancedMemoryRecord,
    MemoryAuditEvent,
    MemoryManagementState,
    MemoryRecallHit,
)
from zentex.memory.management.confidence import (
    ConfidenceCalculator,
    ConfidenceResult,
    MemoryClarity,
)
from zentex.memory.management.versioning import (
    MemoryVersion,
    VersionBranch,
    VersionChain,
    VersionDiff,
    VersionedMemoryStore,
)
from zentex.memory.management.portability import (
    ContaminationEvent,
    MemoryExporter,
    MemoryImportError,
    MemoryImporter,
    MemoryPackage,
    MemoryPackageManifest,
    MemoryPackageRecord,
)

# ── 3. Query & Retrieval ──────────────────────────────────────────────────
from zentex.memory.query.hybrid_retrieval import (
    HybridRetrievalEngine,
    QueryClassifier,
    QueryType,
    RetrievalResult,
)
from zentex.memory.query.deep_recall import DeepRecallEngine
from zentex.memory.query.temporal import TemporalEngine

# ── 4. Consolidation & Lifecycle ──────────────────────────────────────────
from zentex.memory.consolidation.consolidation import (
    ConsolidationEngine,
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
)
from zentex.memory.consolidation.lifecycle import (
    AccessRecord,
    ConsolidationQualityReport,
    LifecycleEvent,
    MemoryAccessTracker,
    MemoryDecayConfig,
    MemoryLifecycleManager,
)
from zentex.memory.consolidation.bridge import (
    ConsolidationToEnhancedBridge,
    ConsolidationScheduler,
)

# ── 5. Security & Governance ──────────────────────────────────────────────
from zentex.memory.security.encryption import (
    EnterpriseEncryptionService,
)
from zentex.memory.security.quarantine import (
    MemoryGate,
    MemoryRejectedError,
    QuarantineDecision,
    QuarantinedMemoryStore,
    StagedMemoryRecord,
    build_default_gates,
)
from zentex.memory.security.consistency import (
    ConsistencyAuditReport,
    ConsistencyViolation,
    CrossLayerConsistencyChecker,
    ViolationType,
)
from zentex.memory.security.provenance import (
    MemoryLineageGraph,
    ProvenanceEdge,
    ProvenanceNode,
    ProvenanceNodeKind,
    ProvenanceTracker,
)

# ── 6. Storage & Persistence ──────────────────────────────────────────────
from zentex.memory.storage.storage_manager import (
    HierarchicalMemoryStorage,
    RotationPolicy,
    StoragePartition,
)
from zentex.memory.storage.storage_format import MessagePackSerializer
from zentex.memory.storage.compression import TieredCompressionService
from zentex.memory.storage.inverted_index import MultiModalIndex
from zentex.memory.storage.vector_search import VectorSearchEngine
from zentex.memory.storage.kuzu_backend import KuzuGraphMemoryClient
from zentex.memory.storage.structured import (
    EntityRegistry,
    EntityType,
    MultimodalMemoryHint,
    RelationshipType,
    RuleBasedEntityExtractor,
    TypedEntity,
    TypedRelationship,
)

__all__ = [
    # Management
    "MemoryService", "get_memory_service",
    "EnhancedMemoryRecord", "EnhancedMemoryService", "EpisodeGraphMemoryAdapter",
    "ManagedEnhancedMemoryRecord", "MemoryAuditEvent", "MemoryManagementState",
    "MemoryRecallHit", "MemoryTier", "EmotionalValence", "ConfidenceCalculator",
    "MemoryVersion", "MemoryPackage",
    
    # Query
    "HybridRetrievalEngine", "QueryClassifier", "RetrievalResult",
    "DeepRecallEngine", "TemporalTimelineEngine",

    # Consolidation
    "ConsolidationEngine", "ConsolidationCycle", "MemoryLifecycleManager",
    "ConsolidationToEnhancedBridge",

    # Security
    "EnterpriseEncryptionService", "QuarantinedMemoryStore", "ProvenanceTracker",
    "CrossLayerConsistencyChecker",

    # Storage
    "HierarchicalMemoryStorage", "KuzuGraphMemoryClient", "MessagePackSerializer",
    "build_default_episode_graph_adapter",
    "TieredCompressionService", "MultiModalIndex", "VectorSearchEngine",
]

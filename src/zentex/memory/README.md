# Memory Module / 记忆模块

## Overview / 概述

This module implements comprehensive memory management for the Zentex system. It includes enhanced memory structures, consolidation processes, Kuzu graph database backend, and memory bridge functionality for long-term memory, offline consolidation, forgetting, and sedimentation mechanisms.

本模块为Zentex系统实现全面的记忆管理。它包括增强型记忆结构、巩固过程、Kuzu图数据库后端和记忆桥接功能，用于长期记忆、离线巩固、遗忘和沉淀机制。

## Architecture / 架构

The memory system is organized into 6 sub-domains:

```
zentex/memory/
├── management/          # Core memory services & coordination
│   ├── enhanced.py      # EnhancedMemoryService (main entry point)
│   ├── classification.py # Memory tier & emotional valence
│   ├── versioning.py    # Version control for profiles
│   ├── portability.py   # Export/import with signing
│   └── confidence.py    # Confidence scoring
├── storage/             # Persistence & indexing
│   ├── storage_manager.py # Hierarchical storage (hot/warm/cold)
│   ├── inverted_index.py  # SQLite-based keyword search
│   ├── vector_search.py   # Embedding-based semantic search
│   ├── kuzu_backend.py    # Graph database for episodic memory
│   └── structured.py      # Entity & relationship extraction
├── query/               # Retrieval engines
│   ├── hybrid_retrieval.py # Combined keyword + vector search
│   ├── deep_recall.py      # Multi-hop reasoning
│   └── temporal.py         # Time-based queries
├── consolidation/       # Memory consolidation & lifecycle
│   ├── consolidation.py  # Consolidation engine
│   ├── lifecycle.py      # Memory decay & access tracking
│   └── bridge.py         # Bridge to enhanced memory
├── security/            # Governance & protection
│   ├── quarantine.py     # G38 validation gates
│   ├── consistency.py    # Cross-layer conflict detection
│   ├── provenance.py     # Lineage tracking
│   └── encryption.py     # AES-256-GCM encryption
└── plugins/             # Extension points
```

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface defined in `__init__.py` / 所有交互必须通过 `__init__.py` 中定义的统一公共接口进行
- Internal files are implementation details / 内部文件是实现细节

## Public Interface / 公共接口

The unified public interface is exposed through `__init__.py`:

通过 `__init__.py` 暴露的统一公共接口：

```python
from zentex.memory import (
    # Core Services / 核心服务
    EnhancedMemoryService,
    EnhancedMemoryRecord,
    ManagedEnhancedMemoryRecord,
    
    # Classification / 分类
    MemoryTier,  # hot | warm | cold
    EmotionalValence,  # triumph | concern | neutral | etc.
    
    # Consolidation / 巩固
    ConsolidationEngine,
    ConsolidationCycle,
    ConsolidationToEnhancedBridge,
    
    # Query & Retrieval / 查询与检索
    HybridRetrievalEngine,
    DeepRecallEngine,
    TemporalEngine,
    
    # Security & Governance / 安全与治理
    EnterpriseEncryptionService,
    QuarantinedMemoryStore,
    CrossLayerConsistencyChecker,
    ProvenanceTracker,
    
    # Versioning / 版本控制
    VersionedMemoryStore,
    MemoryVersion,
    VersionBranch,
    
    # Portability / 可移植性
    MemoryExporter,
    MemoryImporter,
    MemoryPackage,
    
    # Structured Knowledge / 结构化知识
    EntityRegistry,
    RuleBasedEntityExtractor,
    TypedEntity,
    TypedRelationship,
    
    # Storage Backends / 存储后端
    KuzuGraphMemoryClient,
    HierarchicalMemoryStorage,
)
```

## Usage Examples / 使用示例

### 1. Basic Memory Service / 基础记忆服务

```python
from zentex.memory import EnhancedMemoryService

# Initialize with storage paths
memory_service = EnhancedMemoryService(
    semantic_store_path="./data/semantic.jsonl",
    procedural_store_path="./data/procedural.jsonl",
    episodic_store_path="./data/episodic.jsonl",
    management_store_path="./data/management.jsonl",
    audit_store_path="./data/audit.jsonl",
)

# Store a memory record
from zentex.memory import EnhancedMemoryRecord

record = EnhancedMemoryRecord(
    memory_layer="semantic",
    source_kind="transcript",
    title="Python Best Practices",
    summary="Use type hints and docstrings",
    content="Python code should include type hints for better maintainability...",
    trace_id="trace-123",
    tags=["python", "best-practices"],
)

# Ingest into appropriate layer
memory_service._semantic_store.append(record)

# Query memories
managed_records = memory_service.list_managed_records(
    layer="semantic",
    limit=10,
    tag="python",
)
```

### 2. Memory Classification & Quarantine / 记忆分类与隔离

```python
from zentex.memory import MemoryTier, EmotionalValence

# Records automatically get classification
record = EnhancedMemoryRecord(
    memory_layer="semantic",
    source_kind="transcript",
    title="User Preference",
    summary="Prefers dark mode",
    content="User explicitly stated preference for dark UI theme",
    trace_id="trace-456",
    # Auto-computed fields:
    # memory_tier = tier_for_source("transcript") -> "hot"
    # emotional_valence = valence_for_transcript_event(...) -> "neutral"
    # content_hash = compute_content_hash(...) -> SHA-256 digest
)

# Quarantine new candidates from consolidation
from zentex.memory.consolidation.bridge import ConsolidationToEnhancedBridge

bridge = ConsolidationToEnhancedBridge(
    engine=consolidation_engine,
    enhanced_service=memory_service,
)

candidate_data = {
    "candidate_type": "lesson",
    "source_ref": "pattern-abc",
    "promotion_reason": "Repeated pattern detected",
}

memory_id = bridge.ingest_candidate(candidate_data)
# Record is now in QUARANTINED status, awaiting G38 validation
```

### 3. Hybrid Retrieval / 混合检索

```python
from zentex.memory import HybridRetrievalEngine

# Initialize retrieval engine
retrieval = HybridRetrievalEngine(
    index=memory_service._index,  # SQLite inverted index
    vector_index=memory_service._vector_index,  # Vector embeddings
    semantic_store=memory_service._semantic_store,
    procedural_store=memory_service._procedural_store,
)

# Search with keyword + semantic similarity
results = retrieval.search(
    query="Python type hints best practices",
    limit=5,
    filter_by_tier="warm",  # Only search validated memories
    min_confidence=0.7,
)

for result in results:
    print(f"{result.memory_id}: score={result.score:.2f}")
    print(f"  Title: {result.title}")
    print(f"  Summary: {result.summary[:100]}...")
```

### 4. Consistency Checking / 一致性检查

```python
from zentex.memory import CrossLayerConsistencyChecker

# Initialize checker
checker = CrossLayerConsistencyChecker(
    title_overlap_threshold=0.8,
    enable_content_heuristics=True,
)

# Get all active records
all_records = [
    record.model_dump(mode="json")
    for record in memory_service.list_managed_records(layer="all")
]

# Run consistency check
report = checker.check(all_records, active_only=True)

print(report.summary())
# Output: "Scanned 150 records; 3 violations (1 critical)"

# Review violations
for violation in report.violations:
    if violation.severity == "critical":
        print(f"CRITICAL: {violation.violation_type}")
        print(f"  Between {violation.memory_id_a} and {violation.memory_id_b}")
        print(f"  Reason: {violation.reason}")
        print(f"  Hint: {violation.resolution_hint}")
```

### 5. Version Control / 版本控制

```python
from zentex.memory import VersionedMemoryStore

# Initialize version store
version_store = VersionedMemoryStore("./data/versions.json")

# Add version for a profile memory
from zentex.memory import MemoryVersion

version = MemoryVersion(
    version_number=1,
    memory_id="profile-123",
    profile_key="semantic::UserProfile::transcript",
    content="User prefers blue theme",
    summary="Color preference",
    content_hash="hash-abc",
    operator="user_input",
    change_note="Initial preference",
)

version_store.add_version(version, active=True)

# Later, update with new version
version_v2 = MemoryVersion(
    version_number=2,
    memory_id="profile-456",
    profile_key="semantic::UserProfile::transcript",
    content="User prefers dark theme",
    summary="Updated color preference",
    content_hash="hash-def",
    operator="user_input",
    change_note="Changed from blue to dark",
)

version_store.add_version(version_v2, active=True)

# Get version chain
chain = version_store.get_chain("semantic::UserProfile::transcript")
print(f"Total versions: {len(chain.versions)}")
print(f"Active memory: {chain.active_memory_id}")

# Diff between versions
diff = chain.diff(1, 2)
if diff:
    print(f"Added lines: {diff.added_lines}")
    print(f"Removed lines: {diff.removed_lines}")
```

### 6. Provenance Tracking / 溯源追踪

```python
from zentex.memory import ProvenanceTracker

# Initialize tracker
tracker = ProvenanceTracker(store_path="./data/provenance.json")

# Track original memory from transcript
tracker.track_original(
    memory_id="mem-orig",
    source_ref="transcript-entry-789",
    content_hash="hash-orig",
)

# Track derived memory (e.g., from consolidation)
tracker.track_derived(
    memory_id="mem-derived",
    parent_memory_ids=["mem-orig"],
    derivation_method="consolidation",
    operator="consolidation_engine",
)

# Get full lineage
lineage = tracker.get_lineage("mem-derived")
print(f"Nodes: {len(lineage.nodes)}")
print(f"Edges: {len(lineage.edges)}")

# Get ancestors
ancestors = lineage.get_ancestors("mem-derived")
for ancestor in ancestors:
    print(f"  <- {ancestor.memory_id} ({ancestor.kind})")
```

### 7. Export/Import / 导出导入

```python
from zentex.memory import MemoryExporter, MemoryImporter
import os

# Export memories
exporter = MemoryExporter()
aes_key = os.urandom(32)  # AES-256 key

records_to_export = [
    record.model_dump(mode="json")
    for record in memory_service.list_managed_records(layer="semantic", limit=100)
]

package, signing_key = exporter.export(
    records_to_export,
    source_origin="production_system",
    encrypt=True,
    aes_key=aes_key,
)

# Save to file
exporter.save_to_file(package, "./exports/memory_package.json")

# Import on another system
importer = MemoryImporter()
loaded_package = importer.load_from_file("./exports/memory_package.json")

# Validate and deduplicate
validated_records, skipped_hashes = importer.validate_and_deduplicate(loaded_package)
print(f"Imported: {len(validated_records)}, Skipped duplicates: {len(skipped_hashes)}")
```

### 8. Structured Knowledge Extraction / 结构化知识抽取

```python
from zentex.memory import RuleBasedEntityExtractor, EntityRegistry

# Initialize
extractor = RuleBasedEntityExtractor()
registry = EntityRegistry()

# Extract entities from text
text = """
John Smith from Google presented the new TensorFlow model.
The project uses Python and runs on AWS infrastructure.
"""

entities = extractor.extract(text)

# Add to registry
for entity in entities:
    registry.add_entity(entity)

# Query by type
persons = registry.query_by_type("PERSON")
technologies = registry.query_by_type("TECHNOLOGY")
organizations = registry.query_by_type("ORGANIZATION")

print(f"Found {len(persons)} persons, {len(technologies)} technologies")

# Extract relationships
relationships = extractor.extract_relationships(text, entities)
for rel in relationships:
    print(f"{rel.source_entity_id} --[{rel.relationship_type}]--> {rel.target_entity_id}")
```

### 9. Consolidation Bridge / 巩固桥接

```python
from zentex.memory.consolidation import ConsolidationEngine
from zentex.memory.consolidation.bridge import ConsolidationToEnhancedBridge

# Setup consolidation
consolidation_engine = ConsolidationEngine(memory_service=memory_service)

# Create bridge
bridge = ConsolidationToEnhancedBridge(
    engine=consolidation_engine,
    enhanced_service=memory_service,
)

# Process consolidation cycle results
# (This would normally be called after a consolidation cycle completes)
cycle_results = consolidation_engine.run_cycle()
bridge.process_consolidation_results(cycle_results)

# Candidates are now in quarantine, waiting for G38 validation
quarantined = memory_service.list_managed_records(status="quarantined")

# Promote after validation
for record in quarantined:
    try:
        promoted = memory_service.promote_from_quarantine(
            record.memory_id,
            operator="g38_validator",
        )
        print(f"Promoted {promoted.memory_id} to ACTIVE")
    except ValueError as e:
        print(f"Validation failed: {e}")
        # Record stays in quarantine
```

## Core Components / 核心组件

### Memory Management / 记忆管理

- **EnhancedMemoryService** (`management/enhanced.py`): Main service orchestrating all memory operations / 主服务，协调所有记忆操作
- **Classification System** (`management/classification.py`): Three-tier lifecycle (hot/warm/cold) + emotional valence / 三层生命周期 + 情感价态
- **Confidence Calculator** (`management/confidence.py`): Dynamic confidence scoring based on evidence / 基于证据的动态置信度评分

### Storage & Indexing / 存储与索引

- **HierarchicalMemoryStorage** (`storage/storage_manager.py`): Tiered storage with automatic rotation / 分层存储，自动轮换
- **MultiModalIndex** (`storage/inverted_index.py`): SQLite-based keyword search with metadata filtering / 基于SQLite的关键词搜索
- **VectorSearchEngine** (`storage/vector_search.py`): Semantic search using embeddings / 基于嵌入的语义搜索
- **KuzuGraphMemoryClient** (`storage/kuzu_backend.py`): Graph database for episodic/provenance memory / 情景记忆的图数据库

### Query & Retrieval / 查询与检索

- **HybridRetrievalEngine** (`query/hybrid_retrieval.py`): Combines keyword + vector + graph search / 结合关键词+向量+图搜索
- **DeepRecallEngine** (`query/deep_recall.py`): Multi-hop reasoning over memory graphs / 记忆图上的多跳推理
- **TemporalEngine** (`query/temporal.py`): Time-based queries and timeline reconstruction / 基于时间的查询和时间线重建

### Consolidation & Lifecycle / 巩固与生命周期

- **ConsolidationEngine** (`consolidation/consolidation.py`): Identifies patterns and promotes candidates / 识别模式并提升候选记忆
- **MemoryLifecycleManager** (`consolidation/lifecycle.py`): Handles decay, access tracking, tier transitions / 处理衰减、访问跟踪、层级转换
- **ConsolidationToEnhancedBridge** (`consolidation/bridge.py`): Connects consolidation output to enhanced memory / 连接巩固输出到增强记忆

### Security & Governance / 安全与治理

- **QuarantinedMemoryStore** (`security/quarantine.py`): G38 validation gates for new memories / G38验证门控
- **CrossLayerConsistencyChecker** (`security/consistency.py`): Detects contradictions across layers / 检测跨层矛盾
- **ProvenanceTracker** (`security/provenance.py`): Tracks memory lineage and derivation chains / 追踪记忆血缘和派生链
- **EnterpriseEncryptionService** (`security/encryption.py`): AES-256-GCM encryption for sensitive data / 敏感数据加密

### Versioning & Portability / 版本控制与可移植性

- **VersionedMemoryStore** (`management/versioning.py`): Version control for profile memories / Profile记忆的版本控制
- **MemoryExporter/MemoryImporter** (`management/portability.py`): Signed export/import with deduplication / 签名导出/导入，去重

### Structured Knowledge / 结构化知识

- **RuleBasedEntityExtractor** (`storage/structured.py`): Extracts entities from unstructured text / 从非结构化文本抽取实体
- **EntityRegistry** (`storage/structured.py`): Manages typed entities and relationships / 管理类型化实体和关系

## Usage Example / 使用示例

See detailed examples in the "Usage Examples" section above.

Basic initialization:

```python
from zentex.memory import EnhancedMemoryService, ConsolidationEngine

# Use only the public interface / 仅使用公共接口
memory_service = EnhancedMemoryService(
    semantic_store_path="./data/semantic.jsonl",
    management_store_path="./data/management.jsonl",
)
consolidation = ConsolidationEngine(memory_service=memory_service)
```

## Testing / 测试

Comprehensive test suites have been created for all major components:

```bash
# Run all memory tests
python -m pytest tests/memory/ -v

# Run specific component tests
python -m pytest tests/memory/test_consistency.py -v
python -m pytest tests/memory/test_versioning.py -v
python -m pytest tests/memory/test_provenance.py -v
python -m pytest tests/memory/test_portability.py -v
python -m pytest tests/memory/test_structured_knowledge.py -v
python -m pytest tests/memory/test_consolidation_bridge.py -v

# Run with coverage report
python -m pytest tests/memory/ --cov=zentex.memory --cov-report=html
```

**Test Coverage Summary:**
- Total test cases: 120+
- Components covered: Consistency, Versioning, Provenance, Portability, Structured Knowledge, Consolidation Bridge
- See [MEMORY_TEST_RESULTS.md](../../MEMORY_TEST_RESULTS.md) for detailed results

## Configuration / 配置

### `.env` Configuration

```dotenv
# Vector search configuration
MEMORY_VECTOR_SEARCH_MOCK=false  # Set to true for testing without model downloads
MEMORY_VECTOR_MODEL_NAME="sentence-transformers/all-MiniLM-L6-v2"

# Encryption
MEMORY_ENCRYPTION_ENABLED=true
MEMORY_ENCRYPTION_KEY_SOURCE="file"  # vault | file
MEMORY_AES_KEY_FILE="config/memory.key"

# Storage paths
MEMORY_DATA_DIR="./data"
MEMORY_INDEX_PATH="./data/memory_index.db"
MEMORY_VECTOR_INDEX_DIR="./data/vector_index"
```

### Future: YAML Configuration

Planned configuration file structure (`config/memory.yml`):

```yaml
memory:
  storage:
    base_path: "./data"
    hot_tier_compression: "none"
    warm_tier_compression: "lz4"
    cold_tier_compression: "zstd"
  
  vector_search:
    enabled: true
    use_mock: false
    model_name: "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: 384
  
  encryption:
    enabled: true
    algorithm: "AES-256-GCM"
    key_source: "vault"
    rotation_days: 90
  
  consolidation:
    cycle_interval_hours: 24
    min_pattern_frequency: 3
    promotion_threshold: 0.8
  
  quarantine:
    auto_validation: true
    nine_question_timeout_seconds: 300
```

## Performance Considerations / 性能考虑

### Current Limitations

1. **Large File Loading**: Files >100MB are loaded entirely into memory
   - **Solution**: Implement streaming decompression (planned)

2. **Synchronous Index Rebuild**: Startup blocks while rebuilding indexes
   - **Solution**: Async background rebuild (planned)

3. **Vector Search Mock Mode**: Default uses mock embeddings
   - **Solution**: Configure real model with `MEMORY_VECTOR_SEARCH_MOCK=false`

### Optimization Tips

- Use appropriate compression per tier (hot=none, warm=lz4, cold=zstd)
- Enable encryption only for sensitive memory layers
- Schedule consolidation cycles during low-traffic periods
- Monitor quarantine size and promote/reject promptly

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.memory` only, never from `zentex.memory.enhanced` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.memory` 导入，绝不能从 `zentex.memory.enhanced` 或其他内部路径导入。

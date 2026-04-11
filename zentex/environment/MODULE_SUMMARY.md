# Environment Awareness Module / 环境感知模块

## Overview

This module provides comprehensive environment awareness capabilities for the Zentex brain system.

该模块为 Zentex 大脑系统提供全面的环境感知能力。

## Module Structure

```
environment/
├── __init__.py                    # Module initialization and exports
├── models.py                      # Data models (PhysicalHostState, ContextSnapshot, etc.)
├── scouter.py                     # EnvironmentScouter - Physical host state sampling
├── interpreter.py                 # SituationInterpreter - State interpretation
├── cleaner.py                     # SensoryDataCleaner - Signal sanitization
├── snapshot.py                    # ContextSnapshotStore - Snapshot management
├── comparator.py                  # MultiSourceComparator - Conflict detection
├── service.py                     # EnvironmentAwarenessService - Unified API (MAIN ENTRY POINT)
└── README.md                      # This file
```

## Key Components

### 1. EnvironmentScouter (scouter.py)
- Samples CPU, memory, disk, and network metrics
- Implements debouncing to prevent rapid state oscillations
- Cross-platform support (Linux, macOS)
- Fail-safe defaults (unknown/degraded on failure)

### 2. SituationInterpreter (interpreter.py)
- Translates host states into actionable insights
- Recommends cognitive mode adjustments
- Assesses risk levels
- Identifies need for rational audit

### 3. SensoryDataCleaner (cleaner.py)
- Detects and redacts prompt injection attempts
- Sanitizes external signals
- Provides confidence scoring
- Batch processing support

### 4. ContextSnapshotStore (snapshot.py)
- Time-series state recording
- In-memory caching with configurable limits
- Optional disk persistence (JSONL format)
- Flexible querying and filtering

### 5. MultiSourceComparator (comparator.py)
- Cross-source conflict detection
- Severity scoring (0.0-1.0)
- Resolution recommendations
- Critical field identification

### 6. EnvironmentAwarenessService (service.py) ⭐ MAIN ENTRY POINT
**This is the ONLY class external modules should use.**

Unified service interface that wraps all components:
- `sample_host_state()` - Sample physical host state
- `interpret_environment()` - Interpret environmental impacts
- `sanitize_signal()` - Clean external signals
- `create_context_snapshot()` - Record system state
- `compare_sources()` - Detect conflicts between sources

## Usage Example

```python
from zentex.environment import EnvironmentAwarenessService

# Create service instance
env_service = EnvironmentAwarenessService()

# 1. Sample host state
host_state = env_service.sample_host_state()
print(f"Memory: {host_state.memory_pressure}")
print(f"Network: {host_state.network_health}")

# 2. Interpret environment
impact = env_service.interpret_environment(
    host_state=host_state,
    current_role="assistant"
)
print(f"Recommended mode: {impact.recommended_cognitive_mode}")
print(f"Risk level: {impact.risk_level}")

# 3. Sanitize external signal
clean_signal = env_service.sanitize_signal("raw input")
if clean_signal.injection_risk:
    print("Warning: Injection detected!")

# 4. Create context snapshot
snapshot = env_service.create_context_snapshot(
    host_state=host_state,
    session_id="session_123",
    tags=["important"]
)

# 5. Compare sources
conflict = env_service.compare_sources(
    source_a_id="sensor_1",
    source_b_id="sensor_2",
    field_name="cpu_load",
    value_a=30.0,
    value_b=90.0
)
if conflict:
    print(f"Conflict severity: {conflict.conflict_severity}")
```

## Design Principles

1. **Fail-Safe Defaults**: Sampling failures output unknown/degraded, never healthy defaults
2. **Debouncing**: State changes within debounce window are suppressed (default: 5s)
3. **Module Boundaries**: External modules MUST use EnvironmentAwarenessService only
4. **Auditability**: All signals fingerprinted, snapshots provide state records

## Testing

Run tests:
```bash
pytest tests/environment/test_environment_awareness.py -v
```

Run demo:
```bash
python3 examples/environment_awareness_demo.py
```

## Dependencies

Required:
- pydantic (for data models)

Optional:
- psutil (for enhanced network monitoring)

## Integration Points

This module integrates with:
- **ThinkLoop**: Phase 1 (Observe) - sample environment state
- **Safety Gate**: Check environment health before risky operations
- **Sensory Plugins**: Sanitize incoming external signals
- **BrainSession**: Create context snapshots for state recovery

## Related Documentation

- Product Spec: [G8 Environment Awareness](../../Zentex_产品功能文档/03_运行时主链.md)
- Full README: [README.md](README.md)
- Demo Script: [examples/environment_awareness_demo.py](../../examples/environment_awareness_demo.py)

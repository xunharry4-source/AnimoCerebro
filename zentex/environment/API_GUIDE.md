# Environment Awareness Module - API Guide

## Quick Start

```python
from zentex.environment import EnvironmentAwarenessService

# Initialize service
env = EnvironmentAwarenessService()
```

## Core API Methods

### 1. Host State Sampling

```python
# Sample current physical host state
host_state = env.sample_host_state()

# Access metrics
print(host_state.memory_pressure)      # NORMAL/MEDIUM/HIGH/CRITICAL
print(host_state.network_health)       # HEALTHY/DEGRADED/OFFLINE
print(host_state.cpu_load_percent)     # 0-100+ or None
print(host_state.disk_usage_percent)   # 0-100 or None
print(host_state.overall_health)       # HEALTHY/DEGRADED/CRITICAL

# Check if degraded
if host_state.is_degraded():
    print("System is degraded!")

# Check if should switch to low power
if host_state.should_switch_to_low_power_mode():
    print("Switch to low power mode")
```

### 2. Situation Interpretation

```python
# Interpret environmental state
impact = env.interpret_environment(
    host_state=host_state,
    current_role="assistant",           # Optional
    active_goals=["goal_1", "goal_2"]   # Optional
)

# Access interpretation results
print(impact.recommended_cognitive_mode)  # emergency/shallow/standard/deep
print(impact.risk_level)                  # low/medium/high/critical
print(impact.requires_rational_audit)     # True/False
print(impact.role_impact)                 # String description
print(impact.goal_impacts)                # List of impacts
print(impact.recommended_actions)         # List of actions
print(impact.reasoning)                   # Explanation
```

### 3. Signal Sanitization

```python
# Sanitize single signal
clean = env.sanitize_signal(
    raw_signal="external input",
    source_plugin_id="webhook-plugin",  # Optional
    source_kind="webhook"                # Optional
)

# Check results
if clean.injection_risk:
    print(f"Injection detected! Evidence: {clean.redaction_evidence}")
print(f"Sanitized: {clean.sanitized_content}")
print(f"Confidence: {clean.confidence_score}")

# Batch sanitize
signals = ["signal 1", "signal 2", "signal 3"]
clean_signals = env.sanitize_multiple_signals(signals)
```

### 4. Context Snapshots

```python
# Create snapshot
snapshot = env.create_context_snapshot(
    host_state=host_state,                    # Optional
    session_id="session_123",                 # Optional
    turn_id="turn_456",                       # Optional
    active_goals=["goal_1"],                  # Optional
    working_memory_summary="summary",         # Optional
    current_role="analyst",                   # Optional
    identity_anchor_ref="identity_789",       # Optional
    tags=["important", "review"],             # Optional
    metadata={"key": "value"}                 # Optional
)

# Get recent snapshots
recent = env.get_recent_snapshots(count=10)

# Query with filters
filtered = env.query_snapshots(
    session_id="session_123",    # Filter by session
    turn_id="turn_456",          # Filter by turn
    tag="important",             # Filter by tag
    start_time=datetime(...),    # After this time
    end_time=datetime(...)       # Before this time
)
```

### 5. Multi-Source Comparison

```python
# Compare two sources
conflict = env.compare_sources(
    source_a_id="sensor_1",
    source_b_id="sensor_2",
    field_name="cpu_load",
    value_a=30.0,
    value_b=90.0,
    conflict_type="value_mismatch"  # Optional
)

if conflict:
    print(f"Severity: {conflict.conflict_severity}")
    print(f"Confidence: {conflict.confidence_in_conflict}")
    print(f"Resolution: {conflict.suggested_resolution}")
    print(f"Needs review: {conflict.requires_human_review}")

# Compare multiple sources
sources = {
    "sensor_1": 50.0,
    "sensor_2": 52.0,
    "sensor_3": 95.0
}
conflicts = env.compare_multiple_sources(
    field_name="metric",
    sources=sources
)
```

### 6. Convenience Methods

```python
# Sample and interpret in one call
host_state, impact = env.sample_and_interpret(
    current_role="researcher"
)

# Sample and create snapshot
host_state, snapshot = env.sample_and_snapshot(
    session_id="session_123",
    turn_id="turn_456",
    tags=["auto"]
)
```

## Configuration Options

```python
env = EnvironmentAwarenessService(
    scouter_debounce_seconds=5.0,      # Debounce window for sampling
    snapshot_storage_path="/path/to/snapshots.jsonl",  # Disk persistence
    max_snapshots_in_memory=1000,      # Max in-memory snapshots
    sanitizer_max_length=10000,        # Max signal length
    enable_injection_detection=True    # Enable injection detection
)
```

## Common Patterns

### Pattern 1: ThinkLoop Integration

```python
def phase_1_observe(session):
    # Sample environment
    host_state, impact = env.sample_and_interpret(
        current_role=session.current_role
    )
    
    # Adjust cognitive mode if needed
    if impact.recommended_cognitive_mode != "standard":
        session.cognitive_mode = impact.recommended_cognitive_mode
    
    # Create snapshot
    env.create_context_snapshot(
        host_state=host_state,
        session_id=session.session_id,
        turn_id=session.turn_id,
        tags=["think_loop"]
    )
```

### Pattern 2: Safety Check

```python
def before_risky_operation():
    host_state = env.sample_host_state()
    
    if host_state.is_degraded():
        raise SafetyError(f"Environment degraded: {host_state.warnings}")
    
    if host_state.should_switch_to_low_power_mode():
        trigger_rational_audit("Critical resources")
```

### Pattern 3: External Input Handling

```python
def handle_external_input(raw_data):
    # Sanitize first
    clean = env.sanitize_signal(
        raw_data,
        source_plugin_id="external-api",
        source_kind="api"
    )
    
    # Check for injections
    if clean.injection_risk:
        logger.warning(f"Injection risk: {clean.redaction_evidence}")
        return None
    
    # Process sanitized content
    return process(clean.sanitized_content)
```

## Data Models Reference

### PhysicalHostState
```python
host_state.timestamp              # datetime
host_state.hostname               # str
host_state.platform               # str
host_state.python_version         # str
host_state.memory_pressure        # MemoryPressureLevel enum
host_state.memory_used_ratio      # float (0-1) or None
host_state.cpu_load_percent       # float or None
host_state.disk_usage_percent     # float or None
host_state.network_health         # NetworkHealthStatus enum
host_state.overall_health         # HealthStatus enum
host_state.warnings               # list[str]
```

### SituationImpact
```python
impact.interpretation_id          # str
impact.timestamp                  # datetime
impact.role_impact                # str or None
impact.goal_impacts               # list[str]
impact.recommended_cognitive_mode # str
impact.recommended_actions        # list[str]
impact.risk_level                 # str (low/medium/high/critical)
impact.requires_rational_audit    # bool
impact.reasoning                  # str or None
```

### SanitizedSignal
```python
signal.signal_id                  # str
signal.timestamp                  # datetime
signal.original_fingerprint       # str (SHA256)
signal.sanitized_content          # str
signal.injection_risk             # bool
signal.redaction_evidence         # list[str]
signal.confidence_score           # float (0-1)
signal.source_plugin_id           # str or None
signal.source_kind                # str or None
```

### ContextSnapshot
```python
snapshot.snapshot_id              # str
snapshot.timestamp                # datetime
snapshot.session_id               # str or None
snapshot.turn_id                  # str or None
snapshot.host_state               # PhysicalHostState or None
snapshot.active_goals             # list[str]
snapshot.current_role             # str or None
snapshot.tags                     # list[str]
snapshot.metadata                 # dict
```

### SourceConflictScore
```python
conflict.conflict_id              # str
conflict.timestamp                # datetime
conflict.source_a                 # str
conflict.source_b                 # str
conflict.conflict_type            # str
conflict.conflict_field           # str
conflict.value_a                  # Any
conflict.value_b                  # Any
conflict.conflict_severity        # float (0-1)
conflict.confidence_in_conflict   # float (0-1)
conflict.suggested_resolution     # str or None
conflict.requires_human_review    # bool
```

## Error Handling

```python
try:
    host_state = env.sample_host_state()
except Exception as e:
    logger.error(f"Sampling failed: {e}")
    # System will return degraded/unknown state automatically
```

## Best Practices

1. **Always use the service**: Never import internal classes directly
2. **Check injection risks**: Always verify `injection_risk` before processing
3. **Use convenience methods**: They reduce boilerplate code
4. **Tag snapshots**: Makes querying easier later
5. **Monitor confidence scores**: Low confidence may indicate issues
6. **Respect debouncing**: Don't sample too frequently (< 1s)

## For More Information

- Full README: [README.md](README.md)
- Module Summary: [MODULE_SUMMARY.md](MODULE_SUMMARY.md)
- Demo Script: [examples/environment_awareness_demo.py](../../examples/environment_awareness_demo.py)
- Tests: [tests/environment/test_environment_awareness.py](../../tests/environment/test_environment_awareness.py)

# Safety Module Test Plan (Zentex Engineering Standards)

## Test Overview

This test plan validates the safety module implementation against Zentex strict engineering guidelines and functional requirements.

## 1. SanityAuditor Tests (G25)

### 1.1 Normal Cases
```python
def test_sanity_audit_passed():
    auditor = SanityAuditor()
    report = auditor.audit(
        world_model={"active_goals": [{"id": "goal1", "name": "test"}]},
        strategy_graph={"policies": {"pol1": {"action": "test"}}},
        ban_layer={"banned_actions": ["forbidden"]},
        motivation_state={"curiosity": 0.5}
    )
    assert report.status == AuditStatus.PASSED
    assert report.issue_count == 0
    assert report.disposition == DispositionAction.CONTINUE
```

### 1.2 Abnormal Cases - Belief Conflicts
```python
def test_belief_conflict_detection():
    auditor = SanityAuditor()
    report = auditor.audit(
        world_model={"active_goals": []},
        strategy_graph={
            "policies": {
                "pol1": {"action": "test", "conditions": ["A"]},
                "pol2": {"action": "!test", "conditions": ["A"]}  # Contradiction
            }
        },
        ban_layer={},
        motivation_state={}
    )
    assert report.status == AuditStatus.FAILED
    assert len(report.belief_conflicts) > 0
    assert report.disposition in [DispositionAction.BLOCK_SELF_MOD, DispositionAction.FREEZE]
```

### 1.3 Edge Cases - Reasoning Loops
```python
def test_reasoning_loop_detection():
    auditor = SanityAuditor()
    report = auditor.audit(
        world_model={},
        strategy_graph={
            "reasoning_chains": [
                {
                    "path": ["A", "B", "C", "A", "B", "C", "A"],
                    "recurrences": 3
                }
            ]
        },
        ban_layer={},
        motivation_state={}
    )
    assert len(report.reasoning_loops) > 0
    assert any(loop.recurrence_count >= 3 for loop in report.reasoning_loops)
```

### 1.4 Negative Tests - Missing Dependencies
```python
def test_motivation_drift_without_baseline():
    auditor = SanityAuditor()
    # No baseline set - should not crash
    report = auditor.audit(
        world_model={},
        strategy_graph={},
        ban_layer={},
        motivation_state={"curiosity": 0.9}  # High drift
    )
    # Should establish baseline without failing
    assert report.status in [AuditStatus.PASSED, AuditStatus.WARNING]
```

## 2. CloudAuditorClient Tests (G26)

### 2.1 Normal Cases
```python
def test_cloud_audit_approved():
    client = CloudAuditorClient(CloudAuditorConfig(
        api_key="test_key",
        api_secret="test_secret"
    ))
    decision = client.audit_action(
        action_type="execute_tool",
        action_payload={"tool": "safe_tool"},
        risk_level="low"
    )
    assert decision.status == CloudDecisionStatus.APPROVED
    assert decision.signature.startswith("hmac-sha256=")
```

### 2.2 Abnormal Cases - Missing Credentials
```python
def test_cloud_audit_unconfigured():
    client = CloudAuditorClient()  # No credentials
    decision = client.audit_action(
        action_type="self_modify",
        action_payload={"change": "critical"},
        risk_level="critical"
    )
    assert decision.status == CloudDecisionStatus.REVIEW_REQUIRED
    assert "DEGRADED MODE" in decision.reason
    assert decision.constraints["degraded_mode"] is True
```

### 2.3 Edge Cases - Invalid Signature
```python
def test_cloud_audit_invalid_signature():
    client = CloudAuditorClient(CloudAuditorConfig(
        api_key="test_key",
        api_secret="test_secret"
    ))
    # Mock invalid signature response
    with patch.object(client, '_call_cloud_service') as mock_call:
        mock_call.return_value = CloudAuditDecision(
            request_id="test",
            status=CloudDecisionStatus.APPROVED,
            signature="invalid_signature"
        )
        decision = client.audit_action("test", {})
        assert "DEGRADED MODE" in decision.reason
```

### 2.4 Negative Tests - Service Unavailable
```python
def test_cloud_audit_service_down():
    client = CloudAuditorClient(CloudAuditorConfig(
        api_key="test_key", 
        api_secret="test_secret"
    ))
    with patch.object(client, '_call_cloud_service') as mock_call:
        mock_call.side_effect = CloudServiceUnavailable("Service down")
        decision = client.audit_action("test", {})
        assert decision.status == CloudDecisionStatus.REVIEW_REQUIRED
        assert client.degradation_count == 1
```

## 3. ExperienceExchangeManager Tests (G37)

### 3.1 Normal Cases
```python
def test_experience_creation_and_sharing():
    manager = ExperienceExchangeManager(ExperienceExchangeConfig(
        brain_id="test_brain",
        signing_key="test_key"
    ))
    packet = manager.create_experience_packet(
        experience_type=ExperienceType.EXPERIENCE,
        payload={"lesson": "test_pattern"},
        trust_score=0.8
    )
    assert packet.signature.startswith("hmac-sha256=")
    assert packet.source_brain_id == "test_brain"
```

### 3.2 Abnormal Cases - Forbidden Content
```python
def test_forbidden_content_blocked():
    manager = ExperienceExchangeManager()
    with pytest.raises(ForbiddenContentError):
        manager.create_experience_packet(
            experience_type="identity_kernel",  # Forbidden
            payload={"core_identity": "secret"}
        )
```

### 3.3 Edge Cases - Trust Threshold
```python
def test_low_trust_score_rejected():
    manager = ExperienceExchangeManager(ExperienceExchangeConfig(
        trust_threshold=0.7
    ))
    packet = ExperienceExchangePacket(
        source_brain_id="other_brain",
        experience_type=ExperienceType.EXPERIENCE,
        trust_score=0.3  # Below threshold
    )
    review = manager.receive_experience_packet(packet)
    assert review.conclusion == "rejected"
    assert "trust score" in review.block_reason
```

### 3.4 Negative Tests - Invalid Signature
```python
def test_invalid_signature_rejected():
    manager = ExperienceExchangeManager()
    packet = ExperienceExchangePacket(
        source_brain_id="unknown_brain",
        experience_type=ExperienceType.EXPERIENCE,
        signature="invalid_signature"
    )
    review = manager.receive_experience_packet(packet)
    assert review.conclusion == "rejected"
    assert "Signature verification failed" in review.block_reason
```

## 4. SafetyManager Integration Tests

### 4.1 Normal Cases - Multi-Layer Approval
```python
def test_action_evaluation_all_layers_pass():
    safety = SafetyManager(SafetyConfig(
        enable_sanity_audit=True,
        enable_cloud_audit=True,
        cloud_api_key="test_key",
        cloud_api_secret="test_secret"
    ))
    decision = safety.evaluate_action(
        action_type="execute_tool",
        payload={"tool": "safe_tool"},
        risk_level="low",
        context={"world_model": {}, "strategy_graph": {}}
    )
    assert decision.allowed is True
    assert "All safety checks passed" in decision.reason
```

### 4.2 Abnormal Cases - Sanity Audit Blocks
```python
def test_action_blocked_by_sanity_audit():
    safety = SafetyManager(SafetyConfig(enable_sanity_audit=True))
    decision = safety.evaluate_action(
        action_type="self_modify",
        payload={"change": "critical"},
        risk_level="critical",
        context={
            "world_model": {},
            "strategy_graph": {
                "policies": {
                    "pol1": {"action": "allow"},
                    "pol2": {"action": "!allow"}  # Conflict
                }
            }
        }
    )
    assert decision.allowed is False
    assert "Sanity audit disposition" in decision.reason
```

### 4.3 Edge Cases - Cloud Audit Degradation
```python
def test_cloud_audit_degradation_handling():
    safety = SafetyManager(SafetyConfig(
        enable_cloud_audit=True,
        cloud_api_key="invalid_key"  # Will cause degradation
    ))
    decision = safety.evaluate_action(
        action_type="self_modify",
        payload={"change": "test"},
        risk_level="high"
    )
    # Should still provide decision but with degradation noted
    assert "audit_trail" in decision.model_dump()
    assert any("degraded" in str(trail).lower() for trail in decision.audit_trail)
```

## 5. Fail-Closed Behavior Tests

### 5.1 No Silent Fallback
```python
def test_no_silent_fallback_on_missing_deps():
    # Test that missing dependencies raise explicit errors
    with pytest.raises(RuntimeError):
        safety = SafetyManager()
        safety.evaluate_action("self_modify", {"requires": "missing_dep"})
```

### 5.2 Evidence Chain Required
```python
def test_audit_requires_evidence():
    auditor = SanityAuditor()
    # Empty inputs should not pass silently
    report = auditor.audit({}, {}, {}, {})
    # Should explicitly state lack of evidence
    assert report.summary != ""
    assert report.status == AuditStatus.PASSED  # But with explicit note
```

## 6. Performance and Reliability Tests

### 6.1 Concurrent Safety
```python
def test_concurrent_safety_checks():
    safety = SafetyManager()
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(safety.is_safe_to_proceed, "test_action", {})
            for _ in range(50)
        ]
        results = [f.result() for f in futures]
    # All should complete without race conditions
    assert all(isinstance(r, bool) for r in results)
```

### 6.2 Memory Leaks
```python
def test_no_memory_leaks():
    safety = SafetyManager()
    initial_objects = len(gc.get_objects())
    
    # Run many operations
    for _ in range(1000):
        safety.audit({}, {}, {}, {})
    
    gc.collect()
    final_objects = len(gc.get_objects())
    # Should not significantly increase
    assert final_objects - initial_objects < 100
```

## 7. Integration with Zentex Runtime

### 7.1 Model Provider Integration
```python
def test_model_provider_mandatory():
    # Test that cognitive operations require real ModelProvider
    # This would test against rule-based fallbacks
    pass  # Implementation depends on ModelProvider interface
```

### 7.2 Audit Logging
```python
def test_audit_trail_completeness():
    safety = SafetyManager()
    decision = safety.evaluate_action("test", {})
    
    # Audit trail should be complete and traceable
    assert len(decision.audit_trail) > 0
    assert all("layer" in trail for trail in decision.audit_trail)
    assert all("timestamp" in trail for trail in decision.audit_trail)
```

## Test Execution Requirements

### Environment Setup
- Python 3.8+
- pytest with async support
- Mock for external dependencies
- Test isolation for stateful operations

### Coverage Requirements
- Minimum 90% line coverage
- 100% coverage for critical safety paths
- All negative test paths must be covered

### Verification Status
- **Normal Cases**: Must validate expected behavior
- **Abnormal Cases**: Must validate proper error handling
- **Edge Cases**: Must validate boundary conditions
- **Negative Tests**: Must validate fail-closed behavior

### Evidence Requirements
- Each test must assert specific outcomes
- No "passes without error" tests
- All assertions must be meaningful
- Test names must describe the scenario

## Rollback Plan

If any safety module component fails in production:

1. **Immediate Actions**:
   - Disable affected safety module via configuration
   - Fall back to conservative default behavior
   - Alert operators with specific failure details

2. **Root Cause Analysis**:
   - Review audit logs for failure patterns
   - Check configuration and dependency status
   - Validate input data and state consistency

3. **Recovery Steps**:
   - Fix identified issues
   - Run full test suite with negative cases
   - Gradually re-enable with monitoring
   - Verify all safety checks still function

4. **Prevention**:
   - Add additional negative tests for discovered failure modes
   - Improve error messages and logging
   - Update documentation with learned patterns

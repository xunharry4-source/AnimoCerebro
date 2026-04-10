# 任务验证模块 - 快速参考

## 📦 导入

```python
from zentex.tasks.verification.models import (
    VerificationConfig,
    VerifierConfig,
    VerificationType,
    VerificationStrategy
)
```

## 🔧 快速配置

### 启用验证
```python
contract = TaskContract(
    verification=VerificationConfig(
        enabled=True,
        strategy=VerificationStrategy.ALL_MUST_PASS,
        verifiers=[...]
    )
)
```

### 禁用验证（默认）
```python
contract = TaskContract()  # verification.enabled = False
```

## 🎯 验证器类型

### 1. 自动化测试
```python
VerifierConfig(
    verifier_id="test",
    verifier_type=VerificationType.AUTOMATED_TEST,
    config={
        "command": "pytest tests/",
        "timeout_seconds": 60
    }
)
```

### 2. LLM评估
```python
VerifierConfig(
    verifier_id="quality",
    verifier_type=VerificationType.LLM_EVALUATION,
    config={
        "model": "gpt-4",
        "evaluation_criteria": ["内容准确", "结构清晰"],
        "min_confidence": 0.8
    }
)
```

### 3. 规则检查
```python
VerifierConfig(
    verifier_id="format",
    verifier_type=VerificationType.RULE_BASED,
    config={
        "rules": [
            {"type": "required_field", "field": "output"},
            {"type": "min_length", "field": "content", "min_length": 100}
        ]
    }
)
```

## 📊 验证策略

| 策略 | 说明 |
|------|------|
| `ALL_MUST_PASS` | 全部通过 |
| `MAJORITY_WINS` | 多数通过 |
| `ANY_PASSES` | 任一通过 |
| `WEIGHTED_VOTE` | 加权投票 |

## 🔄 失败处理

```python
VerificationConfig(
    fallback_action="retry",     # retry / escalate / fail
    max_total_retries=3,
    escalation_target="reviewer"  # 仅escalate时需要
)
```

## 💻 使用示例

### Service层
```python
result = await service.complete_task_with_verification(
    task_id="task-001",
    result={"output": "完成"},
    remarks="Worker提交"
)

if result["success"]:
    print("✓ 验证通过")
else:
    print(f"✗ 验证失败: {result['error']}")
```

### Interface层
```python
result = await interface.complete_task_with_verification(
    task_id="task-001",
    result={"output": "完成"}
)
```

## 🔍 状态检查

```python
status = service.get_verification_engine_status()
print(status["initialized"])  # True/False
print(status["verifier_count"])  # 已注册验证器数量
```

## 📝 规则类型

| 规则类型 | 参数 | 示例 |
|---------|------|------|
| required_field | field | `{"type": "required_field", "field": "title"}` |
| min_length | field, min_length | `{"type": "min_length", "field": "content", "min_length": 100}` |
| max_length | field, max_length | `{"type": "max_length", "field": "title", "max_length": 50}` |
| pattern_match | field, pattern | `{"type": "pattern_match", "field": "email", "pattern": r"^[\w.-]+@[\w.-]+\.\w+$"}` |
| value_range | field, min, max | `{"type": "value_range", "field": "score", "min": 0, "max": 100}` |
| enum_value | field, allowed_values | `{"type": "enum_value", "field": "status", "allowed_values": ["a", "b"]}` |

## ⚡ 性能提示

- RuleBasedVerifier: <100ms
- AutomatedTestVerifier: 1-10秒
- LLMEvaluationVerifier: 5-15秒

**优化：**
- 减少验证器数量
- 降低LLM模型复杂度
- 设置合理timeout

## 🎓 最佳实践

### 高可靠性任务
```python
strategy = ALL_MUST_PASS
verifiers = [自动化测试, LLM评估, 规则检查]
fallback = escalate
```

### 中等可靠性
```python
strategy = MAJORITY_WINS
verifiers = [自动化测试, LLM评估]
fallback = retry
```

### 快速验证
```python
strategy = ANY_PASSES
verifiers = [规则检查]
fallback = fail
```

## 📚 文档

- [完整README](src/zentex/tasks/verification/README.md)
- [使用指南](src/zentex/tasks/verification/USAGE_GUIDE.md)
- [实现总结](IMPLEMENTATION_SUMMARY.md)

---

**快速开始，立即使用！** 🚀

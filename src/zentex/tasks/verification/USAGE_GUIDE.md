# 任务验证模块使用指南

## 📖 概述

任务验证模块为Zentex系统提供了多Agent协作场景下的自动任务完成验证功能。当Worker Agent声称完成任务时，系统可以自动执行多种验证器来确认任务的真实完成质量。

## 🚀 快速开始

### 1. 基本用法

```python
from zentex.tasks.models import ZentexTask, TaskType, TaskContract
from zentex.tasks.verification.models import (
    VerificationConfig,
    VerifierConfig,
    VerificationType,
    VerificationStrategy
)

# 创建带验证配置的任务
contract = TaskContract(
    verification=VerificationConfig(
        enabled=True,  # 启用验证
        strategy=VerificationStrategy.ALL_MUST_PASS,  # 所有验证器必须通过
        verifiers=[
            VerifierConfig(
                verifier_id="code-test",
                verifier_type=VerificationType.AUTOMATED_TEST,
                config={
                    "command": "pytest tests/test_feature.py -v",
                    "working_dir": "/path/to/project",
                    "timeout_seconds": 120
                }
            )
        ]
    )
)

task = ZentexTask(
    task_id="task-001",
    title="实现用户认证功能",
    task_type=TaskType.AGENT_DELEGATION,
    originator_id="planner-agent",
    idempotency_key="unique-key-001",
    contract=contract
)
```

### 2. 通过Service层使用

```python
from zentex.tasks import TaskManagementService

# 初始化服务（验证引擎会自动初始化）
service = TaskManagementService(
    registry=task_registry,
    transcript_store=transcript_store,
    decomposer=decomposer
)

# Worker完成任务后，调用验证流程
result = await service.complete_task_with_verification(
    task_id="task-001",
    result={
        "output": "代码实现完成",
        "files": ["auth.py", "test_auth.py"],
        "tests_passed": True
    },
    remarks="Worker声称已完成"
)

if result["success"]:
    print(f"✓ 任务完成: {result['message']}")
    if "verification_result" in result:
        vr = result["verification_result"]
        print(f"  验证状态: {'通过' if vr['overall_passed'] else '失败'}")
        print(f"  置信度: {vr['confidence_score']}")
else:
    print(f"✗ 任务失败: {result['error']}")
```

### 3. 通过Interface层使用

```python
from zentex.tasks.interface import TaskServiceInterface

# 创建接口实例
interface = TaskServiceInterface(service)

# 使用接口完成任务
result = await interface.complete_task_with_verification(
    task_id="task-001",
    result={"output": "完成"},
    remarks="通过接口调用"
)
```

---

## 🔧 验证器类型

### 1. 自动化测试验证器 (AutomatedTestVerifier)

执行shell命令或脚本来验证任务。

**适用场景：**
- 代码开发任务
- 脚本执行任务
- 任何可以自动化测试的场景

**配置示例：**
```python
VerifierConfig(
    verifier_id="unit-tests",
    verifier_type=VerificationType.AUTOMATED_TEST,
    config={
        "command": "pytest tests/ -v --cov=src",
        "working_dir": "/workspace/project",
        "timeout_seconds": 180
    }
)
```

**配置参数：**
- `command` (必需): 要执行的命令
- `working_dir` (可选): 工作目录，默认为当前目录
- `timeout_seconds` (可选): 超时时间（秒），默认60秒

**返回结果：**
- 退出码为0 → 通过
- 退出码非0 → 失败
- 超时 → TIMEOUT状态

---

### 2. LLM评估验证器 (LLMEvaluationVerifier)

调用LLM服务对任务完成质量进行语义评估。

**适用场景：**
- 认知任务（分析、总结）
- 创作任务（文章、报告）
- 需要主观判断的任务

**配置示例：**
```python
VerifierConfig(
    verifier_id="quality-check",
    verifier_type=VerificationType.LLM_EVALUATION,
    weight=2.0,  # 加权投票时权重更高
    config={
        "model": "gpt-4",
        "evaluation_criteria": [
            "内容准确无误，有数据支撑",
            "结构清晰，逻辑连贯",
            "建议具有可操作性",
            "字数不少于500字"
        ],
        "min_confidence": 0.8  # 最低置信度阈值
    }
)
```

**配置参数：**
- `model` (可选): LLM模型，默认gpt-4
- `evaluation_criteria` (可选): 评估标准列表
- `min_confidence` (可选): 最低置信度，默认0.0

**返回结果：**
LLM会返回JSON格式的评估结果：
```json
{
  "passed": true,
  "confidence": 0.92,
  "summary": "报告质量良好，符合所有标准",
  "reasoning": "详细内容...",
  "criteria_met": ["内容准确", "结构清晰"],
  "criteria_failed": []
}
```

---

### 3. 规则检查验证器 (RuleBasedVerifier)

基于预定义规则检查任务结果的结构化字段。

**适用场景：**
- 需要验证输出格式
- 检查必填字段
- 数据范围验证

**支持的规则类型：**

#### required_field - 必填字段检查
```python
{"type": "required_field", "field": "output"}
```

#### min_length / max_length - 长度检查
```python
{"type": "min_length", "field": "summary", "min_length": 100}
{"type": "max_length", "field": "title", "max_length": 50}
```

#### pattern_match - 正则匹配
```python
{"type": "pattern_match", "field": "email", "pattern": r"^[\w.-]+@[\w.-]+\.\w+$"}
```

#### value_range - 数值范围
```python
{"type": "value_range", "field": "score", "min": 0, "max": 100}
```

#### enum_value - 枚举值检查
```python
{
  "type": "enum_value", 
  "field": "status", 
  "allowed_values": ["pending", "approved", "rejected"]
}
```

**完整配置示例：**
```python
VerifierConfig(
    verifier_id="format-check",
    verifier_type=VerificationType.RULE_BASED,
    config={
        "rules": [
            {"type": "required_field", "field": "title"},
            {"type": "required_field", "field": "content"},
            {"type": "min_length", "field": "content", "min_length": 200},
            {"type": "pattern_match", "field": "version", "pattern": r"^\d+\.\d+\.\d+$"}
        ]
    }
)
```

---

## 🎯 验证策略

### 1. ALL_MUST_PASS（全部通过）

所有验证器都必须通过，整体才通过。

**适用场景：** 高可靠性要求的关键任务

```python
VerificationConfig(
    strategy=VerificationStrategy.ALL_MUST_PASS,
    verifiers=[verifier1, verifier2, verifier3]
)
# 结果：3个都通过 → PASSED
#      任意1个失败 → FAILED
```

### 2. MAJORITY_WINS（多数通过）

超过半数的验证器通过即可。

**适用场景：** 容错场景，允许个别验证器误判

```python
VerificationConfig(
    strategy=VerificationStrategy.MAJORITY_WINS,
    verifiers=[verifier1, verifier2, verifier3]
)
# 结果：2个或以上通过 → PASSED
#      2个或以上失败 → FAILED
```

### 3. ANY_PASSES（任一通过）

只要有一个验证器通过即可。

**适用场景：** 快速验证，多个验证方法是"或"的关系

```python
VerificationConfig(
    strategy=VerificationStrategy.ANY_PASSES,
    verifiers=[verifier1, verifier2]
)
# 结果：任意1个通过 → PASSED
#      全部失败 → FAILED
```

### 4. WEIGHTED_VOTE（加权投票）

根据验证器权重计算加权通过率。

**适用场景：** 不同验证器重要性不同

```python
VerificationConfig(
    strategy=VerificationStrategy.WEIGHTED_VOTE,
    verifiers=[
        VerifierConfig(verifier_id="llm-check", weight=2.0, ...),
        VerifierConfig(verifier_id="rule-check", weight=1.0, ...)
    ]
)
# 结果：加权通过率 > 50% → PASSED
#      LLM验证器通过即可主导结果（2/(2+1) = 67% > 50%）
```

---

## 🔄 验证失败处理

### 1. 自动重试 (retry)

验证失败后，任务退回IN_PROGRESS状态，Worker可以重新执行。

```python
VerificationConfig(
    fallback_action="retry",
    max_total_retries=3  # 最多重试3次
)
```

**工作流程：**
```
验证失败 → IN_PROGRESS → Worker重试 → 再次验证
                                    ↓
                          超过重试次数 → 升级或失败
```

### 2. 升级审核 (escalate)

验证失败后，创建人工审核任务。

```python
VerificationConfig(
    fallback_action="escalate",
    escalation_target="human-reviewer-agent"  # 审核者ID
)
```

**工作流程：**
```
验证失败 → SUSPENDED → 创建审核任务 → 等待人工处理
```

### 3. 直接失败 (fail/reject)

验证失败后，直接标记任务为FAILED。

```python
VerificationConfig(
    fallback_action="fail"
)
```

---

## 💡 实战示例

### 示例1：代码开发任务验证

```python
from zentex.tasks.models import ZentexTask, TaskType, TaskContract
from zentex.tasks.verification.models import (
    VerificationConfig,
    VerifierConfig,
    VerificationType,
    VerificationStrategy
)

# 创建代码开发任务，配置多重验证
contract = TaskContract(
    verification=VerificationConfig(
        enabled=True,
        strategy=VerificationStrategy.ALL_MUST_PASS,
        verifiers=[
            # 1. 单元测试
            VerifierConfig(
                verifier_id="unit-tests",
                verifier_type=VerificationType.AUTOMATED_TEST,
                config={
                    "command": "pytest tests/ -v --tb=short",
                    "timeout_seconds": 120
                }
            ),
            # 2. 代码风格检查
            VerifierConfig(
                verifier_id="lint-check",
                verifier_type=VerificationType.AUTOMATED_TEST,
                config={
                    "command": "flake8 src/ --max-line-length=100",
                    "timeout_seconds": 30
                }
            ),
            # 3. LLM代码质量评估
            VerifierConfig(
                verifier_id="code-quality",
                verifier_type=VerificationType.LLM_EVALUATION,
                weight=1.5,
                config={
                    "model": "gpt-4",
                    "evaluation_criteria": [
                        "代码结构清晰，易于维护",
                        "遵循最佳实践",
                        "有适当的注释和文档",
                        "无明显bug或安全漏洞"
                    ]
                }
            )
        ],
        fallback_action="retry",
        max_total_retries=2
    )
)

task = ZentexTask(
    task_id="dev-001",
    title="实现REST API端点",
    task_type=TaskType.AGENT_DELEGATION,
    originator_id="tech-lead-agent",
    idempotency_key="api-endpoint-001",
    contract=contract
)

# Worker完成后提交
result = await service.complete_task_with_verification(
    task_id="dev-001",
    result={
        "output": "API端点已实现",
        "files": ["api.py", "test_api.py"],
        "endpoints": ["/users", "/posts"]
    }
)
```

### 示例2：分析报告任务验证

```python
# 创建分析报告任务
contract = TaskContract(
    verification=VerificationConfig(
        enabled=True,
        strategy=VerificationStrategy.WEIGHTED_VOTE,
        verifiers=[
            # 1. 格式检查（轻量级）
            VerifierConfig(
                verifier_id="format-check",
                verifier_type=VerificationType.RULE_BASED,
                weight=0.5,
                config={
                    "rules": [
                        {"type": "required_field", "field": "executive_summary"},
                        {"type": "required_field", "field": "data_analysis"},
                        {"type": "required_field", "field": "recommendations"},
                        {"type": "min_length", "field": "executive_summary", "min_length": 200},
                        {"type": "min_length", "field": "data_analysis", "min_length": 500}
                    ]
                }
            ),
            # 2. LLM质量评估（重量级）
            VerifierConfig(
                verifier_id="quality-assessment",
                verifier_type=VerificationType.LLM_EVALUATION,
                weight=2.0,
                config={
                    "model": "gpt-4",
                    "evaluation_criteria": [
                        "分析深入，洞察有价值",
                        "数据引用准确",
                        "结论有说服力",
                        "建议可操作"
                    ],
                    "min_confidence": 0.85
                }
            )
        ],
        fallback_action="escalate",
        escalation_target="senior-analyst-agent"
    )
)

task = ZentexTask(
    task_id="analysis-001",
    title="Q4销售数据分析报告",
    task_type=TaskType.COGNITIVE_STEP,
    originator_id="manager-agent",
    idempotency_key="q4-analysis-001",
    contract=contract
)
```

### 示例3：简单任务（禁用验证）

对于简单或不重要的任务，可以禁用验证以提高效率：

```python
contract = TaskContract(
    verification=VerificationConfig(
        enabled=False  # 禁用验证
    )
)

# 或者不配置verification，默认就是禁用的
contract = TaskContract()
```

---

## 🔍 监控和调试

### 1. 检查验证引擎状态

```python
status = service.get_verification_engine_status()
print(status)
# 输出：
# {
#   "available": True,
#   "initialized": True,
#   "registered_verifiers": {
#     "automated_test": "AutomatedTestVerifier",
#     "llm_evaluation": "LLMEvaluationVerifier",
#     "rule_based": "RuleBasedVerifier"
#   },
#   "verifier_count": 3,
#   "message": "Verification engine ready"
# }
```

### 2. 查看验证历史

验证结果会自动记录到transcript_store中：

```python
# 查询某个任务的验证历史
audit_entries = transcript_store.query(
    session_id=f"verification:{task_id}",
    entry_type=BrainTranscriptEntryType.PLUGIN_AUDIT_EVENT
)

for entry in audit_entries:
    print(f"时间: {entry.payload['timestamp']}")
    print(f"动作: {entry.payload['action']}")
    print(f"详情: {entry.payload['details']}")
```

### 3. 验证结果示例

```python
{
  "task_id": "task-001",
  "overall_status": "passed",
  "overall_passed": true,
  "strategy": "all_must_pass",
  "verifier_results": [
    {
      "verifier_id": "unit-tests",
      "verifier_type": "automated_test",
      "status": "passed",
      "passed": true,
      "confidence": 1.0,
      "summary": "自动化测试通过",
      "execution_time_ms": 3456
    },
    {
      "verifier_id": "code-quality",
      "verifier_type": "llm_evaluation",
      "status": "passed",
      "passed": true,
      "confidence": 0.92,
      "summary": "代码质量良好",
      "details": {
        "reasoning": "代码结构清晰...",
        "criteria_met": ["结构清晰", "遵循最佳实践"]
      },
      "execution_time_ms": 8234
    }
  ],
  "summary": "所有 2 个验证器均通过",
  "recommendation": "accept",
  "confidence_score": 0.92,
  "total_execution_time_ms": 11690
}
```

---

## ⚠️ 注意事项

### 1. 性能考虑

- **LLM验证器较慢**：通常需要5-10秒，设置合理的timeout
- **并行执行**：验证引擎会按顺序执行验证器，未来可优化为并行
- **缓存策略**：相同任务的验证结果可以考虑缓存

### 2. 成本控制

- **LLM调用成本**：频繁调用LLM验证器会产生较高成本
- **建议**：只对关键任务启用LLM验证，或使用小模型做初筛

### 3. 可靠性

- **验证器失败不影响系统**：单个验证器异常不会导致系统崩溃
- **超时保护**：所有验证器都有超时机制
- **重试限制**：避免无限重试导致资源浪费

### 4. 安全性

- **命令注入风险**：自动化测试验证器执行shell命令，确保命令来源可信
- **沙箱环境**：建议在隔离环境中执行验证命令

---

## 🎓 最佳实践

### 1. 验证器组合策略

**高可靠性任务：**
```python
strategy = ALL_MUST_PASS
verifiers = [自动化测试, LLM评估, 规则检查]
fallback = escalate
```

**中等可靠性任务：**
```python
strategy = MAJORITY_WINS
verifiers = [自动化测试, LLM评估]
fallback = retry
```

**快速验证任务：**
```python
strategy = ANY_PASSES
verifiers = [规则检查]
fallback = fail
```

### 2. 渐进式启用

1. **第一阶段**：在测试环境中启用验证，观察效果
2. **第二阶段**：对非关键任务启用验证
3. **第三阶段**：逐步扩展到关键任务
4. **第四阶段**：根据历史数据优化验证配置

### 3. 监控和优化

- 定期检查验证通过率
- 分析验证失败的常见原因
- 调整验证器配置和策略
- 移除无效或低价值的验证器

---

## 📚 相关文档

- [验证模块README](README.md) - 技术实现细节
- [TaskContract文档](../DOCUMENTATION.md) - 任务合约完整说明
- [Zentex产品功能文档](../../../Zentex_产品功能文档/) - 系统设计理念

---

## 🆘 常见问题

### Q1: 验证引擎未初始化怎么办？

A: 检查是否正确导入了验证模块：
```python
from zentex.tasks.verification.engine import VerificationEngine
```

如果导入失败，可能是循环依赖问题。确保在TaskManagementService初始化之前，验证模块已经正确安装。

### Q2: 如何添加自定义验证器？

A: 继承BaseVerifier并注册：
```python
from zentex.tasks.verification.verifiers import BaseVerifier

class MyCustomVerifier(BaseVerifier):
    @property
    def verifier_type(self) -> str:
        return "my_custom"
    
    async def verify(self, task, result):
        # 实现验证逻辑
        pass

# 注册
registry.register_verifier_type(
    VerificationType("my_custom"),
    MyCustomVerifier
)
```

### Q3: 验证太慢怎么办？

A: 
1. 减少验证器数量
2. 降低LLM模型的复杂度（使用gpt-3.5而非gpt-4）
3. 缩短timeout时间
4. 考虑禁用某些非关键验证器

### Q4: 如何调试验证失败？

A:
1. 查看transcript中的验证审计日志
2. 检查每个验证器的详细结果
3. 单独测试每个验证器
4. 调整验证器配置参数

---

**祝您使用愉快！** 🎉

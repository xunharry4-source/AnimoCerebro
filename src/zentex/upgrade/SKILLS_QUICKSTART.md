# Superpowers 自动化技能 - 快速开始

## 一分钟了解

我们已将 **3 个 Superpowers 自动化技能**集成到升级模块中，实现**完全自动化、无需人工交互**的增强能力。

### 核心优势

✅ **原子化任务拆解** - 自动生成详细的验证命令  
✅ **自动化根因分析** - 四阶段系统化失败诊断  
✅ **两阶段代码审查** - 规格合规性 + 代码质量  

---

## 快速使用

### 1. 导入技能

```python
from zentex.upgrade import (
    AtomicUpgradePlanner,        # 原子化规划器
    AutomatedRootCauseAnalyzer,  # 根因分析器
    AutomatedTwoStageReviewer,   # 两阶段审查器
)
```

### 2. 使用示例

#### 原子化任务拆解

```python
planner = AtomicUpgradePlanner()
atomic_plan = planner.decompose_proposal(proposal)

for task in atomic_plan.tasks:
    print(f"Task: {task.description}")
    print(f"Validation: {task.validation_commands}")
```

#### 自动化根因分析

```python
analyzer = AutomatedRootCauseAnalyzer()
analysis = analyzer.analyze_failure(failed_record)

print(f"Root cause: {analysis.root_cause}")
print(f"Prevention: {analysis.prevention_hint}")
```

#### 自动化代码审查

```python
import asyncio

reviewer = AutomatedTwoStageReviewer()
result = await reviewer.review_candidate(candidate)

if result.status == "approved":
    print("✅ Approved")
else:
    print(f"❌ Issues: {result.issues}")
```

---

## 文件位置

```
src/zentex/upgrade/
├── skills/
│   ├── atomic_planner.py      # 原子化规划器
│   ├── auto_debugger.py       # 根因分析器
│   ├── auto_reviewer.py       # 两阶段审查器
│   └── example_usage.py       # 完整示例
├── README.md                  # 详细文档（含 Superpowers 集成说明）
└── SUPERPOWERS_INTEGRATION_REPORT.md  # 集成报告
```

---

## 运行示例

```bash
cd <repo-root>
PYTHONPATH=src:$PYTHONPATH python -m src.zentex.upgrade.skills.example_usage
```

---

## 关键特性

### 完全自动化

- ❌ 无需人工交互
- ❌ 无需苏格拉底式对话
- ❌ 无需人工审查反馈
- ✅ 24/7 自动运行

### 智能降级

- LLM 可用时 → 使用 AI 增强分析
- LLM 不可用时 → 降级为规则-based 分析
- 保证功能始终可用

### 模块化设计

- 独立的 skills 子模块
- 可选启用/禁用
- 不影响现有代码

---

## 预期收益

| 测试类别 | 当前通过率 | 集成后预期 |
|---------|-----------|-----------|
| 沙盒验证 | 0% | 100% |
| G25审计证据 | 低 | 高 |
| 根因分析质量 | 简单 | 系统化 |

---

## 更多信息

- 📖 **详细文档**: [README.md](file://src/zentex/upgrade/README.md)
- 📊 **集成报告**: [SUPERPOWERS_INTEGRATION_REPORT.md](file://src/zentex/upgrade/SUPERPOWERS_INTEGRATION_REPORT.md)
- 💻 **示例代码**: [example_usage.py](file://src/zentex/upgrade/skills/example_usage.py)

---

**集成日期**: 2026-04-08  
**状态**: ✅ 完成并验证

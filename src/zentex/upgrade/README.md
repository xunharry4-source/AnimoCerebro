# Upgrade Module / 升级模块

## Overview / 概述

This module implements controlled self-evolution and upgrade mechanisms for the Zentex system. It manages version control, plugin upgrades, evidence tracking, execution management, and AI-powered upgrade executors to enable safe, auditable system evolution.

本模块为Zentex系统实现受控的自我进化和升级机制。它管理版本控制、插件升级、证据跟踪、执行管理和AI驱动的升级执行器，以实现安全、可审计的系统进化。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface defined in `__init__.py` / 所有交互必须通过 `__init__.py` 中定义的统一公共接口进行
- Internal files are implementation details / 内部文件是实现细节

## Public Interface / 公共接口

The unified public interface is exposed through `__init__.py`:

通过 `__init__.py` 暴露的统一公共接口：

```python
from zentex.upgrade import (
    # Service / 服务
    UpgradeService,
    
    # Models / 模型
    UpgradeProposal,
    UpgradeResult,
    UpgradeStatus,
    VersionInfo,
    
    # Execution / 执行
    UpgradeExecutor,
    AIUpgradeExecutor,
    
    # Evidence / 证据
    EvidenceTracker,
    EvidenceRecord,
    
    # Ledger / 账本
    UpgradeLedger,
    
    # Management / 管理
    UpgradeManager,
    
    # Plugin upgrade / 插件升级
    PluginUpgradeHandler,
    
    # Versioning / 版本控制
    VersionManager,
    
    # Cleanup / 清理
    CleanupService,
)
```

## Core Components / 核心组件

### Service Layer / 服务层

- **UpgradeService** (`service.py`): Main upgrade service / 主升级服务
- **UpgradeManager** (`management.py`): Manages upgrade processes / 管理升级流程

### Execution / 执行

- **UpgradeExecutor** (`execution.py`): Executes upgrade operations / 执行升级操作
- **AIUpgradeExecutor** (`ai_executors.py`): AI-powered upgrade execution / AI驱动的升级执行

### Evidence Tracking / 证据跟踪

- **EvidenceTracker** (`evidence.py`): Tracks upgrade evidence / 跟踪升级证据
- **UpgradeLedger** (`ledger.py`): Maintains upgrade ledger / 维护升级账本

### Plugin Upgrades / 插件升级

- **PluginUpgradeHandler** (`plugin/`): Handles plugin upgrades / 处理插件升级

### LLM Integration / LLM集成

- **LLMUpgradeAssistants** (`llm/`): LLM-based upgrade assistance / 基于LLM的升级辅助

### Automated Skills / 自动化技能 (NEW)

**Inspired by Superpowers framework** - Fully automated, no human interaction required.

**受 Superpowers 框架启发** - 完全自动化，无需人工交互。

- **AtomicUpgradePlanner** (`skills/atomic_planner.py`): Automatically decomposes upgrade proposals into atomic tasks (2-5 minutes each) with validation commands
  - **自动升级规划器**：将升级提案自动拆解为原子任务（每个2-5分钟），包含验证命令
  
- **AutomatedRootCauseAnalyzer** (`skills/auto_debugger.py`): Performs four-phase systematic root cause analysis on failures (Reproduce → Isolate → Identify → Verify)
  - **自动化根因分析器**：对失败进行四阶段系统化根因分析（重现 → 隔离 → 识别 → 验证）
  
- **AutomatedTwoStageReviewer** (`skills/auto_reviewer.py`): Conducts automated two-stage code review (Spec Compliance + Code Quality) without human intervention
  - **自动化两阶段审查器**：执行自动化两阶段代码审查（规格合规性 + 代码质量），无需人工干预

**Key Benefits / 核心优势**:
- ✅ No human interaction required / 无需人工交互
- ✅ Improves upgrade success rate / 提升升级成功率
- ✅ Generates detailed validation commands / 生成详细的验证命令
- ✅ Provides actionable prevention hints / 提供可操作的预防建议
- ✅ Reduces rollback frequency / 减少回滚频率

### Version Control / 版本控制

- **VersionManager** (`versioning.py`): Manages system versions / 管理系统版本

## Features / 功能特性

- Controlled self-evolution / 受控的自我进化
- Version management / 版本管理
- Evidence-based upgrades / 基于证据的升级
- Audit trail / 审计跟踪
- Rollback capabilities / 回滚能力
- Plugin upgrade support / 插件升级支持
- **Automated upgrade skills** / **自动化升级技能** (Superpowers-inspired)
  - Atomic task decomposition / 原子化任务拆解
  - Automated root cause analysis / 自动化根因分析
  - Two-stage automated code review / 两阶段自动化代码审查

## Usage Example / 使用示例

### Basic Upgrade / 基础升级

```python
from zentex.upgrade import UpgradeService, UpgradeProposal

# Use only the public interface / 仅使用公共接口
service = UpgradeService()
proposal = UpgradeProposal(description="Improve reasoning")
result = await service.execute_upgrade(proposal)
```

### Using Automated Skills / 使用自动化技能

```python
from zentex.upgrade.skills import (
    AtomicUpgradePlanner,
    AutomatedRootCauseAnalyzer,
    AutomatedTwoStageReviewer,
)
from zentex.upgrade.base_models import SelfUpgradeProposal

# 1. Atomic Task Decomposition / 原子化任务拆解
planner = AtomicUpgradePlanner()
proposal = SelfUpgradeProposal(
    program_id="plugin-example",
    target_metric="reliability",
    baseline_version="1.0.0",
    candidate_version="1.1.0-candidate",
    description="Improve error handling",
    risk_score=0.3,
    capability_gap="Plugin fails on network timeout"
)

# Automatically generate atomic tasks with validation commands
atomic_plan = planner.decompose_proposal(proposal)
print(f"Generated {len(atomic_plan.tasks)} atomic tasks")
for task in atomic_plan.tasks:
    print(f"  - {task.description}")
    print(f"    Validation: {task.validation_commands}")

# 2. Automated Root Cause Analysis / 自动化根因分析
analyzer = AutomatedRootCauseAnalyzer()
failed_record = upgrade_management_store.get("failed-record-id")

analysis = analyzer.analyze_failure(failed_record)
print(f"Root cause: {analysis.root_cause}")
print(f"Prevention: {analysis.prevention_hint}")
print(f"Verification steps: {analysis.verification_plan}")

# 3. Automated Two-Stage Code Review / 自动化两阶段代码审查
import asyncio
reviewer = AutomatedTwoStageReviewer()
candidate_patch = CandidatePatch(...)

async def review():
    result = await reviewer.review_candidate(candidate_patch)
    if result.status == "approved":
        print("✅ Candidate approved for promotion")
    elif result.status == "needs_refactor":
        print(f"⚠️ Needs refactoring: {result.summary}")
        for issue in result.issues:
            print(f"  - [{issue.severity}] {issue.description}")
    else:
        print(f"❌ Rejected: {result.summary}")

asyncio.run(review())
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.upgrade` only, never from `zentex.upgrade.execution` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.upgrade` 导入，绝不能从 `zentex.upgrade.execution` 或其他内部路径导入。

## Integration with Superpowers Framework / 与 Superpowers 框架集成

### Background / 背景

This module integrates automated skills inspired by the [Superpowers framework](https://github.com/obra/superpowers), 
but adapted for **fully automated upgrade workflows without human interaction**.

本模块集成了受 [Superpowers 框架](https://github.com/obra/superpowers) 启发的自动化技能，
但已适配为**完全自动化的升级工作流，无需人工交互**。

### What We Integrated / 我们集成了什么

| Superpowers Skill | Our Implementation | Automation Level |
|-------------------|-------------------|------------------|
| writing-plans | AtomicUpgradePlanner | ✅ Fully automated |
| systematic-debugging | AutomatedRootCauseAnalyzer | ✅ Fully automated |
| subagent-driven-development (review) | AutomatedTwoStageReviewer | ✅ Fully automated |

### What We Excluded / 我们排除了什么

The following Superpowers skills were **NOT** integrated because they require human interaction:

以下 Superpowers 技能**未**集成，因为它们需要人工交互：

- ❌ brainstorming (requires Socratic dialogue)
- ❌ requesting-code-review (requires human feedback)
- ❌ receiving-code-review (requires processing human comments)
- ❌ finishing-a-development-branch (requires user decision on merge/PR)

### Why This Approach / 为什么采用这种方法

1. **Consistency with Auto-Upgrade Philosophy**: Our upgrade system is designed for autonomous operation
   - **与自动升级理念一致**：我们的升级系统专为自主运行而设计

2. **No Blocking on Human Input**: Upgrades can proceed 24/7 without waiting for approvals
   - **不因人工输入而阻塞**：升级可以 24/7 进行，无需等待审批

3. **Improved Success Rate**: Automated skills provide structured validation and analysis
   - **提升成功率**：自动化技能提供结构化的验证和分析

4. **Better Evidence Chain**: Systematic debugging generates comprehensive RCA documentation
   - **更好的证据链**：系统化调试生成全面的根因分析文档

### Architecture Decision / 架构决策

**Decision**: Integrate Superpowers-inspired skills as an **enhancement layer**, not a replacement.

**决策**：将 Superpowers 启发的技能集成为**增强层**，而非替代品。

**Rationale / 理由**:
- Existing upgrade infrastructure is mature and functional
- Skills enhance specific weak points (task decomposition, root cause analysis, code review)
- Maintains backward compatibility with existing code
- Allows gradual adoption without disrupting current workflows

### Future Enhancements / 未来增强

Potential areas for further Superpowers integration:

进一步集成 Superpowers 的潜在领域：

1. **Git Worktree Isolation**: Replace tempfile with Git worktrees for better version tracking
   - **Git Worktree 隔离**：用 Git worktrees 替代临时目录，实现更好的版本追踪

2. **Parallel Task Execution**: Execute independent atomic tasks concurrently
   - **并行任务执行**：并发执行独立的原子任务

3. **Learning from Failures**: Automatically update planning patterns based on historical failures
   - **从失败中学习**：基于历史失败自动更新规划模式

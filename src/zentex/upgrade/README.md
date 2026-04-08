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

### Version Control / 版本控制

- **VersionManager** (`versioning.py`): Manages system versions / 管理系统版本

## Features / 功能特性

- Controlled self-evolution / 受控的自我进化
- Version management / 版本管理
- Evidence-based upgrades / 基于证据的升级
- Audit trail / 审计跟踪
- Rollback capabilities / 回滚能力
- Plugin upgrade support / 插件升级支持

## Usage Example / 使用示例

```python
from zentex.upgrade import UpgradeService, UpgradeProposal

# Use only the public interface / 仅使用公共接口
service = UpgradeService()
proposal = UpgradeProposal(description="Improve reasoning")
result = await service.execute_upgrade(proposal)
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.upgrade` only, never from `zentex.upgrade.execution` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.upgrade` 导入，绝不能从 `zentex.upgrade.execution` 或其他内部路径导入。

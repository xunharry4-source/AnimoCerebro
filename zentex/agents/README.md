# Agents Module / 智能体模块

## Overview / 概述

This module provides agent management, coordination, and service capabilities for the Zentex system. It handles agent lifecycle, registration, and bridge functionality between internal and external agents.

本模块为Zentex系统提供智能体管理、协调和服务能力。它处理智能体生命周期、注册以及内部和外部智能体之间的桥接功能。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface defined in `__init__.py` / 所有交互必须通过 `__init__.py` 中定义的统一公共接口进行
- Internal files (`manager.py`, `service.py`, `bridge.py`) are implementation details / 内部文件（`manager.py`、`service.py`、`bridge.py`）是实现细节

## Public Interface / 公共接口

The unified public interface is exposed through `__init__.py`:

通过 `__init__.py` 暴露的统一公共接口：

```python
from zentex.agents import (
    AgentManager,           # Agent lifecycle management / 智能体生命周期管理
    AgentAsset,             # Agent asset representation / 智能体资产表示
    AgentStatus,            # Agent status enumeration / 智能体状态枚举
    AgentTrustLevel,        # Trust level enumeration / 信任级别枚举
    AgentCoordinationService,  # Coordination service / 协调服务
    AgentRegistrationRequest,  # Registration request model / 注册请求模型
    AgentBridge,            # Component bridge / 组件桥接
)
```

## Core Components / 核心组件

- **AgentManager** (`manager.py`): Manages agent registration, status, and lifecycle / 管理智能体注册、状态和生命周期
- **AgentCoordinationService** (`service.py`): Handles agent coordination and communication / 处理智能体协调和通信
- **AgentBridge** (`bridge.py`): Bridges internal and external agent systems / 桥接内部和外部智能体系统

## Usage Example / 使用示例

```python
from zentex.agents import AgentManager, AgentCoordinationService

# Use only the public interface / 仅使用公共接口
manager = AgentManager()
service = AgentCoordinationService(manager)
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.agents` only, never from `zentex.agents.manager` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.agents` 导入，绝不能从 `zentex.agents.manager` 或其他内部路径导入。

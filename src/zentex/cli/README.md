# CLI Module / 命令行界面模块

## Overview / 概述

This module provides command-line interface functionality and adapter services for the Zentex system. It enables external systems to interact with Zentex through standardized CLI protocols.

本模块为Zentex系统提供命令行界面功能和适配器服务。它使外部系统能够通过标准化的CLI协议与Zentex交互。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface defined in `__init__.py` / 所有交互必须通过 `__init__.py` 中定义的统一公共接口进行
- Internal files (`adapter.py`, `service.py`) are implementation details / 内部文件（`adapter.py`、`service.py`）是实现细节

## Public Interface / 公共接口

The unified public interface is exposed through `__init__.py`:

通过 `__init__.py` 暴露的统一公共接口：

```python
from zentex.cli import (
    CliTransportClient,         # Transport client protocol / 传输客户端协议
    SubprocessCliTransport,     # Subprocess transport implementation / 子进程传输实现
    CliAdapterPlugin,           # CLI adapter plugin / CLI适配器插件
    CliCognitiveToolPlugin,     # Cognitive tool plugin / 认知工具插件
    CliExecutionDomainPlugin,   # Execution domain plugin / 执行域插件
    CliIntegrationService,      # Integration service / 集成服务
)
```

## Core Components / 核心组件

- **CliTransportClient** (`adapter.py`): Protocol definition for CLI transport clients / CLI传输客户端的协议定义
- **SubprocessCliTransport** (`adapter.py`): Subprocess-based transport implementation / 基于子进程的传输实现
- **CliAdapterPlugin** (`adapter.py`): CLI adapter plugin base class / CLI适配器插件基类
- **CliIntegrationService** (`service.py`): Provides CLI integration service capabilities / 提供CLI集成服务能力

## Usage Example / 使用示例

```python
from zentex.cli import CliIntegrationService, SubprocessCliTransport

# Use only the public interface / 仅使用公共接口
transport = SubprocessCliTransport()
service = CliIntegrationService(transport)
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.cli` only, never from `zentex.cli.adapter` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.cli` 导入，绝不能从 `zentex.cli.adapter` 或其他内部路径导入。

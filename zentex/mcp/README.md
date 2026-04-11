# MCP Module / 模型上下文协议模块

## Overview / 概述

This module implements Model Context Protocol (MCP) integration for the Zentex system. It provides adapters, SDK transport, and service management for MCP communications with external tools and services.

本模块为Zentex系统实现模型上下文协议（MCP）集成。它为与外部工具和服务的MCP通信提供适配器、SDK传输和服务管理。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface defined in `__init__.py` / 所有交互必须通过 `__init__.py` 中定义的统一公共接口进行
- Internal files (`adapter.py`, `sdk_transport.py`, `service.py`) are implementation details / 内部文件是实现细节

## Public Interface / 公共接口

The unified public interface is exposed through `__init__.py`:

通过 `__init__.py` 暴露的统一公共接口：

```python
from zentex.mcp import (
    McpTransportClient,         # Transport client protocol / 传输客户端协议
    McpAdapterPlugin,           # MCP adapter plugin / MCP适配器插件
    McpCognitiveToolPlugin,     # Cognitive tool plugin / 认知工具插件
    McpExecutionDomainPlugin,   # Execution domain plugin / 执行域插件
    SseMcpTransport,            # SSE transport implementation / SSE传输实现
    StdioMcpTransport,          # Stdio transport implementation / 标准输入输出传输实现
    McpIntegrationService,      # Integration service / 集成服务
)
```

## Core Components / 核心组件

- **McpTransportClient** (`adapter.py`): Protocol definition for MCP transport clients / MCP传输客户端的协议定义
- **SseMcpTransport** (`sdk_transport.py`): Server-Sent Events transport / 服务器发送事件传输
- **StdioMcpTransport** (`sdk_transport.py`): Standard I/O transport / 标准输入输出传输
- **McpAdapterPlugin** (`adapter.py`): MCP adapter plugin base class / MCP适配器插件基类
- **McpIntegrationService** (`service.py`): Provides MCP integration capabilities / 提供MCP集成能力

## Usage Example / 使用示例

```python
from zentex.mcp import McpIntegrationService, SseMcpTransport

# Use only the public interface / 仅使用公共接口
transport = SseMcpTransport(url="https://mcp-server.example.com")
service = McpIntegrationService(transport)
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.mcp` only, never from `zentex.mcp.adapter` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.mcp` 导入，绝不能从 `zentex.mcp.adapter` 或其他内部路径导入。

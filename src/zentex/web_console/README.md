# Web Console Module / Web控制台模块

## Overview / 概述

This module implements the web-based console and API interface for the Zentex system. It provides RESTful APIs, WebSocket support, real-time monitoring, transcript replay, and a comprehensive web UI for interacting with and managing the Zentex brain system.

本模块为Zentex系统实现基于Web的控制台和API接口。它提供RESTful API、WebSocket支持、实时监控、转录回放以及用于交互和管理Zentex大脑系统的全面Web UI。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface (import from specific modules) / 所有交互必须通过统一的公共接口（从特定模块导入）进行
- Internal files are implementation details / 内部文件是实现细节

## Public Interfaces / 公共接口

This module exposes interfaces through individual files:

本模块通过各个文件暴露接口：

### Main Application / 主应用

```python
from zentex.web_console.app import create_app, ZentexWebApp
```

### API Routes / API路由

```python
from zentex.web_console.api import register_api_routes
from zentex.web_console.router import setup_routers
```

### Services / 服务

```python
from zentex.web_console.services import (
    BrainService,
    SessionService,
    TranscriptService,
    MemoryService,
)
```

### Dependencies / 依赖注入

```python
from zentex.web_console.dependencies import get_brain_runtime, get_transcript_store
```

### CLI / 命令行

```python
from zentex.web_console.cli import web_console_cli
```

## Core Components / 核心组件

### Application Layer / 应用层

- **ZentexWebApp** (`app.py`): Main web application / 主Web应用
- **create_app** (`app.py`): Application factory / 应用工厂

### API Layer / API层

- **register_api_routes** (`api.py`): Registers API endpoints / 注册API端点
- **setup_routers** (`router.py`): Sets up route handlers / 设置路由处理器

### Services / 服务

- **BrainService** (`services/`): Brain management service / 大脑管理服务
- **SessionService** (`services/`): Session management service / 会话管理服务
- **TranscriptService** (`services/`): Transcript management service / 转录管理服务
- **MemoryService** (`services/`): Memory management service / 记忆管理服务

### Routers / 路由器

Multiple routers in `routers/` directory handle different API domains:
`routers/` 目录中的多个路由器处理不同的API域：

- Brain operations / 大脑操作
- Session management / 会话管理
- Transcript access / 转录访问
- Memory queries / 记忆查询
- Plugin management / 插件管理
- And more... / 等等...

## Features / 功能特性

- RESTful API endpoints / RESTful API端点
- WebSocket real-time updates / WebSocket实时更新
- Transcript replay / 转录回放
- Real-time monitoring / 实时监控
- Plugin management UI / 插件管理UI
- System configuration / 系统配置
- Debugging tools / 调试工具

## Usage Example / 使用示例

```python
from zentex.web_console.app import create_app

# Use only the public interface / 仅使用公共接口
app = create_app()
app.run(host="0.0.0.0", port=8000)
```

Or via CLI / 或通过CLI:

```bash
python -m zentex.web_console.cli --port 8000
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules should import from specific web_console submodules. The web console is the external interface layer.

⚠️ **重要提示**：其他模块应从特定的web_console子模块导入。Web控制台是外部接口层。

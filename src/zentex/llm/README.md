# LLM Module / 大语言模型模块

## Overview / 概述

This module provides Large Language Model gateway and integration capabilities for the Zentex system. It manages LLM connections, routing, provider integration, and fail-safe mechanisms.

本模块为Zentex系统提供大型语言模型网关和集成能力。它管理LLM连接、路由、提供商集成和故障安全机制。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface defined in `__init__.py` (if exists) or gateway.py / 所有交互必须通过统一公共接口进行
- Internal implementation details are hidden / 内部实现细节被隐藏

## Public Interface / 公共接口

The unified public interface is exposed through `__init__.py`:

通过 `__init__.py` 暴露的统一公共接口：

```python
from zentex.llm import (
    LLMGateway,        # Main LLM gateway / 主LLM网关
    LLMGatewayCall,    # Gateway call model / 网关调用模型
    LLMTokenUsage,     # Token usage tracking / Token使用跟踪
)
```

## Core Components / 核心组件

- **LLMGateway** (`gateway.py`): Main LLM gateway managing all LLM communications / 主LLM网关，管理所有LLM通信
- **LLMGatewayCall** (`gateway.py`): LLM gateway call model / LLM网关调用模型
- **LLMTokenUsage** (`gateway.py`): Token usage tracking / Token使用跟踪

## Features / 功能特性

- Multi-provider support / 多提供商支持
- Connection pooling / 连接池
- Fail-safe mechanisms / 故障安全机制
- Request routing / 请求路由
- Response caching / 响应缓存

## Usage Example / 使用示例

```python
from zentex.llm import LLMGateway

# Use only the public interface / 仅使用公共接口
gateway = LLMGateway()
response = await gateway.complete(prompt="Hello")
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: Other modules must import from `zentex.llm` only, never from `zentex.llm.gateway` or other internal paths.

⚠️ **重要提示**：其他模块只能从 `zentex.llm` 导入，绝不能从 `zentex.llm.gateway` 或其他内部路径导入。

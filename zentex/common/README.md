# Common Module / 通用模块

## Overview / 概述

This module provides shared infrastructure utilities used across the Zentex system. It includes plugin registry, distributed locking, state management, and cache clients.

本模块提供Zentex系统中使用的共享基础设施实用程序。它包括插件注册表、分布式锁定、状态管理和缓存客户端。

## Module Independence / 模块独立性

**This is an independent functional module.** / **这是一个独立的功能模块。**

- Modules should NOT directly access internal implementation files / 其他模块不应直接访问内部实现文件
- All interactions must go through the unified public interface (individual module imports) / 所有交互必须通过统一的公共接口（各个模块导入）进行
- Internal files are implementation details / 内部文件是实现细节

## Public Interfaces / 公共接口

This module exposes multiple independent interfaces:

本模块暴露多个独立接口：

### Plugin Registry / 插件注册表

```python
from zentex.common.plugin_registry import AbstractPluginRegistry, PluginRegistry
```

### Distributed Locking / 分布式锁定

```python
from zentex.common.locking import AbstractDistributedLock, get_lock_provider
```

### State Management / 状态管理

```python
from zentex.common.state import CognitiveState, WorkingMemoryState
```

### Cache Clients / 缓存客户端

```python
from zentex.common.diskcache_client import get_diskcache_client
from zentex.common.redis_client import get_redis_client, RedisConfig
```

### Coordination / 协调

```python
from zentex.common.coordination import CoordinationService
```

## Core Components / 核心组件

- **AbstractPluginRegistry** (`plugin_registry.py`): Abstract base for plugin registries / 插件注册表的抽象基类
- **AbstractDistributedLock** (`locking.py`): Abstract distributed lock interface / 抽象分布式锁接口
- **CognitiveState** (`state.py`): Cognitive state management / 认知状态管理
- **Cache Clients** (`diskcache_client.py`, `redis_client.py`): Caching infrastructure / 缓存基础设施

## Usage Example / 使用示例

```python
from zentex.common.plugin_registry import PluginRegistry
from zentex.common.locking import get_lock_provider

# Use only the public interfaces / 仅使用公共接口
registry = PluginRegistry()
lock_provider = get_lock_provider()
```

## Design Principle / 设计原则

⚠️ **IMPORTANT**: This module provides foundational utilities. Import specific components as needed, but avoid direct file path imports when possible.

⚠️ **重要提示**：本模块提供基础实用程序。根据需要导入特定组件，但尽可能避免直接的文件路径导入。

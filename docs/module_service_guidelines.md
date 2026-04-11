# Zentex Module Service Facade Guidelines

## 概述 (Overview)

为了规范模块间的调用关系，降低系统耦合度，Zentex 项目采用 **Service Facade（服务门面）** 模式。每个核心功能模块都必须提供一个 `service.py`（或 `service_facade.py`），作为该模块对外提供功能的**唯一入口**。

## 核心原则 (Core Principles)

1.  **唯一入口 (Single Entry Point):** 外部模块严禁直接导入模块内部的实现类（如 `Engine`, `Store`, `Manager` 等）。所有跨模块调用必须通过 `service.py` 中暴露的类或全局函数进行。
2.  **封装复杂性 (Encapsulation):** `service.py` 负责初始化内部组件、管理生命周期、处理异常以及协调子模块之间的逻辑。
3.  **统一接口 (Unified Interface):** 对外提供简洁、高层级的 API，隐藏底层的存储路径、配置细节和复杂的业务流程。
4.  **单例模式 (Singleton Pattern):** 每个 `service.py` 应提供一个全局单例获取函数（如 `get_xxx_service()`），方便其他模块快速接入。

## 模块清单与职责 (Module Registry)

| 模块名称 | 服务文件路径 | 主要职责 | 全局获取函数 |
| :--- | :--- | :--- | :--- |
| **Memory (记忆)** | `src/zentex/memory/service.py` | 协调语义、程序、情景三层记忆的存储与检索。 | `get_memory_service()` |
| **Reflection (反思)** | `src/zentex/reflection/service_facade.py` | 管理反思记录的生成、治理、验证与模式分析。 | `get_reflection_service()` |
| **Learning (学习)** | `src/zentex/learning/service.py` | 处理学习记录的摄入、模式分析与模型进化触发。 | `get_learning_service()` |
| **Safety (安全)** | `src/zentex/safety/service.py` | 执行内容安全检查、策略 enforcement 及审计日志记录。 | `get_safety_service()` |

## 使用示例 (Usage Example)

### ✅ 正确做法：通过 Service Facade 调用
```python
from zentex.memory import get_memory_service

def process_data():
    # 获取全局服务实例
    memory_svc = get_memory_service()
    
    # 调用高层级接口
    record = memory_svc.remember(
        content="用户确认了交易策略",
        title="策略确认",
        layer="episodic"
    )
```

### ❌ 错误做法：直接导入内部实现
```python
# 禁止这样做！这会导致模块间强耦合，且一旦内部重构，所有调用方都会报错。
from zentex.memory.management.enhanced import EnhancedMemoryService

def process_data():
    svc = EnhancedMemoryService(...) 
    svc.store_memory(...)
```

## 开发规范 (Development Standards)

1.  **新增模块时：** 必须同步创建 `service.py`，并在模块的 `__init__.py` 中优先导出服务类。
2.  **更新文档时：** 在模块的 `README.md` 顶部显著位置标注“本模块对外接口请参见 `service.py`”。
3.  **代码审查 (Code Review)：** 如果发现跨模块直接引用非 `service.py` 的文件，应视为架构违规并要求整改。

---
*Last Updated: 2026-04-08*

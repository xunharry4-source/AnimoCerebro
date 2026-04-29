# 外部插件目录

## 概览

本目录（仓库根目录下的 `plugins/`）用于存放 AnimoCerebro 项目的**外部插件**。

## 核心原则

### 独立架构
- 外部插件是**完全独立、专用**的
- **不得依赖** `src/` 下的任何代码（包括但不限于 `src/zentex`）
- 每个插件独立运行，边界清晰

### 可放置内容
您可以在本目录中放置：
- 第三方包
- 独立进程
- 独立脚本
- 外部资源和资产
- 自定义集成

### 集成指南

与 Zentex 主工程的集成应使用：
- ✅ 约定的 API 和协议
- ✅ 配置文件
- ✅ 进程间通信（IPC）
- ✅ 标准接口

**禁止使用**：
- ❌ 从 `src/` 导入 Python 模块
- ❌ 对 `src/zentex` 的直接代码依赖
- ❌ 与核心模块的紧耦合

## 插件类型

### 外部插件 vs 内部插件

**外部插件** (`plugins/`)：
- 将外部功能作为组件连接
- 充当外部系统与大脑之间的桥梁
- **严格规则**：不能导入或调用 `src/` 目录中的任何代码
- 必须仅通过定义的 API 和协议与大脑交互
- 专为第三方集成和自定义扩展设计

**内部插件** (`src/plugins/`)：
- 核心系统自我进化机制的一部分
- 可以访问并与 `src/zentex/` 核心模块交互
- 支持热重载和动态升级
- 实现核心认知功能（如九问 Q1-Q9）
- 由内部插件注册表系统管理

## 示例用例

### 外部插件示例
- 自定义数据源连接器
- 第三方服务集成
- 专用工具适配器
- 外部 API 封装器
- 遗留系统桥接

### 集成模式

#### 模式 1：基于 API 的集成
```python
# 外部插件通过 HTTP/gRPC 通信
import requests

def call_zentex_api(endpoint, data):
    response = requests.post(
        f"http://localhost:8000/api/{endpoint}",
        json=data
    )
    return response.json()
```

#### 模式 2：基于配置
```yaml
# plugin_config.yml
plugin:
  name: my_external_plugin
  api_endpoint: http://zentex:8000/api/v1
  authentication: bearer_token
```

#### 模式 3：消息队列
```python
# 使用 RabbitMQ/Kafka 进行异步通信
import pika

def send_to_zentex(message):
    connection = pika.BlockingConnection(
        pika.ConnectionParameters('localhost')
    )
    channel = connection.channel()
    channel.basic_publish(
        exchange='zentex',
        routing_key='plugin.input',
        body=message
    )
```

## 开发指南

### 独立性要求
1. **无 src/ 导入**：永远不要从 `src/` 目录导入
2. **自包含**：所有依赖必须在插件的 requirements 中声明
3. **清晰接口**：定义明确的 API 契约
4. **错误处理**：优雅地处理所有边缘情况
5. **日志记录**：使用标准日志进行调试

### 最佳实践
- 文档化您的插件 API 和用法
- 提供示例配置
- 为插件包含单元测试
- 遵循语义化版本控制
- 尽可能保持向后兼容性

## 目录结构示例

```
plugins/
├── README.md              # 本文档（英文）
├── README_ZH.md           # 中文版本
├── .gitkeep               # 在 git 中保留目录
├── my_custom_plugin/
│   ├── __init__.py
│   ├── main.py
│   ├── config.yml
│   ├── requirements.txt
│   └── README.md
└── another_plugin/
    ├── __init__.py
    ├── service.py
    └── README.md
```

## 快速开始

1. 为您的插件创建一个新目录
2. 定义插件的接口和功能
3. 仅使用外部依赖实现
4. 独立于主代码库进行测试
5. 文档化与 Zentex 的集成点
6. 提交审查

## 支持

有关外部插件开发的问题：
- 查看 [PLUGIN_GUIDES.md](../docs/operability/PLUGIN_GUIDES.md)
- 查阅 [FUNCTION_MODULES.md](../docs/operability/FUNCTION_MODULES.md)
- 在 GitHub 上打开 issue
- 加入 GitHub Discussions

---

**最后更新**: 2026年4月29日  
**维护者**: AnimoCerebro 开发团队

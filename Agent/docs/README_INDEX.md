# Agent 文档中心

> **独立的外部测试 Agent** - 通过标准协议接入 AnimoCerebro

本文档中心提供 Agent 系统的完整技术文档导航。

---

## 📋 快速导航

### 新用户必读
- **[对接协议说明](README.md)** - 标准 HTTP/WebSocket 接口规范
- **[架构文档](ARCHITECTURE.md)** - 完整的 Agent 系统设计
- **[集成指南](INTEGRATION_GUIDE.md)** - 如何连接你的系统

### 核心原则
✅ **DO**:
- 保持 Agent 完全独立
- 实现标准 HTTP/WebSocket 接口
- 提供完整的文档和元数据

❌ **DON'T**:
- 引入 zentex 模块
- 修改 Zentex 核心代码
- 依赖 Zentex 内部数据结构

---

## 📚 文档分类

### 1️⃣ 基础文档

#### 对接协议
- **[README.md](README.md)** - 完整的对接协议说明 (718行)
  - 标准协议接口定义
  - CLI 工具接入
  - MCP Server 接入
  - Agent 接入
  - 测试 Agent 示例

#### 架构设计
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Agent 模块完整指南 (457行)
  - 模块概述
  - 架构设计
  - 核心组件
  - 外部 Agent 接入流程
  - API 参考

#### 集成指南
- **[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)** - 快速集成指南

### 2️⃣ 社交媒体自动化

基于 Playwright + LangGraph + CrewAI 的智能发布系统。

#### 核心文档
- **[社交发布架构](social_posting/ARCHITECTURE.md)** - 模块边界和数据流 (150行)
- **[工作流程](social_posting/FLOW.md)** - 发布流程详解
- **[节点说明](social_posting/NODES.md)** - LangGraph 节点设计
- **[启动指南](social_posting/STARTUP.md)** - 环境配置和启动
- **[测试指南](social_posting/TESTING.md)** - 测试方法和验证
- **[项目技能](social_posting/PROJECT_SKILLS.md)** - 核心技能和能力

#### 功能特性
| 功能 | 描述 | 状态 |
|------|------|------|
| X.com 发帖 | 带 permalink 验证 | ✅ 已实现 |
| Reddit 发帖 | 社区规则检查 + Flair 选择 | ✅ 已实现 |
| GitHub Discussion | GraphQL API 创建和验证 | ✅ 已实现 |
| AnimoCerebro 宣传 | 多社区定制化内容 | ✅ 已实现 |
| 社区规则管理 | 自动缓存和更新 | ✅ 已实现 |

#### 技术栈
- **Playwright Stealth Chrome** - 绕过检测
- **LangGraph** - 工作流编排
- **CrewAI** - 内容创作协作
- **OCR (Tesseract)** - 视觉识别
- **LLM** - 弹窗翻译和内容生成

### 3️⃣ LLM 配置

- **[LLM_CONFIG_GUIDE.md](LLM_CONFIG_GUIDE.md)** - LLM 配置指南 (5.8KB)
  - Provider 配置
  - API 密钥管理
  - 模型选择

### 4️⃣ 社区规则管理

- **[COMMUNITY_RULES_GUIDE.md](COMMUNITY_RULES_GUIDE.md)** - 社区规则管理指南 (6.8KB)
  - 规则抓取
  - 缓存机制
  - 合规检查

### 5️⃣ 推广助手

- **[ANIMOCEREBRO_PROMOTER_GUIDE.md](ANIMOCEREBRO_PROMOTER_GUIDE.md)** - AnimoCerebro 宣传指南 (12.8KB)
- **[ANIMOCEREBRO_PROMOTION_SUMMARY.md](ANIMOCEREBRO_PROMOTION_SUMMARY.md)** - 宣传系统总结 (11.9KB)

### 6️⃣ 其他文档

- **[QUICK_START.md](QUICK_START.md)** - 快速开始 (6.2KB)
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - 快速参考卡片 (4.8KB)
- **[PROMOTION_AGENT_README.md](PROMOTION_AGENT_README.md)** - 推广 Agent 说明 (8.2KB)
- **[SOCIAL_POSTING_STATUS.md](SOCIAL_POSTING_STATUS.md)** - 社交发布状态 (0.7KB)

---

## 🔌 标准协议接口

### Agent 需要实现的端点

```python
# 1. 能力握手
@app.post("/handshake")
def handshake():
    return {
        "agent_id": "my-agent",
        "version": "1.0.0",
        "capabilities": [...],
        "status": "online"
    }

# 2. 接收任务
@app.post("/execute")
def execute(request: dict):
    task_id = request["task_id"]
    action = request["action"]
    params = request["params"]
    
    result = perform_action(action, params)
    
    return {
        "task_id": task_id,
        "success": True,
        "result": result,
        "timestamp": "..."
    }

# 3. 状态查询
@app.get("/status")
def status():
    return {
        "agent_id": "my-agent",
        "status": "online",
        "uptime_seconds": 3600,
        "tasks_completed": 150
    }
```

### Zentex 提供的调用接口

```bash
POST http://your-agent/handshake   # 能力握手
POST http://your-agent/execute     # 执行任务
GET  http://your-agent/status      # 查询状态
POST http://your-agent/heartbeat   # 心跳上报（可选）
```

### 注册到 Zentex

```bash
curl -X POST http://localhost:8000/api/web/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "agent_name": "My Agent",
    "version": "1.0.0",
    "description": "Agent description",
    "endpoint": "http://localhost:9001",
    "protocol_type": "http",
    "capabilities": [...],
    "scope": ["feature1", "feature2"]
  }'
```

---

## 🧪 测试 Agent 示例

### Calculator Agent (端口 9001)

**功能**: 数学计算

**支持的操作**:
- add (加法)
- subtract (减法)
- multiply (乘法)
- divide (除法)
- power (幂运算)

**启动方式**:
```bash
./start_calculator.sh
```

**测试**:
```bash
curl http://127.0.0.1:9001/status
curl -X POST http://127.0.0.1:9001/handshake
```

### Data Generator Agent (端口 9002)

**功能**: 生成随机 CSV 数据

**生成内容**:
- 文件名: `agent_generated_data.csv`
- 位置: `testdata/` 目录
- 行数: 10 行随机数据
- 字段: id, name, value, category, status, created_at, score, description, is_valid, priority, tags

**启动方式**:
```bash
./start_data_generator.sh
```

---

## 🌐 浏览器自动化 Agent

### 核心模块

| 文件 | 大小 | 描述 |
|------|------|------|
| browser_automation.py | 23KB | 浏览器自动化核心模块 |
| reddit_smart_poster.py | 36KB | Reddit 智能发帖器 (975行) |
| animocerebro_promoter.py | 21KB | AnimoCerebro 宣传助手 (742行) |
| community_rules_manager.py | 17KB | 社区规则管理器 (517行) |
| test_social_media_automation.py | 35KB | 综合测试脚本 (901行) |

### 测试报告

- **[Stealth Chrome 测试报告](STEALTH_CHROME_TEST_REPORT.md)** - 隐身模式测试结果
- **[测试修复记录](TEST_FIX_RECORD.md)** - 问题修复记录
- **[测试配置说明](SOCIAL_MEDIA_TEST_CONFIG.md)** - 测试环境配置
- **[测试总结](SOCIAL_MEDIA_TEST_SUMMARY.md)** - 测试结果汇总

### Reddit 相关文档

- **[Reddit 发帖指南](REDDIT_SMART_POSTER_GUIDE.md)** - Reddit 智能发帖详细说明
- **[规则管理总结](REDDIT_POSTING_WITH_RULES_SUMMARY.md)** - 社区规则管理总结

---

## 📁 文件结构

```
Agent/docs/
├── README.md                      # 本文档
├── ARCHITECTURE.md                # Agent 架构文档
├── INTEGRATION_GUIDE.md           # 集成指南
├── QUICK_START.md                 # 快速开始
├── QUICK_REFERENCE.md             # 快速参考
├── LLM_CONFIG_GUIDE.md            # LLM 配置指南
├── COMMUNITY_RULES_GUIDE.md       # 社区规则管理
├── ANIMOCEREBRO_PROMOTER_GUIDE.md # 宣传指南
├── ANIMOCEREBRO_PROMOTION_SUMMARY.md # 宣传总结
├── PROMOTION_AGENT_README.md      # 推广 Agent 说明
├── SOCIAL_POSTING_STATUS.md       # 社交发布状态
│
├── social_posting/                # 社交媒体发布文档
│   ├── ARCHITECTURE.md            # 发布架构
│   ├── FLOW.md                    # 工作流程
│   ├── NODES.md                   # 节点说明
│   ├── STARTUP.md                 # 启动指南
│   ├── TESTING.md                 # 测试指南
│   └── PROJECT_SKILLS.md          # 项目技能
│
├── promotion_config.example.json  # 配置示例
└── __init__.py                    # 包初始化
```

---

## 🚀 快速开始

### 1. 激活虚拟环境

```bash
source .venv/bin/activate
```

### 2. 启动测试 Agent

```bash
# Calculator Agent
./start_calculator.sh

# Data Generator Agent
./start_data_generator.sh
```

### 3. 运行社交媒体测试

```bash
# Stealth Chrome 测试
python test_auto_stealth_wait.py

# 综合社交媒体测试
python tests/test_social_media_automation.py
```

### 4. 注册到 Zentex

```bash
curl -X POST http://localhost:8000/api/web/agents/register \
  -H "Content-Type: application/json" \
  -d @agent-registration.json
```

---

## 📊 统计数据

| 指标 | 数量 |
|------|------|
| 核心代码 | ~3,500+ 行 |
| 文档 | ~2,500+ 行 |
| 总计 | ~6,000+ 行 |
| 文档文件 | 20+ 个 |
| 测试脚本 | 10+ 个 |

---

## 🔗 相关文档

### 主项目文档
- [AnimoCerebro 文档中心](../../docs/README.md)
- [Agent & MCP 管理](../../docs/operability/AGENT_AND_MCP.md)
- [功能模块总览](../../docs/operability/FUNCTION_MODULES.md)

### 产品文档
- [Zentex 产品功能文档](../../Zentex_产品功能文档/)

---

## ⚠️ 重要提醒

### 真实性边界
- **禁止伪造执行结果** - 所有测试结果必须基于真实运行
- **证据必须物理存在** - 截图、日志、API 响应等
- **失败必须显式标注** - 不得掩盖错误

### 安全红线
- **禁止引入 Zentex 代码** - 外部 Agent 不能 import zentex.*
- **禁止修改核心代码** - 通过标准 API 交互
- **初始状态为 PENDING** - 必须通过握手和安全审计

---

**最后更新**: 2026-04-27  
**维护者**: AnimoCerebro Team  
**许可证**: GNU GPL v3

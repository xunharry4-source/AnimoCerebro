# Self-Promotion Agent 快速开始指南

## 🚀 一键安装和启动

### 方法一：使用 Make（推荐）

```bash
# 1. 安装所有依赖
make self-promotion-install

# 2. 启动服务器
make self-promotion-dev

# 3. 运行测试
make self-promotion-test
```

### 方法二：使用独立脚本

```bash
# 1. 安装依赖
./scripts/install_self_promotion_deps.sh

# 2. 启动服务器
./scripts/start_self_promotion_agent.sh

# 3. 运行测试
pytest Agent/test_self_promotion_agent.py -v
```

## 📋 完整工作流程

### 1️⃣ 安装阶段

```bash
# 使用 Make（自动处理所有依赖）
make self-promotion-install

# 输出示例：
# ==========================================
#   Installing Self-Promotion Agent...
# ==========================================
# >>> Installing FastAPI and dependencies...
# >>> Installing Playwright...
#    Method: npm CLI (recommended by Playwright docs)
# ✅ Playwright Python package installed
# ✅ Chromium browser ready
# ==========================================
#   ✓ Self-Promotion Agent installed!
# ==========================================
```

### 2️⃣ 配置阶段

创建或编辑 `.env` 文件：

```bash
# 查看当前默认提供商
cat config/provider_tools.yml | grep default_provider
# 输出: default_provider: openai_compat

# 根据提供商配置 API 密钥
echo "your-api-key=your-local-proxy-key" >> .env  # openai_compat
# 或
echo "GEMINI_API_KEY=your-gemini-key" >> .env      # gemini
# 或
echo "OPENAI_API_KEY=sk-your-key" >> .env          # openai
```

### 3️⃣ 启动阶段

```bash
# 启动服务器
make self-promotion-dev

# 输出示例：
# 🚀 Starting Self-Promotion Agent server...
# 🔍 Checking dependencies...
# ✅ Playwright installed
# ✅ Chromium browser ready
# ✅ Found .env file for LLM configuration
# 
# ==========================================
#   Self-Promotion Agent Configuration
# ==========================================
#   Port: 9004
#   Host: 127.0.0.1
#   Reload: Enabled
#   WebSocket: websockets-sansio
# ==========================================
# 
# 🌐 Starting FastAPI server...
# INFO:     Uvicorn running on http://127.0.0.1:9004
```

### 4️⃣ 验证阶段

打开新终端，运行：

```bash
# 健康检查
curl http://127.0.0.1:9004/status

# 握手测试
curl -X POST http://127.0.0.1:9004/handshake

# 查看 API 文档
open http://127.0.0.1:9004/docs
```

### 5️⃣ 测试阶段

```bash
# 运行单元测试
make self-promotion-test

# 输出示例：
# 🧪 Running Self-Promotion Agent tests...
# pytest Agent/test_self_promotion_agent.py -v
# ===================== test session starts ======================
# collected 15 items
# 
# Agent/test_self_promotion_agent.py::TestSelfPromotionAgentInit::test_agent_init_normal PASSED
# ...
# =================== 14 passed, 1 skipped in 0.05s ===============
```

## 🎯 常用命令速查

### Make 命令

| 命令 | 说明 |
|------|------|
| `make self-promotion-install` | 安装所有依赖（FastAPI + Playwright） |
| `make self-promotion-dev` | 启动开发服务器 |
| `make self-promotion-test` | 运行单元测试 |
| `make help` | 查看所有可用命令 |

### 脚本命令

| 命令 | 说明 |
|------|------|
| `./scripts/install_self_promotion_deps.sh` | 交互式安装依赖 |
| `./scripts/start_self_promotion_agent.sh` | 启动服务器 |

### cURL 测试

```bash
# 健康检查
curl http://127.0.0.1:9004/status

# 握手
curl -X POST http://127.0.0.1:9004/handshake

# 生成周计划
curl -X POST http://127.0.0.1:9004/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-001",
    "action": "generate_weekly_plan",
    "params": {
      "project_info": {
        "name": "Test Project",
        "description": "A test project",
        "tech_stack": ["Python"],
        "features": ["Feature 1"]
      },
      "target_audience": "Developers",
      "goals": ["Test"],
      "target_communities": ["r/test"],
      "week_start": "2026-04-20T00:00:00+00:00"
    }
  }'

# 提交人类干预请求
curl -X POST http://127.0.0.1:9004/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-002",
    "action": "submit_human_request",
    "params": {
      "content": "Please promote our new feature",
      "platform": "x",
      "priority": "high"
    }
  }'

# 查询审计日志
curl -X POST http://127.0.0.1:9004/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-003",
    "action": "get_audit_log",
    "params": {
      "limit": 5
    }
  }'
```

## 🔧 故障排除

### 问题 1：Playwright 安装失败

```bash
# 使用国内镜像
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
playwright install chromium

# 或手动安装
npx playwright install chromium --with-deps
```

### 问题 2：端口被占用

```bash
# 查找占用端口的进程
lsof -i :9004

# 杀死进程
kill -9 <PID>

# 或使用不同端口
uvicorn Agent.self_promotion_server:app --port 9005
```

### 问题 3：LLM 调用失败

```bash
# 检查 .env 文件
cat .env

# 检查配置文件
cat config/provider_tools.yml

# 测试 LLM 连接
python -c "from zentex.llm import get_llm_service; print(get_llm_service())"
```

### 问题 4：浏览器无法启动

```bash
# 重新安装浏览器
playwright install chromium --with-deps

# 检查浏览器版本
playwright show-browsers

# 测试浏览器
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(); print('✅ Browser works'); b.close(); p.stop()"
```

## 📚 相关文档

- [Self-Promotion Agent README](SELF_PROMOTION_AGENT_README.md) - 完整使用指南
- [LLM 配置说明](LLM_CONFIG_GUIDE.md) - LLM 提供商配置详解
- [Playwright 官方文档](https://playwright.dev/docs/getting-started-cli) - 浏览器自动化

## 💡 提示

1. **首次使用**：建议先运行 `make self-promotion-install` 确保所有依赖正确安装
2. **开发模式**：使用 `make self-promotion-dev` 启动，支持代码热重载
3. **测试驱动**：修改代码后运行 `make self-promotion-test` 验证功能
4. **查看日志**：服务器运行时会在终端显示详细日志，包括 LLM 调用和浏览器操作

---

**祝使用愉快！** 🎉

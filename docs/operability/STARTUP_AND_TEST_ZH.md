# 启动与测试说明

本文档说明当前仓库如何一键启动前端，以及如何一键运行前后端测试。

**最后更新**: 2026-04-09

## 项目当前状态

- ✅ 已提供可运行的后端 FastAPI Web Console 入口：`zentex.web_console.dev_server:app`
- ✅ 一键启动会同时拉起后端（Uvicorn）与前端（Vite），并做依赖检查（Fail-Closed）
- ✅ 一键重启会清理占用端口的旧进程后重新执行一键启动
- ✅ WebSocket 实现统一使用 `websockets-sansio`
- ✅ 后端健康检查机制完善，确保服务可用性
- ✅ 支持自定义端口配置（BACKEND_PORT, FRONTEND_PORT）

## 一键命令

### 一键重启（最常用）

当你遇到以下情况，优先用这一条：
- 前端/后端进程残留导致端口被占用
- Uvicorn reload 卡死、前端 Vite 热更新异常
- 你希望“先清理，再完整拉起”确保页面绑定真实后端

```bash
make restart-dev
```

等价于直接执行脚本：

```bash
./scripts/restart_dev.sh
```

重启脚本会做这些事：
- 读取端口：`BACKEND_PORT`（默认 `8000`）、`FRONTEND_PORT`（默认 `5173`）
- 用 `lsof` 找到占用端口的进程并尝试结束（先 `TERM`，再 `KILL`）
- 若端口仍处于占用状态，会 fail-closed 直接中止，并打印占用端口的 PID 供手动处理
- 若当前终端/环境没有权限结束占用端口的进程（例如受沙箱限制），脚本会提示使用 `sudo` 手动关闭或临时改端口启动
- 兜底清理当前项目相关的 `uvicorn zentex.web_console.dev_server:app`
- 最后调用 `make dev` 重新启动前后端

### 环境初始化（首次使用）

```bash
# 一键安装所有依赖（后端 + 前端）
./scripts/setup_env.sh
```

或分步安装：

```bash
# 1. 安装后端依赖（建议使用本地虚拟环境）
make backend-install
# 等价于：
# python3 -m venv .venv
# .venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt

# 2. 安装前端依赖
make frontend-install
# 等价于：
# cd src/admin-portal && npm install
```

### 安装前端依赖

```bash
make frontend-install
# 等价于：cd src/admin-portal && npm install
```

### 一键运行全部测试

```bash
make test
# 等价于：./scripts/test_all.sh
```

该命令会执行：
- **Python 测试**：`pytest test tests`（90个测试文件，291+用例）
- **前端测试**：`cd src/admin-portal && npm run test`

#### 测试分类说明

**核心模块测试**：
- Runtime 运行时测试：`tests/runtime/`
- 插件系统测试：`tests/plugins/`
- Web Console API 测试：`tests/web_console/`
- Agent 系统测试：`tests/agents/`
- 学习系统测试：`tests/learning/`
- 升级系统测试：`tests/upgrade/`
- 记忆系统测试：`tests/memory/`
- 反思系统测试：`tests/reflection/`

**专项测试**：
- Phase 3 进化系统：`pytest tests/test_phase3_evolution.py`（4个测试）
- Phase 4 记忆巩固：`pytest tests/test_phase4_memory.py`（4个测试）
- 真实业务场景：`pytest tests/test_real_business_cases.py`（5个端到端测试）
- ThinkLoop 认知循环：`pytest tests/test_think_loop.py`（5个核心测试）

**WebSocket 实时流测试**：
- 协议级回归：
  ```bash
  pytest -q tests/web_console/test_events_stream_lifecycle.py
  pytest -q tests/web_console/test_api.py -k events_stream
  ```
- 真实 uvicorn 集成 soak：
  ```bash
  pytest -q tests/web_console/test_events_stream_integration.py -m integration
  ```
  
  说明：
  - 这条集成测试会临时启动一个真实 `uvicorn --ws websockets-sansio` 进程
  - 使用真实 `websockets` 客户端多轮执行"连接 -> 空闲 -> 关闭"
  - 断言日志里不得出现 `keepalive ping failed` 或 `socket.send() raised exception.`

### 一键启动开发环境

```bash
make dev
# 等价于：./scripts/dev_all.sh
```

该命令会执行：
1. **依赖检查**：
   - 后端：必须具备 `fastapi` / `pydantic` / `uvicorn`，并具备 `websockets` 或 `wsproto` 其一
   - 前端：必须已安装 `node_modules`
   - 若依赖缺失则直接退出并提示安装方式（不伪装成已启动）

2. **端口检查**：
   - 检查 BACKEND_PORT（默认 8000）是否被占用
   - 检查 FRONTEND_PORT（默认 5173）是否被占用
   - 若端口被占用则提示使用 `make restart-dev`

3. **启动后端**：
   - 命令：`uvicorn zentex.web_console.dev_server:app --reload --ws websockets-sansio --host 127.0.0.1 --port $BACKEND_PORT`
   - 特性：热重载、WebSocket sansio 实现、超时保活 5 秒

4. **健康检查**：
   - 等待后端就绪（最多 30 秒）
   - 检查点：`curl http://127.0.0.1:$BACKEND_PORT/api/web/overview`
   - 若后端进程意外退出则中止启动

5. **启动前端**：
   - 命令：`cd src/admin-portal && VITE_BACKEND_PORT=$BACKEND_PORT npm run dev -- --host 127.0.0.1 --port $FRONTEND_PORT`
   - 特性：Vite 热模块替换（HMR）

6. **输出访问地址**：
   - Frontend: http://127.0.0.1:5173
   - Backend:  http://127.0.0.1:8000
   - API:      http://127.0.0.1:8000/api/web/plugins/cognitive

**默认端口**：
- 后端：`http://127.0.0.1:8000`
- 前端：`http://127.0.0.1:5173`

**自定义端口**：
```bash
BACKEND_PORT=8001 FRONTEND_PORT=5174 make dev
```

### 一键重启开发环境（清理旧进程 + 重启）

```bash
make restart-dev
# 等价于：./scripts/restart_dev.sh
```

**适用场景**：
- 前端/后端进程残留导致端口被占用
- Uvicorn reload 卡死、前端 Vite 热更新异常
- 希望"先清理，再完整拉起"确保页面绑定真实后端
- 修改了核心配置需要完全重启

**重启流程**：
1. 读取端口配置：`BACKEND_PORT`（默认 8000）、`FRONTEND_PORT`（默认 5173）
2. 用 `lsof` 找到占用端口的进程并尝试结束（先 TERM，再 KILL，最多 5 次尝试）
3. 若端口仍处于占用状态，会 fail-closed 直接中止，并打印占用端口的 PID 供手动处理
4. 若当前终端/环境没有权限结束占用端口的进程（例如受沙箱限制），脚本会提示：
   - 使用 `sudo` 手动关闭：`sudo lsof -ti :8000 | xargs sudo kill -9`
   - 或临时改端口启动：`BACKEND_PORT=8001 make dev`
5. 兜底清理当前项目相关的 `uvicorn zentex.web_console.dev_server:app` 进程
6. 清理大型运行时文件以加速启动（`.zentex/runtime/*.jsonl` > 1MB 的文件）
7. 最后调用 `make dev` 重新启动前后端

**示例（重启到非默认端口）**：
```bash
BACKEND_PORT=8001 FRONTEND_PORT=5174 make restart-dev
```

## 可单独执行的命令

### 仅启动前端

```bash
make frontend-dev
```

### 仅运行前端测试

```bash
make frontend-test
```

### 仅运行 Python 测试

```bash
make backend-test
```

### 仅运行 WebSocket 实时流回归

协议级回归：

```bash
pytest -q tests/web_console/test_events_stream_lifecycle.py
pytest -q tests/web_console/test_api.py -k events_stream
```

真实 `uvicorn` 集成 soak：

```bash
pytest -q tests/web_console/test_events_stream_integration.py -m integration
```

说明：
- 这条集成测试会临时启动一个真实 `uvicorn --ws websockets-sansio` 进程
- 使用真实 `websockets` 客户端多轮执行“连接 -> 空闲 -> 关闭”
- 断言日志里不得出现 `keepalive ping failed` 或 `socket.send() raised exception.`

## 当前前端脚手架

当前已补齐 `src/admin-portal` 的最小前端工程配置：
- `package.json`
- `tsconfig.json`
- `vite.config.ts`
- `index.html`
- `src/main.tsx`
- `src/App.tsx`
- `src/test/setup.ts`

因此以下文件可以直接纳入前端测试：
- `src/admin-portal/src/pages/dashboard/RealtimeDashboard.tsx`
- `src/admin-portal/src/pages/dashboard/RealtimeDashboard.test.tsx`

## 当前后端状态说明

当前 Python 侧已经具备大量运行时模块与测试：
- `src/zentex/runtime/*`
- `tests/*`
- `test/runtime/test_transcript.py`

并且已经提供 FastAPI app 入口：
- `src/zentex/web_console/dev_server.py`（开发态 Web Console 服务）

因此当前“前后端一键启动”中的后端部分是“真实启动 + 真实健康检查”，仍遵守 Zentex 的禁止假启动原则。

## 推荐启动顺序

1. 安装后端依赖（建议虚拟环境）

```bash
make backend-install
```

2. 安装前端依赖

```bash
make frontend-install
```

3. 跑全量测试

```bash
make test
```

4. 一键启动开发环境

```bash
make dev
```

## 下一步建议

如果要从 dev_server 进一步走向生产化入口，建议补齐：
- 独立的 production app 装配（将 dev seed 与 production wiring 分离）
- 更严格的启动配置校验（例如必须绑定 `core.model_provider` 的 active 插件）
- 生产级日志、指标与持久化存储接入

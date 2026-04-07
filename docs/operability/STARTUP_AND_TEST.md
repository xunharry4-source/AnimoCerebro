# 启动与测试说明

本文档说明当前仓库如何一键启动前端，以及如何一键运行前后端测试。

当前状态：
- 已提供可运行的后端 FastAPI Web Console 入口：`zentex.web_console.dev_server:app`
- 一键启动会同时拉起后端（Uvicorn）与前端（Vite），并做依赖检查（Fail-Closed）
- 一键重启会清理占用端口的旧进程后重新执行一键启动

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

### 安装后端依赖（建议使用本地虚拟环境）

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
```

也可以使用封装命令：

```bash
make backend-install
```

### 安装前端依赖

```bash
make frontend-install
```

### 一键运行全部测试

```bash
make test
```

该命令会执行：
- Python 测试：`pytest test tests`
- 前端测试：`cd src/admin-portal && npm run test`

补充说明：
- `tests/web_console/test_events_stream_lifecycle.py` 与 `tests/web_console/test_api.py -k events_stream` 负责校验实时事件流的协议语义：`idle disconnect`、`cursor 增量推送`、`无 cursor 默认只订阅未来增量`
- 更长时间的 WebSocket churn / soak 不应伪装成 `TestClient` 单测；这类验证由真实 `uvicorn --ws websockets-sansio` 子进程集成测试承担，见 `tests/web_console/test_events_stream_integration.py`

### 一键启动开发环境

```bash
make dev
```

该命令会执行：
- 启动后端 Web Console：`uvicorn zentex.web_console.dev_server:app --reload --ws websockets-sansio`
- 启动前端 Admin Portal（Vite dev server）
- 后端依赖检查（必须具备 `fastapi` / `pydantic` / `uvicorn`，并具备 `websockets` 或 `wsproto` 其一）
- 若依赖缺失则直接退出并提示安装方式（不伪装成已启动）

默认端口：
- 后端：`http://127.0.0.1:8000`
- 前端：`http://127.0.0.1:5173`

可通过环境变量覆盖端口（与脚本保持一致）：

```bash
BACKEND_PORT=8001 FRONTEND_PORT=5174 make dev
```

### 一键重启开发环境（清理旧进程 + 重启）

```bash
make restart-dev
```

说明：
- 会优先清理占用 `BACKEND_PORT` / `FRONTEND_PORT` 的旧进程（默认 8000/5173）
- 随后调用 `make dev` 重新拉起服务
- 该命令用于“端口被占用 / reload 卡死 / 前端残留 node 进程”等情况的临床级自救

示例（重启到非默认端口）：

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

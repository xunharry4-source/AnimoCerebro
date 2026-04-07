# openClaw 插件真实测试与联调记录

更新时间：`2026-04-01`

本文档记录 `integrations/openclaw-plugin/` 与 Zentex `openClaw bridge API` 的真实安装、启用和联调过程，目的是避免下次重复踩坑。

## 结论先看

已确认通过：

- `openClaw` CLI 本机可用
- 插件可真实构建，且必须使用编译产物 `dist/index.js`
- 插件可真实安装到隔离的 `openclaw --dev` 环境
- 插件可被 `openclaw plugins inspect zentex-brain-bridge` 识别为 `loaded`
- Zentex 本地 bridge 服务可真实启动并对外提供：
  - `GET /api/host-adapters/openclaw/state`
  - `POST /api/host-adapters/openclaw/capability-handshake`
- 隔离的 OpenClaw dev gateway 可真实启动并通过 `health` 检查
- 真实 Web API `GET /api/web/openclaw/state` 可返回九问摘要与一致性结果
- 真实 `/api/web/agents` 可看到 `openclaw-local`
- 真实 `/api/web/agents/openclaw-local/handshake` 可读
- provider-free 的 `POST /tools/invoke -> zentex_state` 已打通
- 真实 trace 已出现 `tool:entered`

当前不再纳入默认标准的点：

- `before_dispatch` 已从插件主链和代码中删除，不再作为插件职责
- `openclaw --dev agent --agent main ...` 仍可能先撞到 OpenClaw 自身模型鉴权问题：
  - `No API key found for provider "anthropic"`
- 因此默认真实验收只覆盖注册、状态同步、工具转发和回执闭环

当前代码已切到新的收口方案，但真实环境需要按新的 `real-check` 重新复跑：

- 插件启动链已改成多入口幂等 bootstrap，不再只赌 `gateway_start`
- `register(api)`、`gateway_start`、显式工具/命令入口都会触发同一个 `ensureBridgeRuntimeStarted()`
- runtime snapshot 会在首次 bootstrap 尝试时就落盘
- runtime trace 已升级为正式调试接口，记录 `bootstrap:*`、`tool:entered`、`command:entered`
- `npm run openclaw-plugin:real-check` 已改为优先检查：
  - runtime snapshot / trace
  - `/api/web/agents`
  - `/api/web/agents/openclaw-local/handshake`
  - provider-free 的 `POST /tools/invoke -> zentex_state`
- `openclaw --dev agent` 只保留为 provider-backed 增强验收
- `before_tool_call` 默认关闭，只保留为可选增强

## 2026-04-01 复跑结果

本次重新拉起真实 bridge 与 dev gateway 后，`provider-free` 主链已拿到完整通过结论。

执行命令：

```bash
HOME=/tmp/openclaw-home openclaw --dev gateway run --port 19001 --force --allow-unconfigured --verbose
curl --max-time 5 -sS -H 'Authorization: Bearer bridge-token' http://127.0.0.1:18989/api/host-adapters/openclaw/state
npm run openclaw-plugin:real-check
```

关键结果：

- `npm run openclaw-plugin:real-check` 返回 `ok: true`
- `bridge.state_ok == true`
- `bridge.handshake_ok == true`
- `gateway_health.ok == true`
- `plugin_inspect.ok == true`
- `runtime_snapshot.exists == true`
- `runtime_snapshot.data.handshake_status == "ok"`
- `runtime_snapshot.data.registration_status == "ok"`
- `runtime_snapshot.data.last_heartbeat_success_at` 已写入
- `runtime_trace` 含 `bootstrap:begin / bootstrap:register_ok / bootstrap:heartbeat_ok / tool:entered`
- `/api/web/openclaw/state` 返回 `nine_question_alignment.matches == true`
- 真实 `/api/web/agents` 可见 `openclaw-local`
- 真实 `/api/web/agents/openclaw-local/handshake` 可读

当前剩余未闭环项：

- `provider_smoke.status == "skipped"`，原因仍是 provider key 缺失
- 该项只属于 provider-backed 增强验收，不再阻断默认主链

当前代码已补上的收口能力：

- 插件会持久化运行态快照到：
  - `$HOME/.openclaw-dev/zentex-brain-bridge.runtime.json`
- 插件会持久化运行态 trace 到：
  - `$HOME/.openclaw-dev/zentex-brain-bridge.trace.log`
- `zentex_state` 会返回 `plugin_runtime`，直接暴露：
  - `startup_status`
  - `startup_source`
  - `last_start_attempt_at`
  - `last_start_success_at`
  - `handshake_status`
  - `last_handshake_at`
  - `registration_status`
  - `last_registration_at`
  - `last_heartbeat_at`
  - `last_register_attempt_at`
  - `last_register_success_at`
  - `last_heartbeat_attempt_at`
  - `last_heartbeat_success_at`
  - `last_sync_error`
  - `tool_review_count`
  - `pending_inbox_commands`
  - `pending_help_requests`
  - `last_inbox_poll_at`
  - `last_inbox_error`
  - `last_tool_review_event`
  - `last_bridge_error`
- 新增工具：
  - `zentex_inbox_state`
  - `zentex_update_inbox_item`
- 已提供 3 个标准脚本：
  - `npm run openclaw-plugin:probe`
  - `npm run openclaw-plugin:real-setup`
  - `npm run openclaw-plugin:real-check`

当前主链口径已收敛为：

- 插件负责注册、状态同步、任务转发、回执回写
- `openClaw` 自己决定是否调用 `zentex_state / zentex_think_task / zentex_delegate_task`
- 不再把自动消息拦截当成插件主职责

## 2026-04-01 更深真实交互复跑

本轮新增了 provider-free 的深度联调脚本：

```bash
npm run openclaw-plugin:real-deep-check
```

脚本目标：

- 轮询 `openclaw --dev health`
- 轮询 bridge `/api/host-adapters/openclaw/state`
- 通过 gateway `POST /tools/invoke` 调用：
  - `zentex_inbox_state`
  - `zentex_state`
  - `zentex_delegate_task`
  - `zentex_update_inbox_item`
  - `zentex_task_checkpoint`
- 再核对：
  - `/api/web/delegation/state`
  - `/api/web/formal-autonomy/tasks`
  - runtime snapshot / trace

本次真实结果：

- 脚本已生成完整 JSON 报告
- 结论当前为 `ok: false`
- 失败不是“脚本没写完”，而是隔离 `openclaw --dev` gateway 到本地 bridge 的更深真实链路仍不稳定

本次观察到的真实失败现象：

- `openclaw --dev health --json --timeout 5000` 间歇报：
  - `gateway closed (1006 abnormal closure)`
- `openclaw --dev plugins inspect zentex-brain-bridge` 虽然仍显示 `Status: loaded`，但 stderr 会出现：
  - `bridge request failed: TypeError: fetch failed`
  - `bootstrap degraded: Zentex bridge is unavailable.`
- gateway 日志持续出现：
  - `inbox poll failed: OpenClaw 大脑桥当前只允许本机 loopback 访问。`
  - `openclaw agent sync failed: Error: OpenClaw 大脑桥当前只允许本机 loopback 访问。`
- 即使直接对本地 bridge `curl` 可得到 `200` 和真实 JSON，隔离 gateway 内部的深度工具调用仍没有稳定闭环

已确认根因之一：

- 这类报错不一定表示“用户真的在远程访问”
- 当 Zentex 部署在 Docker 容器内，而 OpenClaw 在宿主机或其他网络命名空间访问它时，源地址通常会变成容器网桥地址，而不是 `127.0.0.1`
- 如果 Zentex 没有设置 `ZENTEX_OPENCLAW_BRIDGE_ALLOW_NON_LOOPBACK=true`，就会把这种“同机但跨网桥”的访问误判成非法来源

当前修正口径：

- Docker / split-process / reverse-proxy 场景默认应开启 `ZENTEX_OPENCLAW_BRIDGE_ALLOW_NON_LOOPBACK=true`
- 同时保留 `ZENTEX_OPENCLAW_BRIDGE_TOKEN`，并配合 TLS、反向代理或内网隔离

当前判断：

- `real-check` 级别的 provider-free 主链仍可通过
- 但“更深真实交互”这一级别，也就是 `delegate_task -> inbox -> receipt/checkpoint`，当前**尚未完成**
- 当前应按真实 `P1` 集成缺陷处理，而不是把 `plugin loaded` 或历史 heartbeat 误写成“深度交互已验收”

## 正确的联调方式

### 1. 先准备 Zentex 本地 Python 环境

在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

原因：

- 本机系统 Python 默认缺 `PyYAML / fastapi / uvicorn`
- 不装依赖，`animocerebro web start` 起不来

### 2. 先构建插件，再安装插件

正确顺序：

```bash
npm --prefix integrations/openclaw-plugin run build
HOME=/tmp/openclaw-home openclaw --dev plugins install -l ./integrations/openclaw-plugin
```

原因：

- 插件入口现在指向 `integrations/openclaw-plugin/dist/index.js`
- 如果不先构建，真实 OpenClaw 运行时没有可加载的 JS 产物

### 3. 用隔离 HOME 做真实联调

建议固定使用：

```bash
HOME=/tmp/openclaw-home openclaw --dev ...
```

原因：

- 不污染现有 `~/.openclaw` / `~/.openclaw-dev`
- 插件安装、gateway token、dev workspace、会话状态都隔离在 `/tmp/openclaw-home`
- 可随时删掉 `/tmp/openclaw-home` 重来

### 4. 先起 Zentex bridge，再起 OpenClaw gateway

正确顺序：

```bash
ZENTEX_OPENCLAW_BRIDGE_TOKEN=bridge-token .venv/bin/animocerebro web start \
  --state-dir .animocerebro/state \
  --config animocerebro_vision.yaml \
  --host 127.0.0.1 \
  --port 18989
```

然后再配置 OpenClaw 插件：

```bash
HOME=/tmp/openclaw-home openclaw --dev config set plugins.entries.zentex-brain-bridge.config.zentexBaseUrl http://127.0.0.1:18989
HOME=/tmp/openclaw-home openclaw --dev config set plugins.entries.zentex-brain-bridge.config.zentexAuthToken bridge-token
```

然后再起 gateway：

```bash
HOME=/tmp/openclaw-home openclaw --dev gateway run --port 19001 --force --allow-unconfigured --verbose
```

### 5. dev gateway 最好直接跑默认端口 `19001`

这次联调里最容易绕远路的点之一：

- `openclaw --dev agent ...` 默认会去找 dev gateway 的默认端口 `19001`
- 即使你手工把 gateway 起在 `18789`，`agent` 相关命令也未必按你预期走自定义地址
- 所以如果目的是“让 `openclaw --dev` 这套 CLI 自然打到 gateway”，最稳妥的方法就是直接把 gateway 起在 `19001`

## 已确认有效的真实检查命令

### 插件构建与单测

```bash
npm --prefix integrations/openclaw-plugin run build
npm run openclaw-plugin:test
npm run web:test -- --run src/studio/src/App.test.tsx
npm run web:build
npm run openclaw-plugin:probe
```

本次结果：

- `pytest -q tests/test_openclaw_bridge_api.py tests/test_g31_web_console_api.py` 通过，当前为 `28 passed`
- `openclaw-plugin:test` 通过，当前为 `6 files / 20 tests passed`
- `web:test -- --run src/studio/src/App.test.tsx` 通过，当前为 `13 passed`
- `web:build` 通过
- `probe` 输出完整 JSON 报告，覆盖 6 类 `think-task` 和 4 类 `think-action`

### 标准化真实联调脚本

先做隔离安装与配置：

```bash
npm run openclaw-plugin:real-setup
```

本次结果已经确认：

- `ok: true`
- `plugin_loaded: true`
- 已串行写入 bridge 地址、token、autoHandshake 和 `criticalActionMode`

再在 bridge 和 gateway 都启动后做真实检查：

```bash
npm run openclaw-plugin:real-check
```

`real-check` 当前固定检查：

- bridge `/state` 和 `/capability-handshake`
- `openclaw --dev health --json --timeout 5000`
- `openclaw --dev plugins inspect zentex-brain-bridge`
- 运行态快照文件是否存在
- `runtime_snapshot.data.handshake_status === "ok"`
- provider key 缺失时，把真实 agent smoke 标成 `skipped`

本次在本机启动 bridge 与 gateway 后的真实结果：

- `bridge.state_ok == true`
- `bridge.handshake_ok == true`
- `gateway_health.ok == true`
- `plugin_inspect.ok == true`
- `provider_smoke.status == "skipped"`
- `runtime_snapshot.exists == true`

当前解释：

- 这轮已经能证明 bridge、gateway、插件加载、bootstrap 落盘和 provider-free 工具转发主链是通的
- `real-check` 默认通过标准已经切到“注册 + 同步 + 工具转发”，不再把消息前置拦截当成阻塞项

## 当前阻塞的原子证据

- 原子问题 `G42.8.f.2`：
  - 证据：`provider_smoke.status == "skipped"`，原因是 provider key missing
  - 当前只能得出：完整 provider-backed 会话链路尚未被真实会话验证

### Zentex bridge API 自动化

```bash
pytest -q tests/test_openclaw_bridge_api.py
```

本次结果：

- `4 passed`

### 真实插件安装检查

```bash
HOME=/tmp/openclaw-home openclaw --dev plugins inspect zentex-brain-bridge
```

本次真实结果已经确认：

- `Status: loaded`
- `Source: ./integrations/openclaw-plugin/dist/index.js`
- 已注册：
  - `gateway_start`
  - `before_tool_call`
  - `zentex_think_task`
  - `zentex_delegate_task`
  - `zentex_state`
  - `zentex_inbox_state`
  - `zentex_update_inbox_item`

### 真实 gateway 健康检查

```bash
HOME=/tmp/openclaw-home openclaw --dev health --json --timeout 5000
```

本次真实结果已经确认：

- `ok: true`
- `defaultAgentId: "main"`

### 真实 Zentex bridge 连通检查

```bash
curl -H 'Authorization: Bearer bridge-token' \
  http://127.0.0.1:18989/api/host-adapters/openclaw/state

curl -H 'Authorization: Bearer bridge-token' \
  -H 'Content-Type: application/json' \
  -d '{"host_name":"openClaw","plugin_version":"0.1.0"}' \
  http://127.0.0.1:18989/api/host-adapters/openclaw/capability-handshake
```

本次真实结果已经确认：

- 两个接口都返回 `200`

### 真实 Web API 核验

```bash
curl http://127.0.0.1:18989/api/web/openclaw/state
curl http://127.0.0.1:18989/api/web/agents
curl http://127.0.0.1:18989/api/web/agents/openclaw-local/handshake
```

本次真实结果已经确认：

- `/api/web/openclaw/state` 返回 `200`，并带有：
  - `nine_question_summary`
  - `nine_question_alignment`
- `/api/web/agents` 已出现 `openclaw-local`
- `/api/web/agents/openclaw-local/handshake` 已可读

当前结论：

- Web 侧 openClaw 状态代理已经可用
- `openclaw-local` 的 Agent 管理可见性与 truthful handshake 已闭环
- 当前真实未覆盖项只剩 provider-backed 完整会话链

## 这次踩过的坑

### 坑 1：不要直接用系统 Python 起 Zentex

错误表现：

- `ModuleNotFoundError: No module named 'yaml'`

正确做法：

- 用仓库内 `.venv`
- `.venv/bin/pip install -e .`

### 坑 2：不要把插件入口继续留在 `.ts`

真实运行时不是单测环境：

- 单测里可以直接 mock `index.ts`
- 真实 OpenClaw 加载插件时，需要 JS 产物

正确做法：

- 先构建
- 插件 `package.json` 的 `openclaw.extensions` 指向 `./dist/index.js`

### 坑 3：不要并行执行多个 `openclaw config set`

错误表现：

- 两个配置写同一个 `openclaw.json`
- 后写入的值把前一次覆盖掉

正确做法：

- 串行执行每一条 `config set`
- 改完后直接 `cat /tmp/openclaw-home/.openclaw-dev/openclaw.json` 确认最终值

### 坑 4：不要假设 `--dev` 下所有命令都会自动跟着你自定义的端口走

这次联调里出现过：

- gateway 实际起在 `18789`
- 但 `openclaw --dev agent ...` 仍试图连 `19001`

正确做法：

- 如果要走 `openclaw --dev agent ...` 这条默认链路，直接把 gateway 起在 `19001`
- 如果一定要用自定义地址，就不要假设所有 CLI 子命令都会自动继承

### 坑 5：不要把 `openclaw --dev agent` 直接当成插件主链验收方法

这次真实结果显示：

- `agent` 路径先撞到模型 provider 鉴权
- 报错为：
  - `No API key found for provider "anthropic"`

这说明：

- 当前隔离 dev agent 没有可用模型鉴权
- 即使 gateway 本身健康，agent 主链仍可能先死在模型层
- 所以这条链路适合验证“gateway 能工作”，但不适合作为插件默认通过标准

### 坑 6：不要只靠控制台日志判断插件有没有真正握手

日志能看，但不稳定，也不适合脚本验收。

正确做法：

- 先看 `npm run openclaw-plugin:real-check` 的 JSON 输出
- 再看 `$HOME/.openclaw-dev/zentex-brain-bridge.runtime.json`
- 以 `handshake_status`、`registration_status`、`tool_review_count` 作为主证据

## 当前已做的插件修复

本轮已经补过：

- 插件入口从源码改为编译产物
- 新增 `integrations/openclaw-plugin/tsconfig.json`
- 新增插件本地 `build` 脚本
- Hook 对事件字段名做了更宽兼容：
  - `message/body/content/text/input`
  - `toolName/tool_name/name/tool`
  - `params/arguments/args/input`
  - `sessionKey/session_key/conversationId/conversation_id`
- Tool 调用失败时返回可读错误文本，而不是直接抛异常
- 增加了运行时日志：
  - handshake 成功/失败
  - `before_tool_call` allow/block/approval

## 下次继续联调时的正确顺序

```bash
cd <repo-root>

python3 -m venv .venv
.venv/bin/pip install -e .

npm --prefix integrations/openclaw-plugin run build
npm run openclaw-plugin:test
npm run openclaw-plugin:probe
pytest -q tests/test_openclaw_bridge_api.py

npm run openclaw-plugin:real-setup

ZENTEX_OPENCLAW_BRIDGE_TOKEN=bridge-token .venv/bin/animocerebro web start \
  --state-dir .animocerebro/state \
  --config animocerebro_vision.yaml \
  --host 127.0.0.1 \
  --port 18989

HOME=/tmp/openclaw-home openclaw --dev gateway run --port 19001 --force --allow-unconfigured --verbose

npm run openclaw-plugin:real-check
```

如果 `real-check` 中的 `provider_smoke.status` 为 `skipped`：

- 这是允许的
- 表示主闭环已按“无 provider 依赖”策略完成
- 后续只在有可用模型鉴权时再补真实 agent smoke

## 还需要补的真实验收

- 在具备可用模型鉴权的 dev agent 上，再做一次 provider-backed 完整会话联调
- 找到一个可控的真实工具调用场景，验证 `before_tool_call`
- 观察运行态快照和插件日志，确认：
  - `gateway_start` 期间确实有 handshake 成功
  - `agent-register / agent-heartbeat` 已持续刷新
  - `before_tool_call` 期间 `tool_review_count` 增长

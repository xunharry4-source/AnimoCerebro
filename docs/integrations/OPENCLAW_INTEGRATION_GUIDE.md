# OpenClaw Integration Guide / OpenClaw 集成手册

## 1. What This Guide Covers / 本文档说明什么

**English**

This is the practical step-by-step guide for integrating OpenClaw with AnimoCerebro.

It focuses on:

- what runs on the AnimoCerebro side
- what runs on the OpenClaw side
- how to configure the bridge token
- how to use remote hosts or non-default ports
- how to verify that registration and delegation actually work

**中文**

这是一份把 OpenClaw 接入 AnimoCerebro 的实操手册。

它重点说明：

- AnimoCerebro 侧要启动什么
- OpenClaw 侧要配置什么
- bridge token 怎么设置
- 远程部署和非默认端口怎么配
- 如何验证注册和委托链已经真的可用

## 2. Integration Boundary / 接入边界

**English**

The bridge is not a takeover layer.

- OpenClaw keeps execution ownership.
- AnimoCerebro acts as the external brain.
- The plugin registers the host, syncs capabilities and runtime state, receives delegated work, and writes back receipts, escalations, and experience.

**中文**

这个桥接层不是接管层。

- OpenClaw 保留执行权。
- AnimoCerebro 充当外部大脑。
- 插件负责注册宿主、同步能力和运行态、接收委托任务，并回写回执、升级和经验。

## 3. What You Need / 需要准备什么

**English**

- one running AnimoCerebro instance
- one running OpenClaw gateway
- the local OpenClaw plugin source from this repository
- one shared bridge token that both sides use

**中文**

- 一个正在运行的 AnimoCerebro
- 一个正在运行的 OpenClaw gateway
- 本仓库里的 OpenClaw 插件源码
- 一个双方共用的 bridge token

## 4. Step 1: Start AnimoCerebro / 第一步：启动 AnimoCerebro

**English**

Set a bridge token first. You choose it yourself and use the same value on both sides.

The current web UI can display and copy the token after it is already configured in the local AnimoCerebro process, but it does not generate a new token for you.

Example:

```bash
export ZENTEX_OPENCLAW_BRIDGE_TOKEN="$(openssl rand -hex 32)"
animocerebro web start --state-dir .animocerebro/state --config animocerebro_vision.yaml --host 127.0.0.1 --port 8899
```

If you do not want to use `openssl`, you can also choose your own long random string manually.

**中文**

先设置 bridge token。这个 token 需要你自己准备，并且两边使用同一个值。

当前 Web 管理页在 token 已经配置到本地 AnimoCerebro 进程后，可以显示并复制它，但不会替你生成新的 token。

例如：

```bash
export ZENTEX_OPENCLAW_BRIDGE_TOKEN="$(openssl rand -hex 32)"
animocerebro web start --state-dir .animocerebro/state --config animocerebro_vision.yaml --host 127.0.0.1 --port 8899
```

如果不想用 `openssl`，也可以自己手动准备一个足够长的随机字符串。

If OpenClaw reaches AnimoCerebro through Docker bridge, a reverse proxy, or any non-loopback address on the same machine, also set:

```bash
export ZENTEX_OPENCLAW_BRIDGE_ALLOW_NON_LOOPBACK=true
animocerebro web start --state-dir .animocerebro/state --config animocerebro_vision.yaml --host 0.0.0.0 --port 8899
```

This is required because "same machine" is not always a loopback source address at the socket layer.

如果 OpenClaw 是通过 Docker bridge、反向代理或同机非 loopback 地址访问 AnimoCerebro，还需要额外设置：

```bash
export ZENTEX_OPENCLAW_BRIDGE_ALLOW_NON_LOOPBACK=true
animocerebro web start --state-dir .animocerebro/state --config animocerebro_vision.yaml --host 0.0.0.0 --port 8899
```

原因是“同一台机器”在 socket 层并不一定表现成 loopback 来源地址。

## 5. Step 2: Build And Install The Plugin / 第二步：构建并安装插件

```bash
npm --prefix integrations/openclaw-plugin run build
openclaw plugins install ./integrations/openclaw-plugin
```

For an isolated local dev home:

```bash
npm run openclaw-plugin:real-setup
```

隔离本地 dev home 可直接用：

```bash
npm run openclaw-plugin:real-setup
```

## 6. Step 3: Configure OpenClaw / 第三步：配置 OpenClaw

Minimal example:

```json
{
  "plugins": {
    "entries": {
      "zentex-brain-bridge": {
        "enabled": true,
        "config": {
          "enabled": true,
          "zentexBaseUrl": "http://127.0.0.1:8899",
          "zentexAuthToken": "replace-with-the-same-bridge-token",
          "openclawEndpoint": "http://127.0.0.1:19001",
          "autoHandshake": true,
          "enableToolReview": false
        }
      }
    }
  }
}
```

Field meanings:

- `zentexBaseUrl`: where AnimoCerebro lives
- `zentexAuthToken`: the same shared bridge token
- `openclawEndpoint`: the reachable gateway address that AnimoCerebro should record for this host
- `autoHandshake`: lets the plugin bootstrap registration on startup

字段含义：

- `zentexBaseUrl`: AnimoCerebro 在哪里
- `zentexAuthToken`: 双方共用的 bridge token
- `openclawEndpoint`: AnimoCerebro 应该记录的 OpenClaw gateway 可达地址
- `autoHandshake`: 插件启动时自动完成注册链

## 7. Remote Host Or Custom Port / 远程宿主或自定义端口

**English**

If AnimoCerebro is not on localhost:

```json
{
  "zentexBaseUrl": "http://your-brain-host:8899"
}
```

And AnimoCerebro must allow non-loopback bridge access:

```bash
export ZENTEX_OPENCLAW_BRIDGE_ALLOW_NON_LOOPBACK=true
```

If OpenClaw does not use the default local gateway port:

```json
{
  "openclawEndpoint": "http://your-openclaw-host:29001"
}
```

**中文**

如果 AnimoCerebro 不在 localhost：

```json
{
  "zentexBaseUrl": "http://your-brain-host:8899"
}
```

并且 AnimoCerebro 必须允许非 loopback 的 bridge 访问：

```bash
export ZENTEX_OPENCLAW_BRIDGE_ALLOW_NON_LOOPBACK=true
```

如果 OpenClaw 不是默认本地 gateway 端口：

```json
{
  "openclawEndpoint": "http://your-openclaw-host:29001"
}
```

## 8. Step 4: Verify Registration / 第四步：验证注册

**English**

The smallest successful chain is:

1. runtime snapshot exists
2. bridge trace exists
3. `openclaw-local` appears in `/api/web/agents`
4. handshake is readable
5. `POST /tools/invoke -> zentex_state` succeeds

Useful checks:

```bash
curl -sS http://127.0.0.1:18989/api/web/openclaw/state
curl -sS http://127.0.0.1:18989/api/web/agents
curl -sS http://127.0.0.1:18989/api/web/agents/openclaw-local/handshake
npm run openclaw-plugin:real-check
```

**中文**

最小成功链是：

1. runtime snapshot 已生成
2. bridge trace 已生成
3. `/api/web/agents` 里出现 `openclaw-local`
4. handshake 可读
5. `POST /tools/invoke -> zentex_state` 成功

常用检查命令：

```bash
curl -sS http://127.0.0.1:18989/api/web/openclaw/state
curl -sS http://127.0.0.1:18989/api/web/agents
curl -sS http://127.0.0.1:18989/api/web/agents/openclaw-local/handshake
npm run openclaw-plugin:real-check
```

## 9. Step 5: Verify Delegation / 第五步：验证委托链

**English**

After registration works, verify the real main chain:

1. AnimoCerebro creates a delegated command for `openclaw-local`
2. OpenClaw pulls it into its inbox
3. OpenClaw executes or updates it
4. AnimoCerebro receives the receipt or escalation

This is the core value path. It does not require OpenClaw to surrender its own execution architecture.

**中文**

注册成功后，再验证真实主链：

1. AnimoCerebro 给 `openclaw-local` 下发委托命令
2. OpenClaw 拉到本地 inbox
3. OpenClaw 自己执行或更新任务
4. AnimoCerebro 收到回执或升级

这才是核心价值链，而且不要求 OpenClaw 交出自己的执行架构。

## 10. Common Questions / 常见问题

### Q1. Does this require an LLM key? / 这需要 LLM key 吗？

**English**

The main bridge chain does not. Registration, capability sync, heartbeat, inbox, receipts, escalations, and provider-free tool checks do not require an LLM provider key.

**中文**

主桥接链不需要。注册、能力同步、心跳、inbox、回执、升级，以及 provider-free 的工具验证都不需要 LLM provider key。

### Q2. Can the current web UI generate the bridge token? / 当前 Web 界面能生成 bridge token 吗？

**English**

It does not generate a new token for you.

It can now display and copy the currently configured bridge token from the local AnimoCerebro process.

You still need to set the token yourself first and use the same value on both sides.

**中文**

它不会替你生成新的 token。

它现在可以显示并复制当前本地 AnimoCerebro 进程已经配置好的 bridge token。

你仍然需要先自己设置 token，并在两边写成同一个值。

### Q3. Does the plugin take over OpenClaw message handling? / 插件会接管 OpenClaw 消息吗？

**English**

No. The main design is registration, sync, delegation, and writeback. It is not a forced takeover layer.

**中文**

不会。主设计是注册、同步、委托和回写，不是强制接管层。

## 11. Related Docs / 相关文档

- [当前对接协议.md](../../当前对接协议.md)
- [OPENCLAW_HOST_ADAPTER_PROTOCOL.md](OPENCLAW_HOST_ADAPTER_PROTOCOL.md)
- [OPENCLAW_HOST_ADAPTER_ARCHITECTURE.md](OPENCLAW_HOST_ADAPTER_ARCHITECTURE.md)
- [OPENCLAW_PLUGIN_REAL_TEST.md](../operability/OPENCLAW_PLUGIN_REAL_TEST.md)
- [README.md](../../integrations/openclaw-plugin/README.md)

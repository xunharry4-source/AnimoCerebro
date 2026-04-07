# OpenClaw Host Adapter Protocol / OpenClaw 宿主适配协议

## Overview / 概览

**English**

This document describes the public bridge protocol between OpenClaw and AnimoCerebro.

OpenClaw is treated as:

- a host
- an executor
- a strong external agent

AnimoCerebro is treated as:

- an external brain
- a reasoning and delegation layer

The adapter is only a bridge. It is not a takeover layer.

**中文**

本文件描述 OpenClaw 与 AnimoCerebro 之间的公开桥接协议。

OpenClaw 被视为：

- 宿主
- 执行者
- 强执行的外部 Agent

AnimoCerebro 被视为：

- 外部大脑
- 判断与委托层

适配器只是桥，不是接管层。

## Public Boundaries / 公开边界

**English**

The adapter must preserve these rules:

- do not modify OpenClaw source code
- do not replace OpenClaw UI
- do not merge host identity into the brain
- do not silently take over host execution

**中文**

适配器必须保持以下边界：

- 不修改 OpenClaw 源码
- 不替换 OpenClaw UI
- 不把宿主主体身份并入大脑
- 不静默接管宿主执行权

## Public Interface Shape / 公开接口形态

**English**

Current OpenClaw host adapter endpoints:

- `POST /api/host-adapters/openclaw/capability-handshake`
- `POST /api/host-adapters/openclaw/agent-register`
- `POST /api/host-adapters/openclaw/agent-heartbeat`
- `GET /api/host-adapters/openclaw/inbox`
- `POST /api/host-adapters/openclaw/receipts`
- `POST /api/host-adapters/openclaw/escalations`
- `GET /api/host-adapters/openclaw/state`

**中文**

当前 OpenClaw 宿主适配接口：

- `POST /api/host-adapters/openclaw/capability-handshake`
- `POST /api/host-adapters/openclaw/agent-register`
- `POST /api/host-adapters/openclaw/agent-heartbeat`
- `GET /api/host-adapters/openclaw/inbox`
- `POST /api/host-adapters/openclaw/receipts`
- `POST /api/host-adapters/openclaw/escalations`
- `GET /api/host-adapters/openclaw/state`

The default examples use localhost, but the adapter is not limited to localhost.

默认示例使用 localhost，但适配器并不要求必须部署在 localhost。

If AnimoCerebro is remote, configure the plugin `zentexBaseUrl` to point to the remote brain URL.

如果 AnimoCerebro 不在本地，请把插件里的 `zentexBaseUrl` 改成远程大脑地址。

If the OpenClaw gateway host or port changes, configure `openclawEndpoint` so registration, heartbeat, and host descriptor metadata reflect the correct reachable gateway address.

如果 OpenClaw gateway 的主机或端口变了，请配置 `openclawEndpoint`，这样注册、心跳和宿主描述信息会使用正确的可达地址。

## Public Semantics / 公开语义

**English**

The host adapter supports these cross-system behaviors:

- host registration
- runtime and capability sync
- delegated command delivery
- receipt writeback
- escalation writeback
- state visibility

**中文**

宿主适配器支持以下跨系统行为：

- 宿主注册
- 运行态与能力同步
- 委托命令下发
- 回执回写
- 升级回写
- 状态可见性

## Delegation Boundary / 委托边界

**English**

The adapter should preserve explicit delegation semantics:

- the host keeps execution ownership
- the brain can suggest or delegate
- the adapter must not silently seize the task loop

**中文**

适配器应保留显式委托边界：

- 宿主保留执行权
- 大脑可以给建议或下发委托
- 适配器不能静默夺取任务主循环

## Recommended Integration Model / 推荐接入模型

**English**

Third-party host integrators should follow this shape:

1. register the host
2. sync host capabilities and runtime state
3. accept delegated commands
4. write back receipts
5. write back escalations when needed

**中文**

第三方宿主接入方建议按以下形态实现：

1. 注册宿主
2. 同步宿主能力与运行状态
3. 接收委托命令
4. 回写回执
5. 必要时回写升级

## Relationship To The Global Protocol / 与总协议的关系

**English**

This is an adapter-specific wire protocol.

It is not the full AnimoCerebro protocol. The global protocol is documented in:

- [当前对接协议.md](../../当前对接协议.md)

**中文**

这是适配器专属的 wire protocol。

它不是完整的 AnimoCerebro 总协议。总协议见：

- [当前对接协议.md](../../当前对接协议.md)

# OpenClaw Host Adapter Architecture / OpenClaw 宿主适配架构

## One-Sentence Definition / 一句话定义

**English**

The OpenClaw plugin is a host adapter implemented as a native OpenClaw plugin that bridges the OpenClaw host to the external AnimoCerebro brain.

**中文**

OpenClaw 插件是一个以原生插件形态实现的宿主适配器，用来把 OpenClaw 宿主桥接到外部 AnimoCerebro 大脑。

## Stable Roles / 稳定角色

### AnimoCerebro

**English**

Acts as:

- external brain
- reasoning core
- delegation and judgment layer

**中文**

角色：

- 外部大脑
- 推理核心
- 委托与判断层

### OpenClaw

**English**

Acts as:

- host
- executor
- conversation and tool runtime owner

**中文**

角色：

- 宿主
- 执行者
- 会话与工具运行时拥有者

### Plugin / 插件

**English**

Acts as:

- thin bridge layer

Responsible for:

- protocol translation
- runtime state sync
- host registration and heartbeat
- inbox polling
- receipt and escalation writeback
- runtime evidence persistence

**中文**

角色：

- 薄桥接层

负责：

- 协议翻译
- 运行态同步
- 宿主注册与心跳
- inbox 拉取
- 回执与升级回写
- 运行证据落盘

## Core Concepts / 核心概念

**English**

Public concepts in this adapter:

- `Host Adapter`
- `External Brain`
- `Bridge Protocol`
- `Host Agent`
- `Runtime Evidence`
- `Inbox / Receipt / Escalation`

**中文**

该适配器中的公开概念：

- `Host Adapter`
- `External Brain`
- `Bridge Protocol`
- `Host Agent`
- `Runtime Evidence`
- `Inbox / Receipt / Escalation`

## Layered Architecture / 分层架构

**English**

The adapter can be understood as six layers:

1. host integration layer
2. external brain bridge layer
3. protocol facade layer
4. semantic reuse layer
5. coordination runtime layer
6. observability layer

**中文**

适配器可以理解为六层：

1. 宿主集成层
2. 外部大脑桥接层
3. 协议门面层
4. 语义复用层
5. 协同运行层
6. 可观测层

## Public Guarantees / 公开保证

**English**

The adapter should guarantee:

- host execution ownership remains with OpenClaw
- reasoning ownership remains with AnimoCerebro
- runtime state remains observable
- task result loops remain auditable

**中文**

适配器应保证：

- 宿主执行权仍归 OpenClaw
- 判断与推理权仍归 AnimoCerebro
- 运行态保持可观测
- 任务结果闭环保持可审计

## Not Part Of This Adapter / 不属于该适配器的内容

**English**

The public adapter does not claim to provide:

- host UI replacement
- subject synchronization
- hidden automatic task takeover
- a second execution runtime inside the plugin

**中文**

公开适配器不提供：

- 宿主 UI 替换
- 主体同步
- 隐藏的自动任务接管
- 插件内部的第二执行运行时

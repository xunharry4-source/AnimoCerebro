# 功能模块说明

本文档用于说明 `src` 目录下新增功能模块的职责划分与 Zentex 的整体技术架构，便于后续开发、协作与部署时统一边界。

按功能组织的插件开发规范索引见：
- [PLUGIN_GUIDES.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/PLUGIN_GUIDES.md)

## 开发一键命令（最常用）

本仓库提供前后端联动的“一键启动 / 一键重启”入口，确保 Web 页面绑定真实后端服务（非 mock）。

- 一键启动：`make dev`（等价 `./scripts/dev_all.sh`，默认使用 `websockets-sansio`）
- 一键重启：`make restart-dev`（等价 `./scripts/restart_dev.sh`，会先清理端口占用再拉起）

更完整的启动、端口覆盖与测试说明见：
- [STARTUP_AND_TEST.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/STARTUP_AND_TEST.md)

## 目录清单

### `src/plugins`

工具能力目录，用于承载第三方模型与外部能力的调用方法封装。

适用范围：
- 第三方模型调用封装
- 外部平台 HTTP 调用方法
- 统一请求体与响应体标准化
- 提供可被运行时直接接入的工具方法

建议内容：
- 工具调用入口
- Provider 配置模型
- 请求体与响应体封装
- 外部调用方法说明

当前关键文件：
- `src/plugins/provider_tools.py`
  负责 OpenAI、ChatGPT、Gemini、Claude 的调用方法封装。

插件开发规范：
- 优先查看按功能组织的总索引 `docs/operability/PLUGIN_GUIDES.md`
- 再进入对应插件目录查看家族级 `DEVELOPMENT_GUIDE.md`
- `src/plugins/model_providers/DEVELOPMENT_GUIDE.md`
- `src/plugins/cognitive/DEVELOPMENT_GUIDE.md`
- `src/plugins/execution/DEVELOPMENT_GUIDE.md`
- `src/plugins/sensory/DEVELOPMENT_GUIDE.md`
- `src/plugins/simulation/DEVELOPMENT_GUIDE.md`
- `src/plugins/weights/DEVELOPMENT_GUIDE.md`

### `src/admin-portal`

后台管理页面目录，用于承载系统通用管理端前端页面。

适用范围：
- 用户管理
- 角色与权限管理
- 系统配置
- 仪表盘与运营管理页面

建议内容：
- 页面路由
- 通用布局
- 管理端组件
- 管理端接口调用封装

### `src/cloud-audit-web`

云审计 Web 页面目录，用于承载面向业务用户的云审计前端能力。

适用范围：
- 审计日志查询
- 风险事件展示
- 审计报表查看
- 资源审计结果筛选与分析

建议内容：
- 审计查询页面
- 审计详情页面
- 报表与统计视图
- 面向审计业务的前端组件

### `src/cloud-audit-admin`

云审计后台管理功能目录，用于承载云审计相关的后台管理与配置能力。

适用范围：
- 审计规则配置
- 审计任务管理
- 数据源接入管理
- 风险策略与告警配置

建议内容：
- 审计规则管理模块
- 任务调度与执行管理
- 审计数据源管理
- 告警与通知配置

### `src/zentex`

`zentex` 为核心能力域，当前按以下模块拆分：

#### `src/zentex/cognition`

核心认知中枢模块。

适用范围：
- 任务理解与拆解
- 决策编排
- 推理流程组织
- 核心状态协调

#### `src/zentex/memory`

记忆与自我演化模块。

适用范围：
- 会话记忆管理
- 长短期知识存储
- 经验沉淀
- 策略优化与演进

#### `src/zentex/bridge`

宿主桥接与感知执行模块。

适用范围：
- 外部系统桥接
- 输入感知接入
- 工具调用执行
- 环境交互适配

#### `src/zentex/safety`

安全风控与人类监督模块。

适用范围：
- 风险识别
- 权限控制
- 审批与人工介入
- 安全策略校验

#### `src/zentex/network`

组织协作网络模块。

适用范围：
- 多角色协作
- 任务分发
- 协同通信
- 组织关系建模

#### `src/zentex/cluster`

弹性运行时底座模块，目录名采用 `cluster`。

适用范围：
- 集群调度
- 弹性扩缩容
- 运行时资源管理
- 高可用与故障恢复

当前运行时核心骨架代码主要位于 `src/zentex/runtime`。

补充说明文档：
- `docs/operability/RUNTIME_AND_TESTS.md`

#### `src/zentex/协议`

协议模块。

适用范围：
- 对外协议定义
- 跨模块通信约定
- 接口契约与消息模型
- 协议版本兼容管理

#### `src/zentex/common`

common 模块。

适用范围：
- 通用规则依据沉淀
- 跨模块共享基础定义
- 公共判定依据与约束模型
- 可复用基础能力抽象

当前关键文件：
- `src/zentex/common/plugin_registry.py`
  通用生命周期注册表，负责插件注册、晋升、撤销、健康过滤与审计拦截。
- `src/zentex/common/__init__.py`
  common 包入口。

#### `src/zentex/core`

core 模块。

适用范围：
- 统一运行态模型
- 统一插件基类与运行时契约
- 跨运行时共享的底层核心模型

当前关键文件：
- `src/zentex/core/models.py`
  定义 `BrainRuntimeState` 统一运行态快照模型。
- `src/zentex/core/plugin_base.py`
  定义 `BasePluginSpec` 与插件生命周期基础约束。
- `src/zentex/core/plugin_runtime.py`
  定义插件健康探针、回退决策、撤销记录与加载结果等运行态契约。
- `src/zentex/core/cognitive_tools_spec.py`
  认知工具契约层，定义合法认知工具必须满足的静态边界与调度条件。

#### `src/zentex/runtime`

runtime 模块。

适用范围：
- 事件流存储
- 会话连续性
- 单轮认知循环
- 工作记忆、自我模型、时间感、元认知与认知工具编排

当前关键文件：
- `src/zentex/runtime/transcript.py`
  认知事件流存储器。
- `src/zentex/runtime/session.py`
  会话容器与状态恢复。
- `src/zentex/runtime/think_loop.py`
  单轮认知循环执行器。
- `src/zentex/runtime/runtime.py`
  运行时大管家。
- `src/zentex/runtime/cognitive_tools/__init__.py`
  认知工具执行层，负责注册、筛选、编排、调用记录与结果合并。
- `src/zentex/runtime/metacognition.py`
  元认知调度器。
- `src/zentex/runtime/working_memory.py`
  工作记忆与注意力控制器。
- `src/zentex/runtime/self_model.py`
  活的自我模型引擎。
- `src/zentex/runtime/temporal.py`
  内部时间感引擎。

补充说明：
- `src/zentex/core/cognitive_tools_spec.py` 与 `src/zentex/runtime/cognitive_tools/__init__.py` 不是重复文件。
- 前者是契约层，回答“什么是合法的认知工具”。
- 后者是执行层，回答“运行时如何使用认知工具”。

#### `src/zentex/environment`

环境感知与用户偏好辨析模块。

适用范围：
- 物理宿主状态采样与环境态势解释
- 外部信号清洗与多源比较
- **G19: 用户偏好辨析与意图对齐**（v2.0 技术栈升级版）
  - PydanticAI LLM 驱动的智能判定引擎
  - pydantic-settings 统一配置管理
  - SQLite + SQLAlchemy ORM 数据持久化
  - 极端信号拦截与攻击样本标记

当前关键文件：
- `src/zentex/environment/service.py`
  环境感知服务门面，提供统一 API。
- `src/zentex/environment/g19_settings.py` (v2.0 新增)
  G19 配置管理，支持环境变量和 .env 文件。
- `src/zentex/environment/g19_judgment_engine.py` (v2.0 新增)
  PydanticAI 混合判定引擎（LLM + 规则降级）。
- `src/zentex/environment/preference_models.py`
  偏好辨析数据模型定义。
- `src/zentex/environment/preference_storage.py`
  数据存储层（v2.0 升级为 SQLAlchemy）。

补充说明文档：
- `src/zentex/environment/G19_README.md`
- `src/zentex/environment/G19_IMPLEMENTATION_SUMMARY.md`
- `docs/G19_PREFERENCE_MODULE_SPEC.md`
- `docs/G19_UPGRADE_IMPLEMENTATION_PLAN.md` (v2.0 实施计划)

### `src/admin-portal` 文件说明

当前关键文件：
- `src/admin-portal/package.json`
  前端依赖与脚本声明。
- `src/admin-portal/vite.config.ts`
  Vite 与 Vitest 配置。
- `src/admin-portal/src/App.tsx`
  前端应用根组件。
- `src/admin-portal/src/main.tsx`
  前端入口。
- `src/admin-portal/src/pages/dashboard/RealtimeDashboard.tsx`
  专业模式实时指挥台页面。
- `src/admin-portal/src/pages/dashboard/RealtimeDashboard.test.tsx`
  实时指挥台测试。
- `src/admin-portal/src/test/setup.ts`
  前端测试环境初始化。

## 技术架构

Zentex 定位为“独立思考、自主行动与持续进化的外部大脑”系统。它不是传统的请求响应式业务系统，而是偏向类人认知的分布式脑机架构。

当前技术架构可以从以下 6 个核心维度理解。

### 技术选型原则

Zentex 明确规定，核心认知层必须坚持自研，包括主脑语义、自主控制环、九问、安全闸门、记忆治理等关键能力。

因此，系统不会默认引入整套外部 Agent 编排框架来接管主脑语义，LangGraph 及类似大型 Agent 编排框架都不作为主脑核心依赖。

整体选型原则为：
- 通用承载层优先使用成熟第三方框架。
- 主脑语义、自主控制与认知核心坚持自研。
- 不因引入复杂基础设施而破坏单机默认极简可用原则。

### 1. 系统部署与物理架构

Zentex 支持“单实例生产化”与“单脑集群化”两种部署模式，工程底座分为以下层次：

- `Gateway/API` 层：基于 FastAPI 与 Uvicorn，承接用户、宿主 Agent 和管理端的 HTTP 或 WebSocket 请求。该层默认无状态，负责鉴权、限流、快照读取与任务提交。
- `Brain Coordinator` 层：针对每一个 `brain_scope`，集群内仅允许一个 Leader 节点推进状态。负责主脑状态迁移、深思考调度与快照发布。
- `Worker` 层：通过后台任务队列，如 Dramatiq 或本地执行器，异步执行脑循环、记忆整理、安全复核等慢任务。
- `Shared State` 层：通过 SQLAlchemy 2 统一访问底座。单实例默认使用 SQLite WAL，集群模式使用 PostgreSQL，用于存储快照、事件与任务状态。
- `Cache/Lease` 层：引入 Redis，负责热点快照、限流令牌、Leader 租约与幂等键管理，避免双主脑冲突。
- `Memory/Audit` 层：负责正式记忆写入、隔离、污染追踪与云端审计结果落库。

#### 单机与集群的统一语义

Zentex 或 AnimoCerebro 在底层工程架构上明确支持单机与集群两种部署形态。

- 单实例生产化，简称单机模式。
- 单脑集群化，简称集群模式。

两种模式共享完全一致的大脑逻辑语义，包括九问、自主控制环、安全闸门、记忆治理与审计链。二者差异主要体现在执行方式、调度方式与存储底座，用于适配不同量级的承压需求。

#### 单机模式

单机模式是系统默认基础形态，重点是开箱即用、依赖极简，不因集群能力的存在而牺牲本地轻量化体验。

定位与适用场景：
- 面向个人开发者。
- 面向本地开发与调试。
- 面向私有小规模部署。
- 运行在单个进程或单机多进程环境中。

技术底座：
- API 与 Web 承载使用 FastAPI 与 Uvicorn。
- 状态与记忆存储默认使用本地 SQLite，采用 WAL 模式作为正式主库。
- 后台任务与队列采用本地后台执行器处理脑循环与慢任务剥离，不依赖独立消息队列服务。
- 文件与工作区监听使用 `watchdog` 提供本地增量索引能力，避免高频全量扫描。

运行特征：
- 部署极简，默认不要求 PostgreSQL、Redis、Prometheus 或 Docker Compose 等重型基础设施。
- 在单机内仍完整保留类人认知分层，快反应路径与深思考路径分离，避免热路径阻塞。

#### 集群模式

集群模式面向高并发接入、洪峰承载、高可用与租户隔离场景，让多个实例共同承载同一个逻辑脑。

定位与适用场景：
- 面向多实例接入。
- 面向高并发流量。
- 面向多租户生产场景。
- 面向需要横向扩展的生产部署。

技术底座：
- API 与 Web 承载仍使用 FastAPI 与 Uvicorn，但此时主要作为无状态 Gateway。
- 共享数据库使用 PostgreSQL，统一存储共享状态、快照、事件与任务版本。
- 缓存与分布式协调使用 Redis，负责热点快照缓存、Leader 租约、限流令牌与幂等键。
- 后台任务与队列引入 Redis-backed 队列与独立 Worker 进程，目标态为 Dramatiq 执行框架。

集群节点角色划分：
- Gateway 节点负责承接请求、读取缓存快照与提交任务，不直接执行完整脑循环。
- Leader 或 Coordinator 节点针对任意 `brain_scope` 同时只允许一个 Leader 持有租约，负责推进核心脑状态、深思考调度与快照发布，避免脑裂。
- Worker 节点保持无状态并支持水平扩展，专门在后台异步执行高耗能任务，如重规划、记忆整理与安全复核。

一致性与防冲突机制：
- 通过 `snapshot_version`、`idempotency_key` 与乐观并发控制防止陈旧数据覆盖状态。
- Leader 写操作必须携带 `fencing_token`，用于避免网络分区或时钟偏移导致的重复执行与状态竞争。

与目录映射：
- `src/zentex/cluster` 承载集群、调度、运行时资源与高可用相关能力。
- `src/zentex/memory` 承载记忆持久化、审计数据关联与记忆生命周期能力。

### 2. 类人认知分层架构

为避免高并发和复杂任务导致上下文失控，Zentex 的思考路径采用快慢双通道设计：

- 反射层：极速、低成本、可缓存。负责拦截恶意注入、读取快照、执行简单风险判断与浅层路由，不触发完整脑循环。
- 工作记忆层：仅保留当前目标、阻塞原因、最近证据等最小上下文，为当前操作提供信息板。
- 深思考层：彻底剥离到后台 Worker 异步运行，负责角色重推断、目标重规划、复杂协作判定与经验提炼等高成本计算。
- 长期记忆层：采用热、温、冷三区分层。主脑决策前通过混合检索召回强相关记忆，而非装载全部历史。

与目录映射：
- `src/zentex/cognition` 承载反射、工作记忆协同、深思考编排与认知决策能力。
- `src/zentex/memory` 承载长期记忆分层、索引、归档与召回能力。

### 3. 核心运行时架构

底层核心代码不再围绕单体 `brain.py` 循环组织，而是重构为以下核心运行时容器：

- `BrainRuntime`：进程级容器，负责全局依赖、共享状态、工具注册表与底层认知器官初始化。
- `BrainSession`：连续会话容器，管理多轮思考，持有当前工作区、活跃目标与多种快照，并支持回放与恢复。
- `ThinkLoop`：单轮认知循环，包含感知环境、构建上下文、刷新记忆、检测认知风险、模拟预演、元认知调度、编排工具、合成决策、巩固反思 9 个阶段。
- `CognitiveToolOrchestrator`：认知工具编排层，根据元认知调度结果决定串行或并行调用哪些认知工具，并合并结果。
- `BrainTranscriptStore`：事件流存储，以事件溯源方式记录每轮认知事件，作为恢复与审计的真相源。

与目录映射：
- `src/zentex/cognition` 适合放置 `ThinkLoop`、元认知调度器与决策合成逻辑。
- `src/zentex/cluster` 适合放置 `BrainRuntime`、会话恢复、共享状态接入与运行时底座代码。
- `src/zentex/memory` 适合放置 `BrainTranscriptStore` 与记忆关联存储能力。

### 4. 宿主与外部系统桥接架构

Zentex 定位为外部大脑或顾问层，不直接接管外部系统控制权或业务流。宿主接入采用 6 层桥接架构：

- 宿主智能适配层
- 外部大脑桥接层
- 协议门面层，采用 Thin JSON APIs
- 主体语义复用层
- 运行协同层
- 可观测与核验层

在该模式下，宿主通过轻量 API，如 `/think-task`、`/think-action`、`/delegate-task` 向大脑请求判断。大脑返回 `allow`、`pause`、`needs_confirmation`、`change_approach` 等建议或任务拆解，最终动作仍由宿主决定。

与目录映射：
- `src/zentex/bridge` 承载宿主适配、协议门面、语义桥接与运行协同能力。
- `src/plugins` 可承载不同宿主或第三方系统的可插拔桥接扩展。

### 5. 安全风控与治理架构

Zentex 内部拥有独立的防御与审计体系，确保智能增长始终受控：

- 云端理性审计服务：将高风险动作的最终裁决从本地大脑剥离，交由独立云端 HTTP 服务执行双重签名鉴权与策略审计。该服务具备独立持久化、健康检查与管理界面。
- 记忆九重校验栅栏：任何日志、事件或补丁在晋升为长期策略或正式记忆前，必须在隔离区经过 9 个维度的强制安全审查与冲突校验，避免逻辑投毒与身份污染。

与目录映射：
- `src/zentex/safety` 承载风险识别、权限校验、审计联动、人工监督与记忆晋升前安全检查。
- `src/cloud-audit-web` 与 `src/cloud-audit-admin` 承载云审计服务对应的前台展示与后台管理能力。

### 6. 多智能体与群体协作网络

除单脑运行外，Zentex 还包含跨网络、跨实例的多脑社会化协议层：

- 网络通信与发现层：支持实例发现、网络状态上报与心跳保活。
- 跨脑协商与共识协议：支持任务广播、多智能体竞标、失败重派。在高风险决策场景下，可发起基于 Quorum 的多脑共识投票。
- 受控进化与经验交换：多个 Zentex 可在组织边界内共享加密经验包和策略补丁。接收方需经过来源签名校验、可信度评估与污染隔离审查后才会接纳；一旦发现污染，可触发级联撤销与回滚。

与目录映射：
- `src/zentex/network` 承载网络发现、协商协议、共识通信与经验交换能力。
- `src/zentex/safety` 参与跨脑经验接纳前的可信审查与污染隔离。

## 底层技术框架

### 1. 后端与 API 服务层

- `FastAPI + Uvicorn`：作为单实例与集群模式的统一入口，负责承接 HTTP API、管理接口、健康检查与 WebSocket 流式事件推送。
- `Pydantic v2`：用于请求与响应 Schema、DTO 强约束，确保认知输入输出一致。

### 2. 数据存储与持久化层

- `SQLAlchemy 2`：作为统一 ORM 层，负责共享状态、快照、审计与记忆元数据访问。
- `Alembic`：用于数据库 Schema 迁移、版本升级与回滚。
- `SQLite (WAL)`：作为单实例极简部署模式下的默认本地正式状态主库。
- `PostgreSQL`：作为集群部署模式下共享状态、事件与任务版本控制的统一主库。

### 3. 队列、缓存与异步任务

- `Dramatiq`：作为后台任务队列的目标态框架，用于把深思考、记忆整理、安全复核等慢任务从主线程剥离。
- `Redis`：作为集群部署核心辅助层，用于热点快照缓存、Leader Lease、限流令牌与幂等键管理。

### 4. Web 前端控制台

- `React + TypeScript + Vite + MUI`：作为标准前端工程技术栈，用于构建 GUI 控制台。
- 明确禁止继续使用 Python 后端直接拼接 HTML 作为前端成品方案。

### 5. 监控、链路追踪与压测

- `prometheus-client`：用于暴露热路径、脑循环、队列与存储运行指标。
- `OpenTelemetry`：用于 API、队列、数据库、协调节点与工作节点之间的分布式链路追踪。
- `Locust`：作为统一压测框架，用于单实例与集群模式下的高并发压测与故障演练。
- `pytest`：用于单元测试、集成测试与核心测试矩阵质量保障。

### 6. 底层依赖与基础设施

- `watchdog`：用于监听工作区文件系统增量变更，触发增量索引，替代高频全量扫描。
- `Docker / Docker Compose`：用于构建与编排集群模式下的外部环境脚手架，如 PostgreSQL、Redis 与 Prometheus。

### 7. 语义向量引擎

- `LanceDB`：作为语义记忆锚点引擎，符合单机极简可用原则。其部署方式接近嵌入式数据库，无需独立服务，同时支持向量检索。
- 用途：存储 `BrainTranscript` 的向量索引，在九问、记忆治理与历史经验召回场景中，快速找回相似的痛觉经验与证据。

### 8. 结构化输出约束

- `Instructor`：作为轻量级 Pydantic 适配器，用于约束大模型输出，不接管 Agent 逻辑，也不替代主脑语义。
- 用途：在身份重推断、九重校验栅栏与其他高风险认知环节中，确保返回数据严格符合 `Pydantic v2` 模型，避免因 LLM 输出漂移导致自研内核失稳。

### 9. 加密与主权签名

- `PyNaCl`：作为现代密码学能力组件，用于签名、验签与加密交换。
- 用途：实现 `IdentityKernel` 的身份签名能力。对下发给宿主的 `allow`、`pause` 等建议附加基于 `Ed25519` 的数字签名，并支持加密策略补丁交换与双重签名鉴权链路。

### 10. 动态环境配置管理

- `pydantic-settings`：与 `Pydantic v2` 原生集成，支持环境变量、`.env` 文件与 Secrets 自动加载。
- 用途：管理 `IdentityKernel` 的静态配置、`SafetyGate` 的动态阈值，以及不同部署模式下的运行参数。

### 明确排斥引入的技术栈

为保证架构轻量化并满足单机默认极简可用原则，第一阶段明确不引入以下技术栈：

- `Kafka`
- `RabbitMQ`
- `Ray`
- 任何默认接管主脑语义的整套外部 Agent 编排框架

## 职责边界建议

- `plugins` 负责扩展能力本身，不直接承担具体业务页面职责。
- `admin-portal` 负责通用后台管理前端页面。
- `cloud-audit-web` 负责云审计业务 Web 页面与交互展示。
- `cloud-audit-admin` 负责云审计业务的后台管理能力与配置功能。
- `zentex` 负责系统核心能力域，其中各子目录按独立能力模块拆分。

## 后续建议

- 每个目录补充独立 `README.md`，说明启动方式、技术栈与负责人。
- 在功能继续细化后，按领域继续拆分子模块，避免目录职责交叉。
- 插件与业务模块之间通过明确接口通信，减少直接耦合。

# Zentex Tasks 模块技术文档

## 1. 模块定位

`src/zentex/tasks` 是 Zentex 的统一任务管理模块，负责把九问、反思、学习、升级、外部执行器、插件执行、验证和运维分析等流程统一落到 `ZentexTask` 生命周期中。

当前实现的核心边界是：

- 任务表是任务状态的权威来源；共享状态只作为跨进程热缓存。
- 任务创建、状态流转、依赖、归档、结果写回、审计记录统一经过 `TaskManagementService`。
- HTTP API、Web Console、worker、workflow bridge 都不能绕过任务服务直接修改任务状态。
- 任务完成不能只改成 `done`；启用验证时必须通过 verification bridge 生成验证结果与写回记录。
- Q8 负责任务内容与意图，Q9 负责行动姿态与执行约束；发布到任务中心时要保留这个边界。

## 2. 核心入口

| 入口 | 文件 | 说明 |
| --- | --- | --- |
| 核心服务 | `service.py` | 任务生命周期、SQLite 持久化、依赖、批量操作、worker cycle、验证、结果写回、诊断分析的主服务。 |
| 高层封装 | `__init__.py` | 暴露 `TaskManager`，组合 registry、decomposer、service、interface。 |
| 服务接口 | `core/interface.py` | 面向其他模块的安全接口包装，返回统一 `success/error` 字典。 |
| 数据模型 | `models/models.py` | 定义 `ZentexTask`、状态、类型、范围、契约、分解上下文与子任务意图。 |
| SQLite schema | `schema.py` | 创建与补齐 `tasks`、审计、挂起、结果、干预等任务表结构。 |
| DAO | `persistence/dao.py` | 数据库 CRUD、分页、过滤、统计、审计、outcome、idempotency 存取。 |
| HTTP 路由 | `../web_console/routers/tasks.py` | FastAPI 任务中心 REST/WebSocket API，薄路由，实际逻辑委托 service。 |
| 路由辅助 | `../web_console/routers/tasks_handlers.py` | detail、subtasks、logs、bulk operation 等 API 处理器。 |

## 3. 运行主流程

### 3.1 创建任务

1. 调用方通过 `TaskManagementService.create_task()` 或 `/api/web/tasks` 提交 payload。
2. 服务规范化 `task_type`、`task_scope`、`priority`、`contract`、`metadata`、`idempotency_key`。
3. 写入 SQLite `tasks` 表，并同步必要的 shared cache。
4. 记录 `TASK_CREATED` 审计日志。
5. API/UI 通过 `list_tasks()`、`list_tasks_page()` 或 detail API 读回真实数据库状态。

### 3.2 mission 拆解与发布

1. mission 任务进入 `decompose_and_dispatch_mission()`。
2. `core` 或 `decomposition` 下的 decomposer 生成子任务意图。
3. Q9 blueprint 路径使用 `decompose_q9_blueprint_task()` 生成内部/外部任务。
4. 子任务写入统一任务表，父任务记录 `subtask_ids`。
5. assignment router 为任务匹配内部插件、CLI、MCP、Agent、外部连接器等执行资源。

### 3.3 执行与写回

1. `TaskAutoLoopScheduler` 调用 `TaskDispatchManager.run_cycle()`。
2. `TaskExecutionWorker` 查找 `queued/todo` 且依赖满足的任务。
3. `UnifiedTaskRouter` 优先内部 functional plugin，再回退外部执行器候选。
4. `InternalPluginExecutor` 或外部 service 执行任务。
5. `external_result_bridge.py` / worker 将执行输出写回任务记录。
6. 完成状态走 `verification/status_bridge.py`，必要时触发验证引擎。

### 3.4 验证、监督和结果沉淀

1. `VerificationEngine` 根据任务契约中的 `verification` 配置执行多个 verifier。
2. 验证失败进入 failure classifier 和 supervision mapper，生成 retry/fallback/escalation/compensation 决策。
3. `outcomes.py` 将任务结果写回 reflection、memory、learning。
4. `maintenance/outcome_maintenance.py` 可基于结果触发后续维护。
5. `lifecycle_diagnostics.py` 与 `maintenance/garbage_analysis.py` 用于闭环诊断、重复任务和垃圾任务分析。

### Zentex 任务中心 (G31A) 极端详细工作流程图

任务中心（G31A）作为 Zentex 架构中“认知与执行物理隔离”的绝对物理落地层，其工作流是一个从“抽象文本”到“物理工单”、再穿过“三重安全漏斗”、最终“真实验收”的严密状态机管线。

以下是任务中心全生命周期的详细工作流程图：

```text
[上游输入] Q9 产出纯文本的结构化行动蓝图 JSON (ActionPlan)
      │
      ▼
================================================================================
【阶段一：物理建单与依赖匹配】(完全确定性代码，不消耗LLM)
================================================================================
      │
  [1. 数据契约拦截]
  Pydantic v2 强类型校验 ──(字段缺失/枚举越界)──> 触发 ValidationError 阻断
      │
      ▼ (校验通过)
  [2. 物理实例化建单] 
  TaskSplitter (任务拆分器) 生成数据库级 SubtaskRecord 工单
  系统自动分配物理 task_id, subtask_id (防止大模型伪造)
  初始状态: split_required -> assignment_pending
      │
      ▼
  [3. 依赖与资源绑定]
  ├─ DependencyBuilder: 解析 depends_on，构建子任务有向无环图 (DAG)
  ├─ ResourceMatcher: 搜索内部插件、MCP、CLI、外部 Agent 资产库
  └─ TaskAssignmentRouter: 分配执行权，写入 owner_ref 或 candidate_owners
      │
      ▼
================================================================================
【阶段二：执行前三重漏斗防线】(物理 -> 语义 -> 核心安全)
================================================================================
      │
  [防线 1：确定性死规则初筛] (LLM NOT REQUIRED)
  ├─ 状态机非法跨越检测 -> 阻断
  ├─ 绝对幂等键 (idempotency_key) 碰撞 -> 阻断
  ├─ 依赖环死锁检测 (A->B->A) -> 阻断
  ├─ 孤儿与陈旧任务检测 (无 owner/无进展) -> 阻断
  └─ 重试风暴阻断 (retry_count 耗尽) -> 阻断
      │
      ▼ (穿过死规则的任务)
  [防线 2：LLM 语义深度打分漏斗] (LLM MANDATORY)
  智能分析模块对目标(objective)与意图进行打分评估
  ├─ duplicate_score 高分 -> 语义判重命中 -> 【静默合并】不分配资源，复用源任务执行回执
  └─ junk_score 高分 -> 幻觉/噪音 -> 【强制取消】标记为 cancelled_by_policy/conflict
      │
      ▼ (真正有价值的唯一任务)
  [防线 3：最高安全与权限审查]
  审查真实执行参数 (如 target, path, command)，而非抽象意图
  ├─ G12 SafetyGate: 比对身份内核绝对禁令，越权直接拒绝
  └─ G30 CloudAudit: 若为高风险操作(如删除/覆写)，强制请求外部云审计验签批准 (accepted)
      │
      ▼
================================================================================
【阶段三：正式调度执行与状态机流转】
================================================================================
      │
  [状态迁移: queued -> in_progress]
  SubtaskScheduler (子任务调度器) 正式调起外部连接器或内部插件
      │
  [运行时并行与干预机制]
  ├─ 并行控制: SubtaskParallelismController 基于 parallel_group_id 与并发配额(concurrency_quota) 执行任务
  ├─ 状态聚合: SubtaskStateAggregator 实时将子任务 progress_percent 和状态(active/partially_done/blocked) 汇总给主任务
  │
  ├─ <异常分支 A: 权限/资源硬缺口> -> 触发 G9 资源谈判机制 -> 生成 NegotiationRequest -> 任务进入 SuspendedTask 挂起并保留恢复条件
  ├─ <异常分支 B: 执行方中途失联> -> Orphan检测触发 -> 回收任务资源 -> 失败重派 (Reassign)
  └─ <异常分支 C: 人工干预> -> 进入 waiting_confirmation -> 等待 approve/reject/pause/take_over 指令
      │
      ▼
================================================================================
【阶段四：闭环验收、归档与动态打分】
================================================================================
      │
  [1. 获取客观物理证据]
  系统绝不盲信“自报成功”。外部执行必须收集真实 Before-and-After 物理证据 (文件 Hash、修改时间 mtime、导出产物、远端资源 ID 等)。
      │
  [2. 生成执行回执]
  打包生成唯一的 ActionExecutionReceipt (执行回执) 或 EvidenceBundle。
      │
  [3. 状态收束与长期归档]
  任务流转至 finished (completed / closed_with_outcome_summary) 或 cancelled。
  系统保存最终的“子任务列表快照”、“处理记录日志”和“证据包引用”。
      │
  [4. 动态打分与反思联动]
  基于真实执行质量、副作用控制和人工干预率，对负责执行的 MCP/CLI/Agent 写入 ExecutionScoreEvent 进行动态打分，影响未来任务的分配权重。
  如果任务失败或被拦截，证据包将流入 ReflectionEngine (反思引擎) 生成 FailureAnalysis (失败分析)。
```

### 核心处理环节详细说明：

**1. Pydantic v2 与物理建单层**
任务中心的最前端是一个没有大模型的**纯代码物理隔离层**。通过 Pydantic v2 校验 Q9 JSON 的四维契约（步骤说明、步骤目标、验证方式、涉及模块），校验通过后 `TaskSplitter` 强行将 JSON 转化为数据库实例 `SubtaskRecord`，生成系统级的 `task_id`，切断大模型直接控制底层工单的可能。

**2. 三重漏斗校验的层次递进**
* **物理死规则漏斗**：拦截 100% 确定的程序错误（如相同 `idempotency_key` 正在执行、`depends_on` 依赖环死锁、`retry_count` 重试风暴），极速且不耗费算力。
* **语义与噪音漏斗**：引入独立 LLM 拦截大模型的“高层内耗”。如果 `duplicate_score` 过高，任务中心不仅不分配资源，还会执行**“静默合并”**，直接将当前任务的指针挂载到那个相似的源任务上，复用执行回执。若 `junk_score` 极高（幻觉脱离现实），强行转化为 `cancelled_by_policy` 状态剥离资源。
* **安全与审查漏斗**：审查的焦点从“任务描述”变成“底层执行参数”。必须通过 G12 安全红线审核，高风险如需覆盖必须获得外部独立的 G30 云审计服务端 `accepted` 批准签名。

**3. 异常状态处理的极高韧性**
任务中心绝不只有“成功”和“失败”二值。当 `ResourceMatcher` 或执行过程中遭遇权限断崖或工具失联时，任务不会崩溃，而是由 G9 机制生成**资源谈判请求**，任务流入 `suspended`（挂起）状态，完整封存现场。一旦人类补充了权限或资源条件满足，系统自动将任务从断点 `resume`，这保证了任务中心的长周期推进能力。

## 4. 目录结构

```text
src/zentex/tasks/
├── __init__.py
├── service.py
├── schema.py
├── dao.py
├── archive_manager.py
├── lifecycle_diagnostics.py
├── timeout_recovery.py
├── outcomes.py
├── core/
├── decomposition/
├── dispatch/
├── docs/
├── documents/
├── execution/
├── experience/
├── integration/
├── maintenance/
├── management/
├── models/
├── persistence/
├── plugins/
├── reanalysis/
├── registry/
├── scheduling/
├── supervision/
└── verification/
```

`__pycache__` 是 Python 运行缓存，不属于源码设计文档范围。

## 5. 顶层文件说明

| 文件 | 说明 |
| --- | --- |
| `README.md` | 当前模块概览、关键入口、能力范围和集成边界。 |
| `DOCUMENTATION.md` | 历史详细说明，包含架构、数据模型、API、插件、持久化等介绍。阅读时需结合当前源码。 |
| `API_REFERENCE.md` | 本地接口形态的历史 API 参考；HTTP API 以 `web_console/routers/tasks.py` 为准。 |
| `QUICK_START.md` | 快速上手说明。 |
| `TECHNICAL_DOCUMENTATION.md` | 本文件，面向维护者的当前目录和职责索引。 |
| `__init__.py` | 暴露 `TaskManager`，提供高层创建、查询、状态、依赖、挂起恢复等便捷方法。 |
| `service.py` | 模块主服务。包括任务 CRUD、状态机、数据库同步、shared cache、依赖、批量操作、worker、Q9 blueprint 拆解、验证桥、outcome 写回、诊断、任务插件函数。 |
| `schema.py` | 初始化和迁移 SQLite schema，补齐任务表、干预回执、任务结果等列。 |
| `dao.py` | 兼容导出层，指向 `persistence/dao.py` 中的 DAO 实现。 |
| `archive_manager.py` | 任务归档管理脚本/工具，用于处理归档数据。 |
| `lifecycle_diagnostics.py` | 构建任务生命周期诊断、故障注入报告和完成度评估。 |
| `timeout_recovery.py` | 根据阻塞、租约、运行状态等生成 timeout recovery action。 |
| `outcomes.py` | 记录任务结果，并提供写回 reflection、memory、learning 的 readback 校验路径。 |
| `migrate_to_sqlite.py` | 历史 JSON 数据迁移到 SQLite 的脚本。 |

## 6. 子目录与文件说明

### 6.1 `models/`

任务领域模型。

| 文件 | 说明 |
| --- | --- |
| `models.py` | 定义 `TaskStatus`、`TaskType`、`TaskScope`、`TaskPriority`、`CoordinationMode`、`SuspendedTask`、`TaskContract`、`ZentexTask`、`DecompositionContext`、`SubtaskIntent` 等核心模型。 |
| `errors.py` | 定义 `TaskStateError`，用于非法状态流转等任务状态错误。 |
| `__init__.py` | 汇总导出模型与错误类型。 |

关键状态包括：`split_required`、`assignment_pending`、`queued`、`todo`、`in_progress`、`blocked`、`waiting_confirmation`、`suspended`、`done`、`failed`、`archived`、`cancelled`。

### 6.2 `persistence/`

SQLite 数据访问层。

| 文件 | 说明 |
| --- | --- |
| `dao.py` | `TaskDAO`、`SuspendedTaskDAO`、`TaskAuditLogDAO`、`TaskOutcomeDAO`、`InterventionReceiptDAO`、`IdempotencyLogDAO`。负责 JSON 字段序列化、数据库过滤、分页、计数、审计和 outcome 持久化。 |
| `__init__.py` | DAO 包导出。 |

重要查询能力：

- `status/statuses`
- `priority`
- `task_type`
- `task_scope`
- `parent_task_id`
- `originator_id`
- `target_id`
- `source_module`
- `metadata_filters`
- `tags`
- `overdue_only`
- `root_only`
- `limit/offset`

### 6.3 `core/`

基础拆解接口、LLM prompt 和 prompt upgrade contract。

| 文件 | 说明 |
| --- | --- |
| `decomposer.py` | 基础 `TaskDecomposerPlugin` 和分解输出 schema。 |
| `interface.py` | `TaskServiceInterface`，给外部模块使用的统一安全接口。 |
| `llm_decomposer.py` | LLM mission decomposition 插件与 Pydantic 输出模型。 |
| `llm_prompt.py` | 通用 decomposition prompt 片段构建。 |
| `simple_llm_decomposer.py` | 简化版 LLM 拆解插件。 |
| `simple_llm_prompt.py` | 简化拆解 prompt builder，输出 system/prompt sections。 |
| `semantic_kernel_decomposer.py` | Semantic Kernel 风格拆解插件。 |
| `semantic_kernel_llm_prompt.py` | Semantic Kernel decomposition/analysis prompt builder。 |
| `service.py` | prompt upgrade contract 注册与查询。 |
| `__init__.py` | core 导出。 |

### 6.4 `decomposition/`

当前更严格的原子任务拆解与审查路径。

| 文件 | 说明 |
| --- | --- |
| `pydantic_ai_decomposer.py` | Pydantic AI 原子子任务模型、Q9 对齐审查模型和任务拆解插件。 |
| `reviewer.py` | 原子子任务审查报告与 reviewer。 |
| `__init__.py` | decomposition 包导出。 |

### 6.5 `dispatch/`

执行器候选与路由策略。

| 文件 | 说明 |
| --- | --- |
| `models.py` | `ExecutorType`、`ExecutorCandidate`、`DispatchDecision`、`DispatchResult`。 |
| `router.py` | `TaskRouter` 抽象接口。 |
| `router_impl.py` | `UnifiedTaskRouter`，内部 functional plugin 优先，外部执行器回退，记录 dispatch decision 与执行结果。 |
| `internal.py` | `InternalPluginExecutor`，把任务交给内部插件执行。 |
| `registry.py` | `ExecutorRegistry`，维护外部执行器候选。 |
| `errors.py` | dispatch routing 错误类型。 |
| `__init__.py` | dispatch 包导出。 |

### 6.6 `execution/`

任务执行闭环、worker、外部结果写回。

| 文件 | 说明 |
| --- | --- |
| `README.md` | 执行子系统说明。 |
| `assignment_flow.py` | `ResourceMatcher` 与 `TaskAssignmentRouter`，在任务流程中把 `assignment_pending` 子任务映射到真实 Agent/CLI/MCP/外部连接器，或触发 G9 资源谈判挂起。 |
| `dispatch_manager.py` | `TaskDispatchManager`，把 Q9 action posture 转换为 worker 配置和执行约束。 |
| `worker.py` | `TaskExecutionWorker`，按 cycle 拉取可执行任务、路由、执行、写回、重试或失败。 |
| `external_result_bridge.py` | 外部执行开始/完成写回；持久化输出、状态、错误和结果摘要。 |
| `workflow_sync.py` | 等待任务状态、恢复 waiting confirmation 等工作流同步工具。 |
| `task_persistence.py` | 外部执行任务持久化服务，生成标准任务记录和 executor metadata。 |
| `__init__.py` | execution 包导出。 |

### 6.7 `verification/`

任务完成验证系统。

| 文件 | 说明 |
| --- | --- |
| `README.md`、`USAGE_GUIDE.md`、`QUICK_REFERENCE.md` | 验证系统说明与使用文档。 |
| `models.py` | 验证类型、策略、状态、失败类型、证据、单 verifier 结果、总结果等模型。 |
| `engine.py` | `VerificationEngine`，执行 verifier、聚合结果、生成 recommendation，并接入失败分类。 |
| `registry.py` | `VerifierRegistry`，根据配置创建 verifier。 |
| `verifiers.py` | automated test、LLM evaluation、rule-based、log audit 等 verifier 实现。 |
| `classifier.py` | `FailureClassifier`，对验证失败做类型、严重度和建议处理分类。 |
| `status_bridge.py` | 拦截 `done` 状态更新，在需要时路由到验证完成流程。 |
| `external_evidence.py` | 文件、图片、MongoDB、Agent ledger、外部副作用等真实证据校验工具。 |
| `writebacks.py` | reflection/memory/learning 写回内容 readback 校验。 |
| `llm_prompt.py` | LLM evaluation prompt builder。 |
| `service.py` | verification prompt upgrade contract。 |
| `__init__.py` | verification 包导出。 |

### 6.8 `supervision/`

失败后的监督决策模型与执行。

| 文件 | 说明 |
| --- | --- |
| `models.py` | `SupervisionAction`、retry/fallback/escalation/compensation 决策和 policy 模型。 |
| `mapper.py` | `FailureResponseMapper`，把失败类型映射为监督动作。 |
| `executor.py` | `SupervisionExecutor`，执行监督决策。 |
| `__init__.py` | supervision 包导出。 |

### 6.9 `integration/`

任务模块与其他业务模块的同步边界。

| 文件 | 说明 |
| --- | --- |
| `workflow_bridge.py` | `WorkflowTaskBridge`，把 reflection、learning、upgrade 等工作流同步为统一任务，并写入 `source_module/workflow_*` metadata。 |
| `reflection_integration.py` | 反思服务与任务服务集成。 |
| `task_execution_with_reflection.py` | 任务执行后触发反思记录、学习和错误分析的集成路径。 |
| `nine_questions_integration.py` | 九问任务编排事件、dispatch/verification/supervision/experience 事件映射。 |
| `__init__.py` | integration 包导出。 |

### 6.10 `maintenance/`

任务运维、垃圾任务分析和 outcome 维护。

| 文件 | 说明 |
| --- | --- |
| `garbage_analysis.py` | 重复任务、低信息任务、死锁依赖、重试耗尽、Q9 子任务重复等分析。支持规则评分和可选 LLM 语义评分。 |
| `garbage_analysis_prompt.py` | 任务创建噪音评分 prompt 和上下文 builder。 |
| `outcome_maintenance.py` | 自动 outcome maintenance，把任务结果与 memory/reflection/learning 维护事件连接起来。 |
| `__init__.py` | maintenance 包导出。 |

### 6.11 `management/`

面向文档/产品计划的任务生成与谈判管理。

| 文件 | 说明 |
| --- | --- |
| `task_generator.py` | 产品文档到任务列表转换，定义 `SubTask`、`GeneratedTask`、`TaskList`。 |
| `negotiation.py` | `NegotiationGenerator`，为阻塞、冲突、资源不足等任务生成 negotiation request。 |
| `__init__.py` | management 包导出。 |

### 6.12 `documents/`

产品文档和系统架构文档模型。

| 文件 | 说明 |
| --- | --- |
| `product_document.py` | 产品文档模型：验证方法、功能点、模块、目标、计划、产品文档。 |
| `document_template.py` | 文档模板、格式化器、验证器，以及 JSON 保存/加载工具。 |
| `system_architecture.py` | 系统架构组件与数据流模型。 |
| `product_document_example.py` | 产品文档构建示例。 |
| `task_with_document_example.py` | 文档驱动任务生成示例。 |
| `__init__.py` | documents 包导出。 |

### 6.13 `experience/`

任务经验抽取与排序。

| 文件 | 说明 |
| --- | --- |
| `models.py` | 经验记录、经验教训、执行器表现统计、经验上下文模型。 |
| `extractor.py` | `ExperienceExtractor`，从任务执行结果中抽取经验。 |
| `ranker.py` | `ExperienceRanker`，按相关性/置信度等排序经验。 |
| `__init__.py` | experience 包导出。 |

### 6.14 `reanalysis/`

部分完成和再分析流程。

| 文件 | 说明 |
| --- | --- |
| `models.py` | partial completion、improvement suggestion、reanalysis plan/result 模型。 |
| `analyzer.py` | `ReanalysisService`，分析部分完成、改进机会和后续计划。 |
| `examples.py` | 再分析使用示例。 |
| `__init__.py` | reanalysis 包导出。 |

### 6.15 `registry/`

任务注册与拆解插件注册。

| 文件 | 说明 |
| --- | --- |
| `registry.py` | `TaskRegistry`，进程内任务注册表。 |
| `plugin_registry.py` | 基础任务拆解插件 registry 与 manager。 |
| `plugin_registry_llm.py` | LLM 任务拆解插件 registry 与 manager。 |
| `semantic_kernel_registry.py` | Semantic Kernel 拆解插件 registry 与 manager。 |
| `dual_decomposition_registry.py` | 双路径 decomposition registry，支持多种拆解插件组合。 |
| `__init__.py` | registry 包导出。 |

### 6.16 `plugins/`

任务拆解插件定义。

| 文件 | 说明 |
| --- | --- |
| `decomposition_plugin.py` | 基础任务拆解 functional plugin spec 和实现。 |
| `decomposition_plugin_llm.py` | LLM 版本拆解 functional plugin spec 和实现。 |
| `__init__.py` | plugins 包导出。 |

### 6.17 `scheduling/`

后台自动循环。

| 文件 | 说明 |
| --- | --- |
| `loop_scheduler.py` | `TaskAutoLoopScheduler`，周期性触发 worker cycle、自动恢复、timeout republish 等。 |
| `__init__.py` | scheduling 包导出。 |

### 6.18 `docs/`

模块内文档镜像。

| 文件 | 说明 |
| --- | --- |
| `README.md` | docs 子包说明。 |
| `DOCUMENTATION.md` | 文档镜像。 |
| `API_REFERENCE.md` | API 参考镜像。 |
| `QUICK_START.md` | 快速开始镜像。 |
| `__init__.py` | docs 包占位。 |

## 7. 关联目录

任务中心不是只由 `src/zentex/tasks` 组成，以下目录是运行时相关边界：

| 目录/文件 | 说明 |
| --- | --- |
| `src/zentex/web_console/routers/tasks.py` | 任务 HTTP API 和 WebSocket。 |
| `src/zentex/web_console/routers/tasks_handlers.py` | API 详情、日志、子任务、批量操作 handler。 |
| `src/admin-portal/src/pages/tasks/` | Web Console 任务中心页面，包含列表、详情、日志、状态 chip、分页 hook、展示转换和测试。 |
| `src/plugins/tasks/` | 任务功能插件，包括能力匹配、约束检查、证据抽取、结果归一化、补偿清理、文档路由、规则验证等。 |
| `src/zentex/nine_questions/q8_tasks.py` | Q8 任务计划与任务中心同步相关逻辑。 |
| `src/zentex/nine_questions/q9_tasks.py` | Q9 姿态约束后的任务发布/同步逻辑。 |
| `src/plugins/nine_questions/q8_what_should_i_do_now/*_tasks/` | Q8 内部/外部任务 planner、validator、runtime。 |
| `src/plugins/nine_questions/q9_how_should_i_act/*_tasks/` | Q9 内部/外部行动 planner、validator、runtime。 |

## 8. HTTP API 概览

主要路由定义在 `src/zentex/web_console/routers/tasks.py`：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/tasks` | 按状态、scope、source_module、metadata、root_only 分页列出任务。 |
| `POST` | `/tasks` | 创建任务。 |
| `GET` | `/tasks/by-status` | 按展示分组返回任务。 |
| `GET` | `/tasks/page` | 返回单个展示分组的精确分页和总数。 |
| `GET` | `/tasks/diagnostics/closure` | 任务闭环诊断。 |
| `GET` | `/tasks/garbage-analysis` | 垃圾任务、重复任务、噪声任务分析。 |
| `GET` | `/tasks/worker/status` | worker/scheduler/database 状态。 |
| `GET` | `/tasks/logs` | 任务审计日志列表。 |
| `POST` | `/tasks/diagnostics/fault-injection` | 故障注入矩阵。 |
| `GET` | `/tasks/{task_id}/detail` | 任务详情、子任务、依赖、干预和统计。 |
| `GET` | `/tasks/{task_id}/outcome` | 任务 outcome。 |
| `DELETE` | `/tasks/{task_id}` | 删除任务。 |
| `GET` | `/tasks/{task_id}/logs` | 单任务审计日志。 |
| `GET` | `/tasks/{task_id}/subtasks` | 子任务列表。 |
| `POST` | `/tasks/{task_id}/decompose` | mission 拆解。 |
| `GET` | `/tasks/{task_id}/execution-history` | 执行历史。 |
| `WS` | `/tasks/stream` | 任务更新流。 |
| `GET` | `/tasks/tree/{task_id}` | 依赖树。 |
| `GET` | `/tasks/negotiations` | negotiation 列表。 |
| `POST` | `/tasks/{task_id}/intervene` | 人工干预。 |
| `POST` | `/tasks/bulk-operation` | 批量操作。 |

## 9. 数据与审计

任务模块主要表由 `schema.py` 维护，DAO 层负责读写：

- `tasks`：核心任务记录。
- `suspended_tasks`：挂起任务及恢复条件。
- `task_audit_log`：任务创建、状态变化、干预、删除、验证等审计。
- `task_outcomes`：任务完成结果、verification、writeback 状态。
- `intervention_receipts`：人工干预回执。
- `idempotency_log`：幂等键到任务 ID 的映射。

关键原则：

- 读列表、分页、计数必须走 DAO/Service，不直接扫共享状态。
- 修改/删除/新增后要通过查询读回确认。
- 审计日志是页面日志和回放的来源，不应只写前端状态。
- `metadata.source_module`、`workflow_kind`、`workflow_status`、`workflow_progress` 是跨模块筛选和展示的关键字段。

## 10. 测试入口

与任务模块直接相关的真实验收测试主要在：

- `tests/ci_acceptance/real_ci_modules/tasks/`
- `tests/ci_acceptance/test_tasks_agents_cli_mcp.py`
- `tests/full_workflow/test_01_internal_stock_data_task_flow.py`
- `tests/full_workflow/test_02_cli_external_task_flow.py`
- `tests/full_workflow/test_03_mcp_external_task_flow.py`
- `tests/full_workflow/test_04_agent_sync_task_flow.py`
- `tests/full_workflow/test_05_agent_callback_task_flow.py`

测试约束：

- API 暴露的流程应通过真实 HTTP 请求验证。
- 任务 CRUD、状态更新、删除、批量操作必须包含读回验证。
- 禁止 mock、假正常、吞异常、隐藏错误或生产代码测试特判。
- 外部执行、副作用和 writeback 应校验真实证据或服务 readback。

## 11. 维护规则

修改任务模块时按以下顺序检查：

1. 是否改变 `ZentexTask` schema、状态枚举或 contract。
2. 是否需要同步更新 `schema.py`、DAO 序列化/反序列化和 API response。
3. 是否需要更新 Web Console 展示转换和任务详情页。
4. 是否影响 Q8/Q9 的任务边界、source_module、metadata 或发布时机。
5. 是否影响 worker 路由、外部执行写回或 verification bridge。
6. 是否有新增/修改/删除后的 readback 测试。
7. 是否需要新增 task audit log 或 outcome writeback 校验。

不要做：

- 不要绕过 `TaskManagementService` 直接写任务状态。
- 不要把 shared cache 当成权威任务数据。
- 不要在任务完成时绕过 verification/status bridge。
- 不要让 Q9 修改 Q8 的任务内容；Q9 只能施加行动姿态、节奏、批准门和执行约束。
- 不要把外部执行失败包装成成功结果。

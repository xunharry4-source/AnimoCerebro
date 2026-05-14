# Tasks Execution LangGraph ReAct 执行模块实现文档

## 1. 背景与根因

当前 `src/zentex/tasks/execution` 已经具备真实执行链路：worker 能从任务表拉取可执行任务，构造 dispatch payload，调用 CLI/MCP/external connector/agent service，并把 execution output、task outcome 和 verification result 写回任务中心。

但当前链路本质仍是薄调度：

```text
Task metadata -> Dispatch payload -> Service call -> Outcome write-back -> Generic verification
```

它的实战性不足，根因是执行模块缺少一个显式的执行认知与执行控制层：

1. 没有 `ExecutionPlan`，worker 直接把 metadata 转成 dispatch，无法表达“先检查什么、缺什么、执行什么、观察什么、如何恢复”。
2. 没有 capability 级执行契约，参数 schema、preflight、输出 schema、验证规则和回滚策略没有成为 capability 的强约束。
3. 参数缺失没有正式状态，只能表现为 dispatch 构造失败、pre-dispatch block 或执行失败。
4. 验证偏通用，未按 capability 绑定真实 readback 断言。
5. `external_connector` 仍通过 `test_call` 执行业务能力，语义上混淆了健康探测和正式执行。
6. 失败分类不足，缺少 parameter gap、permission gap、preflight failure、execution failure、observation failure、verification failure、rollback failure 的明确分层。

本实现文档定义一个基于 LangGraph + ReAct 的执行模块，把任务执行升级为：

```text
Reason -> Resolve Parameters -> Preflight -> Act -> Observe -> Verify -> Recover/Complete
```

LLM 可以参与 Reason/diagnosis，但不得伪造 Act/Observe/Verify 结果。真实副作用、真实读回和 fail-closed 是硬边界。

LangGraph 负责把执行过程固化成可恢复、可观测、可重试的状态图；ReAct 负责每轮执行的 Reason/Act/Observe 语义；任务中心仍然负责状态落库、审计和 verification bridge。

## 2. 目标

### 2.1 功能目标

1. 在 `tasks/execution` 下实现 LangGraph ReAct 执行编排模块。
2. 让 worker 从一次性 dispatch 升级为执行循环编排器。
3. 引入 capability 执行契约，强制参数、权限、preflight、输出、验证和恢复策略。
4. 引入参数解析与 `parameter_gap` 挂起机制，禁止缺参数时猜测执行。
5. 将 external connector 的正式业务执行从 `test_call` 语义迁移到 `execute_capability`。
6. 为每次执行生成可审计的 ExecutionRun、ActionAttempt、Observation 和 EvidenceBundle。
7. 保持任务表为权威状态源，所有状态变更必须经过 `TaskManagementService` 或现有任务 DAO/service 边界。
8. 增加失败重试策略，按失败类型控制 retry/suspend/fail/rollback。
9. 增加执行检查节点，对执行前、执行后和验证前的关键证据做强制检查。

### 2.2 非目标

1. 不让 LLM 直接调用外部系统。
2. 不允许 LLM 生成“执行成功”结果。
3. 不把 parameter gap 降级为默认参数。
4. 不绕过 CLI/MCP/external connector/agent 各自的 service.py。
5. 不把测试 fixture 或 mock 结果标记为真实执行。
6. 不把 LangGraph/ReAct 的所有实现塞进一个巨石文件。
7. 不在任何 owner module 的 `service.py` 中编写业务逻辑。

## 3. 设计原则

1. **任务中心只编排，不拥有外部业务实现**  
   CLI/MCP/external connector/agent 的真实动作仍由各自 service 执行。

2. **Reason 可用 LLM，Act/Observe/Verify 必须真实**  
   ReAct 中的 Reason 阶段可以调用 LLM 辅助判断下一步，但 Act 只能调用真实 executor，Observe 必须读真实输出或持久化证据，Verify 必须基于物理证据。

3. **LangGraph 是执行状态机，不是业务兜底层**  
   LangGraph 节点只能编排已声明的动作和检查；不能在节点里补假参数、吞异常或把失败转成成功。

4. **参数缺失 fail-closed**  
   缺少必填参数时进入 `parameter_gap` 或 `suspended`，不能猜测、不能用空参数执行、不能伪造成功。

5. **capability contract 是执行权威**  
   一个 task 被绑定到 executor 后，执行参数和验证方式必须由 capability contract 约束。

6. **每一步可审计、可回放、可恢复**  
   每次 Reason、Act、Observe、Verify、Recovery 都必须记录 trace_id、task_id、attempt_id、输入摘要、输出摘要、错误分类和证据引用。

7. **失败重试必须受 contract 约束**  
   retry 只能用于明确可重试的失败类型，例如 transient executor error、timeout、observation readback delay；参数缺失、权限缺失、安全阻断、contract violation 不允许盲目重试。

8. **兼容现有 worker，分阶段迁移**  
   初期可以在 `TaskExecutionWorker` 内调用 ReAct executor；完成迁移后 worker 只保留调度循环，具体执行交给 ReAct 模块。

9. **service.py 只做服务边界，不承载业务逻辑**  
   每个模块的 `service.py` 只能负责公开接口、参数 DTO 转换、权限/事务/审计入口、依赖注入和调用 domain/application 层。具体业务逻辑必须落在该模块自己的 domain/application/execution 子模块中，不能把复杂执行、验证、readback、retry、LLM 判断直接写进 `service.py`。

10. **执行模块按职责拆分，禁止巨石实现**  
    `tasks/execution` 的 LangGraph/ReAct 实现必须按 graph state、nodes、edges、contract、profile、parameter、preflight、dispatch、observation、validation、verification、retry、recovery、events、persistence 拆分。任何单文件试图同时实现图编排、五类执行方、参数解析、验证和落库，都视为架构违规。

## 4. 当前 service.py 能力审计

本节记录实现前的真实代码现状。结论：五类执行方的 `service.py` 边界已经存在，但尚未统一支持复杂执行、复杂参数 contract、复杂结果验证和 readback verifier。后续实现必须先补齐这些能力，再接入 LangGraph ReAct 执行图。

### 4.1 总体现状

| 执行方 | 当前正式入口 | 复杂执行 | 复杂参数 | 复杂验证 | 当前问题 |
| --- | --- | --- | --- | --- | --- |
| CLI | `zentex.cli.service.CliIntegrationService.execute_task` | 部分支持 | 弱支持 | 不足 | 支持一次 CLI 调用和写回，但没有 capability 级 result/readback verifier |
| Agent | `zentex.agents.service.get_service().dispatch_task` -> coordination service | 部分支持 | 中等支持 | service 层部分支持 | `dispatch_task` 支持 `verification_plan`，但 worker 当前没有传入，复杂验证没有进入任务执行链 |
| MCP | `zentex.mcp.service.McpIntegrationService.execute_task` | 部分支持 | 中等支持 | 不足 | `execute_task` 内部仍调用 `test_call`，成功条件主要是 `status=completed` |
| 外接 connector | `zentex.external_connectors.service.ExternalConnectorService.test_call` | 部分支持 | 中等支持 | 部分支持 | 有 capability/evidence 检查，但业务执行仍混在 `test_call` 语义里，缺正式 `execute_capability` |
| 内部插件 | `zentex.plugins.service.manager.execute_plugin_once` / `execute_functional_plugin` | 部分支持 | 中等支持 | 不足 | 插件能执行复杂逻辑，但 task worker 只做 DONE + dispatch_plugin_id 读回，不是 capability 级验证 |

### 4.2 CLI service.py 现状

已支持：

1. 注册 CLI tool，并保存 runtime state。
2. `test_call(...)` 可传 `arguments`、`stdin_input`、`working_directory`、`timeout_seconds`。
3. `execute_task(...)` 可执行 CLI 并写入 runtime log 和 task-center result。
4. usage profile 中有 `argument_schema`、examples、side_effects、risk_notes。

不足：

1. worker 当前只校验 usage profile 的顶层参数类型：CLI 只判断 schema 为 array 时参数是不是 list。
2. 没有按 CLI capability 绑定 output schema。
3. 没有检查 expected artifact 是否真实产生。
4. 没有 read-after-write / file readback verifier。
5. exit code 为 0 与业务成功没有强区分。

必须补：

1. `cli_registered_tool_execution_v1` executor profile。
2. CLI 参数 contract：arguments schema、stdin policy、cwd scope、env allowlist、timeout。
3. CLI result validator：exit_code、stdout/stderr schema、artifact refs。
4. CLI readback verifier：file_exists、file_contains、db_readback、audit runtime log。

### 4.3 Agent service.py 现状

已支持：

1. `dispatch_task(agent_id, task_payload, verification_plan, zentex_task_id, idempotency_key, ...)`。
2. invocation ledger：`external_task_ref`、`invocation_id`、trace、request、result。
3. Agent verification plan：`remote_result_view`、`active_probe`、`rule_analysis`、`llm_analysis`。
4. runtime log 和 audit。

不足：

1. worker 调 Agent 时没有传 `verification_plan`。
2. worker 只按 `ServiceResponse.is_error` 判断 succeeded。
3. Agent artifact/readback 没有进入 task-level verification gate。
4. Agent 自身 verification result 没有和 task completion verification 统一汇总。
5. Agent 自报 done 仍可能被任务中心接受为成功。

必须补：

1. `agent_dispatch_execution_v1` executor profile。
2. 从 task/capability contract 构造 AgentVerificationPlan。
3. Agent result validator：run id、external_task_ref、normalized_result、artifact refs。
4. Agent readback verifier：invocation ledger、agent log、artifact readable、LLM semantic verdict。

### 4.4 MCP service.py 现状

已支持：

1. MCP server 注册和 tool binding。
2. `test_call(server_id, tool_name, arguments, trace_id)`。
3. `execute_task(...)` 写回 task-center result。
4. tool binding 包含 read_only、side_effect_free、mutates_state、requires_cloud_audit。
5. MCP usage profile 可记录 tool argument schema。

不足：

1. `execute_task` 当前仍调用 `test_call`，缺正式 business execution API。
2. MCP tool schema drift 只在局部路径处理，没有成为任务执行硬门禁。
3. resource readback/hash 没有统一进入 task outcome。
4. mutation tool 没有强制 read-after-write verifier。
5. MCP health 和 MCP business tool success 仍容易混淆。

必须补：

1. `mcp_tool_execution_v1` executor profile。
2. MCP 参数 contract：server_id、tool_name、tool input_schema、resource_uri。
3. MCP result validator：tool result status/schema、resource hash、error_code。
4. MCP readback verifier：resource readback、schema drift check、runtime log。

### 4.5 外接 connector service.py 现状

已支持：

1. connector 注册、health check、capability declaration。
2. `test_call(connector_id, ConnectorTestCallRequest)` 会检查 active 和 capability。
3. SDK connector 要求返回 `output_summary`、`before_evidence`、`after_evidence`、`evidence_refs`。
4. mutation/high profile 能检查 evidence requirement。
5. connector invocation history 和 runtime log。

不足：

1. 缺正式 `execute_capability` 接口。
2. task worker 当前仍调用 `service.test_call(...)` 执行业务任务。
3. read-only capability 的 evidence validation 可能返回 `not_required`，但任务业务验证仍需要 `output_summary/evidence_refs`。
4. capability argument schema、output schema、verification rules 还没有统一成为 task contract。
5. connector replacement 只解决健康替换，不解决 capability 等价性和验证策略等价性。

必须补：

1. `external_connector_capability_execution_v1` executor profile。
2. 新增 `execute_capability(connector_id, request)`，保留 `test_call` 只做 health/smoke。
3. connector result validator：capability、output_summary、evidence_refs、invocation_id。
4. connector readback verifier：runtime log、history、read-after-write、task outcome。

### 4.6 内部插件 service.py 现状

已支持：

1. `execute_plugin_once(...)` 能执行单个插件实例。
2. 支持 `execute/process/run/handle/run_tool` 多种入口。
3. 支持参数映射、context 注入、audit/memory/reflection/learning/llm_service 注入。
4. 有 timeout、None result、empty cognitive result、masked error 防护。
5. `execute_functional_plugin(...)` 和 `execute_cognitive_plugin(...)` 作为公开 service boundary。

不足：

1. worker 内部插件成功后主要验证 task row 是 DONE、dispatch_plugin_id 匹配。
2. 插件 capability 的 input/output schema 没有进入统一 ExecutionContract。
3. 认知插件要求 LLM 时，任务执行层没有强制 LLM trace/readback。
4. 插件状态落库、公共投影、SQLite snapshot 没有统一 readback verifier。
5. 插件真实业务结果和 task outcome 的语义对齐没有 LLM/hybrid gate。

必须补：

1. `internal_plugin_service_execution_v1` executor profile。
2. 内部插件参数 contract：plugin_id、capability、context/session/task scope。
3. 内部插件 result validator：TaskFeedback、structured output、error contract。
4. 内部插件 readback verifier：plugin state、SQLite snapshot、LLM trace、public projection。

### 4.7 当前 worker 执行链缺口

当前 `TaskExecutionWorker` 已经能 lazy resolve 各模块 service.py，但仍是简单分支调用：

```text
external_dispatch_from_task
  -> if cli: cli_service.execute_task(...)
  -> if mcp: mcp_service.execute_task(...)
  -> if external_connector: service.test_call(...)
  -> if agent: agent_service.dispatch_task(...)
  -> attach evidence
```

内部插件路径则是：

```text
router decision -> _execute_on_plugin(...) -> _write_success(...)
```

缺口：

1. 没有统一 `ExecutionGraphState`。
2. 没有 executor profile gate。
3. 没有按五类执行方分开的 parameter contract。
4. 没有统一 result validation。
5. 没有统一 readback verifier。
6. 没有把 retry budget 和 failure class 绑定到 capability contract。
7. LangGraph 未安装时不能声称已实现 ReAct 执行。

## 5. 目标目录结构

目录设计本身就是架构约束：新增实现必须按职责拆分。`service.py`、`worker.py`、`langgraph_react_executor.py` 都不能变成承载所有业务分支的总控巨石。

```text
src/zentex/tasks/execution/
├── langgraph_react_executor.py    # LangGraph ReAct 主执行入口
├── graph_state.py                 # LangGraph ExecutionGraphState
├── graph_nodes/                   # 按节点功能拆分的 LangGraph node 实现
│   ├── load_context_node.py
│   ├── reason_node.py
│   ├── resolve_parameters_node.py
│   ├── preflight_node.py
│   ├── execution_check_node.py
│   ├── act_node.py
│   ├── observe_node.py
│   ├── result_validate_node.py
│   ├── verify_node.py
│   ├── retry_decision_node.py
│   ├── recover_node.py
│   └── complete_node.py
├── graph_edges.py                 # 条件边和失败路由
├── execution_context.py           # ExecutionContext / ExecutionRun / ActionAttempt
├── capability_contract.py         # CapabilityExecutionContract 与 contract resolver
├── executor_profiles.py           # CLI/Agent/MCP/外接/内部插件的执行与验证 profile
├── parameter_resolver.py          # 参数解析、schema 校验、parameter_gap
├── preflight.py                   # executor/capability/input/permission/idempotency 检查
├── execution_check.py             # 执行前/执行后/验证前检查
├── action_dispatcher.py           # CLI/MCP/connector/agent 的统一 Act 分发
├── observation.py                 # 观察执行输出、读回物理证据
├── result_validator.py            # 结果结构、业务字段、输出语义验证
├── capability_verifier.py         # capability 级验证器
├── validation_strategy.py         # 规则/LLM/混合验证策略选择与审计
├── retry_policy.py                # retry budget、backoff、retryable 分类
├── recovery.py                    # retry/suspend/rollback/compensation 决策
├── persistence.py                 # execution run / graph node IO / evidence 引用落库
├── events.py                      # 执行审计事件与结构化日志
├── errors.py                      # 结构化错误类型
└── README.md                      # 更新后的执行层总览
```

允许继续细分为子目录，但不能反向合并成单文件：

```text
src/zentex/tasks/execution/
├── graph/
│   ├── state.py
│   ├── builder.py
│   └── edges.py
├── nodes/
│   ├── load_context.py
│   ├── reason.py
│   ├── resolve_parameters.py
│   ├── preflight.py
│   ├── execution_check.py
│   ├── act.py
│   ├── observe.py
│   ├── result_validate.py
│   ├── verify.py
│   ├── retry_decision.py
│   ├── recover.py
│   └── complete.py
├── contracts/
│   ├── capability_contract.py
│   └── executor_profiles.py
├── validation/
│   ├── result_validator.py
│   ├── capability_verifier.py
│   └── validation_strategy.py
├── dispatch/
│   ├── action_dispatcher.py
│   ├── cli_adapter.py
│   ├── agent_adapter.py
│   ├── mcp_adapter.py
│   ├── external_connector_adapter.py
│   └── internal_plugin_adapter.py
└── persistence/
    ├── graph_run_store.py
    └── evidence_store.py
```

拆分规则：

1. `langgraph_react_executor.py` 只构建和运行 graph，不写五类执行方业务逻辑。
2. 每个 LangGraph 节点必须按节点功能独立成文件，禁止重新合并成 `graph_nodes.py` 大文件。
3. 节点文件只编排本节点阶段，不直接操作 CLI/MCP/connector/agent/plugin 的私有实现。
4. `action_dispatcher.py` 只按 executor profile 路由到 adapter，不承载 capability 业务分支。
5. 五类 executor adapter 只负责把统一 ActionRequest 转换成各自 service boundary 请求。
6. result validation、readback verifier、LLM/hybrid 判断必须在 validation/verifier 模块，不写进 dispatcher 或 service.py。
7. persistence 只负责 graph run、node input/output、evidence refs 的落库和读回，不执行任务。
8. 单文件超过约 700 行或同时承担两个以上核心职责时，必须拆分；不能以“先快速实现”为理由合并。

节点文件划分：

| LangGraph 节点 | 文件 | 允许依赖 | 禁止内容 |
| --- | --- | --- | --- |
| `load_context` | `graph_nodes/load_context_node.py` | task DAO/service、contract resolver | executor dispatch、LLM 规划 |
| `reason` | `graph_nodes/reason_node.py` | planning service、LLM gateway、contract | 直接执行动作、写最终成功 |
| `resolve_parameters` | `graph_nodes/resolve_parameters_node.py` | parameter resolver、schema validator | LLM 猜测参数、调用 executor |
| `preflight` | `graph_nodes/preflight_node.py` | preflight checks、profile、contract | 实际执行业务动作 |
| `execution_check_before` / `execution_check_after` | `graph_nodes/execution_check_node.py` | execution_check module | 修改 executor result |
| `act` | `graph_nodes/act_node.py` | action dispatcher | CLI/MCP/connector/agent/plugin 私有业务逻辑 |
| `observe` | `graph_nodes/observe_node.py` | observation/readback modules | 相信自报成功而不读证据 |
| `result_validate` | `graph_nodes/result_validate_node.py` | result validator、validation strategy | 补默认字段、吞 validation error |
| `verify` | `graph_nodes/verify_node.py` | capability verifier | 用 LLM 覆盖物理 readback 失败 |
| `retry_decision` | `graph_nodes/retry_decision_node.py` | retry policy | 对 non-retryable failure 继续重试 |
| `recover` | `graph_nodes/recover_node.py` | recovery policy、rollback/compensation service | 把 suspended/fail 改写成 success |
| `complete` | `graph_nodes/complete_node.py` | completion writer、TaskManagementService/DAO | 绕过 verification 直接 DONE |

现有文件保留：

```text
assignment_flow.py                 # G31A 执行方绑定，继续作为 assignment gate
worker.py                          # 调度循环，后续委托 react_executor
external_result_bridge.py          # 外部执行结果写回桥
dispatch_manager.py                # 过渡期可保留
task_persistence.py                # 任务持久化辅助
workflow_sync.py                   # workflow 同步
```

## 6. LangGraph 依赖与边界

### 6.1 依赖要求

仓库 `requirements.txt` 必须声明：

```text
langgraph>=0.2.0
```

实现前必须通过本地命令验证当前虚拟环境已经安装：

```bash
.venv/bin/python -c "import langgraph; print(langgraph.__version__)"
```

如果该命令失败，ReAct 执行器不得 fallback 到旧 worker 成功路径；只能返回结构化 `LANGGRAPH_RUNTIME_MISSING`，并阻断 ReAct 执行。

### 6.2 使用边界

LangGraph 只负责执行图编排：

- 管理 graph state。
- 定义节点顺序和条件边。
- 支持 retry/recover 路由。
- 支持 checkpoint/resume。

LangGraph 不负责：

- 直接访问外部系统。
- 伪造 executor 输出。
- 绕过 TaskManagementService 写状态。
- 替代 capability contract。
- 替代 verification engine。

## 7. 核心数据模型

### 7.1 ExecutionContext

用于描述一次执行循环的完整上下文。

```python
class ExecutionContext(BaseModel):
    task_id: str
    parent_task_id: str | None = None
    trace_id: str
    session_id: str | None = None
    task_scope: Literal["internal", "external"]
    executor_type: Literal["cli", "mcp", "external_connector", "agent", "internal_plugin"]
    owner_ref: str
    capability: str
    task_title: str
    objective: str
    contract: dict[str, Any]
    metadata: dict[str, Any]
    q9_blueprint_step: str | None = None
    constraints: dict[str, Any] = {}
```

来源：

- task row
- task metadata
- task contract
- G31A assignment metadata
- capability registry
- Q9 blueprint metadata

### 7.2 ExecutionGraphState

LangGraph 的 state 必须是显式结构，禁止把任意 dict 在节点之间无约束传递。

```python
class ExecutionGraphState(TypedDict):
    task_id: str
    trace_id: str
    run_id: str
    phase: str
    context: dict[str, Any]
    contract: dict[str, Any]
    plan: dict[str, Any] | None
    arguments: dict[str, Any] | None
    parameter_resolution: dict[str, Any] | None
    preflight_result: dict[str, Any] | None
    execution_check_result: dict[str, Any] | None
    current_attempt: dict[str, Any] | None
    observations: list[dict[str, Any]]
    result_validation: dict[str, Any] | None
    verification_result: dict[str, Any] | None
    retry_state: dict[str, Any]
    failure: dict[str, Any] | None
    audit_events: list[dict[str, Any]]
```

`retry_state` 示例：

```json
{
  "attempt_count": 1,
  "max_attempts": 3,
  "retryable_failures": ["executor_timeout", "transient_connector_error", "observation_readback_not_ready"],
  "last_failure_type": "executor_timeout",
  "next_retry_after": "2026-05-14T01:00:00Z",
  "backoff_seconds": 30
}
```

### 7.3 CapabilityExecutionContract

每个 capability 必须声明执行契约。

```python
class CapabilityExecutionContract(BaseModel):
    owner_ref: str
    executor_type: Literal["cli", "mcp", "external_connector", "agent", "internal_plugin"]
    capability: str
    version: str
    execution_profile_id: str
    risk_level: Literal["read_only", "write", "destructive", "external_side_effect"]
    parameter_schema: dict[str, Any]
    required_parameters: list[str]
    optional_parameters: list[str] = []
    preflight_checks: list[dict[str, Any]]
    execution_mode: Literal["read", "write", "mutation", "workflow", "agent_task"]
    output_schema: dict[str, Any]
    observation_sources: list[Literal["executor_result", "task_outcome", "file_readback", "db_readback", "http_readback", "audit_log", "plugin_state_readback", "agent_artifact_readback", "mcp_resource_readback"]]
    evidence_requirements: list[dict[str, Any]]
    verification_rules: list[dict[str, Any]]
    verification_strategy: Literal["rule", "llm", "hybrid"]
    llm_validation_policy: dict[str, Any] | None = None
    hybrid_validation_policy: dict[str, Any] | None = None
    retry_policy: dict[str, Any]
    rollback_policy: dict[str, Any] | None = None
    parameter_gap_policy: dict[str, Any]
```

示例：`mongodb_csv_inspect`

```json
{
  "owner_ref": "external_connector:task-mongodb-csv-88de354c",
  "executor_type": "external_connector",
  "capability": "mongodb_csv_inspect",
  "execution_profile_id": "external_connector_capability_execution_v1",
  "risk_level": "read_only",
  "required_parameters": ["csv_paths"],
  "optional_parameters": ["timestamp_column", "max_files"],
  "preflight_checks": [
    {"type": "path_exists", "field": "csv_paths"},
    {"type": "file_extension", "allowed": [".csv"]},
    {"type": "connector_health", "required": "healthy"}
  ],
  "evidence_requirements": [
    {"field": "output_summary.file_count", "type": "integer", "min": 1},
    {"field": "output_summary.total_rows", "type": "integer", "min": 1},
    {"field": "evidence_refs", "type": "non_empty_list"}
  ],
  "observation_sources": ["executor_result", "task_outcome", "audit_log"],
  "verification_rules": [
    {"type": "required_field", "field": "actual_outcome.status"},
    {"type": "enum_value", "field": "actual_outcome.status", "allowed_values": ["success"]},
    {"type": "required_field", "field": "actual_outcome.output_summary.file_count"},
    {"type": "required_field", "field": "actual_outcome.output_summary.total_rows"}
  ],
  "verification_strategy": "rule",
  "llm_validation_policy": null,
  "hybrid_validation_policy": null
}
```

### 7.4 ExecutionPlan

Reason 阶段输出，不是执行结果。

```python
class ExecutionPlan(BaseModel):
    task_id: str
    trace_id: str
    plan_id: str
    next_action: Literal["resolve_parameters", "preflight", "act", "observe", "verify", "recover", "complete"]
    action_reason: str
    required_capability_contract: CapabilityExecutionContract
    parameter_requirements: list[dict[str, Any]]
    expected_observations: list[dict[str, Any]]
    stop_conditions: list[dict[str, Any]]
    max_react_steps: int = 8
```

### 7.5 ParameterResolutionResult

```python
class ParameterResolutionResult(BaseModel):
    status: Literal["resolved", "parameter_gap", "invalid_parameters"]
    arguments: dict[str, Any]
    missing_parameters: list[str] = []
    invalid_parameters: list[dict[str, Any]] = []
    parameter_sources: dict[str, str] = {}
    evidence: dict[str, Any] = {}
```

参数来源优先级：

1. child task metadata executor-specific 参数  
   `external_connector_arguments` / `mcp_arguments` / `cli_arguments` / `agent_task_payload`
2. parent Q9 metadata  
   `q9_external_connector_arguments[capability]` 或 `q9_external_connector_arguments["*"]`
3. task contract declared inputs
4. safe runtime context，例如 `task_id`、`trace_id`、`session_id`
5. 人工补充后的 suspended recovery context

禁止来源：

- LLM 猜测本地路径、数据库 filter、权限 token、外部资源 ID
- 空 dict 作为万能参数
- 从自然语言目标中正则硬猜高风险参数

### 7.6 ActionAttempt

```python
class ActionAttempt(BaseModel):
    attempt_id: str
    task_id: str
    trace_id: str
    executor_type: str
    owner_ref: str
    capability: str
    arguments_hash: str
    started_at: str
    finished_at: str | None = None
    status: Literal["started", "succeeded", "failed", "blocked"]
    error_code: str | None = None
    error_message: str | None = None
    result_ref: str | None = None
```

### 7.7 Observation

```python
class Observation(BaseModel):
    observation_id: str
    task_id: str
    attempt_id: str
    source: Literal["executor_result", "file_readback", "db_readback", "http_readback", "task_outcome", "audit_log"]
    observed_at: str
    payload: dict[str, Any]
    evidence_refs: list[str]
    physical_artifacts: list[dict[str, Any]]
```

### 7.8 ResultValidationResult

结果验证专门验证 executor 返回的业务结果是否符合 capability output contract。它不同于 execution check，也不同于最终 verification。

```python
class ResultValidationResult(BaseModel):
    status: Literal["passed", "failed"]
    validation_id: str
    task_id: str
    attempt_id: str
    capability: str
    checked_schema_version: str
    field_results: list[dict[str, Any]]
    semantic_results: list[dict[str, Any]]
    evidence_results: list[dict[str, Any]]
    failure_type: str | None = None
    failure_code: str | None = None
    retryable: bool = False
```

结果验证必须至少覆盖：

1. 输出 JSON 是否符合 `CapabilityExecutionContract.output_schema`。
2. 必填业务字段是否存在。
3. 字段类型、枚举、范围是否正确。
4. 输出摘要是否和 observation/readback 一致。
5. 写操作是否带有 read-after-write 证据。
6. 不允许 executor 自报成功但无 evidence。

## 8. LangGraph ReAct 主流程

### 8.1 状态流

```text
queued
  -> react_planning
  -> parameter_resolving
  -> parameter_gap          (缺参数，挂起)
  -> preflight_running
  -> preflight_failed       (不可执行，挂起或失败)
  -> acting
  -> observing
  -> verifying
  -> recovery_planning      (失败恢复)
  -> done / failed / suspended
```

初期不一定新增所有 DB status，可以先把细粒度状态写入 metadata：

```json
{
  "react_execution": {
    "phase": "preflight_running",
    "run_id": "...",
    "attempt_id": "...",
    "last_observation_id": "...",
    "failure_classification": null
  }
}
```

正式迁移后再考虑扩展 `TaskStatus`。

### 8.2 Graph 节点

LangGraph 必须显式定义以下节点：

每个节点必须有独立节点文件，节点文件之间只能通过 `ExecutionGraphState` 传递状态。

| 节点 | 节点文件 | 职责 | 失败出口 |
| --- | --- | --- | --- |
| `load_context` | `graph_nodes/load_context_node.py` | 从任务服务/DAO 读取 task、metadata、contract、assignment | `fail_context_invalid` |
| `reason` | `graph_nodes/reason_node.py` | 生成 ExecutionPlan；LLM mandatory 或 contract-only planning | `fail_reason` |
| `resolve_parameters` | `graph_nodes/resolve_parameters_node.py` | 解析并校验参数 | `parameter_gap` / `invalid_parameters` |
| `preflight` | `graph_nodes/preflight_node.py` | executor health、capability、权限、输入资源、幂等检查 | `preflight_failed` |
| `execution_check_before` | `graph_nodes/execution_check_node.py` | 执行前强检查，确认 dispatch 可构造且风险满足策略 | `execution_check_failed` |
| `act` | `graph_nodes/act_node.py` | 调用真实 executor service | `act_failed` |
| `observe` | `graph_nodes/observe_node.py` | 读回 executor result、DB/file/audit evidence | `observation_failed` |
| `execution_check_after` | `graph_nodes/execution_check_node.py` | 执行后强检查，确认 result/evidence 基本完整 | `execution_check_failed` |
| `result_validate` | `graph_nodes/result_validate_node.py` | 验证 executor 输出结构、业务字段、输出摘要与 observation 一致 | `result_validation_failed` |
| `verify` | `graph_nodes/verify_node.py` | capability 级 verification | `verification_failed` |
| `retry_decision` | `graph_nodes/retry_decision_node.py` | 判断是否允许重试、计算 backoff | `retry_wait` / `recover` / `fail` |
| `recover` | `graph_nodes/recover_node.py` | suspend、rollback、compensate、fail 分类处理 | `suspended` / `failed` |
| `complete` | `graph_nodes/complete_node.py` | 写 outcome、status done、审计 | terminal |

### 8.3 条件边

```text
START
  -> load_context
  -> reason
  -> resolve_parameters
  -> preflight
  -> execution_check_before
  -> act
  -> observe
  -> execution_check_after
  -> result_validate
  -> verify
  -> complete
```

失败边：

```text
resolve_parameters -- parameter_gap --> recover
resolve_parameters -- invalid_parameters --> recover
preflight -- failed --> retry_decision
execution_check_before -- failed --> recover
act -- failed --> retry_decision
observe -- failed --> retry_decision
execution_check_after -- failed --> retry_decision
result_validate -- failed --> retry_decision
verify -- failed --> retry_decision
retry_decision -- retry_allowed --> preflight
retry_decision -- retry_denied --> recover
recover -- suspended --> END
recover -- failed --> END
complete --> END
```

### 8.4 LangGraph 构造伪代码

```python
from langgraph.graph import END, StateGraph

from .graph_nodes.act_node import act_node
from .graph_nodes.complete_node import complete_node
from .graph_nodes.execution_check_node import (
    execution_check_after_node,
    execution_check_before_node,
)
from .graph_nodes.load_context_node import load_context_node
from .graph_nodes.observe_node import observe_node
from .graph_nodes.preflight_node import preflight_node
from .graph_nodes.reason_node import reason_node
from .graph_nodes.recover_node import recover_node
from .graph_nodes.resolve_parameters_node import resolve_parameters_node
from .graph_nodes.result_validate_node import result_validate_node
from .graph_nodes.retry_decision_node import retry_decision_node
from .graph_nodes.verify_node import verify_node

def build_execution_graph() -> CompiledGraph:
    graph = StateGraph(ExecutionGraphState)

    graph.add_node("load_context", load_context_node)
    graph.add_node("reason", reason_node)
    graph.add_node("resolve_parameters", resolve_parameters_node)
    graph.add_node("preflight", preflight_node)
    graph.add_node("execution_check_before", execution_check_before_node)
    graph.add_node("act", act_node)
    graph.add_node("observe", observe_node)
    graph.add_node("execution_check_after", execution_check_after_node)
    graph.add_node("result_validate", result_validate_node)
    graph.add_node("verify", verify_node)
    graph.add_node("retry_decision", retry_decision_node)
    graph.add_node("recover", recover_node)
    graph.add_node("complete", complete_node)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "reason")
    graph.add_edge("reason", "resolve_parameters")
    graph.add_conditional_edges("resolve_parameters", route_parameter_result)
    graph.add_conditional_edges("preflight", route_preflight_result)
    graph.add_conditional_edges("execution_check_before", route_execution_check_result)
    graph.add_conditional_edges("act", route_action_result)
    graph.add_conditional_edges("observe", route_observation_result)
    graph.add_conditional_edges("execution_check_after", route_execution_check_result)
    graph.add_conditional_edges("result_validate", route_result_validation)
    graph.add_conditional_edges("verify", route_verification_result)
    graph.add_conditional_edges("retry_decision", route_retry_result)
    graph.add_conditional_edges("recover", route_recovery_result)
    graph.add_edge("complete", END)
    return graph.compile()
```

### 8.5 主循环伪代码

```python
async def execute_task_with_react(task_id: str) -> ExecutionRunResult:
    context = await context_loader.load(task_id)
    initial_state = build_initial_graph_state(context)
    final_state = await execution_graph.ainvoke(initial_state)
    return await finalizer.from_graph_state(final_state)
```

节点内部仍要遵守现有 service 边界：

```python
async def act_node(state: ExecutionGraphState) -> ExecutionGraphState:
    dispatch = build_dispatch_from_state(state)
    attempt = await action_dispatcher.dispatch(dispatch)
    return {**state, "current_attempt": attempt, "phase": "observing"}
```

## 9. 失败重试设计

### 9.1 RetryPolicy

新增 `retry_policy.py`：

```python
class RetryPolicy(BaseModel):
    max_attempts: int = 3
    base_backoff_seconds: int = 10
    max_backoff_seconds: int = 120
    retryable_failure_types: list[str] = [
        "executor_timeout",
        "transient_connector_error",
        "transient_mcp_error",
        "transient_cli_error",
        "observation_readback_not_ready",
    ]
    non_retryable_failure_types: list[str] = [
        "parameter_gap",
        "invalid_parameters",
        "permission_gap",
        "safety_gate_blocked",
        "capability_contract_missing",
        "capability_not_supported",
        "mutation_guard_blocked",
        "verification_contract_failed",
    ]
```

### 9.2 重试规则

允许重试：

1. executor 临时超时。
2. connector health 在执行前通过，但执行时出现 transient remote error。
3. MCP/CLI 临时不可用但 registry 仍 active。
4. observation 读回延迟，例如异步日志尚未落库。
5. verification 的 evidence readback 延迟，且 contract 标记 retryable。

禁止重试：

1. 缺必填参数。
2. 参数类型错误。
3. connector capability 不存在。
4. 健康检查能力被用于业务任务。
5. MongoDB 写操作缺 trace marker。
6. 安全门禁或权限门禁拒绝。
7. LLM Reason 失败且该任务必须 LLM。
8. capability contract 缺失。

### 9.3 retry_decision 节点输出

```json
{
  "decision": "retry",
  "reason": "executor_timeout",
  "attempt_count": 1,
  "max_attempts": 3,
  "backoff_seconds": 20,
  "next_node": "preflight"
}
```

或：

```json
{
  "decision": "recover",
  "reason": "parameter_gap",
  "next_node": "recover"
}
```

### 9.4 重试落库要求

每次 retry 必须写入：

- `metadata.react_execution.retry_state`
- audit event `REACT_RETRY_SCHEDULED`
- 上一次 attempt 的 error_code/error_message
- next_retry_after

不得只在内存里递增 attempt。

## 10. 执行检查设计

### 10.1 execution_check_before

执行前检查必须在 Act 前运行。目标是证明“这个 dispatch 可以被真实执行”。

检查项：

1. `owner_ref` 存在且与 task target 一致。
2. `executor_type` 与 task scope 一致。
3. capability contract 存在。
4. 参数已 resolved，且 hash 已记录。
5. 参数 schema 校验通过。
6. executor health 检查通过。
7. 高风险写操作包含 trace_id/session_id/task_id。
8. expected evidence requirements 已知。
9. idempotency key 存在。

失败输出：

```json
{
  "passed": false,
  "check_stage": "before_act",
  "failure_type": "execution_check_failed",
  "failure_code": "ARGUMENT_SCHEMA_INVALID",
  "retryable": false,
  "details": {...}
}
```

### 10.2 execution_check_after

执行后检查在 Observe 后、Verify 前运行。目标是证明“执行结果具备可验证证据”。

检查项：

1. executor result 非空。
2. result status 明确，不允许 unknown。
3. evidence_refs 存在或 contract 声明允许无 evidence_refs。
4. output_summary 满足最低字段要求。
5. task outcome 已写回或存在可写回 payload。
6. external execution metadata 包含 executor_type、owner_ref、capability。
7. 对写操作，read-after-write query 已声明。

失败输出：

```json
{
  "passed": false,
  "check_stage": "after_observe",
  "failure_type": "execution_check_failed",
  "failure_code": "EVIDENCE_REFS_MISSING",
  "retryable": false,
  "details": {...}
}
```

### 10.3 execution_check 与 verification 的区别

| 层 | 目标 | 失败含义 |
| --- | --- | --- |
| execution_check_before | 证明可以执行 | 不能 Act |
| execution_check_after | 证明结果可被验证 | 不能进入 Verify 或需 retry observation |
| capability_verifier | 证明业务结果满足 contract | 任务成功或失败 |

execution_check 不替代 verification。

## 11. 结果验证设计

### 11.1 result_validate 节点定位

`result_validate` 节点位于 `execution_check_after` 与 `verify` 之间：

```text
observe -> execution_check_after -> result_validate -> verify
```

它解决的问题是：executor 返回了结果，但这个结果是否满足业务输出契约，不能只靠 `status=success` 或字段存在判断。

### 11.2 与 execution_check / verification 的区别

| 层 | 检查对象 | 目标 | 示例 |
| --- | --- | --- | --- |
| `execution_check_after` | 执行结果的最低可验证性 | 判断是否具备进入结果验证的基本条件 | result 非空、evidence_refs 存在 |
| `result_validate` | executor 输出的业务结构与语义 | 判断输出是否符合 capability output contract | CSV file_count、total_rows、timestamp stats |
| `verify` | 任务完成条件与物理证据 | 判断任务是否可标记 done | task_outcome + readback + verifier rules |

### 11.3 结果验证输入

`result_validate` 必须读取：

1. `CapabilityExecutionContract.output_schema`
2. 最新 `ActionAttempt`
3. 最新 `Observation`
4. executor result payload
5. task outcome draft
6. evidence refs

禁止只读取 executor 返回的 `status`。

### 11.4 结果验证规则类型

建议支持以下规则：

```json
[
  {"type": "json_schema", "schema_ref": "contract.output_schema"},
  {"type": "required_field", "path": "$.output_summary.file_count"},
  {"type": "required_field", "path": "$.output_summary.total_rows"},
  {"type": "number_min", "path": "$.output_summary.file_count", "min": 1},
  {"type": "number_min", "path": "$.output_summary.total_rows", "min": 1},
  {"type": "equals_observation", "result_path": "$.output_summary.file_count", "observation_path": "$.payload.file_count"},
  {"type": "non_empty_list", "path": "$.evidence_refs"}
]
```

### 11.5 `mongodb_csv_inspect` 结果验证示例

必须验证：

1. `output_summary.file_count >= 1`
2. `output_summary.total_rows >= 1`
3. `output_summary.total_invalid_timestamp_count` 是整数。
4. `output_summary.total_duplicate_timestamp_count` 是整数。
5. `output_summary.files` 是非空列表。
6. 每个 file entry 至少包含：
   - `path`
   - `filename`
   - `row_count`
   - `timestamp_column`
   - `format_valid`
   - `timestamp_accuracy_valid`
7. `evidence_refs` 非空。
8. observation 中读回的文件数与 output_summary 一致。

失败示例：

```json
{
  "status": "failed",
  "failure_type": "result_validation_failed",
  "failure_code": "CSV_INSPECT_TOTAL_ROWS_MISSING",
  "retryable": false,
  "field_results": [
    {
      "path": "$.output_summary.total_rows",
      "passed": false,
      "message": "Required numeric total_rows is missing"
    }
  ]
}
```

### 11.6 retry 关系

结果验证失败默认不可重试，除非 contract 明确标记为 readback eventual consistency。

可重试：

- observation 缺少刚写入的异步日志，但 executor result 有 invocation_id。
- 远端结果已成功，connector evidence store 暂未可读。

不可重试：

- output schema 错误。
- 必填字段缺失。
- executor 自报 success 但无 evidence。
- read-after-write 查询明确证明没有写入。

### 11.7 落库要求

结果验证必须写入：

```json
{
  "react_execution": {
    "result_validation": {
      "status": "passed",
      "validation_id": "...",
      "checked_schema_version": "...",
      "failure_code": null
    }
  }
}
```

失败时必须写 audit event：

```text
REACT_RESULT_VALIDATION_FAILED
```

通过时必须写：

```text
REACT_RESULT_VALIDATION_PASSED
```

### 11.8 规则/LLM/混合验证分层

验证策略必须由 `CapabilityExecutionContract.verification_strategy` 显式声明，不能由执行时代码按省 token、执行成本或临时便利自动替换。

```python
ValidationMode = Literal["rule", "llm", "hybrid"]
```

三类验证的边界如下：

| 验证类型 | 适用对象 | 可以裁定 | 不允许裁定 | 失败语义 |
| --- | --- | --- | --- | --- |
| 规则验证 | schema、字段、枚举、数值范围、权限、参数、readback、审计、幂等、状态机 | 客观结构是否满足 contract；物理证据是否存在；写入是否真的发生 | 复杂语义是否满足用户意图；自然语言质量；开放式诊断结论 | hard fail，可 retry 取决于 retry_policy |
| LLM 验证 | 目标对齐、语义一致性、自然语言输出质量、异常解释、证据解释、计划合理性 | 语义是否对齐；诊断是否充分；是否需要人工介入或补充参数 | 文件是否存在；DB 是否写入；HTTP 是否成功；connector 是否真实执行；物理成功状态 | fail-closed，LLM 缺失或解析失败就是验证失败 |
| 混合验证 | 同时包含客观证据和语义判断的任务 | 规则先证明物理事实，LLM 再判断语义；任一硬门禁失败都不得成功 | LLM 覆盖规则失败；规则替代 contract 要求的 LLM 判断 | 任一层失败即失败，除非 contract 明确允许 retry |

### 11.9 按 LangGraph 节点划分验证方式

| Graph 节点 | 默认验证方式 | 原因 | 示例 |
| --- | --- | --- | --- |
| `reason` | LLM 或混合 | 需要理解任务目标、约束、风险和下一步动作；规则只能校验输出结构 | 判断 CSV 检查任务应该读取哪些 contract 参数 |
| `resolve_parameters` | 规则为主，LLM 只做语义映射 | 参数存在性、类型、来源必须可追溯；自然语言参数映射可用 LLM 辅助 | 用户说“所有时间序列 CSV”时，LLM 可解释意图，但路径必须来自 workspace inventory/readback |
| `preflight` | 规则验证 | 执行前必须是客观门禁 | 文件存在、connector healthy、权限 token、idempotency_key |
| `execution_check_before` | 规则验证 | Act 前不能依赖 LLM 主观判断 | owner_ref、capability、parameter_hash、risk guard |
| `act` | 不做验证，只执行真实 executor | Act 是副作用动作，不允许 LLM 或规则伪造执行 | 调用 external connector `execute_capability` |
| `observe` | 规则验证 | Observe 必须读取真实输出和证据 | connector log、SQLite task outcome、artifact ref |
| `execution_check_after` | 规则验证 | 判断结果是否具备进入结果验证的最低证据 | result 非空、evidence_refs 存在、metadata 完整 |
| `result_validate` | 规则或混合 | 结构字段用规则；自然语言/开放语义输出用 LLM 辅助 | CSV 数量用规则；报告摘要是否覆盖异常原因可用 LLM |
| `verify` | capability contract 决定：规则/LLM/混合 | 最终完成判断必须跟 capability 类型绑定 | DB CRUD 用规则；研究报告质量用 LLM；Agent 工作流用混合 |
| `retry_decision` | 规则验证，LLM 只可诊断 | retry budget、failure class、attempt_count 必须确定 | transient timeout 可 retry；schema 缺字段不可 retry |
| `recover` | 规则为主，LLM 可生成诊断说明 | 状态迁移必须确定，诊断文本可由 LLM 辅助 | suspend_for_parameter_gap、resource_gap 说明 |
| `complete` | 规则验证 | 完成状态必须由最终 verification result 和 readback 决定 | task status、outcome、audit event 都已落库 |

### 11.10 必须使用规则验证的场景

以下场景必须使用规则验证，禁止用 LLM 替代：

1. `parameter_schema`、`output_schema`、required field、enum、number range。
2. `owner_ref`、`executor_type`、capability 是否匹配 registry。
3. external connector health、version、capability contract 是否存在。
4. 文件、目录、DB collection、HTTP endpoint、artifact ref 是否真实存在。
5. mutation 的 read-after-write / verify-after-write / delete-after-delete。
6. task status、outcome、metadata、audit event 是否落库。
7. retry budget、attempt_count、backoff、idempotency_key。
8. permission、scope、risk_level、trace_id、session_id、task_id。
9. `evidence_refs` 非空、可读、与 observation 一致。
10. 任何可以通过 JSON Schema、Pydantic、SQL/HTTP readback、日志查询、哈希、状态机断言证明的事实。

规则验证失败时，LLM 不得把失败解释为成功；最多只能生成诊断建议。

### 11.11 必须使用 LLM 验证的场景

以下场景如果被 contract 标记为验证目标，必须使用 LLM，禁止为了省 token 改成规则链：

1. 任务目标与执行计划是否语义对齐。
2. 执行结果是否回答了用户的自然语言目标。
3. 报告、总结、诊断、分类、风险说明是否语义充分。
4. 多证据之间是否存在语义冲突、遗漏或目标漂移。
5. Agent 产出的自然语言交付物是否满足角色、边界、禁止事项。
6. 失败原因归类存在多种可能，需要结合上下文判断主因。
7. Q9 external/internal blueprint 的 objective alignment、fake execution party、zero-trust verification method 这类语义合规审查。

LLM 验证必须满足：

1. 使用真实激活态 `ModelProvider`，不能用规则 provider、静态样本或 fallback。
2. 输入必须包含完整 allowed context、contract、evidence summary 和禁止事项。
3. 输出必须是结构化 verdict：`passed`、`failure_code`、`reasoning_summary`、`required_followup`。
4. LLM 调用失败、JSON 解析失败、provider 不可用时 fail-closed。
5. LLM 只能 veto、diagnose、request_followup，不能制造物理证据。

### 11.12 必须使用混合验证的场景

混合验证用于“客观事实 + 语义判断”同时存在的任务。执行顺序必须固定：

```text
rule_gate -> llm_semantic_judge -> rule_readback_finalizer
```

必须混合验证的典型场景：

| 场景 | 规则层 | LLM 层 | 最终裁定 |
| --- | --- | --- | --- |
| external connector 生成业务报告 | 验证 invocation、artifact、output_schema、evidence_refs | 判断报告是否覆盖任务目标和异常原因 | 任一失败均失败 |
| Agent 执行研究/分析任务 | 验证 agent run、日志、artifact、状态落库 | 判断分析是否符合目标、限制和证据 | LLM 可 veto，不能覆盖规则失败 |
| Q9 子任务拆分合规 | 验证 child task 字段、executor、capability、verification contract | 判断 objective alignment、granularity、fake party | 规则和 LLM 都必须通过 |
| CRUD/导入类任务带业务摘要 | 验证 DB 实际变化和 row count | 判断摘要是否真实描述变化范围 | DB readback 是硬门禁 |
| 异常恢复报告 | 验证状态迁移、audit、retry budget | 判断 RCA 是否和证据一致 | 状态规则失败直接失败 |

混合验证的禁止行为：

1. `rule_gate` 失败后继续调用 LLM 让其“解释为通过”。
2. LLM 通过后跳过 `rule_readback_finalizer`。
3. LLM 生成缺失的 `evidence_refs`、row count、artifact path。
4. 把 LLM verdict 存成普通 warning，然后仍标记任务 done。
5. contract 要求 LLM 时，因为 token 成本改走纯规则。

### 11.13 capability 级验证策略示例

#### `mongodb_csv_inspect`

```json
{
  "verification_strategy": "rule",
  "rule_validators": [
    "schema_required_fields",
    "csv_path_readback",
    "output_summary_numeric_bounds",
    "observation_consistency",
    "evidence_refs_readback"
  ],
  "llm_validation_policy": null
}
```

原因：CSV 文件数、行数、timestamp 字段、格式错误数量都能通过结构化输出和 readback 客观验证。

#### `q9_subtask_split_compliance`

```json
{
  "verification_strategy": "hybrid",
  "rule_validators": [
    "child_task_schema",
    "executor_owner_ref_present",
    "capability_present",
    "verification_contract_present",
    "no_owner_only_external_task"
  ],
  "llm_validators": [
    "objective_alignment",
    "granularity_check",
    "zero_trust_verification_method"
  ],
  "failure_policy": "any_failed_blocks_child_creation"
}
```

原因：owner-only、capability 缺失、字段缺失可以规则判断；objective alignment 和 granularity 需要 LLM 语义判断。两者都不能省略。

#### `agent_research_summary`

```json
{
  "verification_strategy": "hybrid",
  "rule_validators": [
    "agent_run_status_readback",
    "artifact_exists",
    "audit_event_exists",
    "output_schema_valid"
  ],
  "llm_validators": [
    "answers_user_objective",
    "evidence_supported_claims",
    "prohibition_compliance"
  ],
  "failure_policy": "llm_or_rule_failure_blocks_completion"
}
```

原因：agent 是否运行、artifact 是否存在是规则；研究内容是否回答目标必须由 LLM 语义验证。

### 11.14 验证结果落库字段

每次验证必须记录策略和执行者：

```json
{
  "react_execution": {
    "validation_strategy": {
      "mode": "hybrid",
      "rule_validation": {
        "status": "passed",
        "validator_ids": ["schema_required_fields", "evidence_refs_readback"]
      },
      "llm_validation": {
        "status": "passed",
        "provider": "ollama",
        "model": "qwen3:32b",
        "trace_id": "llm-validation-...",
        "verdict_id": "..."
      },
      "final_decision": "passed"
    }
  }
}
```

`llm_validation` 被 contract 要求但未执行时，最终结果必须是 `failed`，failure code 使用 `LLM_VALIDATION_REQUIRED_BUT_NOT_EXECUTED`。

## 12. 执行方分型：CLI / Agent / MCP / 外接 / 内部插件

执行模块不能把所有执行方合并成一个“通用 executor”。统一的是 LangGraph 状态机，不统一的是执行入口、参数形态、证据来源、验证方式和失败恢复。

### 12.1 分型总原则

1. `action_dispatcher` 只做路由和适配，不承载具体业务逻辑。
2. 每类执行方必须通过各自 owner module 的 `service.py` 或公开 service boundary 执行。
3. 每类执行方必须有独立 `execution_profile_id`，由 `executor_profiles.py` 解析。
4. 每类执行方必须声明自己的 `observation_sources`，不能默认相信 executor 自报成功。
5. 每类执行方必须声明自己的 `verification_strategy`，不能统一套用 rule、LLM 或 hybrid。
6. 每类执行方的参数必须来自 task metadata、capability contract 或 authorized runtime context，禁止 LLM 现场编造路径、命令、filter、credential 或资源 ID。

### 12.2 执行方 profile 总表

| 执行方 | 正式执行入口 | 参数载体 | 默认验证策略 | 主要证据 | 不可接受的成功条件 |
| --- | --- | --- | --- | --- | --- |
| CLI | CLI 工具模块 `service.py` 的 execute 接口 | `cli_arguments`、`stdin_input`、`working_directory`、env allowlist | 规则或混合 | exit_code、stdout/stderr、artifact、audit、文件 readback | 只看到进程启动或 stdout 包含 success |
| Agent | Agent 模块 `service.py` / coordination service 的 task dispatch | `agent_task_payload`、capability、asset scope、auth scope | 混合，语义任务可 LLM | agent run id、artifact、agent log、task outcome、audit | agent 自报 done 但无 artifact/readback |
| MCP | MCP service 的 tool/resource 调用接口 | `mcp_arguments`、tool name、resource uri、server identity | 规则或混合 | tool result、resource readback、schema validation、audit | MCP health 成功但业务 tool 未调用 |
| 外接 connector | external connector service 的 `execute_capability` | `external_connector_arguments`、capability、trace/idempotency | 规则或混合 | invocation_id、output_summary、evidence_refs、connector log | `test_call` / ping / health_check 当业务成功 |
| 内部插件 | functional plugin registry 对应插件 service | plugin capability payload、session/task context | 规则、LLM 或混合，由插件 capability 决定 | plugin state readback、DB snapshot、audit、LLM trace | 插件函数返回 truthy 但未落库/无审计 |

### 12.3 CLI 执行与验证

CLI 适合执行本地命令、脚本、工具查询和文件处理任务。CLI 执行必须限制在注册过的 CLI tool capability 内。

执行要求：

1. 执行入口必须是 CLI 模块 service，不允许任务模块直接 `subprocess.run`。
2. `cli_arguments` 必须按 list 传递，不允许 shell 拼接字符串。
3. `working_directory` 必须来自 contract 或 task metadata，并通过路径白名单/工作区边界检查。
4. stdin、env、timeout 必须显式声明。
5. 写操作必须带 trace marker 或 idempotency key。

验证要求：

| 验证层 | 策略 | 必查项 |
| --- | --- | --- |
| preflight | 规则 | CLI 注册存在、binary path 可执行、版本/health 可读、cwd 可读、参数 schema 通过 |
| result_validate | 规则 | exit_code、stdout/stderr schema、artifact path、output_summary |
| verify | 规则或混合 | 文件/DB/readback 是否匹配任务目标；自然语言报告类输出再加 LLM 语义验证 |

CLI 禁止：

1. 只因 exit code 为 0 就标记业务成功。
2. 用 stdout 文本 `success` 替代 artifact/readback。
3. 让 LLM 生成未授权 shell 命令后直接执行。
4. 把 CLI 注册测试、`--version`、health check 当成业务任务执行。

### 12.4 Agent 执行与验证

Agent 适合执行需要多步推理、工具使用、外部服务协调或自然语言交付物的任务。

执行要求：

1. 执行入口必须是 Agent 模块 service 或 coordination service。
2. `agent_task_payload` 必须包含目标、限制、允许工具、证据要求和 completion contract。
3. Agent run 必须有 `run_id`、`task_id`、`trace_id`。
4. Agent 产生的 artifact 必须有可读引用，不能只写在内存对话里。

验证要求：

| 验证层 | 策略 | 必查项 |
| --- | --- | --- |
| preflight | 规则 | agent registered、capability active、auth scope、tool scope、run quota |
| observe | 规则 | run status、artifact refs、agent log、task outcome、audit event |
| result_validate | 混合 | artifact schema 用规则；自然语言交付物完整性用 LLM |
| verify | 混合 | 规则证明 run 和 artifact 真实存在；LLM 判断是否满足目标、限制和证据要求 |

Agent 禁止：

1. Agent 自报 `done` 后没有 artifact/readback 仍完成任务。
2. API 返回 200 就认为 Agent 工作完成。
3. Agent LLM 失败后写入 fallback 总结。
4. 用任务中心的 LLM verifier 替代 Agent 自身的真实执行。

### 12.5 MCP 执行与验证

MCP 适合调用已注册 server 的 tool/resource/prompt 能力。MCP 执行必须区分 server health 和具体 tool 执行。

执行要求：

1. 执行入口必须是 MCP 模块 service。
2. 必须指定 `server_id`、`tool_name` 或 `resource_uri`。
3. `mcp_arguments` 必须通过 tool schema 校验。
4. resource 读取类任务必须记录 resource URI 和 readback hash。

验证要求：

| 验证层 | 策略 | 必查项 |
| --- | --- | --- |
| preflight | 规则 | server active、tool exists、schema match、权限范围 |
| observe | 规则 | tool result、resource content、schema drift check、audit |
| result_validate | 规则或混合 | 结构化 tool result 用规则；自然语言 tool 输出可加 LLM |
| verify | 规则或混合 | resource/tool 真实返回与任务目标一致 |

MCP 禁止：

1. MCP server health 通过就认定业务 capability 可执行。
2. tool schema 漂移时继续按旧参数执行。
3. 缺 resource readback 时伪造 resource 内容。
4. 把 prompt/template 调用结果当成 tool 副作用完成证据。

### 12.6 外接 connector 执行与验证

外接 connector 适合执行外部系统、数据库、第三方 API、专用服务能力。外接 connector 必须 capability-first，禁止 owner-only。

执行要求：

1. 正式入口必须是 `execute_capability`。
2. 必须同时具备 `owner_ref`、`connector_id`、`capability`、`arguments`。
3. mutation 必须带 `trace_id`、`task_id`、`session_id`、`idempotency_key`。
4. read-only 和 mutation capability 必须使用不同 risk policy。

验证要求：

| 验证层 | 策略 | 必查项 |
| --- | --- | --- |
| preflight | 规则 | connector active、capability exists、argument schema、permission、risk guard |
| observe | 规则 | invocation_id、connector runtime log、output_summary、evidence_refs |
| result_validate | 规则或混合 | 结构化业务字段、row count、artifact refs；业务报告类再加 LLM |
| verify | 规则或混合 | readback、connector log、task outcome、capability-specific verifier |

外接 connector 禁止：

1. `test_call`、ping、health_check 作为业务执行。
2. 只有 connector owner，没有具体 capability。
3. connector 自报 success 但无 `output_summary` 或 `evidence_refs`。
4. connector 缺失时自动换一个不等价 executor 继续执行。

### 12.7 内部插件执行与验证

内部插件适合执行 Zentex 内部功能能力，例如九问模块、记忆/学习模块、任务分析模块、功能插件 registry 中声明的内部 capability。

执行要求：

1. 执行入口必须来自 functional plugin registry 声明的 service boundary。
2. `executor_type` 使用 `internal_plugin`，不得和 external connector 混用。
3. 插件 capability 必须声明输入 schema、输出 schema、状态落库位置和审计事件。
4. 认知类内部插件若 contract 要求 LLM，必须走真实 ModelProvider。

验证要求：

| 验证层 | 策略 | 必查项 |
| --- | --- | --- |
| preflight | 规则 | plugin active、capability exists、session/task context、schema、权限 |
| observe | 规则 | plugin state readback、SQLite snapshot、LLM trace、audit event |
| result_validate | 规则或混合 | 输出结构用规则；认知/目标/总结类输出用 LLM |
| verify | rule / llm / hybrid，由 capability contract 决定 | 数据落库、公共投影、LLM trace、业务语义 |

内部插件禁止：

1. 插件函数返回成功但没有落库/readback。
2. 认知类 capability 用规则链冒充 LLM。
3. 从多个 fallback snapshot 拼接输出，伪装为单一真实来源。
4. 绕过插件自己的 service.py 直接调用内部私有函数完成任务。

### 12.8 执行方分型失败码

| failure_code | 适用执行方 | 含义 |
| --- | --- | --- |
| `EXECUTOR_PROFILE_MISSING` | all | task 缺少执行方 profile |
| `EXECUTOR_PROFILE_TYPE_MISMATCH` | all | profile 声明的执行方类型与 task executor_type 不一致 |
| `EXECUTOR_SERVICE_BOUNDARY_MISSING` | all | 找不到对应 owner module service |
| `CLI_COMMAND_NOT_REGISTERED` | CLI | CLI 未注册或 capability 不存在 |
| `CLI_ARTIFACT_READBACK_FAILED` | CLI | CLI 输出 artifact 不可读 |
| `AGENT_RUN_READBACK_FAILED` | Agent | agent run / artifact / log 不可读 |
| `MCP_TOOL_SCHEMA_DRIFT` | MCP | MCP tool schema 与 contract 不一致 |
| `MCP_RESOURCE_READBACK_FAILED` | MCP | MCP resource 未真实读回 |
| `CONNECTOR_CAPABILITY_MISSING` | 外接 connector | connector owner 存在但 capability 缺失 |
| `CONNECTOR_EVIDENCE_MISSING` | 外接 connector | 缺 output_summary/evidence_refs/log |
| `INTERNAL_PLUGIN_STATE_READBACK_FAILED` | 内部插件 | 插件状态或 SQLite snapshot 未读回 |
| `INTERNAL_PLUGIN_LLM_REQUIRED_BUT_NOT_EXECUTED` | 内部插件 | 认知类插件要求 LLM 但未执行 |

### 12.9 分型落库要求

每次执行必须在 metadata 中记录执行方 profile：

```json
{
  "react_execution": {
    "executor_profile": {
      "executor_type": "external_connector",
      "execution_profile_id": "external_connector_capability_execution_v1",
      "service_boundary": "external_connector.service.execute_capability",
      "observation_sources": ["executor_result", "task_outcome", "audit_log"],
      "verification_strategy": "rule"
    }
  }
}
```

缺少 `executor_profile` 时，任务不得进入 Act。

## 13. ReAct 主循环旧伪代码保留说明

以下伪代码用于表达 ReAct 语义；实际实现必须以 LangGraph 节点和条件边为准。

```python
async def execute_task_with_react_without_langgraph(task_id: str) -> ExecutionRunResult:
    context = await context_loader.load(task_id)
    run = await run_store.start(context)

    for step_index in range(max_react_steps):
        plan = await reasoner.plan_next_step(context, run)

        if plan.next_action == "resolve_parameters":
            resolution = await parameter_resolver.resolve(context, plan)
            if resolution.status == "parameter_gap":
                return await recovery.suspend_for_parameter_gap(context, resolution)
            if resolution.status == "invalid_parameters":
                return await recovery.fail_invalid_parameters(context, resolution)
            context.arguments = resolution.arguments

        elif plan.next_action == "preflight":
            preflight = await preflight_runner.run(context)
            if not preflight.passed:
                return await recovery.handle_preflight_failure(context, preflight)

        elif plan.next_action == "act":
            attempt = await action_dispatcher.dispatch(context)
            run.add_attempt(attempt)

        elif plan.next_action == "observe":
            observation = await observer.observe(context, attempt)
            run.add_observation(observation)

        elif plan.next_action == "verify":
            verification = await verifier.verify(context, observation)
            if verification.passed:
                return await completion.complete(context, run, verification)
            return await recovery.handle_verification_failure(context, verification)

        elif plan.next_action == "recover":
            return await recovery.recover(context, run)

        elif plan.next_action == "complete":
            return await completion.complete(context, run)

    return await recovery.fail_step_limit_exceeded(context, run)
```

## 14. 模块职责

### 14.0 代码组织硬约束

本实现禁止把复杂执行系统堆在一个文件里。每个文件只能拥有一个清晰职责，跨职责协作必须通过显式 DTO、contract、profile、result 对象传递。

禁止形态：

1. `langgraph_react_executor.py` 同时包含 graph 定义、五类 executor 分支、参数解析、result validation、readback verifier 和 DB 落库。
2. `worker.py` 继续保留 CLI/MCP/connector/agent/plugin 的业务执行分支，同时又调用 ReAct executor。
3. `action_dispatcher.py` 内部写大量 capability 专用业务判断。
4. `service.py` 中新增复杂参数解析、业务执行步骤、结果验证、readback 或 retry/recovery 逻辑。
5. 为了减少文件数，把规则验证、LLM 验证、混合验证合并成一个不可审计的大函数。

必须形态：

1. graph 编排归 `langgraph_react_executor.py`、`graph_edges.py` 和 `graph_nodes/*_node.py`。
2. contract/profile 归 `capability_contract.py`、`executor_profiles.py`。
3. 参数解析归 `parameter_resolver.py`。
4. 执行前检查归 `preflight.py`、`execution_check.py`。
5. 五类执行方调用归 `dispatch/*_adapter.py` 或等价独立模块。
6. 结果结构验证归 `result_validator.py`。
7. readback 与 capability 验证归 `observation.py`、`capability_verifier.py`。
8. 规则/LLM/混合裁决归 `validation_strategy.py`。
9. 重试恢复归 `retry_policy.py`、`recovery.py`。
10. graph run 和 node input/output 落库归 `persistence.py` 或 `persistence/*`。

`service.py` 允许做的事情：

1. 暴露稳定 public service API。
2. 校验调用者身份、权限和最外层请求 DTO。
3. 打开事务、注入 repository/manager/runtime 依赖。
4. 调用 application/domain/execution 模块。
5. 统一转换 service response 和审计 envelope。

`service.py` 禁止做的事情：

1. 不直接写 LangGraph 节点。
2. 不直接写 ReAct loop。
3. 不直接拼复杂 executor 参数。
4. 不直接实现 capability result validation。
5. 不直接实现 readback verifier。
6. 不直接调用 LLM 做业务裁决。
7. 不把多个 executor 的业务分支写成一个大 `if/elif`。
8. 不吞异常并返回成功。

验收时如果发现 `service.py` 承载上述业务逻辑，即使测试通过，也判定为架构不合格。

### 14.1 `langgraph_react_executor.py`

职责：

- 构建并调用 LangGraph execution graph。
- 暴露 `execute(task_id: str)` 给 worker。
- 保证 max steps、timeout、attempt count、状态落库。
- 只调用模块接口，不直接执行 CLI/MCP/connector/agent。
- 每阶段写审计事件。

禁止：

- 吞掉 stage 异常后继续成功。
- LLM 失败后用规则计划冒充 Reason 成功。
- Act 阶段伪造 executor result。

### 14.2 `graph_state.py`

职责：

- 定义 `ExecutionGraphState`。
- 定义 state merge/serialization 策略。
- 保证 checkpoint/resume 时 state 可 JSON 化。

### 14.3 `graph_nodes/*_node.py`

职责：

- 按节点功能提供 LangGraph 节点函数。
- 每个节点文件只处理一个阶段或一个成对阶段，例如 `execution_check_before/after`。
- 节点失败必须返回结构化 failure 或抛出结构化异常，不能吞错。
- 节点文件只能读取和写入 `ExecutionGraphState` 中本节点负责的字段。
- 节点文件必须把复杂业务委托给对应模块，例如 `parameter_resolver`、`preflight`、`action_dispatcher`、`observation`、`result_validator`、`capability_verifier`、`retry_policy`、`recovery`。

节点文件清单：

| 文件 | 导出函数 | 状态输入 | 状态输出 |
| --- | --- | --- | --- |
| `graph_nodes/load_context_node.py` | `load_context_node` | `task_id`, `trace_id` | `context`, `contract` |
| `graph_nodes/reason_node.py` | `reason_node` | `context`, `contract`, `retry_state` | `plan`, `phase` |
| `graph_nodes/resolve_parameters_node.py` | `resolve_parameters_node` | `context`, `contract`, `plan` | `arguments`, `parameter_resolution`, `failure` |
| `graph_nodes/preflight_node.py` | `preflight_node` | `context`, `contract`, `arguments` | `preflight_result`, `failure` |
| `graph_nodes/execution_check_node.py` | `execution_check_before_node`, `execution_check_after_node` | `preflight_result`, `current_attempt`, `observations` | `execution_check_result`, `failure` |
| `graph_nodes/act_node.py` | `act_node` | `context`, `contract`, `arguments` | `current_attempt`, `failure` |
| `graph_nodes/observe_node.py` | `observe_node` | `current_attempt`, `contract` | `observations`, `failure` |
| `graph_nodes/result_validate_node.py` | `result_validate_node` | `current_attempt`, `observations`, `contract` | `result_validation`, `failure` |
| `graph_nodes/verify_node.py` | `verify_node` | `observations`, `result_validation`, `contract` | `verification_result`, `failure` |
| `graph_nodes/retry_decision_node.py` | `retry_decision_node` | `failure`, `retry_state`, `contract` | `retry_state`, `phase` |
| `graph_nodes/recover_node.py` | `recover_node` | `failure`, `retry_state`, `context` | terminal `suspended` / `failed` result |
| `graph_nodes/complete_node.py` | `complete_node` | `verification_result`, `observations`, `context` | terminal completion result |

禁止：

- 新建 `graph_nodes.py` 汇总实现所有节点。
- 在 `reason_node.py` 里写参数解析或 dispatch。
- 在 `act_node.py` 里写五类 executor 的私有业务逻辑。
- 在 `complete_node.py` 里绕过 `verification_result`。
- 节点之间通过全局变量、临时文件或隐式单例传递执行状态。

### 14.4 `graph_edges.py`

职责：

- 定义所有条件路由。
- 根据 `failure_type/retryable/decision` 路由到 retry/recover/complete。
- 禁止默认路由到 complete。

### 14.5 `execution_context.py`

职责：

- 从 task row 构造 ExecutionContext。
- 校验 task status、owner_ref、executor_type、capability、trace_id。
- 读取 parent/q9/session 上下文，但不从自然语言猜参数。

失败行为：

- 缺 owner_ref：`EXECUTOR_OWNER_MISSING`
- 缺 capability：`CAPABILITY_MISSING`
- 缺 trace_id：允许生成执行 trace，但必须写入 metadata 并审计。

### 14.6 `capability_contract.py`

职责：

- 从真实 registry 解析 capability contract。
- external connector 从 connector manifest/capability profile 读取。
- CLI/MCP 从 usage profile 读取。
- agent 从 agent asset scope/auth/capabilities 读取。
- 内部插件从 functional plugin registry 读取。

缺 contract 时：

- read-only health check 可以使用最小 contract。
- 业务 capability 缺 contract 必须 `contract_gap`，不能继续执行。

### 14.7 `executor_profiles.py`

职责：

- 解析 CLI、Agent、MCP、外接 connector、内部插件的 `execution_profile_id`。
- 提供每类执行方的 service boundary、参数字段、preflight checklist、observation sources、默认验证策略。
- 校验 task 的 `executor_type` 与 profile 是否一致。
- 为 `action_dispatcher`、`observation`、`validation_strategy` 提供同一份 profile。

禁止：

- 把 health/test-call profile 当成业务 execution profile。
- owner-only profile 缺 capability 时继续执行。
- 多类执行方共用同一个无差别 profile。

### 14.8 `parameter_resolver.py`

职责：

- 合并 task metadata、parent metadata、contract inputs、runtime context。
- 按 parameter_schema 校验类型、必填字段、安全约束。
- 记录每个参数来源。
- 输出 `resolved` / `parameter_gap` / `invalid_parameters`。

parameter gap 处理：

```json
{
  "status": "parameter_gap",
  "missing_parameters": ["csv_paths"],
  "required_by": "mongodb_csv_inspect",
  "acceptable_sources": ["task.metadata.external_connector_arguments.csv_paths", "parent.metadata.q9_external_connector_arguments.mongodb_csv_inspect.csv_paths"],
  "recovery_conditions": ["Provide at least one existing readable CSV path"]
}
```

### 14.9 `preflight.py`

职责：

- executor health 检查。
- capability existence 检查。
- 参数对应资源检查，例如文件存在、目录可读、DB filter 有 trace marker。
- 幂等冲突检查。
- 风险策略检查。

preflight 必须产生结构化结果：

```json
{
  "passed": false,
  "failure_type": "parameter_gap",
  "failure_code": "CSV_PATHS_MISSING",
  "evidence": {...}
}
```

### 14.10 `execution_check.py`

职责：

- 实现 `check_before_act(state)`。
- 实现 `check_after_observe(state)`。
- 检查结果必须可审计、可 readback。
- 不允许修改 action result 让 verification 通过。

### 14.11 `action_dispatcher.py`

职责：

- 根据 executor_type 调用真实 service。
- CLI 调 `cli_service.execute_task`。
- MCP 调 `mcp_service.execute_task`。
- external connector 调正式 `execute_capability`。
- agent 调 `agent_service.dispatch_task`。
- internal plugin 调 functional plugin registry 返回的 service boundary。
- 仅做请求适配和路由，不实现 executor 的业务语义。

实现拆分：

- `dispatch/cli_adapter.py`：CLI ActionRequest -> CLI service request。
- `dispatch/agent_adapter.py`：Agent ActionRequest -> Agent dispatch request。
- `dispatch/mcp_adapter.py`：MCP ActionRequest -> MCP tool execution request。
- `dispatch/external_connector_adapter.py`：connector ActionRequest -> `execute_capability` request。
- `dispatch/internal_plugin_adapter.py`：internal plugin ActionRequest -> functional plugin service request。

禁止：

- 在 `action_dispatcher.py` 中写 capability 专用业务逻辑。
- 在 adapter 中绕过各自模块的 service boundary 调私有函数。
- 在 adapter 中做 result validation 或 readback verifier。
- 用一个 `if/elif` 文件承载五类执行方所有参数转换细节。

过渡期 external connector：

- 如果 service 尚未提供 `execute_capability`，可临时适配现有 `test_call`。
- 适配层必须命名为 `LegacyConnectorTestCallAdapter`。
- 适配结果必须标记 `execution_api=legacy_test_call_adapter`。
- 不允许把适配层文档写成最终形态。

### 14.12 `observation.py`

职责：

- 从 executor result、task outcome、文件系统、SQLite、connector evidence refs 中读回证据。
- 生成 Observation。
- 不相信 executor 自报成功，必须至少有一个 objective evidence source。

支持 observation source：

- `executor_result`
- `task_outcome`
- `file_readback`
- `db_readback`
- `http_readback`
- `audit_log`
- `plugin_state_readback`
- `agent_artifact_readback`
- `mcp_resource_readback`

### 14.13 `result_validator.py`

职责：

- 加载 capability output schema。
- 验证 executor result 的业务字段、类型、范围和枚举。
- 对比 Observation 与 output_summary 的一致性。
- 输出 `ResultValidationResult`。
- 失败时给出明确 `failure_code`。

禁止：

- 修改 executor result。
- 用默认字段补齐缺失结果。
- 把 result validation failed 降级为 verification warning。

### 14.14 `capability_verifier.py`

职责：

- 加载 CapabilityExecutionContract.verification_rules。
- 对 Observation 和 task outcome 做字段级、语义级、物理证据级验证。
- 输出 VerificationResult。

示例规则：

```json
[
  {"type": "required_field", "field": "actual_outcome.status"},
  {"type": "enum_value", "field": "actual_outcome.status", "allowed_values": ["success"]},
  {"type": "json_path_min", "path": "$.output_summary.file_count", "min": 1},
  {"type": "json_path_min", "path": "$.output_summary.total_rows", "min": 1}
]
```

### 14.15 `validation_strategy.py`

职责：

- 读取 `CapabilityExecutionContract.verification_strategy`。
- 决定当前 capability 使用规则验证、LLM 验证或混合验证。
- 校验 contract 要求的 LLM 验证是否真实执行。
- 汇总 rule verdict、LLM verdict 和 final decision。
- 写入 validation strategy audit metadata。

禁止：

- 因 token 成本把 `llm` 或 `hybrid` 改为 `rule`。
- 用 LLM verdict 覆盖规则 readback 失败。
- 用规则结果冒充 LLM 语义验证。
- 在 LLM 验证缺失时继续返回 success。

### 14.16 `retry_policy.py`

职责：

- 判断 failure 是否 retryable。
- 计算 backoff。
- 控制 max attempts。
- 记录 retry decision。

禁止：

- 对 non-retryable failure 重试。
- 超过 max attempts 后继续循环。
- retry 时丢失原始 error。

### 14.17 `recovery.py`

职责：

- 分类失败。
- 决定 retry、suspend、fail、rollback、compensate。
- 写入 G9 resource/parameter negotiation。
- 对写操作执行 rollback 或 compensation。

失败分类：

| 分类 | 处理 |
| --- | --- |
| `parameter_gap` | suspend，等待参数补充 |
| `resource_gap` | suspend，等待 executor/权限/连接器补充 |
| `permission_gap` | suspend 或 fail，需要人工授权 |
| `preflight_failed` | 通常 suspend，除非不可恢复 |
| `execution_failed_retryable` | retry |
| `execution_failed_non_retryable` | fail |
| `observation_failed` | retry observation 或 fail |
| `verification_failed` | fail 或 retry，取决于 contract |
| `rollback_failed` | fail + high priority audit |

## 15. 参数处理规范

### 15.1 参数字段约定

| executor | metadata 字段 | 类型 |
| --- | --- | --- |
| CLI | `cli_arguments` | list |
| CLI | `stdin_input` / `cli_stdin_input` | string |
| CLI | `working_directory` / `cli_working_directory` | string |
| MCP | `mcp_arguments` | dict |
| MCP | `mcp_server_id` / `mcp_tool_name` / `mcp_resource_uri` | string |
| External connector | `external_connector_arguments` | dict |
| External connector | `connector_arguments` | dict |
| Agent | `agent_task_payload` | dict |
| Agent | `agent_capability` / `agent_asset_scope` / `agent_auth_scope` | dict/string |
| Internal plugin | `internal_plugin_arguments` | dict |
| Internal plugin | `internal_plugin_id` / `internal_plugin_capability` | string |

### 15.2 Q9 external 参数下发

Q9 父任务 metadata 应使用：

```json
{
  "q9_external_connector_arguments": {
    "mongodb_csv_inspect": {
      "csv_paths": ["/absolute/path/time_series-AAPL-1day.csv"],
      "timestamp_column": "datetime",
      "session_id": "zentex-default-session",
      "trace_id": "zentex-default-session:q9:q9-external"
    }
  }
}
```

拆分阶段按 capability 下发到 child metadata：

```json
{
  "external_connector_id": "task-mongodb-csv-88de354c",
  "external_connector_capability": "mongodb_csv_inspect",
  "external_connector_arguments": {
    "csv_paths": ["..."],
    "timestamp_column": "datetime"
  }
}
```

### 15.3 禁止行为

1. 缺 `csv_paths` 时扫描整个磁盘猜路径。
2. 缺 MongoDB filter 时用 `{}` 作为默认 filter。
3. 缺 trace marker 时执行写操作。
4. 缺权限 token 时降级为只读并返回成功。
5. LLM 生成文件路径、DB filter、credential ref 后直接执行。

## 16. External Connector 正式执行接口

### 16.1 新接口

在 external connector service 中新增正式业务接口：

```python
def execute_capability(
    connector_id: str,
    request: ConnectorExecutionRequest,
) -> ConnectorExecutionResult:
    ...
```

请求：

```python
class ConnectorExecutionRequest(BaseModel):
    capability: str
    arguments: dict[str, Any]
    trace_id: str
    task_id: str
    execution_mode: Literal["dry_run", "execute"]
    idempotency_key: str
```

结果：

```python
class ConnectorExecutionResult(BaseModel):
    invocation_id: str
    connector_id: str
    capability: str
    status: Literal["success", "failed", "blocked"]
    output_summary: dict[str, Any]
    evidence_refs: list[str]
    physical_artifacts: list[dict[str, Any]]
    error_code: str | None = None
    error_message: str | None = None
```

### 16.2 `test_call` 边界

`test_call` 只允许用于：

- connector health probe
- smoke test
- registry onboarding validation

业务任务不得长期使用 `test_call` 作为正式执行接口。

## 17. 审计与落库

### 17.1 必写事件

每个 ReAct run 至少写入：

- `REACT_EXECUTION_STARTED`
- `REACT_EXECUTOR_PROFILE_RESOLVED` 或 `REACT_EXECUTOR_PROFILE_FAILED`
- `REACT_REASON_COMPLETED`
- `REACT_PARAMETERS_RESOLVED` 或 `REACT_PARAMETER_GAP`
- `REACT_PREFLIGHT_PASSED` 或 `REACT_PREFLIGHT_FAILED`
- `REACT_ACTION_STARTED`
- `REACT_ACTION_FINISHED`
- `REACT_OBSERVATION_RECORDED`
- `REACT_RESULT_VALIDATION_PASSED` 或 `REACT_RESULT_VALIDATION_FAILED`
- `REACT_RULE_VALIDATION_PASSED` 或 `REACT_RULE_VALIDATION_FAILED`
- `REACT_LLM_VALIDATION_PASSED` 或 `REACT_LLM_VALIDATION_FAILED` 或 `REACT_LLM_VALIDATION_SKIPPED_NOT_REQUIRED`
- `REACT_HYBRID_VALIDATION_PASSED` 或 `REACT_HYBRID_VALIDATION_FAILED`
- `REACT_VERIFICATION_PASSED` 或 `REACT_VERIFICATION_FAILED`
- `REACT_EXECUTION_COMPLETED` 或 `REACT_EXECUTION_SUSPENDED` 或 `REACT_EXECUTION_FAILED`

### 17.2 metadata 写入

任务 metadata 应记录：

```json
{
  "react_execution": {
    "enabled": true,
    "run_id": "...",
    "phase": "verifying",
    "attempt_count": 1,
    "last_attempt_id": "...",
    "last_observation_id": "...",
    "parameter_sources": {
      "csv_paths": "parent.metadata.q9_external_connector_arguments.mongodb_csv_inspect.csv_paths"
    },
    "failure_classification": null
  }
}
```

### 17.3 outcome 写入

完成时 task outcome 必须包含：

- `actual_outcome.status`
- `actual_outcome.output_summary`
- `actual_outcome.evidence_refs`
- `external_execution.executor_type`
- `external_execution.owner_ref`
- `verification_result`

### 17.4 React Flow 查看数据契约

前端工作流查看必须读取后端真实执行图数据，不能由前端根据 task status 猜节点。后端必须在 task metadata 或专用执行表中提供 `react_execution.graph_runs`。

最小结构：

```json
{
  "react_execution": {
    "enabled": true,
    "run_id": "react-run-...",
    "graph_runtime": "langgraph",
    "graph_runs": [
      {
        "node_id": "resolve_parameters",
        "node_label": "Resolve Parameters",
        "node_type": "resolver",
        "status": "passed",
        "started_at": "2026-05-14T00:00:00Z",
        "finished_at": "2026-05-14T00:00:01Z",
        "input": {
          "task_id": "...",
          "executor_type": "external_connector",
          "capability": "mongodb_csv_inspect"
        },
        "output": {
          "resolved_arguments": {
            "csv_paths": ["/absolute/path/file.csv"]
          },
          "parameter_sources": {
            "csv_paths": "parent.metadata.q9_external_connector_arguments.mongodb_csv_inspect.csv_paths"
          }
        },
        "error": null,
        "evidence_refs": []
      }
    ],
    "graph_edges": [
      {"source": "resolve_parameters", "target": "preflight"},
      {"source": "preflight", "target": "act"}
    ]
  }
}
```

前端 React Flow 节点必须至少显示：

1. node label/type/status。
2. executor type / execution profile。
3. started/finished time。
4. input summary。
5. output summary。
6. error/failure_code。
7. 可展开查看完整 input JSON 和 output JSON。

禁止：

1. 前端自行拼接“假 graph”并声明为执行图。
2. 只显示任务父子关系，不显示 ReAct 节点输入/输出。
3. 隐藏失败节点的 input/output/error。
4. 后端没有 `graph_runs` 时显示绿色成功图。

## 18. 与现有代码迁移关系

### 18.1 第零阶段：service.py 能力补齐

在接入 LangGraph 前，必须先完成五类执行方 service boundary 的能力补齐。否则 LangGraph 只能编排旧的薄调用，无法提升实战性。

这里的“能力补齐”不是把业务逻辑写进 `service.py`。正确做法是：`service.py` 增加或暴露必要接口，接口内部调用本模块 application/domain/execution 层完成真实业务。`service.py` 仍然只做服务边界。

必做项：

1. CLI：补 CLI result/readback verifier，不允许仅凭 exit code 完成。
2. Agent：worker 必须能从 task/capability contract 构造并传入 `verification_plan`。
3. MCP：区分 health/test_call 与正式 tool execution，补 resource readback。
4. 外接 connector：新增 `execute_capability`，`test_call` 只保留 health/smoke。
5. 内部插件：补 plugin capability contract、LLM trace/readback、SQLite/public projection readback。

每类 service.py 的允许改动：

| 模块 | service.py 允许新增 | service.py 禁止承载 |
| --- | --- | --- |
| CLI | `execute_capability` 或增强 `execute_task` 的稳定入口、DTO 转换、审计 envelope | subprocess 细节、artifact 验证、readback 规则、retry |
| Agent | 接收 `verification_plan`、传递 trace/idempotency、返回 invocation envelope | agent 任务语义验证、LLM 裁决、artifact 内容检查 |
| MCP | 区分 health/test 与 business execution 的 service API | tool schema drift 业务判断、resource hash/readback 验证 |
| 外接 connector | 新增 `execute_capability(connector_id, request)` public boundary | capability 参数推断、output_summary 业务验证、read-after-write 判定 |
| 内部插件 | 暴露 capability execution boundary、返回 plugin execution envelope | 插件业务逻辑、SQLite 投影验证、LLM trace 语义裁决 |

对应业务逻辑必须落到各自模块内部独立文件，例如 `execution.py`、`capability_execution.py`、`validators.py`、`readback.py`、`runtime.py` 或现有等价 domain/application 模块。

这一阶段完成前，禁止声明“worker 已经改成 ReAct/LangGraph 实战执行”。

### 18.2 第一阶段：旁路接入

1. 新增 ReAct 模块文件。
2. `TaskExecutionWorker` 增加配置：

```python
WorkerConfig(enable_react_execution: bool = False)
```

3. 默认关闭，不影响现有执行。
4. real CI 使用显式参数开启。

### 18.3 第二阶段：external connector 试点

只对 `executor_type=external_connector` 且 capability 有 contract 的任务启用。

验收范围：

- `mongodb_csv_inspect`
- `mongodb_csv_import`
- `mongodb_create`
- `mongodb_update`
- `mongodb_delete`

### 18.4 第三阶段：CLI/MCP/Agent/内部插件接入

CLI/MCP 从 usage profile 生成 contract。

Agent 从 agent asset scope/auth/capability 生成 contract。

内部插件从 functional plugin registry 生成 contract，并强制 `executor_type=internal_plugin`。

每类执行方接入必须满足：

1. 有独立 `execution_profile_id`。
2. 有参数 contract 测试。
3. 有 result validation 测试。
4. 有 readback verifier 测试。
5. 有失败路径测试，证明不会降级成功。

### 18.5 第四阶段：替换 worker 薄 dispatch

worker 保留：

- 任务扫描
- 依赖检查
- batch 控制
- timeout 控制
- 调用 `react_executor.execute(task_id)`

worker 不再直接拼参数和执行业务分发。

替换完成的判定标准：

1. `_execute_on_external_executor` 不再直接分支调用 CLI/MCP/connector/agent。
2. 内部插件 `_execute_on_plugin` 也通过 ReAct executor 的 `act` 节点调用。
3. worker 只负责扫描、租约、依赖、批量控制和最终统计。
4. 所有执行节点输入/输出都写入 `react_execution.graph_runs`，供前端 React Flow 查看。
5. 没有 LangGraph runtime 时，任务 fail-closed，而不是走旧路径完成。

## 19. 测试计划

所有测试必须标注真实性：`real` / `hybrid` / `invalid`。

### 19.1 单元测试

| 用例 | 目标 | 类型 |
| --- | --- | --- |
| contract resolver 读取 connector capability contract | 验证 contract 完整性 | real/hybrid |
| parameter resolver 缺必填参数 | 返回 parameter_gap | real |
| parameter resolver 参数类型错误 | 返回 invalid_parameters | real |
| executor profile 缺失 | EXECUTOR_PROFILE_MISSING，不进入 Act | real |
| executor profile 与 executor_type 不匹配 | EXECUTOR_PROFILE_TYPE_MISMATCH | real |
| preflight 文件不存在 | 阻断执行 | real |
| preflight MongoDB 写操作缺 trace marker | 阻断执行 | real |
| result validator 缺 `output_summary.total_rows` | result_validation_failed | real |
| result validator `output_summary` 与 observation 不一致 | result_validation_failed | real |
| validation_strategy=rule | 只执行规则验证并记录 rule verdict | real |
| validation_strategy=llm 但 provider 不可用 | fail-closed，不允许规则替代 | real/hybrid |
| validation_strategy=hybrid 且 rule gate 失败 | 不调用 LLM 裁定成功，直接 failed | real |
| validation_strategy=hybrid 且 LLM verdict failed | 即使规则通过也不能 complete | real/hybrid |
| graph run event writer | 每个节点记录 input/output/error | real |
| graph run 缺 output | 前端查看契约失败，不能标记可视化完成 | real |
| verifier 缺 output_summary | verification_failed | real |
| recovery parameter_gap | 写入 suspended context | real |

### 19.2 集成测试

| 用例 | 目标 | 证据 |
| --- | --- | --- |
| CSV inspect 正常执行 | 真实 CSV -> connector -> outcome -> verification | task DB + connector log + outcome |
| CLI profile 正常执行 | 真实 CLI service -> artifact/readback -> verification | cli log + artifact + task outcome |
| Agent profile 正常执行 | 真实 Agent service -> run/artifact/log -> hybrid verification | agent run + artifact + LLM verdict |
| MCP profile 正常执行 | 真实 MCP service -> tool/resource readback -> verification | MCP result + resource hash + audit |
| 内部插件 profile 正常执行 | functional plugin service -> SQLite/readback/LLM trace | plugin state + DB snapshot + audit |
| CSV inspect 缺 `csv_paths` | 进入 parameter_gap，不调用 connector | task status + audit |
| connector unhealthy | preflight_failed 或 resource_gap | health report + task suspension |
| MongoDB import 缺 trace_id/session_id | mutation guard 阻断 | failure code + audit |
| result validation failed | connector 自报 success 但缺业务字段时 fail | result_validation + audit |
| retry then success | 第一次 transient timeout，第二次真实成功 | retry audit + final outcome |
| LLM validation required | contract 要求 LLM 验证时必须有真实 LLM trace | llm trace + verdict + audit |
| hybrid validation blocked by rule | DB readback 失败时 LLM 不能覆盖失败 | readback failure + hybrid audit |
| hybrid validation blocked by LLM | 规则通过但语义不对齐时任务失败 | llm verdict + task failed |
| React Flow graph data | 后端 graph_runs 能被任务详情接口读回 | task detail API + graph node input/output |
| verification failed | 执行结果缺 evidence_refs 时 fail | verification result |

### 19.3 real CI 验收命令

建议新增：

```bash
.venv/bin/python -m pytest tests/ci_acceptance/real_ci_modules/tasks/test_react_execution_external_connector_real.py -q
```

必须包含：

1. 真实 TaskManagementService。
2. 真实 external connector service。
3. 真实 SQLite readback。
4. 真实 connector runtime log readback。
5. 禁止 mock connector 成功。

## 20. 回滚计划

### 20.1 配置回滚

`WorkerConfig.enable_react_execution=False` 后回到旧 worker 执行路径。

### 20.2 数据回滚

ReAct metadata 只追加在 `metadata.react_execution`，不改变现有 task 基础字段语义。回滚时：

1. 停用 ReAct。
2. 保留历史 metadata 作为审计。
3. 新任务不再写 react_execution。

### 20.3 external connector 接口回滚

如果 `execute_capability` 出现问题：

1. 停用正式执行接口。
2. 对 health/smoke 流程保留 `test_call`。
3. 业务任务进入 `resource_gap` 或 `execution_interface_gap`，不得自动降级为 `test_call` 成功。

## 21. 发布门禁

上线前必须满足：

- [ ] ReAct 执行默认关闭，灰度开启。
- [ ] 实现按职责拆分，没有把 LangGraph/ReAct/五类 executor/验证/落库堆进单个巨石文件。
- [ ] LangGraph 节点按节点功能拆分为 `graph_nodes/*_node.py`，不存在承载全部节点实现的 `graph_nodes.py`。
- [ ] 所有 owner module 的 `service.py` 只做 public service boundary，没有承载业务执行、复杂验证、readback、retry/recovery 或 LLM 裁决逻辑。
- [ ] `TaskExecutionWorker` 只做扫描、租约、依赖、批量控制和调用 ReAct executor，不再保留业务执行分支。
- [ ] `action_dispatcher` 只做路由和 adapter 调用，五类 executor 的参数转换分散在独立 adapter 模块。
- [ ] 至少一个 external connector capability 完成真实执行验收。
- [ ] CLI、Agent、MCP、外接 connector、内部插件各有独立 execution profile。
- [ ] 五类执行方的执行入口都经过各自 service boundary。
- [ ] 五类执行方各自有 observation source 和 readback 测试。
- [ ] parameter_gap 有 readback 测试。
- [ ] preflight failure 有 readback 测试。
- [ ] result validation failure 有 readback 测试。
- [ ] retry audit 与 retry budget 有 readback 测试。
- [ ] verification failure 有 readback 测试。
- [ ] rule / LLM / hybrid 三类验证各有明确 contract 示例和测试。
- [ ] contract 要求 LLM 验证时，缺 provider、解析失败、超时都 fail-closed。
- [ ] hybrid 验证中 LLM 不能覆盖 rule readback 失败。
- [ ] 每个 ReAct graph node 的 input/output/error 都可从后端读回。
- [ ] React Flow 页面只渲染后端真实 graph_runs，不自行生成成功状态。
- [ ] LLM Reason 失败时 fail-closed，不 fallback 到规则成功。
- [ ] external connector 业务执行不再依赖 `test_call` 最终语义。
- [ ] 所有状态变更经过 TaskManagementService/DAO，并有审计事件。
- [ ] 回滚开关验证通过。

## 22. Completion Gate

- RCA: passed
- Implementation Design: passed
- Normal Cases: covered
- Abnormal Cases: covered
- Edge Cases: covered
- Evidence Requirements: covered
- Rollback: covered
- Realism Labeling: covered
- Architecture Boundary: service.py interface-only and no monolithic execution file are mandatory gates
- Final Judgment: 设计文档已完成；代码实现未开始，需按本文档分阶段落地并通过 real CI 与架构门禁后才能声明执行模块升级完成。

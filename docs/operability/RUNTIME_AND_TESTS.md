# Runtime 与测试说明

本文档用于说明 Zentex 当前已经落地的运行时底座代码、测试文件分布、各模块职责边界，以及测试覆盖范围。

按功能组织的插件开发规范索引见：
- [PLUGIN_GUIDES.md](docs/operability/PLUGIN_GUIDES.md)

## 目标范围

当前文档覆盖以下运行时骨架模块：

- `BrainTranscriptStore`
- `BrainSession`
- `ThinkLoop`
- `BrainRuntime`
- `BrainRuntimeState`
- `WorkingMemoryController`
- `LivingSelfModelEngine`
- `CognitiveTemporalEngine`
- `MetaCognitionController`
- `CognitiveToolRegistry`
- `CognitiveToolOrchestrator`
- `BasePluginSpec`
- `PluginHealthProbeResult`
- `PluginLoadResult`
- `AbstractPluginRegistry`

同时覆盖与上述模块对应的测试文件与验证目标。

## WebSocket 运行契约

Web Console 的实时事件流属于运行时基础设施，不允许依赖 `uvicorn` 的自动协议选择。

当前项目约束如下：

- 开发态与测试态统一要求使用 `websockets-sansio`
- 启动入口通过 `ZENTEX_WS_IMPLEMENTATION` 明确声明协议实现
- `check-startup` 会在真正构建 Web Console 之前先校验当前 WebSocket 运行时
- 当检测到 `websockets>=16` 但仍试图使用 `auto` 或 `legacy` 路径时，启动必须直接失败，禁止带病运行

目标不是压日志，而是把实时事件流的传输层做成可验证、可复现、可升级的运行时契约。

对应验证分层：

- 单元/接口层：
  - `tests/web_console/test_events_stream_lifecycle.py`
  - `tests/web_console/test_api.py -k events_stream`
  负责校验 `disconnect` 清理、cursor 增量推送、无 cursor 默认只订阅未来增量
- 集成/soak 层：
  - `tests/web_console/test_events_stream_integration.py`
  负责在真实 `uvicorn --ws websockets-sansio` 子进程下验证重复连接、短空闲、长空闲、主动关闭不会回到 `keepalive ping failed` / `socket.send() raised exception.` 路径

## 认知工具分层说明

Zentex 当前有两层名称相近但职责不同的认知工具代码，它们不是重复实现，而是刻意拆分：

- `src/zentex/core/cognitive_tools_spec.py`
  契约层。负责定义“一个合法的认知工具应该长什么样”，包括只读边界、无副作用边界、触发条件和禁用条件。
- `src/zentex/runtime/cognitive_tools/__init__.py`
  执行层。负责定义“运行时如何使用认知工具”，包括注册、候选筛选、并行/串行分组、调用记录和结果合并。

简化理解：
- 契约层定义工具是什么。
- 执行层定义运行时怎么用工具。

## 代码文件说明

### `src/zentex/runtime/transcript.py`

职责：
- 提供基于 JSONL append-only 的认知事件流存储。
- 记录运行过程发生了什么。
- 为会话恢复与状态回放提供统一真相源。

核心对象：
- `BrainTranscriptEntryType`
- `BrainTranscriptEntry`
- `BrainTranscriptStore`

关键能力：
- 追加写入单条事件
- 按 `session_id` 读取历史事件
- 按 `turn_id` 读取历史事件
- 保持事件流只追加，不覆盖历史

边界说明：
- 不替代 `ReflectionStore`
- 不替代 `RuntimeMemoryStore`
- 不承担认知推理逻辑

### `src/zentex/runtime/session.py`

职责：
- 提供连续会话容器。
- 持有某一个会话的内存工作台状态。
- 负责从 transcript 重建会话现场。
- 负责把单轮结果持久化为事件流。
- 为后续的 Identity Package Plugins 提供主体连续性挂载点。

核心对象：
- `BrainSessionSnapshot`
- `BrainSession`

关键能力：
- `restore_from_transcript()`
- `advance_turn()`
- `get_snapshot()`

内部维护的主要状态：
- `turn_counter`
- `current_workspace`
- `active_goal_frame`
- `last_working_memory`
- `last_temporal_agenda`
- `last_living_self_model`
- `last_metacognition`
- `last_conflict_snapshot`
- `last_counterfactual_simulation`
- `last_interaction_mind`
- `last_consolidation`
- `last_reflection`

边界说明：
- 不负责全局依赖初始化
- 不直接加载或执行身份包
- 身份与经验包的切换不替代 transcript 回放恢复
- 身份包故障必须隔离，不能拖垮会话恢复
- 身份包切换、拒绝、撤销、降级、回退都必须可审计
- 不负责九问判断
- 不负责大模型调用
- 不负责工具编排

### `src/zentex/runtime/think_loop.py`

职责：
- 提供单轮认知循环的无状态执行骨架。
- 从 `BrainSession` 读取连续性状态。
- 将“单轮思考”与“长期连续会话”彻底解耦。
- 执行本轮 9 个认知阶段。
- 返回完整的 `BrainTurnResult` 给 `BrainSession` 后续持久化。
- 作为未来 `brain.py` 主执行链的委托目标。

核心对象：
- `BrainTurnResult`
- `ThinkLoop`

定位说明：
- `ThinkLoop` 负责“大脑想一次”。
- `BrainSession` 负责“会话如何连续”。
- `BrainTurnResult` 是单轮全量产物，后续会被展开为 transcript 事件流。

9 个阶段：
- `_phase_1_observe`
  观察：扫描环境、收集宿主状态和外部输入
- `_phase_2_frame`
  框架：生成九问框架与多层上下文结构
- `_phase_3_update_working_state`
  刷新工作状态：更新工作记忆、内部时间感待办和活的自我模型
- `_phase_4_detect_cognitive_risks`
  检测认知风险：捕捉冲突快照、不确定性热点以及自信度漂移
- `_phase_5_simulate`
  模拟预演：执行反事实多分支预演与交互对象心智推断
- `_phase_6_metacognition`
  元认知：决定思考模式、升级姿态以及认知工具调用计划
- `_phase_7_orchestrate_cognitive_tools`
  工具编排：安排串行或并行执行，并合并结果
- `_phase_8_synthesize_decision`
  综合决策：生成行动建议、优先事项、阻塞原因和待确认问题
- `_phase_9_consolidate`
  巩固：生成反思与巩固快照，为 transcript 写入做准备

边界说明：
- `ThinkLoop` 必须保持无状态
- 不长久保存历史数据
- 不直接做运行时装配
- 不直接承担 transcript 物理写入

LLM 真实性边界：
- 涉及角色推断、目标生成和关键推理决策的阶段，当前已通过 `src/plugins/provider_tools.py` 中的 `openai_compat` 工具接入真实 LLM 调用路径。
- 缺 API Key、缺 Provider 或远程调用失败时，必须显式报错，禁止静默退回规则结果后再伪装成 AI 产物。
- 九问问题体拼装和反思协议等确定性工程规则，必须保留 provenance，不能伪装成大模型推理产物。

方法级边界：
- `[LLM MANDATORY]`
  - `_phase_2_frame`
    原因：承担角色推断与多层上下文框架生成，当前通过 `openai_compat` 工具生成 `frame_summary`
  - `_phase_8_synthesize_decision`
    原因：承担目标生成与关键综合推理决策，当前通过 `openai_compat` 工具生成最终 `summary`
- `[Pluginization Boundary]`
  - `_phase_1_observe`
    感官与解释器插件挂载点
  - `_phase_5_simulate`
    思维模拟器插件挂载点
  - `_phase_7_orchestrate_cognitive_tools`
    认知工具插件主挂载点
- `[Deterministic Only]`
  - `_phase_3_update_working_state`
    基于分数、衰减和阈值的状态机运算
  - `_phase_4_detect_cognitive_risks`
    基于规则的冲突、不确定性与漂移探测
  - `_phase_6_metacognition`
    基于风险、负荷和预算的硬规则调度
  - `_phase_9_consolidate`
    结构化反思协议和巩固快照拼装，必须保留 provenance

插件统一红线：
- `[Rollback & State Recovery]`：所有插件的装载、升级、切换和执行都必须支持回退到上一个经过审计的稳态版本。
- `[Failure Isolation & Degrade]`：插件必须带健康探针、超时控制和错误捕获；插件故障只能停留在插件层，必须显式抛出降级态或报错，不能拖垮 `ThinkLoop`。
- `[Audit & Revocation]`：插件加载、切换、降级、拒绝、撤销、回退都必须保留原因，并最终写入 transcript；插件接口必须定义撤销条件。

### `src/zentex/core/models.py`

职责：
- 提供统一运行态投影模型。

核心对象：
- `BrainRuntimeState`

关键用途：
- 面向 Web 控制台、调试面板和运行时观察接口暴露统一快照。

### `src/zentex/core/plugin_base.py`

职责：
- 提供统一插件基类。
- 固化插件生命周期、健康探针、回退条件与撤销原因的底层数据契约。
- 通过 Pydantic v2 校验封死不合规插件进入主链。

核心对象：
- `PluginLifecycleStatus`
- `PluginHealthStatus`
- `BasePluginSpec`

关键规则：
- `active` 状态插件必须显式声明 `rollback_conditions`。
- `degraded` 与 `revoked` 状态插件必须显式声明 `revocation_reasons`。
- 插件必须声明 `health_probe_endpoint` 或 `health_status`。
- 生命周期合法流转由 `transition_to()` 约束。

### `src/zentex/core/plugin_runtime.py`

职责：
- 提供统一插件运行态契约。
- 标准化插件健康探针、加载结果、回退决策与撤销记录。
- 为后续 transcript 审计落库提供统一结构化对象。

核心对象：
- `PluginHealthProbeResult`
- `PluginRollbackDecision`
- `PluginRevocationRecord`
- `PluginLoadResult`
- `PluginLoadAction`
- `PluginDegradeState`

关键规则：
- 回退、降级、拒绝、撤销必须保留审计原因。
- 回退必须显式声明目标版本与回退决策。
- 不健康探针必须携带错误信息。
- 降级与隔离状态必须保留健康证据或错误详情。

### `src/zentex/common/plugin_registry.py`

职责：
- 提供通用生命周期注册表。
- 作为插件注册、晋升、撤销、健康筛选的安全海关。
- 在注册阶段对脏插件对象做失败隔离与审计记录。

核心对象：
- `StateTransitionError`
- `PluginRegistryAuditRecord`
- `AbstractPluginRegistry`

关键规则：
- 新注册插件统一归一化为 `candidate`。
- 禁止 `candidate` 直接晋升到 `active`。
- 晋升与撤销必须显式传入非空审计原因。
- `get_active_plugins()` 只能返回状态为 `active` 且健康的插件。

### `src/zentex/runtime/cognitive_tools/registry.py`

职责：
- 管理认知工具插件的运行态注册、启用、降级、撤销、删除与审计。
- 对同一 `behavior_key` 下的插件实施“单行为单活跃”约束。
- 在强制关闭后执行自动回退，避免功能空洞或假启动状态。

关键规则：
- 所有认知工具状态变化都必须写入 transcript / audit sink，禁止只改内存对象。
- 当 `supports_multiple_plugins=False` 时，同一 `behavior_key` 上只允许一个 `active` 插件。
- `force_enable_plugin()` 会先自动降级同一行为上已激活的冲突插件，再启用目标插件。
- `force_disable_plugin()` 会先降级当前激活插件，再按以下顺序执行回退：
  - 优先启用同一行为下”上一个正式版本”的官方插件。
  - 如果上一个正式版本已删除或不存在，则启用默认版本插件。
  - 如果该行为允许多插件并且还有其他激活插件，则不触发额外回退。
  - 如果没有任何激活插件残留，则至少恢复一个默认版本插件，避免行为出口悬空。
- 受保护的系统默认插件禁止删除；已激活插件也禁止删除。

**⚠️ `supports_multiple_plugins` 子类继承陷阱（2026-04 事故记录）**

旧字段名 `supports_multi_active` 已废弃，正确名称为 `supports_multiple_plugins`。
父类 `CognitiveToolSpec` 通过 `Field(validation_alias=AliasChoices(...))` 同时接受两个名称作为构造参数。

**禁止在子类中用裸注解重新声明该字段**：

```python
# ❌ 错误：会覆盖父类 Field 的 alias，导致运行期 ValidationError
class MyPlugin(CognitiveToolSpec):
    supports_multiple_plugins: bool = True

# ✅ 正确：在 factory 函数传参，不在类体声明
return MyPlugin(
    ...
    supports_multiple_plugins=True,
    ...
)
```

根本原因：Pydantic v2 子类重新声明字段时，即使只是加默认值，也会用裸 bool 完全覆盖父类的
`Field(validation_alias=AliasChoices(...))`，alias 丢失后所有用旧名 `supports_multi_active=`
构造该类的调用都会在运行期被拒绝（`Extra inputs are not permitted`），且错误**不在导入时暴露**，
只在实际实例化时才触发。

`CognitiveToolSpec.__init_subclass__` 现已加入防护，错误的子类声明会在**类定义时**立即抛出 `TypeError`。

Web 控制台对应接口：
- `GET /api/web/plugins/cognitive`
- `POST /api/web/plugins/cognitive/{plugin_id}/force-enable`
- `POST /api/web/plugins/cognitive/{plugin_id}/force-disable`
- `DELETE /api/web/plugins/cognitive/{plugin_id}`

对应测试：
- `tests/runtime/test_cognitive_tool_registry.py`
- `tests/web_console/api/test_plugins_api.py`

### `src/plugins/provider_tools.py`

职责：
- 提供 OpenAI、ChatGPT、Gemini、Claude 的统一工具调用方法。
- 屏蔽不同 Provider 的 HTTP 路径、认证头与响应格式差异。
- 向运行时暴露统一 `call()` 方法和统一响应对象。

核心对象：
- `ProviderToolConfig`
- `ToolInvocationRequest`
- `ToolInvocationResponse`
- `OpenAITool`
- `ChatGPTTool`
- `GeminiTool`
- `ClaudeTool`

关键规则：
- 缺少 API Key 时必须显式报错。
- 请求体构造按 Provider 差异分别处理。
- 输出文本统一被标准化到 `ToolInvocationResponse.output_text`。

### `src/zentex/runtime/runtime.py`

职责：
- 提供顶层进程级容器。
- 装配共享存储、工具注册表与认知器官。
- 统一管理活跃会话生命周期。
- 向外提供运行态总览。

核心对象：
- `BrainRuntime`

关键能力：
- `create_session()`
- `get_session()`
- `get_runtime_state()`
- `build_runtime_with_default_llm()`

当前持有的共享对象：
- `transcript_store`
- `reflection_store`
- `runtime_memory_store`
- `identity_store`
- `tool_registry`
- `llm_tool`
- `working_memory_controller`
- `temporal_engine`
- `living_self_model_engine`
- `metacognition_controller`
- `conflict_engine`
- `counterfactual_engine`
- `interaction_mind_engine`
- `consolidation_engine`

边界说明：
- 只负责装配与生命周期管理
- 不负责单轮推理
- 不持有会话级过程变量
- 当前可统一挂载 `llm_tool`，供 `ThinkLoop` 的 LLM mandatory 阶段通过 `BrainSession.runtime` 进行依赖注入
- `build_runtime_with_default_llm()` 会默认从 `config/provider_tools.yml` 装配 `openai_compat`

### `src/zentex/runtime/metacognition.py`

职责：
- 提供元认知调度器骨架。
- 根据当前工作记忆、自我模型、预算与待办压力，决定怎么想。
- 产出思考模式决策、工具调用计划与升级降级决策。
- 将主观价值偏好开放给 SubjectiveWeightProfile Plugins。

核心对象：
- `ReasoningModeDecision`
- `ToolInvocationPlan`
- `EscalationDecision`
- `MetaCognitionController`

关键规则：
- 高风险且低证据时，优先输出 `clarify` 或 `review` 姿态。
- 高负荷或预算不足时，必须主动降级思考深度，禁止无限深挖。
- 连续失败时，优先 `revisit`，而不是继续提速推进。
- 存在稳定弱点时，优先选择能对冲该弱点的认知工具。
- 风险、成本、创意、连续性等价值偏好可通过 SubjectiveWeightProfile Plugins 动态切换。

边界说明：
- 只负责决定怎么想。
- 不直接下发宿主执行命令。
- 不获取执行权限。
- 不直接对外发送消息。
- 主观权重可插件化升级，但调度器本身仍是确定性规则层。
- 主观权重插件必须具备健康探针、超时与失败隔离。
- 权重切换、降级、拒绝、撤销、回退都必须可审计。

### `src/zentex/runtime/working_memory.py`

职责：
- 提供工作记忆与注意力控制骨架。
- 维护活跃关注项、挂起关注项和注意力预算。
- 处理高优先级事项对低优先级事项的打断与恢复。

核心对象：
- `AttentionItem`
- `FocusBudget`
- `WorkingMemoryFrame`
- `WorkingMemoryController`

关键规则：
- 活跃关注项数量必须受 `FocusBudget` 限制。
- 更高优先级或高风险事项可打断较低优先级事项。
- 被打断且可恢复的事项必须保留 `resume_hint`。

边界说明：
- 只维护脑内注意力槽位。
- 不直接触发任何外部动作。
- 不直接发送任何外部消息。

### `src/zentex/runtime/self_model.py`

职责：
- 提供活的自我模型引擎骨架。
- 维护认知负荷、近期稳定弱点、自信度漂移和姿态调整。
- 对失败模式和高自信低证据状态生成内部建议。
- 作为 Identity Package Plugins 的状态映射承接层。

核心对象：
- `CognitiveStateProfile`
- `RecentWeaknessPattern`
- `ConfidenceDriftIndicator`
- `LivingSelfModel`
- `LivingSelfModelEngine`

关键规则：
- 连续失败时必须降低风险容忍度并切换为更保守姿态。
- 高自信低证据时必须生成 `ConfidenceDriftIndicator`。
- 高认知负荷时应提出压低同时活跃关注项上限的建议。
- 角色包、禁令包、行业经验包的输入必须可隔离、可切换、可回滚。

边界说明：
- 只维护脑内动态自我画像。
- 不直接触发任何外部动作。
- 不直接发送任何外部消息。
- 不把身份包本身当成会话状态机或事件流恢复机制。
- 身份与经验包故障必须被隔离，不能污染自我模型主链。

### `src/zentex/runtime/temporal.py`

职责：
- 提供内部时间感引擎骨架。
- 维护脑内待办的时间治理视图。
- 计算复查窗口、冷却期、过期状态和延迟风险。
- 将高 deferred risk 项上浮到内部 `review_now` 队列。

核心对象：
- `TemporalAgendaState`
- `AgendaAge`
- `ReviewWindow`
- `ReminderCooldown`
- `DeferredRiskScore`
- `CognitiveTemporalEngine`

关键规则：
- 长期未回看的高风险项必须上浮到 `review_now_item_ids`。
- 过期假设或待办必须进入 `expired_item_ids`，供后续降级或关闭。
- 冷却期内同一事项不允许被反复提醒。

架构红线：
- `[LLM NOT REQUIRED]`：该引擎是纯确定性的时间治理引擎，禁止使用大模型代替时间窗口计算。
- `[Cluster vs. Single-Instance]`：未来在集群模式下，状态会受 `snapshot_version` 和 `brain_scope` 约束，避免 Stale Write。
- `[Pluginization Boundary]`：该引擎是核心底座，但其内部提醒可被后续认知工具插件消费；相关插件必须支持回退、失败隔离与撤销审计。
- `[Strict No-Execution]`：该引擎只能改变脑内复查优先级和注意力顺序，不能生成宿主控制命令或对外发送消息。

### `src/zentex/runtime/cognitive_tools/__init__.py`

职责：
- 提供认知工具执行层的注册表与编排器骨架。
- 提供统一的认知工具输入输出数据模型。
- 固化并行、串行、边界校验与调用记录规则。

核心对象：
- `CognitiveToolSpec`
- `CognitiveToolInvocation`
- `CognitiveToolResult`
- `CognitiveToolOrchestrationReport`
- `ToolInvocationPlan`
- `CognitiveToolRegistry`
- `CognitiveToolOrchestrator`

关键规则：
- 只有 `read_only=True` 且 `side_effect_free=True` 的工具允许进入并行安全组。
- 涉及 `working_memory`、`temporal_agenda`、`metacognition` 的工具默认串行。
- 工具结果不能携带外部执行动作。
- 所有工具调用都必须产生记录，便于后续写入 transcript。
- 工具插件升级必须支持回退到上一个经过审计的正常版本。
- 工具插件故障必须停留在工具层，并显式上报降级或错误。
- 工具的拒绝、撤销、降级、回退都必须保留审计原因。
- 该层只负责“运行时怎么用工具”，不重新定义静态工具契约；静态契约属于 `src/zentex/core/cognitive_tools_spec.py`。

## 测试文件说明

### `test/runtime/test_transcript.py`

覆盖目标：
- 验证 `BrainTranscriptStore` 的 append-only 写入与读取。
- 验证按 `session_id` 与 `turn_id` 的事件回放能力。
- 验证枚举与时间戳在序列化和反序列化后不丢失。

说明：
- 该测试属于较早创建的目录结构，当前仍位于 `test/` 目录。

### `tests/runtime/test_session.py`

覆盖目标：
- 验证 `BrainSession` 初始化空态是否正确。
- 验证 `advance_turn()` 是否同时完成状态推进与事件流持久化。
- 验证 `restore_from_transcript()` 是否能从历史事件流重建完整会话现场。

核心验证点：
- `turn_counter` 变更
- `last_*` 状态变更
- transcript 持久化联动
- `BrainSessionSnapshot` 输出正确

### `tests/core/test_plugin_base.py`

覆盖目标：
- 验证 `BasePluginSpec` 的状态相关防御性校验。
- 验证非法插件不会绕过健康探针、回退条件和撤销原因约束。
- 验证合法的 `candidate -> sandbox_verified -> active` 状态流转与序列化。

### `tests/core/test_plugin_runtime.py`

覆盖目标：
- 验证插件健康探针、不健康错误信息、回退决策与撤销记录的运行态约束。
- 验证降级、回退、拒绝、撤销场景下的审计字段要求。

### `tests/common/test_plugin_registry.py`

覆盖目标：
- 验证通用插件注册表的状态机与审计拦截。
- 验证禁止 `candidate -> active` 越级。
- 验证撤销必须带原因。
- 验证 `get_active_plugins()` 会排除 `degraded` 与 `revoked` 插件。

### `tests/plugins/test_provider_tools.py`

覆盖目标：
- 验证 OpenAI、Gemini、Claude、ChatGPT 工具方法的请求组装。
- 验证 Provider 认证头与 URL 是否符合预期。
- 验证缺少 API Key 时显式报错。

### `tests/test_think_loop.py`

覆盖目标：
- 验证 `ThinkLoop` 的无状态执行闭环。
- 验证 9 个阶段是否按顺序执行。
- 验证内部阶段产物是否被正确组装为 `BrainTurnResult`。
- 验证 `_phase_2_frame()` 与 `_phase_8_synthesize_decision()` 会调用 LLM mandatory 工具链。
- 验证 LLM mandatory 阶段失败时显式冒泡，不会退回到规则结果。

核心验证点：
- `ThinkLoop` 运行前后不持久保存状态
- 9 个私有阶段顺序调用
- `metacognition` 与 `decision_summary` 的组装正确性
- mandatory LLM 调用次数与输出映射
- LLM 失败时后续阶段不会继续执行

### `tests/test_runtime.py`

覆盖目标：
- 验证 `BrainRuntime` 的初始化装配。
- 验证会话创建和获取流程。
- 验证统一运行态投影 `BrainRuntimeState` 的正确性。

核心验证点：
- 共享依赖是否成功挂载
- `_sessions` 初始是否为空
- `create_session()` 返回的是否为同一 `BrainSession`
- `active_session_ids` 是否正确
- `BrainRuntime` 是否没有污染会话级过程变量

### `tests/runtime/test_cognitive_tools.py`

覆盖目标：
- 验证 `CognitiveToolRegistry` 的注册与候选筛选。
- 验证 `CognitiveToolOrchestrator` 的并发与串行分组规则。
- 验证认知边界规则是否真实生效。

核心验证点：
- `resolve_candidates()` 是否依据 `trigger_conditions`、`do_not_use_when` 与上下文正确筛选
- 纯读工具是否被分配到 `parallel_groups`
- 状态修改类工具是否被隔离到 `serial_groups`
- 越界的 `external_action` 是否被直接拦截

## 当前测试覆盖概览

当前已落地测试文件：

- `test/runtime/test_transcript.py`
- `tests/runtime/test_session.py`
- `tests/runtime/test_cognitive_tools.py`
- `tests/test_think_loop.py`
- `tests/test_runtime.py`
- `tests/test_metacognition.py`
- `tests/test_cognitive_state.py`

对应关系：

- `src/zentex/runtime/transcript.py`
  由 `test/runtime/test_transcript.py` 覆盖
- `src/zentex/runtime/session.py`
  由 `tests/runtime/test_session.py` 覆盖
- `src/zentex/runtime/think_loop.py`
  由 `tests/test_think_loop.py` 覆盖
- `src/zentex/runtime/runtime.py`
  由 `tests/test_runtime.py` 覆盖
- `src/zentex/runtime/working_memory.py`
  由 `tests/test_cognitive_state.py` 覆盖
- `src/zentex/runtime/self_model.py`
  由 `tests/test_cognitive_state.py` 覆盖
- `src/zentex/runtime/temporal.py`
  当前尚未补测试
- `src/zentex/runtime/metacognition.py`
  由 `tests/test_metacognition.py` 覆盖
- `src/zentex/runtime/cognitive_tools/__init__.py`
  由 `tests/runtime/test_cognitive_tools.py` 覆盖

## 当前目录现状说明

当前测试目录同时存在：

- `test/`
- `tests/`

这是一种历史与新增测试并存的状态。

当前口径：
- 早期 transcript 测试位于 `test/runtime`
- 后续新增运行时测试主要位于 `tests/` 与 `tests/runtime/`

建议：
- 后续统一测试目录规范时，将 `test/runtime/test_transcript.py` 一并迁移到 `tests/runtime/`
- 统一 pytest 收口路径，避免长期双目录并存

## 建议的后续整理方向

- 为 `runtime` 包补充 `__init__.py`，统一导出核心运行时对象。
- 为 `BrainRuntime`、`ThinkLoop` 与 `CognitiveToolOrchestrator` 增加集成级联测试，验证从单轮执行到会话持久化的完整闭环。
- 在文档中继续补充事件类型、运行时状态字段和认知工具协议字段的版本演进说明。

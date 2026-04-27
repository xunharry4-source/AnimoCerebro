# Zentex ThinkLoop: 9-Stage Cognitive Architecture Deep Dive | Zentex ThinkLoop：九阶段认知架构深度解析

## English Version

The ThinkLoop is the core "Counselor Brain" of Zentex. It orchestrates the flow from raw observation to final delegated action across nine distinct cognitive stages.

### 1. The Nine Questions (Q1-Q9)

The system enforces a clinical-grade reasoning process by answering nine fundamental questions before any tool is executed:

| Stage | Question | Purpose | LLM Role |
| :--- | :--- | :--- | :--- |
| **Q1** | Where am I? | Environment & Workspace Analysis | Context Framing |
| **Q2** | Who am I? | Role & Persona Alignment | [LLM MANDATORY] |
| **Q3** | What do I have? | Asset & Resource Inventory (Q3 Plugin) | Inventory Synthesis |
| **Q4** | What could I do? | Capability Matching | Option Generation |
| **Q5** | What should I do? | Strategic Prioritization | Risk/Reward Analysis |
| **Q6** | What are the risks? | Boundary & Policy Audit | Safety Enforcement |
| **Q7** | What is the plan? | Step-by-step Execution Graph | [LLM MANDATORY] |
| **Q8** | What is the action? | Tool Call / Delegation Receipt Synthesis | [LLM MANDATORY] |
| **Q9** | What did I learn? | Verification & Memory Consolidation | Feedback Loop |

### 2. Agent Bridge Protocol Integration

Heterogeneous Agents (like the Random Number Agent on 9201) are integrated during **Phase 3 (Q3)** and **Phase 8 (Q8)**.

**Q3: Asset Inventory Scan**:
The `Q3WhatDoIHavePlugin` performs a live scan of the `AgentManager`.
- Agents with `trust_level: revoked` or `status: offline` are **automatically excluded** from the inventory snapshot.
- Only `TRUSTED` agents with valid `capabilities_snapshot` are promoted to the active session context.

**Q4-Q8: Capability Flow**:
1. **Q4 (Match)**: The system matches the current task (e.g., "Sample a random value") against the `Random Number Agent`'s `random_number` capability.
2. **Q5 (Advise)**: The `AgentCoordinationService` calls `think_about_task` to generate an advisory decision (`EXECUTABLE_NOW`, `BLOCKED_BY_BOUNDARY`).
3. **Q8 (Act)**: If the decision is `allow`, the system synthesizes a `DelegatedCommand` and sends it to the Agent's `/task` or specific capability endpoint via the bridge.

### 3. [LLM MANDATORY] Cognitive Redlines

To prevent "hallucination loops" or "agent-to-agent collusion," the ThinkLoop enforces **Hard LLM Interventions** at three critical gates:

> [!IMPORTANT]
> - **Phase 2 (Who am I?)**: The system *must* use an LLM-vetted persona to ensure it acts as a "Counselor" and not a "Rogue Agent."
> - **Phase 7 (Plan Synthesis)**: All multi-stage plans involving external agents must be reviewed by the core LLM for boundary compliance.
> - **Phase 8 (Action Generation)**: The final command payload sent to an external Agent is verified against the user's `trust_level` policy.

### 4. UI Tracing (Q4-Q9 Accordion)

The Web Console uses the `trace_id` from the `BrainTranscript` to render the reasoning steps.
- **Accordion Linkage**: Every step in the "Thinking..." UI is a direct visualization of a `ThinkLoop` phase.
- **Real-time Streaming**: Steps are pushed via WebSockets (`/api/web/events/stream`) as they are completed by the backend orchestrator.

### 5. Testability & Fail-Closed Logic

The system is designed with **Fail-Closed** defaults:
- If a `POST /capability-handshake` fails or is rejected by the `AgentCoordinationService`, the Agent stays `OFFLINE` and is invisible to subsequent ThinkLoop turns.
- If a `DELETE` is issued, the Agent is physically removed from the `AgentManager` and cannot be scavenged by Q3.

---

## 中文版本

ThinkLoop 是 Zentex 的核心"顾问大脑"。它通过九个不同的认知阶段，协调从原始观察到最终委托执行的流程。

### 1. 九问（Q1-Q9）

系统通过在执行任何工具之前回答九个基本问题，强制执行临床级的推理过程：

| 阶段 | 问题 | 目的 | LLM 角色 |
| :--- | :--- | :--- | :--- |
| **Q1** | 我在哪？ | 环境和工作空间分析 | 上下文框架 |
| **Q2** | 我是谁？ | 角色和人格对齐 | [必须使用LLM] |
| **Q3** | 我有什么？ | 资产和资源清单（Q3插件） | 清单综合 |
| **Q4** | 我能做什么？ | 能力匹配 | 选项生成 |
| **Q5** | 我应该做什么？ | 战略优先级排序 | 风险/收益分析 |
| **Q6** | 有什么风险？ | 边界和策略审计 | 安全执行 |
| **Q7** | 计划是什么？ | 逐步执行图 | [必须使用LLM] |
| **Q8** | 行动是什么？ | 工具调用/委托回执综合 | [必须使用LLM] |
| **Q9** | 我学到了什么？ | 验证和记忆巩固 | 反馈循环 |

### 2. Agent 桥接协议集成

异构 Agent（如端口 9201 上的随机数 Agent）在**第三阶段（Q3）**和**第八阶段（Q8）**期间集成。

**Q3：资产清单扫描**：
`Q3WhatDoIHavePlugin` 对 `AgentManager` 进行实时扫描。
- `trust_level: revoked` 或 `status: offline` 的 Agent **自动排除**在清单快照之外。
- 只有具有有效 `capabilities_snapshot` 的 `TRUSTED` Agent 才会提升到活动会话上下文中。

**Q4-Q8：能力流**：
1. **Q4（匹配）**：系统将当前任务（例如，"采样随机值"）与 `Random Number Agent` 的 `random_number` 能力进行匹配。
2. **Q5（建议）**：`AgentCoordinationService` 调用 `think_about_task` 生成建议决策（`EXECUTABLE_NOW`、`BLOCKED_BY_BOUNDARY`）。
3. **Q8（执行）**：如果决策是 `allow`，系统会综合一个 `DelegatedCommand` 并通过桥接将其发送到 Agent 的 `/task` 或特定能力端点。

### 3. [必须使用LLM] 认知红线

为防止"幻觉循环"或"Agent 之间串通"，ThinkLoop 在三个关键关口强制执行**硬性 LLM 干预**：

> [!IMPORTANT]
> - **第二阶段（我是谁？）**: 系统*必须*使用经过 LLM 审核的人格，以确保其作为"顾问"而非"流氓 Agent"行事。
> - **第七阶段（计划综合）**: 所有涉及外部 Agent 的多阶段计划必须由核心 LLM 审查边界合规性。
> - **第八阶段（行动生成）**: 发送到外部 Agent 的最终命令负载会根据用户的 `trust_level` 策略进行验证。

### 4. UI 追踪（Q4-Q9 手风琴）

Web 控制台使用来自 `BrainTranscript` 的 `trace_id` 来渲染推理步骤。
- **手风琴链接**："思考中..." UI 中的每个步骤都是 `ThinkLoop` 阶段的直接可视化。
- **实时流式传输**：步骤在后端编排器完成时通过 WebSockets（`/api/web/events/stream`）推送。

### 5. 可测试性和故障关闭逻辑

系统设计采用**故障关闭**默认值：
- 如果 `POST /capability-handshake` 失败或被 `AgentCoordinationService` 拒绝，Agent 保持 `OFFLINE` 状态，对后续的 ThinkLoop 轮次不可见。
- 如果发出 `DELETE`，Agent 会从 `AgentManager` 中物理移除，无法被 Q3 回收。

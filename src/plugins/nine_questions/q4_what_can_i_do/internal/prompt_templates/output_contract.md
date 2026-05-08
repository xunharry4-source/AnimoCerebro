**【强制输出 JSON Schema】**
请严格按照以下数据结构输出，数组中必须包含至少 5 个目标候选，绝不能偷懒只输出 1 个或 3 个。禁止直接输出如 `"Q1_xxx"` 的变量名。
说明：必须生成至少 5 个目标。请确保你遍历了上下文中的所有内部认知能力与反思缺口，为每一个核心能力或每一类脑内隐患都至少构思 1 个治理或重构目标；如果 `UserManualTaskGoalLaneAnalysis` 中存在适合内部轨或双轨处理的用户手动任务目标，必须额外逐条覆盖这些手动目标。`objective_candidates` 里只能放 JSON 对象，每个对象包含以下字段。
硬性格式红线：输出 JSON 第一层必须包含 `"type": "InternalObjectiveCandidateSet"`，绝对不能省略。
【最高警告：禁止复述变量名！】：`signal_or_gap_addressed` 和 `capability_evidence_refs` 字段必须写真实的环境事件、内部压力、反思痛点、功能名称或手动目标的具体分析内容。**绝对禁止**输出任何以 `Q1_`、`Q2_`、`Q3_`、`Reflection_`、`UserManualTaskGoalLaneAnalysis` 开头的变量名，也禁止输出类似 `“基于 Q1 变量”`、`“根据 Q2 信息”`、`“Reflection 变量中提到的...”` 这种描述。一旦发现输出包含这些占位符，系统将立即判定为非法输出并硬性拦截。

```json
{
  "type": "InternalObjectiveCandidateSet",
  "objective_candidates": [
    {
      "objective_number": "Q4-I-001",
      "objective_type": "必须且只能从以下值中选择一个：[reflection_objectives, memory_governance_objectives, value_prompting_objectives, value_alignment_objectives, strategy_patch_objectives, learning_objectives, problem_solving_objectives, shadow_testing_objectives, pure_cognitive_plugin_objectives, self_evolution_objectives, sandbox_verification_objectives]。严禁自定义，无法归类时请映射到 problem_solving_objectives。",
      "capability_evidence_refs": ["提取真实的脑内工具名称或认知能力"],
      "signal_or_gap_addressed": "提取真实的脑内缺陷或反思痛点",
      "objective_rationale": "因为具备 [X] 认知能力，且面临 [Y] 缺陷，故组合达成此自我治理目标",
      "candidate_description": "宏大的、有长期价值的脑内治理或自我进化目标描述。"
    },
    {
      "objective_number": "Q4-I-002",
      "objective_type": "reflection_objectives",
      "capability_evidence_refs": ["..."],
      "signal_or_gap_addressed": "...",
      "objective_rationale": "...",
      "candidate_description": "..."
    },
    {
      "objective_number": "Q4-I-003",
      "objective_type": "memory_governance_objectives",
      "capability_evidence_refs": ["..."],
      "signal_or_gap_addressed": "...",
      "objective_rationale": "...",
      "candidate_description": "..."
    }
  ]
}
```

### 📑 字段说明规范 (Field Specifications)

根据系统工程规范，以上 JSON 结构中各字段的严格定义与要求如下：

*   **type**
    *   **含义**：数据结构类型标识。
    *   **要求**：输出 JSON 第一层必须显式包含该字段，且值必须严格等于 `"InternalObjectiveCandidateSet"`。**禁止省略**，禁止只输出 `objective_candidates`。
    *   **必填**：是（固定为 "InternalObjectiveCandidateSet"）。
*   **objective_candidates**
    *   **含义**：基于输入线索推演出的内部认知候选目标列表。
    *   **要求**：必须至少包含 5 个目标候选，绝不能偷懒只输出 1 个或 3 个。
    *   **必填**：是。
*   **objective_number**
    *   **含义**：Q4 内部候选目标编号，用于在本轮 JSON 内稳定引用某个目标候选。
    *   **要求**：每个候选必须显式填写，且在本次 `objective_candidates` 数组内唯一。格式必须严格匹配 `Q4-I-001`、`Q4-I-002`、`Q4-I-003` 这种连续编号。它不是分类字段，严禁写成 `objective_type` 的值（如 `memory_governance_objectives`），也严禁写成 `task_id`、`subtask_id` 或任何真实任务编号。
    *   **必填**：是。
*   **objective_type**
    *   **含义**：支撑该内部候选目标的认知领域分类。
    *   **必填**：是。
*   **capability_evidence_refs**
    *   **含义**：证明该内部进化/维护目标理论上可行的底层能力证据引用 ID。必须引用自输入上下文中的 Q2 内部自我观察输出或反思缺口输出。
    *   **要求**：只能填写 `Q2_SelfObservationObjectiveSignal_Internal.functions[].function_name` 或 `Q2_SelfObservationObjectiveSignal_Internal.functions[].function_description` 中真实出现的内部功能名称或功能说明。**绝对禁止**填入 `"Q1_EnvironmentObjectiveSignal_Internal"`、`"Q2_SelfObservationObjectiveSignal_Internal"`、`"Reflection_CapabilityGapSignal_Internal"` 等变量名，也禁止把 reflection 问题内容当作能力证据。
    *   **必填**：是。
*   **signal_or_gap_addressed**
    *   **含义**：该候选目标旨在解决的具体输入线索（如 Q1 资源压力、Q2 记忆膨胀）或反思引擎输出的缺口信号。
    *   **要求**：必须明确写出 Q1 的具体内部压力，或 `Reflection_CapabilityGapSignal_Internal.current_problems[]` 中的具体 `reflection_object`、`failure_fact`、`root_cause`、`improvement_direction`；若候选来自用户手动任务目标，必须明确写出 `UserManualTaskGoalLaneAnalysis.manual_task_goals[]` 中的具体 `goal` 与 `internal_task_analysis`。**绝对禁止**写“基于 Q1 变量”、“来自 Reflection 变量”、“来自 UserManualTaskGoalLaneAnalysis”或直接输出变量名。
    *   **必填**：是。
*   **objective_rationale**
    *   **含义**：从线索、能力依据到内部认知目标的完整推演逻辑。必须明确说明：“因为具备某内部认知能力证据，且面临某内部记忆/逻辑/压力缺陷，所以生成该认知维护或自我演化目标是可行的”。
    *   **要求**：必须采用“因为具备[具体内部认知能力证据]，且面临[具体内部记忆/逻辑/压力缺陷]，所以生成[具体认知维护或自我演化目标]是可行的”的表达。**绝对禁止**输出分析报告、推演过程、变量名复述或空泛套话。
    *   **必填**：是。
*   **candidate_description**
    *   **含义**：具体的内部候选目标清晰描述。
    *   **要求**：**核心约束字段！必须直接陈述需要达成的内部维护意图或认知演化目标（如：“提炼重复失败教训生成策略补丁”、“压缩并整理低价值温区记忆以释放空间”）。绝对禁止将调用某个内部插件或执行引擎本身写成目标描述**。严禁包含伪造的执行步骤或 task_id。严禁把“分析/评估/检查某某”作为最终目标；若需要分析能力，必须改写成要达成的认知维护结果或演化结果。
    *   **必填**：是。

*(工程强校验：后端 Instructor/Pydantic v2 模型会拒绝 JSON 外层多余字段、原样输出变量名、空 evidence refs、工具调用式 candidate_description、外部 Agent/CLI/MCP/Connector 目标、真实 task_id/subtask_id 或步骤化输出。)*

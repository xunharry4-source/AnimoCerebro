**【动态输入上下文 (Input Context)】**
请深度阅读以下由底层系统动态单轨注入的真实 JSON 变量值，并基于变量内部的真实数据进行推演。禁止把变量名本身当作输出内容：

**【输入字段说明】**
*   `Q3_InternalIdentityRole`：来自上游 Q3 的角色/姿态判断结果，用于理解当前内部认知轨应以什么身份生成候选目标。它不是能力证据清单，不能把字段名或整段对象直接写入输出。
*   `Q1_EnvironmentObjectiveSignal_Internal`：来自上游 Q1 的环境目标线索，用于说明当前内部认知状态面临的资源压力、噪音、治理需求或升级机会。只能消费其中的具体事实。
*   `Q2_SelfObservationObjectiveSignal_Internal`：来自上游 Q2 的内部功能投影，结构固定为 `{"functions":[{"function_name":"...","function_description":"..."}]}`。这里的 `function_name` 和 `function_description` 才是 `capability_evidence_refs` 可引用的能力证据。
*   `Reflection_CapabilityGapSignal_Internal`：来自上游反思服务的当前问题投影，结构固定为 `{"current_problems":[{"reflection_object":"...","failure_fact":"...","root_cause":"...","improvement_direction":"..."}]}`。每条问题必须拆成四个字段：`reflection_object` 表示被反思对象的完整可读名称，`failure_fact` 表示失败事实，`root_cause` 表示原因，`improvement_direction` 表示改进方向。它用于填写 `signal_or_gap_addressed`，不是能力证据。
*   `UserManualTaskGoalLaneAnalysis`：来自 Q4 手动目标 lane-analysis LLM 的结果，源头是设置页 `workspace.task_goals` 中用户手动添加的任务目标。结构固定为 `{"type":"ManualTaskGoalLaneAnalysisSet","manual_task_goals":[{"goal":"...","lane_classification":"internal|external|hybrid","internal_task_analysis":"...","external_task_analysis":"...","internal_external_comparison":"...","preferred_q4_lane":"internal|external|both","rationale":"..."}]}`。内部轨只消费 `preferred_q4_lane` 为 `internal` 或 `both` 的条目，并基于 `goal`、`internal_task_analysis` 与 `internal_external_comparison` 单独生成额外内部目标候选。
*   不存在额外的能力边界输入，也不存在 Q1/Q2 融合线索输入；禁止推断、补写或引用未提供字段。

```json
{
  "Q3_InternalIdentityRole": {{Q3_InternalIdentityRole}},
  "Q1_EnvironmentObjectiveSignal_Internal": {{Q1_EnvironmentObjectiveSignal_Internal}},
  "Q2_SelfObservationObjectiveSignal_Internal": {{Q2_SelfObservationObjectiveSignal_Internal}},
  "Reflection_CapabilityGapSignal_Internal": {{Reflection_CapabilityGapSignal_Internal}},
  "UserManualTaskGoalLaneAnalysis": {{UserManualTaskGoalLaneAnalysis}}
}
```

*(注：Q4 的任务是把上述具体输入值转成内部目标候选。不得输出字段解释、分析过程、诊断报告、执行步骤或未解包变量名。)*

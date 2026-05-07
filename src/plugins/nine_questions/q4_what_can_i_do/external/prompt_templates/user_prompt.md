--------------------------------------------------------------------------------
**【动态输入上下文 (Input Context)】**

```json
{
  "Q3_ExternalDelegationPosture": {{Q3_ExternalDelegationPosture}},
  "Q1_EnvironmentObjectiveSignal_External": {{Q1_EnvironmentObjectiveSignal_External}},
  "Q2_SelfObservationObjectiveSignal_External": {{Q2_SelfObservationObjectiveSignal_External}},
  "Q1Q2_FusedObjectiveSignal_External": {{Q1Q2_FusedObjectiveSignal_External}},
  "Reflection_CapabilityGapSignal_External": {{Reflection_CapabilityGapSignal_External}},
  "CapabilityBoundaryEvidence_External": {{CapabilityBoundaryEvidence_External}},
  "UserManualTaskGoalLaneAnalysis": {{UserManualTaskGoalLaneAnalysis}}
}
```

**【用户手动任务目标说明】**
`UserManualTaskGoalLaneAnalysis` 来自 Q4 手动目标 lane-analysis LLM，源头是设置页 `workspace.task_goals` 中用户手动添加的任务目标。结构固定为 `{"type":"ManualTaskGoalLaneAnalysisSet","manual_task_goals":[{"goal":"...","lane_classification":"internal|external|hybrid","internal_task_analysis":"...","external_task_analysis":"...","internal_external_comparison":"...","preferred_q4_lane":"internal|external|both","rationale":"..."}]}`。外部轨只消费 `preferred_q4_lane` 为 `external` 或 `both` 的条目，并基于 `goal`、`external_task_analysis` 与 `internal_external_comparison` 单独生成额外外部目标候选。

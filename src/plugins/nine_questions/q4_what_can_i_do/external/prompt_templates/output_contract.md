--------------------------------------------------------------------------------
**【强制输出 JSON Schema】**
请严格按照以下数据结构输出，数组中必须包含至少 5 个目标候选，绝不能偷懒只输出 1 个或 3 个。禁止直接输出如 `"Q1_xxx"` 的变量名。
说明：必须生成至少 5 个目标。请确保你遍历了上下文中的所有外部工具（如 Playwright, MongoDB, Gemini 等），为每一个核心工具或每一类环境痛点都至少构思 1 个目标组合；如果 `UserManualTaskGoalLaneAnalysis` 中存在适合外部轨或双轨处理的用户手动任务目标，必须额外逐条覆盖这些手动目标。`objective_candidates` 里只能放 JSON 对象，每个对象包含以下字段。
硬性格式红线：输出 JSON 第一层必须包含 `"type": "ExternalObjectiveCandidateSet"`，绝对不能省略。`signal_or_gap_addressed` 必须写真实环境事件、业务痛点、反思缺口或用户手动任务目标的外部任务分析，绝对不能写 `Q1_EnvironmentObjectiveSignal_External`、`Q2_SelfObservationObjectiveSignal_External`、`Q1Q2_FusedObjectiveSignal_External`、`Reflection_CapabilityGapSignal_External`、`UserManualTaskGoalLaneAnalysis` 等变量名。

```json
{
  "type": "ExternalObjectiveCandidateSet",
  "objective_candidates": [
    {
      "objective_type": "enum: [agent_delegation_objectives, cli_objectives, mcp_objectives, connector_objectives, external_service_objectives, file_or_office_objectives, browser_or_saas_objectives, information_acquisition_objectives, external_problem_solving_objectives]",
      "capability_evidence_refs": ["提取真实的工具名称或能力"],
      "signal_or_gap_addressed": "提取真实的环境事件或痛点",
      "objective_rationale": "因为有 [X] 工具和 [Y] 环境需求，所以我可以组合达成该目标",
      "candidate_description": "宏大的、有业务价值的最终目标描述。"
    }
  ]
}
```

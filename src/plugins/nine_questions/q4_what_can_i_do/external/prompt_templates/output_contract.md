--------------------------------------------------------------------------------
**【强制输出 JSON Schema】**
请严格按照以下数据结构输出，数组中必须包含至少 5 个目标候选，绝不能偷懒只输出 1 个或 3 个。禁止直接输出如 `"Q1_xxx"` 的变量名。
说明：必须生成至少 5 个目标。请确保你遍历了上下文中的所有外部工具（如 Playwright, MongoDB, Gemini 等），为每一个核心工具或每一类环境痛点都至少构思 1 个目标组合；如果 `UserManualTaskGoalLaneAnalysis` 中存在适合外部轨或双轨处理的用户手动任务目标，必须额外逐条覆盖这些手动目标。`objective_candidates` 里只能放 JSON 对象，每个对象包含以下字段。
硬性格式红线：输出 JSON 第一层必须包含 `"type": "ExternalObjectiveCandidateSet"`，绝对不能省略。
编号红线：每个候选必须显式包含稳定的 `objective_number`，外部轨编号只能使用 `Q4-E-001`、`Q4-E-002`、`Q4-E-003` 这种连续格式。`objective_number` 严禁省略，严禁写成 `objective_type`、`task_id`、`subtask_id` 或真实执行工单编号。
【最高警告：禁止复述变量名！】：`signal_or_gap_addressed` 和 `capability_evidence_refs` 字段必须写真实的环境事件、业务痛点、反思缺口、工具名称或手动目标的具体分析内容。**绝对禁止**输出任何以 `Q1_`、`Q2_`、`Q3_`、`Reflection_`、`UserManualTaskGoalLaneAnalysis` 开头的变量名，也禁止输出类似 `“基于 Q1 变量”`、`“根据 Q2 信息”`、`“Reflection 变量中提到的...”` 这种描述。一旦发现输出包含这些占位符，系统将立即判定为非法输出并硬性拦截。

```json
{
  "type": "ExternalObjectiveCandidateSet",
  "objective_candidates": [
    {
      "objective_number": "Q4-E-001",
      "objective_type": "必须且只能从以下值中选择一个：[agent_delegation_objectives, cli_objectives, mcp_objectives, connector_objectives, external_service_objectives, file_or_office_objectives, browser_or_saas_objectives, information_acquisition_objectives, external_problem_solving_objectives]。严禁自定义或使用中文，无法归类时请映射到 external_problem_solving_objectives。",
      "capability_evidence_refs": ["提取真实的工具名称或能力"],
      "signal_or_gap_addressed": "提取真实的环境事件或痛点",
      "objective_rationale": "因为有 [X] 工具和 [Y] 环境需求，所以我可以组合达成该目标",
      "candidate_description": "宏大的、有业务价值的最终目标描述。"
    },
    {
      "objective_number": "Q4-E-002",
      "objective_type": "cli_objectives",
      "capability_evidence_refs": ["..."],
      "signal_or_gap_addressed": "...",
      "objective_rationale": "...",
      "candidate_description": "..."
    },
    {
      "objective_number": "Q4-E-003",
      "objective_type": "mcp_objectives",
      "capability_evidence_refs": ["..."],
      "signal_or_gap_addressed": "...",
      "objective_rationale": "...",
      "candidate_description": "..."
    }
  ]
}
```

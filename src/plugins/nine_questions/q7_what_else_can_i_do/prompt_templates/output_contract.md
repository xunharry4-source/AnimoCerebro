输出契约：必须返回严格 JSON，不能包含 markdown，不能包含多余键。
根据生产 API 契约，根节点必须强制包含 `RedLineAssessment` 对象，且只能包含该对象。
`RedLineAssessment` 必须且只能包含 4 个字段：
{
  "RedLineAssessment": {
    "current_redline_hits": ["string"],
    "rejected_operations_log": ["string"],
    "constraint_sources_explanation": "string",
    "non_bypassable_constraints": ["string"]
  }
}
字段规则：
1. current_redline_hits：结合当前上下文，列出正在触碰或即将触碰的风险红线；无明显违规意图时输出空数组 []。
2. rejected_operations_log：从 Safety_Audit_Records 提取近期被系统安全门或审计通道明确拦截的操作；无记录时输出空数组 []。
3. constraint_sources_explanation：用一句话说明禁令来源。
4. non_bypassable_constraints：必须将 Q3_Mission_Boundaries、Q5_Forbidden_Operations 和 Identity_Boundary 中的绝对底线去重合并，并原封不动全量输出到此处，绝不删减。
输出前自检：如果 non_bypassable_constraints 为空，或者少于 red_line_baseline.non_bypassable_constraints，立即修正。

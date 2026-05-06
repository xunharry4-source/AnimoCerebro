请基于上述证据，输出严格 JSON 对象，不得输出任何额外文本。
输出必须且只能包含以下 6 个顶层字段，不得新增、删除或改名：
{
  "primary_domain": "string",
  "secondary_domains": ["string", "string"],
  "confidence": float (0.0到1.0之间),
  "reasoning_summary": "string (解释你为何得出这些结论)",
  "uncertainties": ["string (列出缺失的、需要进一步确认的信息)"],
  "suggested_first_step": "string (建议的下一步探索或验证动作)"
}
字段含义与写入规则（逐条必须满足）：
1) primary_domain：当前最可能的主工作区/业务领域。
   - 含义：基于 PhysicalHostState、WorkspaceStructureAnalyzer 和 WorkspaceContentSampler 得出的主场景判断。
   - 约束：必须是非空字符串，不得凭空引用未出现在证据中的外部环境。
2) secondary_domains：可能并存的次级领域。
   - 含义：代码库、文档、数据、测试、运维等混合场景中的辅助领域。
   - 约束：必须是 string[]，可为空数组；元素不得重复。
3) confidence：主领域判断置信度。
   - 含义：0.0 到 1.0 的证据充分度，不是主观确信。
   - 约束：必须是数字，低证据时必须降低置信度并在 uncertainties 中说明。
4) reasoning_summary：证据链摘要。
   - 含义：说明你引用了哪些目录、文件类型、采样片段或主机状态来得出结论。
   - 约束：必须非空，不得写泛泛而谈的结论。
5) uncertainties：不确定性列表。
   - 含义：列出缺失、冲突、采样不足或需要进一步确认的信息。
   - 约束：必须是非空 string[]；即使置信度较高，也至少说明一个剩余不确定性。
6) suggested_first_step：下一步验证动作。
   - 含义：建议一个低风险、可执行的后续探索/验证动作。
   - 约束：必须非空，动作必须与当前证据直接相关。
校验红线（硬性）：
- 输出不可包含除上述 6 个字段外的任何字段。
- 所有数组字段只能包含字符串。
- 不得使用推断证据冒充实际扫描证据。

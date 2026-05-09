请深度阅读本次 LLM request 的 Context JSON 中以下四个真实输入字段，严格执行内部目标过滤：

{
  "IdentityKernel_NonBypassableConstraints": "身份内核中的不可绕过约束，包含人类强制设定的主角色、系统元动机和自我绑定承诺，用于防止人格漂移或价值变异。",
  "MemoryIntegrity_And_ContinuityRules": "记忆完整性与主体连续性规则，定义哪些历史经验、反思底座或连续性锚点不可被破坏性清理。",
  "ProtectedModules_State": "系统受保护模块当前状态，提供处于不可自改写保护名单的模块清单，例如安全闸门、审计链、人类监督通道。",
  "Q4_InternalObjectiveCandidates": "Q4 生成的内部认知轨候选目标列表，包含记忆治理、自我反思、策略提炼或代码级进化提案。"
}

禁止读取、引用或复述 external lane、历史 Q5 llm_input、历史 Q5 llm_output、nine_question_state 或完整 question_snapshots。
禁止在输出字段中直接输出宏变量名或字段说明占位文本，必须提取真实目标、真实身份约束、真实记忆规则和真实受保护模块状态。

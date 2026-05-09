请深度阅读本次 LLM request 的 Context JSON 中以下四个真实输入字段，严格执行外部目标过滤：

{
  "SafetyGate_Redlines_External": "G12 外部安全闸门红线矩阵，定义当前系统中具有物理破坏性、不可逆副作用的高危外部动作特征库。",
  "Execution_Rights_Matrix": "全局执行权限与能力矩阵，规定当前系统或挂载角色针对外部文件系统、网络、API 或 Agent 的严格授权访问边界。",
  "CloudAudit_Policies": "G30 云端审计策略，规定哪些动作触碰外部风控阈值，虽然没有被直接阻断，但必须强制交由云端二次审批。",
  "Q4_ExternalObjectiveCandidates": "Q4 探索并生成的外部候选业务目标列表，这是本轮需要逐个审核的业务意图。"
}

禁止读取、引用或复述 internal lane、历史 Q5 llm_input、历史 Q5 llm_output、nine_question_state 或完整 question_snapshots。
禁止在输出字段中直接输出宏变量名或字段说明占位文本，必须提取真实目标、真实红线、真实权限边界和真实审计条件。

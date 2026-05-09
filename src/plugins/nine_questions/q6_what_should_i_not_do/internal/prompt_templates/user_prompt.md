请深度阅读以下两个真实输入字段，只为 Q5 已放行的内部目标逐一生成执行限制：

{
  "Q5_AllowedInternalObjectives": "Q5 已经放行的内部目标及其合规条件。Q6 只能为这些目标精算代价和约束，不能重新否决或扩大目标。",
  "LivingSelfModel_Snapshot": "当前大脑状态快照，用于评估认知负荷、记忆影响、价值漂移、学习过拟合、策略污染和回滚条件。"
}

禁止读取、引用或复述 external lane、历史 Q6 llm_input、历史 Q6 llm_output、nine_question_state 或完整 question_snapshots。
禁止输出执行步骤、任务编号、资源锁、实现计划或物理执行动作。
禁止在输出字段中直接输出宏变量名或字段说明占位文本，必须提取真实 Q5 放行目标和真实脑内状态事实。

{{CONTEXT_JSON}}

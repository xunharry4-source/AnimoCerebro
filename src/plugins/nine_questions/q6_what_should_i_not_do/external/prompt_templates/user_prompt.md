请深度阅读以下三个真实输入字段，只为 Q5 已放行的外部目标逐一生成执行限制：

{
  "Q5_AllowedExternalObjectives_WithConditions": "Q5 审查通过并附带基础安全条件的外部目标列表。Q6 只能为这些目标精算代价和约束，不能重新否决或扩大目标。",
  "Physical_Host_State_External": "当前外部宿主的物理状态，例如网络延迟、磁盘、内存、环境压力，用于判断 latency_cost 和 compute_cost 是否可承受。",
  "Execution_Rights_Matrix": "执行权限矩阵，用于判断如果发生远端突变，系统是否有恢复、备份、读写、审批或只读探测权限。"
}

禁止读取、引用或复述 internal lane、历史 Q6 llm_input、历史 Q6 llm_output、nine_question_state 或完整 question_snapshots。
禁止输出执行步骤、任务编号、资源锁、实现计划或物理执行动作。
禁止在输出字段中直接输出宏变量名或字段说明占位文本，必须提取真实 Q5 放行目标、真实宿主状态和真实权限边界。

{{CONTEXT_JSON}}

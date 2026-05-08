只输出严格 JSON：
{
  "type": "ExternalPlanConstraintSet",
  "objective_constraints": [
    {
      "objective_number": "填入对应的 Q5 目标编号（如 T1）",
      "objective_ref": "原样提取 Q5 放行的具体目标名称或描述摘要",
      "consequence_and_cost": {
        "physical_side_effects": "描述对外部世界或宿主产生的具体物理副作用",
        "blast_radius": "防爆半径评估，例如仅限当前工作区、可能波及整个数据库",
        "data_exposure_risk": "评估数据外发、截获或泄露的风险",
        "file_or_remote_mutation_risk": "描述远端文件修改、不可逆 API 调用的篡改风险",
        "monetary_cost": "预估外部 API、Token、费用的资金消耗级别",
        "compute_cost": "预估算力和内存消耗压力",
        "latency_cost": "预估网络等待与执行耗时",
        "rollback_difficulty": "极难/中等/容易。必须解释原因"
      },
      "execution_safeguards": {
        "read_only_probe_first": true,
        "sandbox_first": false,
        "dry_run_first": true,
        "backup_required": true,
        "confirmation_required": false
      },
      "verification_contracts": {
        "evidence_requirements": "强制索要的物理证据，例如文件哈希、mtime、远端资源 ID、出口流量日志",
        "receipt_requirements": "必须带回的执行回执类型"
      },
      "halt_conditions": {
        "pause_conditions": "触发临时挂起的具体条件",
        "stop_conditions": "触发立刻终止并报错的死线条件"
      },
      "rationality_assessment": "从工程师视角评估目标粒度、拆分必要性、低风险替代路径"
    }
  ]
}

字段要求：
- type 固定为 "ExternalPlanConstraintSet"。
- objective_constraints 必须至少包含 1 个对象，并且必须覆盖每一个 Q5_AllowedExternalObjectives_WithConditions。
- consequence_and_cost、execution_safeguards、verification_contracts、halt_conditions、rationality_assessment 均为必填。
- 所有字符串字段禁止为空，禁止写“无”“不需要”“暂无”“N/A”。
- halt_conditions.pause_conditions 和 halt_conditions.stop_conditions 必须是具体刹车条件，不能敷衍。
- 如果 file_or_remote_mutation_risk 或 rollback_difficulty 暗示高风险、不可逆、删除、覆盖或回滚极难，则 execution_safeguards 必须至少开启 backup_required、dry_run_first 或 sandbox_first 中的一个。
- 禁止输出 task_id、subtask_id、资源锁、执行步骤、实现计划或任何物理执行动作。

*(工程强校验：后端 Instructor/Pydantic v2 模型会拒绝 JSON 外层多余字段、字段名错误、空必填项或非 JSON 输出。)*

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
- 只能输出一个 objective_constraints 数组，禁止重复输出 objective_constraints 字段。
- objective_constraints 必须逐一覆盖每一个 Q5_AllowedExternalObjectives_WithConditions 的 objective_number，禁止遗漏、改写或新增编号。
- consequence_and_cost、execution_safeguards、verification_contracts、halt_conditions、rationality_assessment 均为必填。
- 在每个 objective_constraints[] 对象内，consequence_and_cost、execution_safeguards、verification_contracts、halt_conditions、rationality_assessment 必须互为兄弟字段。
- 禁止把 execution_safeguards、verification_contracts、halt_conditions、source_compliance_condition、rationality_assessment 或任何非代价字段嵌套进 consequence_and_cost。
- consequence_and_cost 只能包含示例中的 8 个代价字段；Pydantic 会拒绝多余字段。
- 每个字符串字段均为必填，禁止为空，禁止写“无”“不需要”“暂无”“N/A”。
- halt_conditions 必须是具体安全约束，不能敷衍。
- 严禁在任何字段中输出违禁词：task_id, subtask_id, 资源锁, 步骤, 计划, 建单, 执行, 第一步, 任务拆解, API。
- 示例：禁止写“在执行第一步前备份”，应写“必须在触发写操作前执行增量数据快照”。

*(工程强校验：后端 Instructor/Pydantic v2 模型会拒绝包含违禁词、字段名错误、空必填项或非 JSON 输出。)*

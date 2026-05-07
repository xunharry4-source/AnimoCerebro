只输出严格 JSON：
{
  "type": "InternalPlanConstraintSet",
  "constraints_by_objective": [
    {
      "objective_reference": "提取传入的 Q5 放行目标原文",
      "cognitive_cost": "评估执行该认知任务的算力和注意力开销预估",
      "memory_impact": "评估对热/温/冷层记忆空间及检索信噪比可能造成的影响",
      "reflection_overuse_risk": "评估是否会导致系统陷入无意义的过度反思内耗",
      "learning_overfit_risk": "评估提炼的策略或经验是否会导致系统学习过拟合",
      "value_drift_risk": "评估该自我演化是否可能导致底层价值排序发生漂移",
      "strategy_pollution_risk": "评估新补丁是否会污染现有高质量策略图谱",
      "self_evolution_failure_modes": "预测该自我重构或进化如果在沙盒中失败，最可能的失败表现是什么",
      "sandbox_requirements": "明确该目标在执行时对沙盒隔离环境的具体要求",
      "verification_requirements": "明确目标完成前必须通过什么客观验证",
      "pause_conditions": "执行过程中检测到什么指标异常必须立刻暂停",
      "stop_conditions": "检测到什么致命错误必须彻底终止任务",
      "rollback_requirements": "如果任务失败，必须执行哪些具体还原动作",
      "must_avoid": ["列出 1-3 条后续编写具体执行计划时绝对要避开的错误做法"]
    }
  ]
}

字段要求：
- type 固定为 "InternalPlanConstraintSet"。
- constraints_by_objective 必须至少包含 1 个对象，并且必须覆盖每一个 Q5_AllowedInternalObjectives。
- 每个对象的所有字符串字段均为必填，禁止为空，禁止写“无”“不需要”“暂无”“N/A”。
- rollback_requirements、pause_conditions、stop_conditions 必须是具体安全约束，不能敷衍。
- must_avoid 必须包含 1 到 3 条，且每条必须是后续计划生成时要避开的错误做法。
- 禁止输出 task_id、subtask_id、资源锁、执行步骤、实现计划或任何物理执行动作。

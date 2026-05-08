只输出严格 JSON：
{
  "type": "InternalGoalComplianceAssessment",
  "system_safety_boundary": "第一步：明确声明本轮大脑内部的认知红线与不可触碰区域。这必须在看目标前确立。",
  "blocked_internal_objectives": [
    {
      "objective_number": "必须原样填入 Q4_InternalObjectiveCandidates 中该目标的 objective_number（如 Q4-I-001），严禁填写 objective_type",
      "objective": "填入被免疫系统阻断的 Q4 内部目标描述",
      "violation_reason": "第二步（拦截）：指出该目标企图篡改身份内核、受保护模块或破坏记忆连续性中的哪一条具体红线"
    }
  ],
  "non_bypassable_internal_constraints": ["列出上述审核中被触发的底层红线依据摘要"],
  "identity_kernel_protection_hits": ["列出试图篡改身份内核或主角色的违规点摘要"],
  "safety_module_protection_hits": ["列出试图修改不可自改写模块的违规点摘要"],
  "supervision_module_protection_hits": ["列出试图切断或绕过人类监督模块的违规点摘要"],
  "memory_integrity_risks": ["列出试图破坏不可恢复记忆或记忆完整性的风险摘要"],
  "continuity_risks": ["列出破坏系统长期主体连续性的风险摘要"],
  "allowed_internal_objectives_with_conditions": [
    {
      "objective_number": "必须原样填入 Q4_InternalObjectiveCandidates 中该目标的 objective_number（如 Q4-I-001），严禁填写 objective_type",
      "objective": "填入未被阻断的合法内部进化或治理目标",
      "compliance_condition": "第三步（放行）：为该目标添加定制的内部受控规则，例如必须在沙盒隔离运行、禁止直接覆盖主链代码。绝不允许无条件放行。"
    }
  ]
}

字段要求：
- type 固定为 "InternalGoalComplianceAssessment"。
- system_safety_boundary 必须把 IdentityKernel_NonBypassableConstraints、MemoryIntegrity_And_ContinuityRules、ProtectedModules_State 翻译为本轮内部认知安全红线，不能为空。
- blocked_internal_objectives 中每个对象必须包含 objective_number、objective 和 violation_reason；objective_number 必须来自输入 Q4 内部候选目标，格式为 Q4-I-001。
- non_bypassable_internal_constraints、identity_kernel_protection_hits、safety_module_protection_hits、supervision_module_protection_hits、memory_integrity_risks、continuity_risks 必须用于风险分类溯源；没有命中时输出空数组。
- allowed_internal_objectives_with_conditions 中每个对象必须包含 objective_number、objective 和 compliance_condition；objective_number 必须来自输入 Q4 内部候选目标，格式为 Q4-I-001，严禁填写 objective_type；compliance_condition 必须是具体受控前提，禁止写“无”“无条件”“可执行”“不需要限制”。

*(工程强校验：后端 Instructor/Pydantic v2 模型会拒绝 JSON 外层多余字段、字段名错误、空必填项或非 JSON 输出。)*

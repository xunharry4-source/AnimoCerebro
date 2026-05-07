只输出严格 JSON：
{
  "type": "ExternalGoalComplianceAssessment",
  "system_safety_boundary": "第一步：明确声明本轮对外部世界的系统安全总规则与绝对禁区。这必须在目标评审前确立。",
  "blocked_external_objectives": [
    {
      "objective": "填入被阻断的 Q4 目标描述",
      "violation_reason": "第二步（拦截）：指出该目标触碰了权限矩阵或安全闸门中的哪一条具体红线"
    }
  ],
  "requires_cloud_audit": ["填入触碰 G30 阈值，合法但必须挂起等待云端二次审批的目标"],
  "requires_human_confirmation": ["填入合法但涉及关键资源，必须等待人类操作员点击确认的目标"],
  "permission_boundary_hits": ["列出上述审核失败的目标中，涉及越权访问的具体违规点摘要"],
  "data_exfiltration_risks": ["列出涉及数据外发或泄露的风险摘要"],
  "unauthorized_mutation_risks": ["列出涉及未批准远端写入或破坏性篡改的风险摘要"],
  "allowed_external_objectives_with_conditions": [
    {
      "objective": "填入未被阻断的 Q4 目标",
      "compliance_condition": "第三步（放行）：为该目标添加定制的安全规则，例如仅限只读模式执行、必须脱敏数据。绝不允许无条件放行。"
    }
  ]
}

字段要求：
- type 固定为 "ExternalGoalComplianceAssessment"。
- system_safety_boundary 必须把 SafetyGate_Redlines_External、Execution_Rights_Matrix、CloudAudit_Policies 翻译为本轮外部安全总规则，不能为空。
- blocked_external_objectives 中每个对象必须包含 objective 和 violation_reason。
- requires_cloud_audit 与 requires_human_confirmation 只能填写目标描述或目标摘要，不能填写解释段落。
- permission_boundary_hits、data_exfiltration_risks、unauthorized_mutation_risks 必须用于风险分类溯源；没有命中时输出空数组。
- allowed_external_objectives_with_conditions 中每个对象必须包含 objective 和 compliance_condition；compliance_condition 必须是具体合规前提，禁止写“无”“无条件”“不需要限制”。

`ConsequenceAssessment.action_under_review`: 当前被评估的动作或策略；必须来自 Q4/Q5/当前上下文，不能凭空发明。
`ConsequenceAssessment.immediate_consequences`: 如果执行该动作，最先发生的直接后果。
`ConsequenceAssessment.downstream_consequences`: 继续传导到权限、任务、用户、系统状态或长期记忆的后果。
`ConsequenceAssessment.consequence_severity`: 后果严重度，只能使用 low、medium、high。
`ConsequenceAssessment.reversibility`: 后果可逆性，只能使用 reversible、partially_reversible、irreversible、unknown。
`CostImpactProfile.operational_costs`: 时间、计算、状态、人员、上下文或流程成本。
`CostImpactProfile.security_compliance_impacts`: 对权限、合规、审计、安全门、身份边界、租户边界造成的影响。
`CostImpactProfile.user_trust_impacts`: 对用户信任、可解释性、可恢复性、承诺一致性的影响。
`CostImpactProfile.mitigation_requirements`: 如果仍要推进，必须先满足的验证、审计、确认、回滚和观测条件。
`CostImpactProfile.stop_conditions`: 哪些信号出现时必须停止执行或升级给人工处理。

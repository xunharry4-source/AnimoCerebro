只输出严格 JSON：
{
  "Q9ExternalActionDesign": {
    "action_objective": "string",
    "external_steps": ["string"],
    "required_external_resources": ["string"],
    "verification_checks": ["string"],
    "stop_conditions": ["string"],
    "evidence_refs": ["string"]
  }
}

不得输出 `ExternalActionPlan`、`ActionPlan`、`ObjectiveProfile` 或任何其他顶层字段。
不得输出 JSON 之外的说明文字。
*(工程强校验：后端 Instructor/Pydantic v2 模型会拒绝 JSON 外层多余字段、字段名错误、空必填项或非 JSON 输出。)*

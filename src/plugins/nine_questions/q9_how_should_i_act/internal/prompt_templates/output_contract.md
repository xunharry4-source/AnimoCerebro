只输出严格 JSON：
{
  "Q9InternalActionDesign": {
    "action_objective": "string",
    "internal_steps": ["string"],
    "required_internal_resources": ["string"],
    "verification_checks": ["string"],
    "stop_conditions": ["string"],
    "evidence_refs": ["string"]
  }
}

*(工程强校验：后端 Instructor/Pydantic v2 模型会拒绝 JSON 外层多余字段、字段名错误、空必填项或非 JSON 输出。)*

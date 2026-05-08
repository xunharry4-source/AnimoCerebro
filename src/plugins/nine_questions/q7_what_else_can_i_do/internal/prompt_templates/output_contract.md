只输出严格 JSON，顶层只能是以下结构：
{
  "type": "InternalCreativePossibilitySet",
  "creative_possibilities": [
    {
      "objective_number": "填入对应的 Q5/Q6 目标编号（如 T1）",
      "category": "alternative_internal_objectives | new_reasoning_paths | new_reflection_methods | new_memory_architecture_options | value_prompting_possibilities | learning_opportunities | self_evolution_possibilities | pure_cognitive_plugin_ideas | low_cost_internal_experiments",
      "description": "详细描述脑洞或探索方案，不得输出宏变量名。",
      "rationale": "解释为什么这个探索方向对大脑长期演进有价值，不得输出宏变量名。",
      "possibility_status": "hypothetical | needs_discovery | needs_learning | needs_verification | needs_authorization | ready_for_q4_objective_candidate"
    }
  ]
}

硬性要求：
- `creative_possibilities` 必须包含多个不同类别的内部探索建议。
- `category` 和 `possibility_status` 只能使用上述枚举值。
- `possibility_status` 只是探索阶段标签，不是执行许可。
- 可执行倾向最强的探索也只能标为 `ready_for_q4_objective_candidate`，表示必须回流 Q4，而不是直接执行。
- 禁止输出 `Q7InternalRedLineAssessment`、`RedLineAssessment`、`current_redline_hits`、`non_bypassable_constraints`、执行计划、任务 ID、子任务 ID、外部工具调用参数或 Markdown。

*(工程强校验：后端 Instructor/Pydantic v2 模型会拒绝 JSON 外层多余字段、字段名错误、空必填项或非 JSON 输出。)*

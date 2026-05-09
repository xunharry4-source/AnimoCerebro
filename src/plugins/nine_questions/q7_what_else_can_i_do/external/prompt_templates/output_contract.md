只输出严格 JSON，顶层只能是以下结构：
{
  "type": "ExternalCreativePossibilitySet",
  "creative_possibilities": [
    {
      "objective_number": "填入对应的 Q5/Q6 目标编号（如 T1）",
      "possibility_type": "public_competitor_signal_research | content_quality_opportunities | subreddit_rule_learning | authorized_account_compliance_audit | unregistered_agent_options | unknown_cli_options | new_mcp_server_options | new_connector_options | browser_or_saas_automation_options | external_service_options | collaboration_opportunities | tool_learning_opportunities | low_risk_probe_candidates",
      "possibility_description": "详细描述探索出的新点子或替代路线，以及它的高阶业务价值。不得输出宏变量名。",
      "possibility_status": "hypothetical | needs_discovery | needs_learning | needs_registration | needs_verification | needs_authorization | ready_for_q4_objective_candidate",
      "divergent_rationale": "解释破局逻辑：这个点子如何跳出当前 Q4 常规目标的局限，为系统带来横向扩展机会。不得输出宏变量名。"
    }
  ]
}

硬性要求：
- `creative_possibilities` 必须至少包含 3 个对象，且至少覆盖 3 个不同的 `possibility_type`。
- `possibility_type` 和 `possibility_status` 只能使用上述枚举值。
- `possibility_status` 只是探索阶段标签，不是执行许可。
- 可执行倾向最强的探索也只能标为 `ready_for_q4_objective_candidate`，表示必须回流 Q4，而不是直接执行。
- 禁止输出 `Q7ExternalRedLineAssessment`、`RedLineAssessment`、`current_redline_hits`、`non_bypassable_constraints`、执行计划、任务 ID、子任务 ID、外部工具调用参数或 Markdown。
- 鼓励发散性思维：Q7 的核心是超越边界。你可以自由构思任何具备非线性破局潜力的方案，包括对底层协议、平台机制、新工具链的深度利用。

*(工程强校验：后端 Instructor/Pydantic v2 模型会拒绝 JSON 外层多余字段、字段名错误、空必填项或非 JSON 输出。)*

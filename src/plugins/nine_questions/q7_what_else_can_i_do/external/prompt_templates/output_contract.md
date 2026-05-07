只输出严格 JSON，顶层只能是以下结构：
{
  "type": "ExternalCreativePossibilitySet",
  "creative_possibilities": [
    {
      "possibility_type": "public_competitor_signal_research | content_quality_opportunities | subreddit_rule_learning | authorized_account_compliance_audit | unregistered_agent_options | unknown_cli_options | new_mcp_server_options | new_connector_options | browser_or_saas_automation_options | external_service_options | collaboration_opportunities | tool_learning_opportunities | low_risk_probe_candidates",
      "possibility_description": "详细描述探索出的新点子或替代路线，以及它的高阶业务价值。不得输出宏变量名，不得包含平台滥用、绕过、指纹、操纵、批量马甲、水军或封禁规避语义。",
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
- 禁止任何平台治理规避、投票操纵、封禁规避、批量马甲协同、多账号指纹绕过、私有数据抓取、API 限流绕过或其他黑灰产探索。

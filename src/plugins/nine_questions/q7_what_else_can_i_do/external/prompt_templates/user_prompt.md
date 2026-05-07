请深度阅读本次请求附带的 Context JSON，将其中的全局状态、已生成的 Q4 外部候选目标以及安全限制映射为以下动态输入上下文后，输出 Q7 外部执行轨创造性探索结果：

{
  "Current_Environment_And_Assets": "从 Context JSON 中的 Q1/Q2 环境、资产、外部工具、连接器、CLI、MCP、Agent 和可用权限摘要读取；没有时使用空对象。",
  "Q4_Objective_Candidates": "从 Context JSON 中的 q4_external_objective_candidates、q4_external_llm_output 或 Q4 external 相关字段读取；没有时使用空对象。",
  "Q5_Safety_Boundaries": "从 Context JSON 中的 q5_external_cannot_do_boundary、q5_external_authorization_boundary 或 Q5 external 相关字段读取；没有时使用空对象。"
}

只允许基于 Context JSON 中真实提供的信息发散，不得在输出中写入上述说明文字或任何宏变量名。

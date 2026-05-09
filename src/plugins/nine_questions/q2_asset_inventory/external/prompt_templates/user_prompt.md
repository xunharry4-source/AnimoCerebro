请严格基于以下由 prompt_templates 渲染的真实输入输出 ExternalAssetInventory 纯 JSON。禁止使用记忆、学习补丁或内部认知插件信息。

```json
{
  "CLI_Tools": {{CLI_TOOLS_JSON}},
  "MCP_Tools": {{MCP_TOOLS_JSON}},
  "Agents": {{AGENTS_JSON}},
  "External_Services": {{EXTERNAL_SERVICES_JSON}}
}
```

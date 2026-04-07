# Model Provider: OpenAI Compatible Gateway

该模型提供商用于通过 OpenAI SDK 的 `chat.completions` 接口调用一个 OpenAI 兼容网关（例如本地模型路由器、代理网关等）。

配置来源：
- `config/provider_tools.yml` -> `providers.openai_compat`

默认行为：
- 若不显式传 `model` 参数，则使用 `providers.openai_compat.default_model`
- 你可以在测试接口里传入 `model` 来切换实际调用的大模型（例如在同一个网关后端切换 Gemini / GPT / Claude 适配器）

审计与统计：
- 每次调用会写入 Transcript（MODEL_PROVIDER_INVOKED / COMPLETED / FAILED）
- COMPLETED 事件会带 `token_usage`（若下游网关返回 usage）

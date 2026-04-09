# Gemini 推理底座插件功能说明

- 功能键：`model_provider:gemini`
- 显示名称：Gemini 推理底座
- 所属插件家族：`model_providers`
- 实现目录：`src/plugins/model_providers/`
- 并发模式：单插件
- 当前用途：为主脑关键阶段提供真实大模型推断能力
- 默认/回退方向：回退到上一个稳定正式版模型插件；若无可用插件，主脑 fail-closed
- 管理红线：绝对禁止规则兜底，绝对禁止返回假 JSON 冒充模型结果
- 家族级规范：
  - [Model Providers DEVELOPMENT_GUIDE](src/plugins/model_providers/DEVELOPMENT_GUIDE.md)


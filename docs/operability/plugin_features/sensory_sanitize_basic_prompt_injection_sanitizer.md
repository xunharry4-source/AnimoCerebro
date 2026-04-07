# 提示注入净化插件功能说明

- 功能键：`sensory_sanitize:basic_prompt_injection_sanitizer`
- 显示名称：提示注入净化
- 所属插件家族：`sensory`
- 实现目录：`src/plugins/sensory/`
- 并发模式：单插件
- 当前用途：清洗原始输入并标记注入风险
- 默认/回退方向：回退到系统默认净化器；若无净化器，则原始信号绝不允许进入主脑
- 管理红线：净化链不可旁路
- 家族级规范：
  - [Sensory DEVELOPMENT_GUIDE](/Users/harry/Documents/git/AnimoCerebro/src/plugins/sensory/DEVELOPMENT_GUIDE.md)


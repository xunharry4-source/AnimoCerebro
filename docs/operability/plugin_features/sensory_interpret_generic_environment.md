# 环境事件解释插件功能说明

- 功能键：`sensory_interpret:generic_environment`
- 显示名称：环境事件解释
- 所属插件家族：`sensory`
- 实现目录：`src/plugins/sensory/`
- 并发模式：单插件
- 当前用途：把净化后的输入翻译成结构化环境事件
- 默认/回退方向：回退到默认解释器；若无解释器，则感官链显式降级
- 管理红线：解释器输入必须是 `SanitizedSignal`
- 家族级规范：
  - [Sensory DEVELOPMENT_GUIDE](src/plugins/sensory/DEVELOPMENT_GUIDE.md)


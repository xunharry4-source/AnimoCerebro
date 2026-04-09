# 市场影响预测插件功能说明

- 功能键：`simulation:market`
- 显示名称：市场影响预测
- 所属插件家族：`simulation`
- 实现目录：`src/plugins/simulation/`
- 并发模式：单插件
- 当前用途：对市场相关后果做专域预演
- 默认/回退方向：回退到通用思维沙盒 `ThoughtSandbox`
- 管理红线：最终结论若依赖 LLM，必须 fail-closed
- 家族级规范：
  - [Simulation DEVELOPMENT_GUIDE](src/plugins/simulation/DEVELOPMENT_GUIDE.md)


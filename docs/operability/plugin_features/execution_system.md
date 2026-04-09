# 系统执行域插件功能说明

- 功能键：`execution:system`
- 显示名称：系统执行域
- 所属插件家族：`execution`
- 实现目录：`src/plugins/execution/`
- 并发模式：单插件
- 当前用途：对本地系统能力进行受控执行
- 默认/回退方向：回退到系统默认正式版执行器；无可用执行器时 fail-closed
- 管理红线：不可旁路 SafetyGate
- 家族级规范：
  - [Execution DEVELOPMENT_GUIDE](src/plugins/execution/DEVELOPMENT_GUIDE.md)


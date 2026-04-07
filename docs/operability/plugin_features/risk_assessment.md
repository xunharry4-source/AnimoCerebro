# 风险评估插件功能说明

- 功能键：`risk_assessment`
- 显示名称：风险评估
- 所属插件家族：`cognitive`
- 实现目录：`src/plugins/cognitive/`
- 并发模式：单插件
- 当前用途：对候选路径做风险比较，输出保守替代建议
- 默认/回退方向：回退到同 `behavior_key` 下的上一个正式版本，或系统默认版本
- 管理红线：启用新版本时必须自动挂起同功能已激活旧版本
- 家族级规范：
  - [Cognitive DEVELOPMENT_GUIDE](/Users/harry/Documents/git/AnimoCerebro/src/plugins/cognitive/DEVELOPMENT_GUIDE.md)


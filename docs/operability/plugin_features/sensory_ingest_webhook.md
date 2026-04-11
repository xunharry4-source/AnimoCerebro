# Webhook 信号摄取插件功能说明

- 功能键：`sensory_ingest:webhook`
- 显示名称：Webhook 信号摄取
- 所属插件家族：`sensory`
- 实现目录：`src/plugins/sensory/`
- 并发模式：单插件
- 当前用途：从 Webhook 等入口摄取原始信号
- 默认/回退方向：回退到系统默认摄取器；若无安全摄取器，则整条感官链阻断
- 管理红线：摄取器不能假装自己完成了净化和解释
- 家族级规范：
  - [Sensory DEVELOPMENT_GUIDE](/Users/harry/Documents/git/AnimoCerebro/src/plugins/sensory/DEVELOPMENT_GUIDE.md)


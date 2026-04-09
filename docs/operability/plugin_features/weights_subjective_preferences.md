# 主观权重偏好插件功能说明

- 功能键：`weights:subjective_preferences`
- 显示名称：主观权重偏好
- 所属插件家族：`weights`
- 实现目录：`src/plugins/weights/`
- 并发模式：多插件候选，但同一时刻只有一个激活权重包
- 当前用途：调节风险、成本、创意、连续性等主观偏好
- 默认/回退方向：回退到 `default_conservative_weight`
- 管理红线：审计拒绝后必须立即回退
- 家族级规范：
  - [Weights DEVELOPMENT_GUIDE](src/plugins/weights/DEVELOPMENT_GUIDE.md)


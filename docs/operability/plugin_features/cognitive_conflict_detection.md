# 认知冲突监控插件功能说明

- 功能键：`cognitive_conflict_detection`
- 显示名称：认知冲突监控
- 所属插件家族：`cognitive`
- 实现目录：`src/plugins/cognitive/`
- 并发模式：多插件
- 当前用途：并发发现语义冲突、预算冲突等认知风险
- 默认/回退方向：保留其他激活检测器；若全部失效，则回退到默认正式版检测器集合
- 管理红线：所有检测器都只允许输出内部冲突报告，禁止直接驱动执行动作
- 家族级规范：
  - [Cognitive DEVELOPMENT_GUIDE](src/plugins/cognitive/DEVELOPMENT_GUIDE.md)


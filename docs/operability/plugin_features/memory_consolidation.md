# memory_consolidation

功能键：`memory_consolidation`

显示名称：离线记忆巩固

所属插件家族：`cognitive`

实现目录：`src/plugins/cognitive/`

并发模式：多插件并发 (`supports_multiple_plugins = true`)

当前用途：
- 在睡眠整理、反思后处理、记忆治理复核和待办清理阶段并行分析记忆片段
- 提取可升格的经验候选
- 清理可遗忘的低价值噪音
- 为大模型生成高价值压缩摘要提供结构化输入

默认/回退方向：
- 默认分析插件：`failure-mode-cluster`
- 默认清理插件：`expired-assumption-cleaner`
- 若大模型调用失败，本次巩固周期必须失败并退避，绝不允许用字符串截断或正则替代语义压缩

管理红线：
- 只能离线运行，严禁阻塞在线热路径
- 严禁清理 `identity_role_pack`、`identity_constraint_pack`、`identity_experience_pack`
- Worker 提交结果前必须校验 `brain_scope`、`lease_id` 和 `snapshot_version`

家族级参考：
- [src/plugins/cognitive/DEVELOPMENT_GUIDE.md](/Users/harry/Documents/git/AnimoCerebro/src/plugins/cognitive/DEVELOPMENT_GUIDE.md)

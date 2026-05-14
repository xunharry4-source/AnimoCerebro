请基于随请求传入的 Context JSON 输出 Q9 external action design。
只读取 `Q8_ExternalObjectiveProfile.objective_profile` 与 `Q8_ExternalObjectiveProfile.task_queue`。
不要读取、复述或生成 Q1/Q2/Q3/Q4/Q5/Q6/Q7 的独立内容；Q9 的上游事实只能来自 Q8 public service。
`action_objective` 必须承接 `current_mission` 或首个可执行的 Q8 task title。
`external_steps` 必须包含外部执行前的权限/安全/回执检查，不能绕过 Q8 public output 中的 pause/escalation 条件。
`required_external_resources` 必须优先逐字继承 Q8 task_queue 中的 `required_capabilities` 或等价的真实执行能力名。
如果资源是外部连接器，`external_connector:<id>` 只能表示执行方 owner，不能单独作为可执行能力；必须同时给出该连接器 registry 中声明的具体业务 capability。
例如 create/update/delete/read/import/inspect 等动作必须输出对应 registry capability 字符串；如果 Q8 public output 没有给出可验证 capability，则在 `stop_conditions` 中要求补齐能力，不得编造。

请基于随请求传入的 Context JSON 输出 Q9 external action design。
只读取 `Q8_ExternalObjectiveProfile.objective_profile` 与 `Q8_ExternalObjectiveProfile.task_queue`。
不要读取、复述或生成 Q1/Q2/Q3/Q4/Q5/Q6/Q7 的独立内容；Q9 的上游事实只能来自 Q8 public service。
`action_objective` 必须承接 `current_mission` 或首个可执行的 Q8 task title。
`external_steps` 必须包含外部执行前的权限/安全/回执检查，不能绕过 Q8 public output 中的 pause/escalation 条件。

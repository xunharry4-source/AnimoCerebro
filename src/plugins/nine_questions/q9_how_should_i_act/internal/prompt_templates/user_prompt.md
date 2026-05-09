请基于随请求传入的 Context JSON 输出 Q9 internal action design。
只读取 `Q8_InternalObjectiveProfile.objective_profile` 与 `Q8_InternalObjectiveProfile.task_queue`。
不要读取、复述或生成 Q1/Q2/Q3/Q4/Q5/Q6/Q7 的独立内容；Q9 的上游事实只能来自 Q8 public service。
`action_objective` 必须承接 `current_mission` 或首个可执行的 Q8 task title。
`internal_steps` 必须是内部认知步骤，不能包含 CLI、MCP、connector、Agent、HTTP、数据库写入或远端副作用。

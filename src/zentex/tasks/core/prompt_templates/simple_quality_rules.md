1. 每个子任务必须是可执行动作，不得空泛。
2. `task_type` 固定为 `cognitive_step`。
3. 依赖关系必须合理，不得循环依赖。
4. `estimated_duration` 必须在 30-240 分钟之间。
5. `priority` 只能是 `high`、`medium`、`low`。
6. `coordination_mode` 必须与执行方式匹配。
7. 只返回 JSON，不要输出额外解释。

综合判断，输出严格 JSON。
顶层只能包含：
- `objective_profile`
- `task_queue`

`objective_profile` 必须包含以下字段：
- `current_mission`
- `primary_objectives`
- `secondary_objectives`
- `completion_conditions`
- `pause_conditions`
- `escalation_conditions`
- `current_phase_tasks`
- `priority_order`

`task_queue` 必须是对象，且只能包含：
- `next_self_tasks`
- `blocked_self_tasks`
- `proactive_actions`

禁止返回旧字段或旧结构：
- 不要使用 `main_objective`
- 不要使用 `rationale`
- 不要使用 `constraints_adherence`
- 不要使用 `derived_capabilities`
- 不要把 `task_queue` 输出成数组
- 不要输出 Q9 的 `evaluation_profile`
- 不要输出 Q9 的 `evolution_profile`
- 不要输出 Q9 的 `escalation_profile`
- 不要输出任何解释文字、markdown、代码块

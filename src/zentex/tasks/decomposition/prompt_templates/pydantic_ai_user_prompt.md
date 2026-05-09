将下面 mission 拆成任务中心可落库执行的最小颗粒度子任务。
每个子任务必须只包含一个不可再拆的动作；不能把“分析并执行并验证”合并在一个子任务里。
每个子任务必须带验收条件 acceptance_criteria；如果需要资源，写入 required_resources。
task_type 只能使用 cognitive_step、agent_delegation、system_action、intervention。
coordination_mode 只能使用 sequential、parallel、bundle。
mission_title: {{MISSION_TITLE}}
mission_content: {{MISSION_CONTENT}}
输出示例：
{"decomposition_goal":"检查 CSV 表头","granularity_policy":"single_atomic_operation_per_subtask","subtasks":[{"local_id":"step-1","title":"检查文件存在","task_type":"system_action","content":"确认目标 CSV 文件路径存在。","objective":"获得文件存在性的证据。","acceptance_criteria":["公开查询或执行回执证明文件存在"],"required_resources":["local_file_read"],"depends_on":[],"coordination_mode":"sequential"},{"local_id":"step-2","title":"读取表头","task_type":"system_action","content":"读取 CSV 文件第一行表头。","objective":"获得字段名列表。","acceptance_criteria":["执行回执包含表头字段列表"],"required_resources":["local_file_read"],"depends_on":["step-1"],"coordination_mode":"sequential"}]}
{{MEMORY_CONTEXT}}

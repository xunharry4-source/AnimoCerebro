## 硬性约束（必须严格遵守）

- 输出必须是合法 JSON，顶层 key 为 `subtasks`（数组）
- 子任务数量必须在 {{MIN_SUBTASKS}}–{{MAX_SUBTASKS}} 之间
- 每个子任务必须包含以下字段（缺一不可）：
  - `local_id`：唯一标识，格式 step-1, step-2, …（不可重复）
  - `title`：子任务标题（简洁，不超过 50 字）
  - `task_type`：枚举之一 — Union[cognitive_step, Union[agent_delegation], Union[system_action], intervention] | mission
  - `content`：子任务描述（具体可执行，不超过 200 字）
  - `objective`：成功标准（不超过 100 字）
  - `requirements`：前置条件列表（字符串数组，可为空数组）
  - `depends_on`：依赖的 local_id 列表（只能引用本批次 local_id，可为空数组）
  - `coordination_mode`：枚举之一 — Union[parallel, bundle] | sequential
- 不得凭空发明能力；requirements 必须是可验证的具体条件
- 请直接返回 JSON，不要包含任何额外解释文字

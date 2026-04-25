# 社交发布项目技能文档

## 文档用途

说明本项目当前具备的 X、Reddit、GitHub 社交发布能力、入口文件、依赖条件和真实性边界。

## 主要职责

- 定义 X / Reddit / GitHub 发帖相关技能模块。
- 标明每个技能依赖的真实运行条件。
- 说明哪些结果可以作为成功证据，哪些只能作为辅助日志。

## 不负责

- 不声明真实发帖已经成功。
- 不用 fixture、mock、示例 URL 冒充真实平台结果。
- 不绕过 X、Reddit、GitHub 的登录、CAPTCHA、风控、权限或社区规则。

## 技能清单

测试文件和真实调用方式见：

- `Agent/docs/social_posting/TESTING.md`

Agent 代码边界：

- 发布链路必须使用 `Agent/` 下自己的代码。
- 禁止在 Agent 发布链路中 `import zentex.*`。
- 禁止在 Agent 发布链路中把 `src/` 注入 `sys.path`。
- LLM 调用入口为 `Agent/local_llm_client.py` 与 `Agent/posting_workflows/llm_client.py`。

### 1. 浏览器会话技能

入口文件：

- `Agent/core_agents/start_agents.py`
- `Agent/browser_automation/browser_automation.py`
- `Agent/browser_automation/test_auto_stealth_wait.py`

能力：

- 启动 Playwright / Chrome 持久化上下文。
- 使用已有 profile/cookies 维持登录状态。
- 为后续 X / Reddit 节点提供真实 browser page。

真实性要求：

- 必须使用真实浏览器页面。
- 登录状态必须由页面实际状态确认，不能只依赖 cookies 文件存在。

### 2. Reddit 智能发帖技能

入口文件：

- `Agent/social_promotion/reddit_smart_poster.py`
- `Agent/run_reddit_smart_poster_real.py`

能力：

- 打开 subreddit 发帖页。
- 填写标题和正文。
- 检查 Flair 是否必选。
- Flair 非必选时跳过选择。
- Flair 必选时调用视觉识别器选择 Flair。
- 提交后只接受 Reddit permalink + 主动打开验证作为成功。

真实性要求：

- 只有 `post_custom_content_with_evidence()` 返回 `success=True` 且包含 `post_url`、`trace_id`、`verified_at`、`verification_source` 时，才允许记录为真实成功。
- 旧 `bool` 入口只能作为兼容层，不能作为完整证据。
- 真实入口测试只运行 `Agent/run_reddit_smart_poster_real.py`，结果写入 `Agent/data/reddit_smart_poster_last_result.json`。

### 3. Reddit 视觉识别技能

入口文件：

- `Agent/reddit_visual_recognizer.py`

能力：

- OCR/DOM 检查 Flair 弹窗。
- 选择 Flair 并验证页面上已经应用。
- 点击 Reddit 提交按钮。
- 提交后分析 URL、弹窗和页面错误。

真实性要求：

- 弹窗文字不是成功证据。
- 成功必须落到 Reddit 帖子 permalink。

### 4. Reddit 弹窗 LLM 翻译与判断技能

入口文件：

- `Agent/reddit_popup_llm_interpreter.py`
- `Agent/reddit_popup_llm_prompt.py`

能力：

- 将 Reddit 中英文弹窗交给激活态 LLM。
- 输出中文摘要、错误分类、是否可重试、是否需要 Flair。

真实性要求：

- LLM provider 不可用时必须 fail-closed。
- 禁止使用静态关键词或规则链冒充 LLM 语义判断。

### 5. 主动成功验证技能

入口文件：

- `Agent/posting_workflows/active_post_verifier.py`
- `Agent/posting_workflows/verification_gate.py`

能力：

- 主动打开 X / Reddit permalink。
- 验证页面仍停留在帖子 URL。
- 验证页面正文包含预期标题或内容。
- 校验真实证据文件 `Agent/data/real_posting_success_evidence.json`。

真实性要求：

- 没有 permalink、trace_id、verified_at、verification_source 时，必须判定未完成。

### 6. LangGraph 节点编排技能

入口目录：

- `Agent/posting_workflows/`

能力：

- 将 X / Reddit 发帖拆成节点。
- 在节点间传递状态和证据。
- 每个关键节点写入 evidence。
- 失败后进入修正/重试路径。

真实性要求：

- 节点成功不等于真实发帖成功。
- 只有最终主动验证节点成功，才允许更新成功文档或表格。

### 7. GitHub Discussions 发帖技能

入口文件：

- `Agent/social_promotion/github_smart_poster.py`
- `Agent/posting_workflows/github/`
- `Agent/run_github_discussion_post_real.py`

默认目标：

- `https://github.com/xunharry4-source/AnimoCerebro`
- `https://github.com/xunharry4-source/AnimoCerebro/discussions`
- 规范化 repo：`xunharry4-source/AnimoCerebro`

能力：

- 使用 `GITHUB_TOKEN` 调用 GitHub GraphQL API。
- 查询目标仓库真实 Discussion categories。
- 创建 Discussion 作为 GitHub 平台发帖。
- 创建后主动读回同一个 Discussion，验证标题、正文、discussion number 和 `url`。
- 输出 `post_url`、`trace_id`、`verified_at`、`verification_source=github_graphql_discussion_get`。

真实性要求：

- 没有 `GITHUB_TOKEN` 时必须失败。
- 仓库没有启用 Discussions 或没有可用 category 时必须失败。
- 请求指定的 category 不存在时必须失败。
- GraphQL 创建或读回验证不通过时必须失败。
- 只支持 Discussion；Issue、Release、PR 发帖不在当前范围内。
- 真实运行脚本需要 `GITHUB_TOKEN`，结果写入 `Agent/data/github_discussion_post_last_result.json`。

## 当前真实状态

- Reddit Flair 必选检测：已加入入口逻辑。
- Reddit 真实发帖成功：已通过只读 permalink 主动验证拿到单平台证据；全平台闸门仍需 X 证据。
- X 真实发帖成功：未验证。
- GitHub Discussions 真实发帖成功：已验证，证据文件为 `Agent/data/github_discussion_post_last_result.json`，真实 URL 为 `https://github.com/xunharry4-source/AnimoCerebro/discussions/2`。
- `Agent/test_real_posting_success_gate.py`：用于阻止无证据时宣称真实成功。

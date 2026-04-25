# 社交发布测试与真实调用说明

## 文档用途

说明 X、Reddit、GitHub 三个平台的测试文件地址、真实调用方式、结果文件和真实性判定标准。

## 主要职责

- 区分契约测试、夹具测试和真实平台运行。
- 给出每个平台的实际调用命令。
- 标明哪些文件可以作为真实证据，哪些只能作为代码回归证据。

## 不负责

- 不声明未验证的平台已经发帖成功。
- 不用 mock、fixture、截图或示例 URL 冒充真实发帖结果。
- 不绕过 X、Reddit、GitHub 的登录、权限、风控、CAPTCHA 或平台规则。

## 统一规则

所有命令默认在项目根目录运行：

```bash
cd /Users/harry/Documents/git/AnimoCerebro-external
```

所有 Python 命令必须使用 `.venv`：

```bash
.venv/bin/python ...
```

Agent 代码边界：

- Agent 发布链路必须使用 `Agent/` 下自己的代码。
- 禁止在 Agent 发布链路中 `import zentex.*`。
- 禁止在 Agent 发布链路中把 `src/` 注入 `sys.path`。
- LLM 调用统一走 `Agent/local_llm_client.py` 和 `Agent/posting_workflows/llm_client.py`。
- 回归守护测试：`.venv/bin/python -m pytest Agent/test_agent_no_src_dependency.py -q`

真实成功必须同时具备：

- `success=true`
- 真实平台 `post_url`
- `trace_id`
- `verified_at` 或节点级主动验证 evidence
- `verification_source`
- 主动读回或主动打开 permalink 的证据

## X

### 契约测试文件

- `Agent/test_x_langgraph_workflow.py`
- `Agent/test_langgraph_posting_workflows.py`

调用方式：

```bash
.venv/bin/python -m pytest Agent/test_x_langgraph_workflow.py -q
.venv/bin/python -m pytest Agent/test_langgraph_posting_workflows.py -q
```

真实性标注：

- `非真实运行结果（夹具）`
- 不会创建真实 X 帖子。
- 只能验证节点证据闸门、URL 形态和 fail-closed 行为。

### 真实调用入口

- `Agent/run_x_real.py`

调用方式：

```bash
.venv/bin/python Agent/run_x_real.py
```

结果文件：

- `Agent/data/x_real_post_last_result.json`

真实前置条件：

- `.venv` 中已安装 `google-genai` 或当前 provider 所需 SDK。
- `.env` 或环境变量中有有效的激活态 ModelProvider API key。
- `chrome_custom_profile` 中有真实 X 登录态，或运行时浏览器已完成登录。
- X 没有 CAPTCHA、风控、账号限制或发布限制。

当前真实状态：

- `Agent/run_x_real.py` 已真实运行。
- 浏览器节点已使用真实 Chrome page。
- Agent 本地 LLM 前置检查已通过，不再调用 `src/zentex`。
- 最新真实发帖结果以 `Agent/data/x_real_post_last_result.json` 为准。
- 只有该文件中 `success=true` 且包含 X status permalink 时，才算 X 真实成功。

## Reddit

### 契约测试文件

- `Agent/test_reddit_smart_poster_contract.py`
- `Agent/test_reddit_popup_llm_interpreter.py`
- `Agent/test_langgraph_posting_workflows.py`

调用方式：

```bash
.venv/bin/python -m pytest Agent/test_reddit_smart_poster_contract.py Agent/test_reddit_popup_llm_interpreter.py -q
.venv/bin/python -m pytest Agent/test_langgraph_posting_workflows.py -q
```

真实性标注：

- `非真实运行结果（夹具）`
- 不会创建真实 Reddit 帖子。
- 只能验证 Flair 必选判断、弹窗 LLM fail-closed、permalink 闸门和节点证据链。

### 真实调用入口

- `Agent/run_reddit_smart_poster_real.py`
- `Agent/check_reddit_recent_posts.py`

调用方式：

```bash
.venv/bin/python Agent/run_reddit_smart_poster_real.py
.venv/bin/python Agent/check_reddit_recent_posts.py
```

结果文件：

- `Agent/data/reddit_smart_poster_last_result.json`
- `Agent/data/reddit_recent_check_last_result.json`

真实成功判定：

- `post_url` 必须是 Reddit permalink。
- 必须主动打开 permalink。
- 页面正文必须包含预期标题或内容。
- Flair 非必选时不选择 Flair；Flair 必选时必须选择并验证已应用。

当前真实状态：

- Reddit 已有单平台真实 permalink 验证证据。
- 全平台总闸门仍需要 X 真实成功证据后才能通过。

## GitHub

### 契约测试文件

- `Agent/test_github_posting_workflow.py`

调用方式：

```bash
.venv/bin/python -m pytest Agent/test_github_posting_workflow.py -q
```

真实性标注：

- `非真实运行结果（夹具）`
- 不会创建真实 GitHub Discussion。
- 只能验证 GraphQL createDiscussion/read-back 的契约、URL 闸门和 fail-closed 行为。

### 真实调用入口

- `Agent/run_github_discussion_post_real.py`

调用方式：

```bash
GITHUB_TOKEN="$(gh auth token)" .venv/bin/python Agent/run_github_discussion_post_real.py
```

也可以使用已导出的 token：

```bash
.venv/bin/python Agent/run_github_discussion_post_real.py
```

结果文件：

- `Agent/data/github_discussion_post_last_result.json`

真实成功判定：

- `post_url` 必须是 `https://github.com/{owner}/{repo}/discussions/{number}`。
- `verification_source` 必须是 `github_graphql_discussion_get`。
- GraphQL 读回同一个 Discussion。
- 标题和正文必须匹配预期内容。

当前真实状态：

- GitHub Discussions 已真实发帖成功。
- 真实 URL：`https://github.com/xunharry4-source/AnimoCerebro/discussions/2`
- 证据文件：`Agent/data/github_discussion_post_last_result.json`

## 全平台真实成功闸门

测试文件：

- `Agent/test_real_posting_success_gate.py`

调用方式：

```bash
.venv/bin/python -m pytest Agent/test_real_posting_success_gate.py -q
```

结果文件要求：

- `Agent/data/real_posting_success_evidence.json`

当前状态：

- 该闸门应保持失败，直到 X、Reddit、GitHub 三个平台都有真实成功证据。
- 缺少任一平台证据时，最终判定必须是未完成。

# 社交发布节点说明

## 文档用途

说明 LangGraph 化后的 X / Reddit 发布节点、输入输出、失败条件和证据要求。

## 主要职责

- 给每个节点定义职责边界。
- 标明节点之间的数据流。
- 标明每个节点的成功证据。

## 不负责

- 不替代真实运行日志。
- 不把节点级成功等同于平台发帖成功。
- 不允许没有最终验证节点时更新成功状态。

## 通用状态字段

- `platform`：目标平台。
- `trace_id`：一次发帖尝试的审计 ID。
- `theme`：当天主题。
- `subreddit`：Reddit 目标社区。
- `title`：Reddit 标题。
- `content`：X 内容或 Reddit 正文。
- `selected_flair`：实际选择的 Flair，非必选时为空。
- `attempts`：提交尝试次数。
- `post_url`：平台 permalink。
- `status`：`pending` / `failed` / `success`。
- `evidence`：节点证据列表。

GitHub 额外字段：

- `repository`：目标仓库，默认 `xunharry4-source/AnimoCerebro`。
- `category_id` / `category_name`：GitHub Discussion 分类。
- `discussion_id`：GitHub Discussion GraphQL ID。
- `discussion_number`：GitHub Discussion 编号。

## X 节点

### X-1 打开浏览器

输入：

- 浏览器配置
- profile/cookies 路径

输出：

- browser page
- 登录态检查结果

失败条件：

- 浏览器启动失败
- 未登录
- CAPTCHA/风控

证据：

- 页面 URL
- 登录态截图或 DOM 状态

### X-2 获取当天主题

输入：

- 发布计划
- 原始素材

输出：

- `theme`
- 生成原因

失败条件：

- LLM provider 不可用
- 输出为空或格式错误

证据：

- LLM 调用 trace
- 主题 JSON

### X-3 进入 X

输入：

- browser page

输出：

- X compose 页面状态

失败条件：

- 导航失败
- compose 不可见

证据：

- URL
- compose DOM 状态

### X-4 书写并发帖

输入：

- `content`

输出：

- click result
- tentative URL

失败条件：

- 输入框缺失
- 发布按钮禁用
- 点击失败

证据：

- 点击方法
- 截图

### X-5 主动验证成功

输入：

- `post_url`
- `content`

输出：

- active verification evidence

失败条件：

- URL 不是 X status permalink
- 打开后跳转
- 页面缺少预期内容

证据：

- observed_url
- page_title
- body_snippet
- content_match

### X-6 更新文档

输入：

- X-5 验证证据

输出：

- “X 发帖成功”记录

失败条件：

- 缺 `post_url`
- 缺 `trace_id`
- 缺 `verified_at`
- 缺 `verification_source`

证据：

- 写入后的文档或表格记录

## Reddit 节点

### R-1 获取社区列表

输入：

- 配置、计划或人工输入

输出：

- subreddit list

失败条件：

- 列表为空
- 社区名非法

证据：

- 社区列表 JSON

### R-2 选择社区并打开发帖页

输入：

- `subreddit`

输出：

- Reddit submit page

失败条件：

- 页面不可达
- 未登录
- 社区不存在

证据：

- URL
- 页面标题

### R-3 获取社区规则

输入：

- `subreddit`

输出：

- rules

失败条件：

- 缓存和网页都不可用
- 规则为空且社区要求必须获取规则

证据：

- rules source
- rules count

### R-4 生成标题和正文

输入：

- rules
- theme
- subreddit

输出：

- `title`
- `content`

失败条件：

- LLM provider 不可用
- 内容为空
- 内容违反明确规则

证据：

- LLM trace
- 生成内容 JSON

### R-5 检查 Flair 是否必选

输入：

- 已填写的 Reddit submit page

输出：

- `flair_requirement`

失败条件：

- 检测异常不阻断，但必须默认跳过 Flair，并等待提交/验证 fail-closed。

证据：

- `required`
- `reason`
- `submit_disabled`
- `has_flair_control`

### R-6 选择 Flair

输入：

- `flair_requirement.required=True`
- 目标 Flair，可为空

输出：

- `selected_flair`

失败条件：

- Flair 必选但弹窗打不开
- 候选项不可识别
- 选择后页面未验证到 Flair

证据：

- OCR 截图
- selected_text
- match_type

### R-7 提交帖子

输入：

- `title`
- `content`
- `selected_flair`

输出：

- submission_result

失败条件：

- Post 按钮缺失
- Post 按钮禁用
- 点击失败

证据：

- click method
- screenshot_path

### R-8 分析弹窗

输入：

- DOM/OCR 弹窗文本

输出：

- translated_message_zh
- category
- should_retry
- needs_flair

失败条件：

- LLM provider 不可用
- JSON 解析失败
- 弹窗文本为空但页面没有 permalink

证据：

- LLM trace
- popup screenshot
- structured analysis

### R-9 主动验证成功

输入：

- Reddit `post_url`
- `title`
- `subreddit`

输出：

- active verification evidence

失败条件：

- URL 不是目标 subreddit permalink
- 打开后跳转
- 页面缺少标题
- 页面显示删除/404/不可用

证据：

- observed_url
- response_status
- page_title
- body_snippet
- content_match

### R-10 失败修正与循环

输入：

- R-8 错误分析
- 当前标题/正文/Flair

输出：

- 修正后的标题/正文/Flair
- attempt + 1

失败条件：

- 错误不可自动修复
- 超出最大重试次数
- LLM provider 不可用

证据：

- correction reason
- previous error
- next attempt number

### R-11 更新文档

输入：

- R-9 验证证据

输出：

- “Reddit 发帖成功”记录

失败条件：

- 缺 permalink
- 缺主动验证证据
- 缺 trace_id

证据：

- 写入后的文档或表格记录

## GitHub 节点

默认目标：

- `https://github.com/xunharry4-source/AnimoCerebro`
- `xunharry4-source/AnimoCerebro`

### G-1 解析目标仓库

输入：

- GitHub URL 或 `owner/repo`

输出：

- `repository`

失败条件：

- 仓库格式非法

证据：

- normalized repository

### G-2 获取 Discussion 主题

输入：

- `repository`
- 日期和项目上下文

输出：

- `topic`
- category 建议

失败条件：

- LLM provider 不可用
- LLM 输出缺 topic

证据：

- LLM trace
- topic payload

### G-3 书写 Discussion 标题和正文

输入：

- `repository`
- `topic`

输出：

- `title`
- `content`
- `category_name`

失败条件：

- LLM provider 不可用
- title/body 为空

证据：

- title
- category_name

### G-4 创建 Discussion

输入：

- `repository`
- `title`
- `content`
- `category_name`
- `GITHUB_TOKEN`

输出：

- `discussion_id`
- `discussion_number`
- `post_url`
- submission_result

失败条件：

- 缺 `GITHUB_TOKEN`
- GitHub GraphQL 返回 errors
- 仓库没有启用 Discussions
- 仓库没有可用 Discussion category
- 请求的 category 不存在
- 返回体缺 discussion number
- 返回体缺 GitHub Discussion URL
- 创建后 GraphQL 读回验证失败

证据：

- discussion_number
- category
- post_url
- `verification_source=github_graphql_discussion_get`

### G-5 主动验证成功

输入：

- G-4 submission_result
- `post_url`

输出：

- active verification evidence

失败条件：

- `post_url` 不是 GitHub Discussions URL
- 缺提交证据
- 缺 read-after-write 验证证据

证据：

- graphql_node_found
- title_match
- body_match
- body_snippet

### G-6 更新文档

输入：

- G-5 验证证据

输出：

- “GitHub 发帖成功”记录

失败条件：

- 缺 Discussion URL
- 缺 submit evidence
- 缺 verify evidence
- 缺 trace_id

证据：

- 写入后的 ledger/status 文档记录

## 节点完成判定

- 普通节点完成：节点输出结构化结果并写 evidence。
- 平台成功完成：必须通过 X-5、R-9 或 G-5。
- 文档更新完成：必须通过 X-6、R-11 或 G-6。

缺任一最终验证证据时，最终状态必须是“未完成”。

# 社交发布流程说明

## 文档用途

说明 X、Reddit 和 GitHub 从主题获取到真实验证、文档更新的完整流程。

## 主要职责

- 给出端到端流程顺序。
- 标明循环迭代条件。
- 标明哪些步骤允许更新“发帖成功”文档。

## 不负责

- 不声明当前真实测试已经通过。
- 不替代代码中的节点实现。
- 不提供绕过平台限制的流程。

## X 发帖流程

1. 打开浏览器
   - 启动真实 Chrome / Playwright context。
   - 确认 X 登录态。

2. 获取当天主题
   - 从计划、素材或人工输入获取当天主题。
   - 主题生成属于认知算子，必须使用激活态 LLM。

3. 进入 X
   - 导航到 X 发帖入口。
   - 页面不可用、未登录、风控时 fail-closed。

4. 书写并发帖
   - 输入内容。
   - 点击发布。
   - 记录点击结果，但点击结果不是成功证据。

5. 判断是否发帖成功
   - 必须拿到 X status permalink。
   - 主动打开 permalink。
   - 验证页面中包含预期内容。

6. 更新文档或表格
   - 只有第 5 步验证通过，才允许写入“X 发帖成功”。
   - 写入内容必须包含 post_url、trace_id、verified_at、verification_source。

## Reddit 发帖流程

1. 获取需要发帖的社区列表
   - 输入可以来自计划、配置或人工指定。
   - 空列表直接失败，不进入发帖。

2. 选择一个社区并打开发帖页面
   - 导航到 `https://www.reddit.com/r/{subreddit}/submit`。
   - 页面不可用、未登录、被风控时 fail-closed。

3. 获取社区规则
   - 优先读缓存。
   - 缓存缺失或过期时打开规则页抓取。
   - 规则获取失败不能伪装为“已理解规则”。

4. 根据社区规则书写标题和正文
   - 内容生成属于认知算子，必须使用激活态 LLM。
   - 不允许固定样本文案冒充社区定制内容。

5. 检查 Flair 是否必选
   - 在标题和正文填写后检查页面要求。
   - 如果检测到“Flair 必选”，进入第 6 步。
   - 如果未检测到必选信号，跳过 Flair，不打开 Flair 弹窗。

6. 选择 Flair
   - 仅 Flair 必选时执行。
   - 使用 OCR/DOM 选择目标 Flair 或最合适候选。
   - 选择后必须验证 Flair 已应用。

7. 提交帖子
   - 点击 Reddit Post 按钮。
   - 记录 click method 和截图。
   - 只点击按钮不代表成功。

8. 分析提交后弹窗
   - 有弹窗时交给 LLM 翻译和分类。
   - LLM 不可用时 fail-closed。
   - 弹窗错误可进入修正循环。

9. 主动验证是否发帖成功
   - 必须拿到 Reddit permalink。
   - 主动打开 permalink。
   - 验证页面正文包含预期标题。

10. 失败后关闭弹窗、修改内容并循环
    - 只有 LLM 判断错误可自动修复时才循环。
    - 每次循环必须增加 attempt 并记录 evidence。
    - 超出最大次数后失败退出。

11. 更新文档或表格
    - 只有第 9 步验证通过，才允许写入“Reddit 发帖成功”。
    - 写入内容必须包含 subreddit、post_url、trace_id、verified_at、verification_source。

## GitHub 发帖流程

默认目标：

- `https://github.com/xunharry4-source/AnimoCerebro`
- `https://github.com/xunharry4-source/AnimoCerebro/discussions`
- 规范化仓库名：`xunharry4-source/AnimoCerebro`

1. 解析目标仓库
   - 支持 GitHub URL 或 `owner/repo`。
   - 仓库格式非法时 fail-closed。

2. 获取 Discussion 主题
   - 使用激活态 LLM 生成 GitHub Discussion 主题、受众、分类建议。
   - LLM 不可用时 fail-closed，不使用静态主题冒充。

3. 书写 Discussion 标题和正文
   - 使用激活态 LLM 生成 title、Markdown body、category_name。
   - 标题或正文为空时 fail-closed。

4. 创建 GitHub Discussion
   - 使用 `GITHUB_TOKEN` 调用 GitHub GraphQL API。
   - 先查询仓库 `discussionCategories`，选择真实存在的 category。
   - 调用 `createDiscussion` 创建 Discussion。
   - 缺 token、权限不足、仓库未启用 Discussions、category 不存在、返回体缺 discussion number 或 `url` 时 fail-closed。
   - 写操作结果不是最终成功证据。

5. 主动验证 Discussion
   - 使用 GraphQL `repository.discussion(number)` 读回同一个 Discussion。
   - 验证 `url` 是 GitHub Discussions URL。
   - 验证标题和正文匹配预期。

6. 更新文档或表格
   - 只有第 5 步验证通过，才允许写入“GitHub 发帖成功”。
   - 写入内容必须包含 repository、discussion_number、category、post_url、trace_id、verified_at、verification_source。

## 循环规则

- 可重试：缺 Flair、标题格式错误、正文格式错误、社区规则提示可修正。
- 不可重试：未登录、CAPTCHA、账号受限、LLM provider 不可用、GitHub token 缺失、没有真实 permalink/Discussion URL。
- 每次循环必须保留失败原因和截图/弹窗证据。

## 真实性闸门

禁止以下内容作为成功证据：

- 点击 Post 按钮成功。
- URL 有变化但不是帖子 permalink。
- 截图显示页面看起来像成功。
- 代码单测通过。
- fixture/mock 返回 success。

允许作为成功证据：

- 真实平台 permalink。
- 主动打开 permalink 的浏览器验证结果。
- GitHub Discussion 创建后的 GraphQL 读回验证结果。
- 页面正文包含预期标题或内容。
- 带 `trace_id` 的结构化 evidence。

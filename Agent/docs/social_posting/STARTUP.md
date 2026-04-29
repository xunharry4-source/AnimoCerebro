# 社交发布服务启动说明

## 文档用途

说明如何启动常驻社交发布服务 `Agent.posting_agent_service`，并验证 X、Reddit、GitHub 发布适配器和持久浏览器状态。

## 主要职责

- 给出从仓库根目录启动服务的最小命令。
- 说明服务浏览器 profile、Google Chrome profile seed、手动登录和状态检查方式。
- 标明哪些命令只是只读验证，哪些命令会触发真实平台副作用。

## 不负责

- 不声明 X、Reddit 或 GitHub 已真实发帖成功。
- 不提供绕过登录、CAPTCHA、风控、社区规则或平台限制的方法。
- 不把 cookie 数量、接口在线或按钮点击成功当作发帖成功证据。

## 启动前提

从仓库根目录执行：

```bash
cd /Users/harry/Documents/git/AnimoCerebro-external
```

必须满足：

- Python 依赖已安装到 `.venv`。
- `.env` 或当前 shell 已配置真实 LLM provider 所需 API key。
- 本机可启动 Google Chrome / Playwright。
- 需要复用登录态时，目标服务 profile 使用 `chrome_custom_profile`。
- Reddit/X 真实发帖前，服务弹出的浏览器里必须已完成对应平台登录。

## 启动服务

推荐使用显式 uvicorn 命令，便于固定端口和 profile：

```bash
AGENT_AUTO_START_BROWSER=true \
AGENT_BROWSER_PROFILE_DIR=./chrome_custom_profile \
AGENT_IMPORT_GOOGLE_CHROME_PROFILE=true \
AGENT_GOOGLE_CHROME_SOURCE_PROFILE="Profile 5" \
.venv/bin/python -m uvicorn Agent.posting_agent_service:app \
  --host 127.0.0.1 \
  --port 9010
```

等价的轻量启动方式：

```bash
.venv/bin/python Agent/posting_agent_service.py
```

服务启动后会自动打开一个非 headless Chrome 持久浏览器。首次启动如果 `chrome_custom_profile` 缺少 Google 登录态，服务会尝试从系统 Chrome 的 `Profile 5` 复制 Google 相关状态。

## 只读状态验证

这些命令不会发帖：

```bash
curl http://127.0.0.1:9010/status
curl http://127.0.0.1:9010/browser/status
curl http://127.0.0.1:9010/platforms
curl -X POST http://127.0.0.1:9010/handshake
```

关键检查点：

- `status=online`
- `browser.started=true`
- `browser.profile_dir` 指向仓库内 `chrome_custom_profile`
- `platforms.x.registered=true`
- `platforms.reddit.registered=true`
- `browser.disk_cookie_counts.x` 大于 0 时，说明磁盘上存在 X cookie
- `browser.disk_cookie_counts.reddit` 大于 0 时，说明磁盘上存在 Reddit cookie

注意：cookie 数量只是登录态诊断，不是发帖成功证据。真实成功必须来自平台 permalink 或 GitHub Discussion URL 的主动验证。

## 手动登录

如果 `/browser/status` 显示 Reddit cookie 为 0，或服务浏览器停在 Reddit 登录、challenge、CAPTCHA 页面：

1. 在服务启动时弹出的 Chrome 窗口里完成 Reddit 登录。
2. 登录后不要关闭服务浏览器。
3. 再次执行：

```bash
curl http://127.0.0.1:9010/browser/status
```

X 也同理：如果 X 页面要求登录或验证，必须先在同一个服务浏览器里完成。

## 提交真实 Job

以下命令会触发真实平台副作用，必须明确带 `allow_side_effects=true`。

### X

X 服务适配器当前运行 canonical workflow，不接受自定义参数：

```bash
curl -X POST http://127.0.0.1:9010/jobs \
  -H 'Content-Type: application/json' \
  -d '{"platform":"x","allow_side_effects":true,"params":{}}'
```

### Reddit

默认目标可由 `params.subreddit` 指定：

```bash
curl -X POST http://127.0.0.1:9010/jobs \
  -H 'Content-Type: application/json' \
  -d '{"platform":"reddit","allow_side_effects":true,"params":{"subreddit":"ArtificialInteligence"}}'
```

### GitHub Discussions

GitHub 需要 `GITHUB_TOKEN`，并且目标仓库必须启用 Discussions：

```bash
curl -X POST http://127.0.0.1:9010/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "platform":"github",
    "allow_side_effects":true,
    "params":{
      "repository":"xunharry4-source/AnimoCerebro",
      "title":"Discussion title",
      "body":"Discussion body",
      "category_name":"General"
    }
  }'
```

## 查询 Job 结果

提交 job 后，响应里会返回 `job_id`。使用该 ID 轮询：

```bash
curl http://127.0.0.1:9010/jobs/<job_id>
```

成功判定：

- `status=success`
- `result.success=true`
- `post_url` 非空
- `result.realism=真实运行结果`
- 结果里有主动验证证据，例如 permalink / Discussion URL 读回验证

失败判定：

- `status=failed`
- `error.code` 或 `result.error.code` 指向失败节点
- `post_url=null`

## 异常路径验证

未确认副作用时，服务必须拒绝真实发帖：

```bash
curl -X POST http://127.0.0.1:9010/jobs \
  -H 'Content-Type: application/json' \
  -d '{"platform":"reddit","params":{"subreddit":"ArtificialInteligence"}}'
```

预期结果：

- HTTP 400
- `detail.code=side_effects_not_confirmed`

不支持的平台必须失败：

```bash
curl -X POST http://127.0.0.1:9010/jobs \
  -H 'Content-Type: application/json' \
  -d '{"platform":"mastodon","allow_side_effects":true,"params":{}}'
```

预期结果：

- HTTP 422 或 400
- 不创建真实发布 job

## 停止服务

在启动服务的终端按 `Ctrl+C`。服务 shutdown 时会关闭持久浏览器 context，并保留 `chrome_custom_profile` 中已经刷盘的登录态。

## 常见问题

### 端口 9010 被占用

```bash
lsof -nP -iTCP:9010 -sTCP:LISTEN
```

停止旧进程后重启，或临时换端口：

```bash
.venv/bin/python -m uvicorn Agent.posting_agent_service:app --host 127.0.0.1 --port 9011
```

### 浏览器 context 已关闭

如果 job 失败信息包含 `Target page, context or browser has been closed`：

1. 停止当前服务。
2. 确认没有其他进程占用 `chrome_custom_profile`。
3. 重新启动 `Agent.posting_agent_service`。
4. 重新检查 `/browser/status` 后再提交真实 job。

### Reddit cookie 为 0

这表示磁盘 cookie 诊断没有读到 Reddit 登录态。必须在服务弹出的 Chrome 中手动登录 Reddit，然后保持服务运行再提交 Reddit job。

## 证据文件

服务和 runner 会写入以下证据文件：

- `Agent/data/posting_agent_service_jobs.json`
- `Agent/data/posting_agent_service_audit.jsonl`
- `Agent/data/x_real_post_last_result.json`
- `Agent/data/reddit_real_post_last_result.json`
- `Agent/data/github_discussion_post_last_result.json`

这些文件是运行证据，不应把 fixture、mock 或空结果当作真实成功。

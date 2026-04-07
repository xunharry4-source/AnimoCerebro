# Public Git Add Commands / 公开提交暂存命令

## 1. Purpose / 目的

**English**

This file gives a practical `git add` scope for a public documentation-first release.

**中文**

本文件给出一份可直接执行的 `git add` 范围，适合做一次“公开文档优先”的发布。

## 2. Recommended Scope / 推荐范围

**English**

If you want the current public-facing documentation set only, stage this scope:

```bash
git add \
  .gitignore \
  README.md \
  README.zh.md \
  帮助文档.md \
  helo.md \
  快速开始-复制即用.md \
  详细部署与集成说明.md \
  当前对接协议.md \
  测试文档.md \
  docs/architecture \
  docs/integrations \
  docs/operability/PUBLIC_RELEASE_CHECKLIST.md \
  docs/operability/GITHUB_PUBLIC_SCOPE.md
```

**中文**

如果你这次只想先提交“公开文档体系”，建议暂存这个范围：

```bash
git add \
  .gitignore \
  README.md \
  README.zh.md \
  帮助文档.md \
  helo.md \
  快速开始-复制即用.md \
  详细部署与集成说明.md \
  当前对接协议.md \
  测试文档.md \
  docs/architecture \
  docs/integrations \
  docs/operability/PUBLIC_RELEASE_CHECKLIST.md \
  docs/operability/GITHUB_PUBLIC_SCOPE.md
```

## 3. Optional Public Source Scope / 可选源码公开范围

**English**

If you also want to publish the OpenClaw integration path, add:

```bash
git add \
  integrations/openclaw-plugin \
  scripts/openclaw-plugin-probe.mjs \
  scripts/openclaw-plugin-real-check.mjs \
  scripts/openclaw-plugin-real-setup.mjs \
  docs/operability/OPENCLAW_PLUGIN_REAL_TEST.md \
  tests/test_openclaw_bridge_api.py
```

**中文**

如果你还想把 OpenClaw 集成路径一起公开，再追加：

```bash
git add \
  integrations/openclaw-plugin \
  scripts/openclaw-plugin-probe.mjs \
  scripts/openclaw-plugin-real-check.mjs \
  scripts/openclaw-plugin-real-setup.mjs \
  docs/operability/OPENCLAW_PLUGIN_REAL_TEST.md \
  tests/test_openclaw_bridge_api.py
```

## 4. Do Not Stage In This Pass / 这轮不要暂存

**English**

Do not stage these in the documentation-first pass:

- `项目计划/`
- local runtime directories such as `.animocerebro/` and `.zentex/`
- `node_modules/`
- local logs, JSONL traces, and SQLite databases
- IDE folders
- private planning docs

**中文**

这轮“文档优先公开”不要暂存这些内容：

- `项目计划/`
- `.animocerebro/`、`.zentex/` 这类本地运行态目录
- `node_modules/`
- 本地日志、JSONL trace、SQLite 数据库
- IDE 目录
- 私有计划文档

## 5. Verify Before Commit / 提交前检查

Run:

```bash
git diff --cached --name-only
```

Then verify the staged set contains only the intended public docs or public code.

然后确认暂存区里只有你打算公开的文档或代码。

# GitHub Public Scope / GitHub 公开提交范围

## 1. Purpose / 目的

**English**

This document defines the practical file scope for a public GitHub release of this repository.

**中文**

本文件定义这个仓库在公开 GitHub 发布时的实际文件范围。

## 2. Include By Default / 默认应提交

**English**

Include these by default:

- source code under `src/`
- integration code under `integrations/`
- scripts under `scripts/`
- public docs under `docs/`
- public entry docs in the repository root
- tests and test fixtures that do not contain secrets
- package and dependency manifests
- deployment scaffolds without private credentials

**中文**

默认应提交这些内容：

- `src/` 下的源码
- `integrations/` 下的集成代码
- `scripts/` 下的脚本
- `docs/` 下的公开文档
- 仓库根目录的公开入口文档
- 不含密钥的测试和测试样例
- 包管理与依赖声明文件
- 不含私密凭据的部署脚手架

## 3. Exclude By Default / 默认不应提交

**English**

Exclude these by default:

- local virtual environments
- local runtime state directories
- local SQLite databases
- runtime logs
- JSONL traces and forensics files
- IDE settings
- dependency caches such as `node_modules/`
- local credentials
- internal planning docs that are marked private

**中文**

默认不应提交这些内容：

- 本地虚拟环境
- 本地运行态目录
- 本地 SQLite 数据库
- 运行日志
- JSONL trace 和取证文件
- IDE 配置
- `node_modules/` 这类依赖缓存
- 本地凭据
- 被标记为私有的内部计划文档

## 4. Public Root Files / 可公开的根目录文件

- [README.md](../../README.md)
- [README.zh.md](../../README.zh.md)
- [帮助文档.md](../../帮助文档.md)
- [helo.md](../../helo.md)
- [快速开始-复制即用.md](../../快速开始-复制即用.md)
- [详细部署与集成说明.md](../../详细部署与集成说明.md)
- [当前对接协议.md](../../当前对接协议.md)
- [测试文档.md](../../测试文档.md)
- [pyproject.toml](../../pyproject.toml)
- [package.json](../../package.json)
- [package-lock.json](../../package-lock.json)
- [alembic.ini](../../alembic.ini)
- [.gitignore](../../.gitignore)

## 5. Public Directories / 可公开目录

- `src/`
- `integrations/`
- `scripts/`
- `docs/`
- `tests/`
- `deploy/`
- `docker/`
- `alembic/`

## 6. Private Or Local-Only Directories / 私有或本地专用目录

- `.animocerebro/`
- `.zentex/`
- `.venv/`
- `.venv_zentex/`
- `.venv_zentex_311/`
- `.venv_zentex_stable/`
- `.idea/`
- `.codex/`
- `node_modules/`
- `MagicMock/`

## 7. Internal Planning / 内部计划

For internal planning files, follow:

- [PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md)

对内部计划文件，请遵循：

- [PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md)

## 8. Release Gate / 提交前检查

Before publishing, verify:

- `.gitignore` covers local runtime and environment files
- no credentials or local-only configs are staged
- no private planning files are staged by accident
- public docs point to public docs, not internal plans

提交前请确认：

- `.gitignore` 已覆盖本地运行态和环境文件
- 没有把凭据或本地专用配置加入暂存区
- 没有误暂存私有计划文件
- 公开文档链接指向的是公开文档，而不是内部计划

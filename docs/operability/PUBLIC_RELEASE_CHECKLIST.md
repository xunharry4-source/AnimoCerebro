# Public Release Checklist / 公开发布清单

## 1. Purpose / 目的

**English**

This document defines what should be published to a public GitHub repository, what should remain private, and what should be sanitized before release.

**中文**

本文件定义哪些内容适合发布到公开 GitHub，哪些内容应保持私有，哪些内容需要脱敏后再发布。

## 2. Default Rule / 默认规则

**English**

Default to private unless the file is clearly part of:

- public source code
- public APIs
- public protocols
- public architecture
- public installation or testing guidance

**中文**

默认按私有处理，除非该文件明显属于以下范围：

- 公开源码
- 公开 API
- 公开协议
- 公开架构
- 公开安装或测试说明

## 3. Safe To Publish / 可直接公开

**English**

These are normally safe to publish:

- runtime source code
- integration source code
- public test code
- public docs under `docs/`
- public entry docs such as `README.md`, `README.zh.md`, `帮助文档.md`
- deployment scaffolds that do not contain private credentials
- stable protocol and adapter docs

**中文**

通常可直接公开的内容：

- 运行时源码
- 集成适配源码
- 公开测试代码
- `docs/` 下的公开文档
- `README.md`、`README.zh.md`、`帮助文档.md` 这类公开入口文档
- 不包含私密凭据的部署脚手架
- 稳定的协议与适配文档

## 4. Keep Private / 建议私有

**English**

These should normally stay private:

- business strategy
- moat design
- commercial rollout plans
- private audit logic
- private strategy patches
- experience-pack internals
- internal roadmap ordering
- security weak points and adversarial notes
- unpublished product positioning details

**中文**

通常应保持私有的内容：

- 商业策略
- 护城河设计
- 商业化推进计划
- 私有审计逻辑
- 私有策略补丁
- 经验包内部实现
- 内部路线图优先级
- 安全弱点和对抗说明
- 未发布的产品定位细节

## 5. Publish After Sanitizing / 脱敏后再公开

**English**

These are often useful publicly, but should be sanitized first:

- project planning docs
- roadmap docs
- execution checklists with internal blockers
- validation matrices with internal environment assumptions
- architecture notes that contain private sequencing or weak-point analysis

Sanitize by removing:

- private goal numbering
- internal blockers and incident details
- future release timing
- sensitive implementation shortcuts
- internal-only commercial notes

**中文**

这些内容通常有公开价值，但建议先脱敏：

- 项目计划文档
- 路线图文档
- 含内部阻塞项的执行清单
- 含内部环境假设的验收矩阵
- 含私有推进顺序或弱点分析的架构说明

脱敏时建议移除：

- 私有目标编号
- 内部阻塞和事故细节
- 未来发布时间点
- 敏感实现诀窍
- 内部商业化备注

## 6. Current Recommendation For This Repository / 当前仓库建议

### 6.1 Publish

- [README.md](../../README.md)
- [README.zh.md](../../README.zh.md)
- [帮助文档.md](../../帮助文档.md)
- [helo.md](../../helo.md)
- [快速开始-复制即用.md](../../快速开始-复制即用.md)
- [详细部署与集成说明.md](../../详细部署与集成说明.md)
- [当前对接协议.md](../../当前对接协议.md)
- [CORE_FOUNDATIONS.md](../architecture/CORE_FOUNDATIONS.md)
- [COGNITIVE_TOOL_INTERFACE.md](../architecture/COGNITIVE_TOOL_INTERFACE.md)
- [OPENCLAW_HOST_ADAPTER_PROTOCOL.md](../integrations/OPENCLAW_HOST_ADAPTER_PROTOCOL.md)
- [OPENCLAW_HOST_ADAPTER_ARCHITECTURE.md](../integrations/OPENCLAW_HOST_ADAPTER_ARCHITECTURE.md)
- [测试文档.md](../../测试文档.md)

### 6.2 Keep Private

- `项目计划/05-社会理性与商业化.md`
- `项目计划/07-云审计服务.md`
- `项目计划/10-记忆安全与治理.md`
- `项目计划/13-当前问题与执行清单.md`
- `项目计划/14-终极目标与九问驱动主体进化.md`
- `项目计划/14B-类人脑功能缺口与补全路线.md`
- `项目计划/14C-工作记忆自我模型与元认知调度技术方案.md`
- `项目计划/14D-内部时间模拟冲突社会认知与巩固技术方案.md`

### 6.3 Sanitize First

- `项目计划/00-总览与治理.md`
- `项目计划/02-运行与防护.md`
- `项目计划/03-模拟与学习.md`
- `项目计划/04-协作与执行.md`
- `项目计划/08-Web界面管理.md`
- `项目计划/09-后期扩展规划.md`
- `项目计划/11-多AnimoCerebro协作/README.md`
- `项目计划/11-多AnimoCerebro协作/01-协作协议与会话.md`
- `项目计划/11-多AnimoCerebro协作/02-受控进化与经验交换.md`
- `项目计划/15-openClaw通用宿主智能接入/02-openClaw接入落地计划.md`
- `项目计划/15-openClaw通用宿主智能接入/04-openClaw功能拆分与可测试验收矩阵.md`
- `项目计划/15-openClaw通用宿主智能接入/README.md`

## 7. Release Gate / 发布前检查

Before publishing, verify:

- no local tokens or secrets are present
- no local machine paths reveal private environments unnecessarily
- no private strategy or business notes are mixed into public docs
- no runtime logs, snapshots, or local databases are included
- no internal planning files are accidentally linked from public entry docs

发布前请确认：

- 没有本地 token 或密钥
- 没有不必要暴露私人环境的本机路径
- 没有把私有策略或商业备注混进公开文档
- 没有把运行日志、snapshot 或本地数据库带进去
- 公开入口文档没有误链到内部计划文件

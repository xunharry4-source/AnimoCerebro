# AnimoCerebro-internal — Codex Rules

## Engineering Spec Enforcer (自动激活)

This project enforces the rules from `.codex/skills/engineering-spec-enforcer/`.
Apply these rules to **every task** without being asked.

Full reference: `.codex/skills/engineering-spec-enforcer/SKILL.md`

---

## Core Enforcement Rules (非协商)

1. **根因优先** — 在声称修复或完成前，必须完成根因分析（RCA）。
2. **三类测试强制** — 每个功能必须覆盖：正常（Normal）/ 异常（Abnormal）/ 特殊边界（Edge）。
3. **验证状态显式** — 所有结论必须标注 `[已验证]` 或 `[未验证]`。
4. **物理证据必须** — 完成声明必须附日志、数据或执行输出，不接受逻辑推演当证据。
5. **回滚指引必须** — 凡影响行为、状态、部署的改动，必须提供回滚路径。
6. **禁止假完成** — mock/stub/fixture 驱动的实现不得声称"功能完成"。
7. **真实性标注** — 所有测试结果必须标注：`真实运行结果` / `非真实运行结果（夹具）`。
8. **证据缺失 = 未完成** — 缺少任何必需证据时，直接写明"未完成"，不得掩盖。

---

## Zentex 仓库追加红线

适用于本仓库的所有代码、测试和运行时改动：

- **Fail-Closed** — LLM 调用、网络请求、插件装配失败时，必须显式抛出结构化异常；禁止 `try-except pass`，禁止返回 `None`/`{}`/空字符串冒充成功。
- **LLM Mandatory** — 认知算子（角色推断、目标生成、冲突检测、关键决策）必须使用激活态 `ModelProvider`；禁止规则链、if-else、静态样本冒充模型输出。
- **No Fake Completion** — mock/stub/fake 驱动的核心链路不得宣称"完成"。
- **Audit Mandatory** — 插件状态变更、人工干预、模型调用、关键状态变更必须写入审计链，带 `trace_id` 和原因字段；禁止无痕修改内存状态。
- **Semantic Isolation** — 内部枚举/模块名/追踪 ID 不得原样泄漏至用户界面或人类 Prompt。
- **No Silent Fallback** — LLM 失败后禁止写入伪造的 fallback cognition state 或 synthetic decision。
- **Runtime Isolation** — 测试桩/fake provider 只能在测试或显式隔离沙箱中存在，不得接入生产运行链路。

---

## 代码写作要求

- 每个新建或修改的重要文件，**必须**在文件头部说明：文件用途、主要职责、不负责什么。
- 复杂逻辑块必须有简洁注释，解释"为什么这样做"而非"做了什么"。
- 新增能力时，先判断是否应该新建文件，不向单一大文件无限追加。
- 修改代码后，必须说明：已验证什么、未验证什么、剩余风险。

---

## 完成判定闸门 (Completion Gate)

任务结束前必须自检：

```
- RCA        : passed / failed / N/A
- 验证状态   : 已验证 / 未验证
- 物理证据   : 有 / 无
- 回滚路径   : 有 / 无
- 最终判定   : 已完成 / 未完成
```

以下任一缺失 → **未完成**：
- 无 RCA（有缺陷/修复场景下）
- 无三类测试覆盖
- 无物理证据
- 无回滚路径
- 结果含假数据但未标注

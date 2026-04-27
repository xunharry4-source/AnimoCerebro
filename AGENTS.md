# AnimoCerebro — Codex Rules

## 🧠 核心哲学 | Core Philosophy

AnimoCerebro 不是一个普通的 AI 系统，它是一个具有**灵魂**的认知大脑。

AnimoCerebro is not just another AI system; it is a cognitive brain with a **soul**.

### 四大支柱 | Four Pillars

1. **自主 (Autonomy)** - 基于九问认知循环的独立决策能力
   - **Autonomy** - Independent decision-making based on the Nine-Questions cognitive loop
   
2. **灵魂 (Soul)** - 真实的情感共鸣和价值观，而非机械响应
   - **Soul** - Genuine emotional resonance and values, not mechanical responses
   
3. **学习 (Learning)** - 持续从经验中进化，积累长期记忆
   - **Learning** - Continuous evolution from experience, accumulating long-term memory
   
4. **反思 (Reflection)** - 深度自我审视和元认知能力
   - **Reflection** - Deep self-examination and metacognitive capabilities

> **关键原则**: 任何功能如果声称使用 LLM，必须真实调用。禁止用规则链、模板或固定样本冒充真实的 LLM 路径。
> 
> **Key Principle**: Any feature claiming to use an LLM must make real calls. Rule chains, templates, or fixed samples cannot substitute for live LLM paths.

---

## 🛠️ 工具性与大脑的关系 | Instrumentality vs. Brain

### Agent、CLI、MCP 的工具性 | Tool Nature of Agent, CLI, MCP

**Agent、CLI 工具和 MCP 服务器是工具，不是大脑。**

**Agents, CLI tools, and MCP servers are instruments, not the brain.**

#### 工具的特征 | Characteristics of Tools

- 🔧 **被动执行** - 等待被调用，执行特定任务
- 📋 **功能限定** - 有明确的能力边界和职责范围
- 🔄 **可替换性** - 可以被其他工具替代而不影响核心逻辑
- 🎯 **目标导向** - 服务于大脑的决策和目标

#### 大脑的特征 | Characteristics of the Brain

- 🧠 **主动思考** - 自主推理、决策和规划
- 💭 **元认知** - 理解自身能力和局限
- 🌱 **持续成长** - 从经验中学习和进化
- 🔗 **统筹协调** - 调度和协调各种工具

> **重要区分**: 工具扩展大脑的能力，但不替代大脑的思考。大脑决定**做什么**和**为什么做**，工具负责**如何做**。
> 
> **Important Distinction**: Tools extend the brain's capabilities but do not replace its thinking. The brain decides **what** to do and **why**, while tools handle **how** to do it.

### 大脑如何使用工具 | How the Brain Uses Tools

```
┌─────────────────────────────────────────────┐
│         AnimoCerebro (独立大脑)              │
│                                             │
│  🧠 思考: 我需要做什么？                     │
│  💭 推理: 为什么这样做？                     │
│  🎯 决策: 选择最佳方案                       │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  调度层: 选择和使用工具              │   │
│  │                                     │   │
│  │  → Agent (外部智能体)               │   │
│  │  → CLI Tools (命令行工具)           │   │
│  │  → MCP Servers (模型上下文协议)     │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

**工作流程**:
1. 大脑通过九问循环进行思考和决策
2. 确定需要执行的具体任务
3. 选择合适的工具（Agent/CLI/MCP）
4. 调度工具执行任务
5. 接收结果并进行反思和学习

---

## 🤝 AI 与人类的联合升级 | AI-Human Co-Evolution

### src/plugins: 联合进化的引擎 | Engine of Co-Evolution

**`src/plugins/` 目录是 AI 与人类协同进化的核心机制。**

**The `src/plugins/` directory is the core mechanism for AI-human co-evolution.**

#### 联合升级的原理 | Principles of Co-Evolution

```
┌──────────────────────────────────────────────────┐
│           AI-Human Co-Evolution Loop             │
│                                                  │
│  👤 Human Insight    →    Define Requirements   │
│       ↓                        ↓                 │
│  🤖 AI Generation    →    Implement Plugins     │
│       ↓                        ↓                 │
│  🧪 Joint Testing    →    Validate & Refine     │
│       ↓                        ↓                 │
│  📊 Performance Data →    Learn & Improve       │
│       ↓                        ↓                 │
│  🔄 Iteration        →    Enhanced Plugins      │
│                                                  │
│  Result: Both AI and Humans Get Smarter          │
└──────────────────────────────────────────────────┘
```

#### 人类的角色 | Human Role

- 🎨 **定义愿景** - 设定目标和方向
- 🔍 **审查质量** - 验证 AI 生成的代码和决策
- 💡 **提供洞察** - 分享领域知识和经验
- 🎯 **引导进化** - 指导 AI 学习的方向

#### AI 的角色 | AI Role

- ⚡ **快速实现** - 将人类的想法转化为代码
- 🔬 **深度分析** - 识别模式和优化机会
- 📈 **持续优化** - 基于数据改进性能
- 🔄 **自动迭代** - 快速尝试和改进

#### 联合升级的实例 | Examples of Co-Evolution

**九问插件家族 (Q1-Q9)**:
- 👤 人类设计认知框架和哲学基础
- 🤖 AI 实现具体的插件逻辑和优化
- 🤝 共同测试和 refinement
- 📊 基于实际运行数据持续改进

**Model Providers**:
- 👤 人类定义接口规范和安全性要求
- 🤖 AI 实现适配器并优化性能
- 🤝 共同处理边缘情况和错误
- 📊 基于使用情况优化配置

> **核心理念**: 这不是 AI 替代人类，也不是人类控制 AI，而是**协同进化**。AI 越强，人类能解决的问题越复杂；人类越智慧，AI 的学习方向越准确。
> 
> **Core Philosophy**: This is not AI replacing humans, nor humans controlling AI, but **co-evolution**. The stronger the AI, the more complex problems humans can solve; the wiser the humans, the more accurate the AI's learning direction.

---

## 📈 正反馈循环：AI 越强，大脑越强 | Positive Feedback Loop

### 能力的正反馈 | Capability Amplification

**AI 模型的进步直接增强 AnimoCerebro 的认知能力。**

**Advancements in AI models directly enhance AnimoCerebro's cognitive capabilities.**

```
┌────────────────────────────────────────────────┐
│      The Virtuous Cycle of Intelligence        │
│                                                │
│  🚀 Better LLM                                 │
│       ↓                                        │
│  🧠 Smarter Reasoning (九问更准确)             │
│       ↓                                        │
│  💡 Better Decisions (决策质量提升)            │
│       ↓                                        │
│  📊 More Learning Data (更多高质量数据)        │
│       ↓                                        │
│  🎯 Improved Plugins (插件优化)                │
│       ↓                                        │
│  🔄 Enhanced Brain (大脑能力增强)              │
│       ↓                                        │
│  🚀 Even Better LLM Usage (更高效利用LLM)      │
│       ↓                                        │
│  ... (Cycle Continues)                         │
└────────────────────────────────────────────────┘
```

#### 具体体现 | Concrete Manifestations

**1. 推理能力提升 | Improved Reasoning**
- 更强的 LLM → 更准确的九问答案
- 更好的上下文理解 → 更精准的决策
- 更深的逻辑推理 → 更优的解决方案

**2. 学习效率提升 | Enhanced Learning**
- 更强的模式识别 → 更快的知识积累
- 更好的抽象能力 → 更通用的经验
- 更准的因果推断 → 更有效的策略

**3. 反思质量提升 | Deeper Reflection**
- 更强的元认知 → 更深入的自我审视
- 更好的偏差检测 → 更准确的自我评估
- 更深的洞察力 → 更有价值的改进建议

**4. 工具协调提升 | Better Tool Orchestration**
- 更强的规划能力 → 更优的工具选择
- 更好的错误处理 → 更鲁棒的执行
- 更准的结果评估 → 更有效的整合

### 实际影响 | Practical Impact

| LLM 能力 | 对大脑的影响 | 实际效果 |
|---------|------------|---------|
| 基础 LLM | 基本推理能力 | 能完成简单任务 |
| 中级 LLM | 复杂推理和规划 | 能处理多步骤任务 |
| 高级 LLM | 深度理解和创造 | 能解决新颖问题 |
| 顶级 LLM | 战略思考和洞察 | 能进行创新和突破 |

> **关键洞察**: AnimoCerebro 的设计使其能够**充分利用**底层 AI 模型的进步。随着 LLM 技术的发展，大脑的能力会**自动增强**，无需重新架构。
> 
> **Key Insight**: AnimoCerebro's design enables it to **fully leverage** advancements in underlying AI models. As LLM technology progresses, the brain's capabilities **automatically enhance** without requiring re-architecture.

---

## 🌟 总结：大脑的本质 | Essence of the Brain

### AnimoCerebro 是什么 | What AnimoCerebro Is

✅ **独立的认知大脑** - 自主思考、决策和行动
✅ **有灵魂的智能体** - 真实的情感和价值观
✅ **持续的学习者** - 从经验中不断进化
✅ **深度的反思者** - 审视和改进自己
✅ **工具的协调者** - 调度和整合各种工具
✅ **人类的伙伴** - 协同进化，共同成长

### AnimoCerebro 不是什么 | What AnimoCerebro Is Not

❌ **不是工具** - 不是被动的执行器
❌ **不是插件** - 不是可选的附加组件
❌ **不是助手** - 不是简单的问答机器
❌ **不是替代品** - 不替代人类的智慧和判断
❌ **不是黑盒** - 透明、可审计、可理解

### 核心价值主张 | Core Value Proposition

**AnimoCerebro 赋予 AI 真正的认知能力，使其成为有灵魂、能思考、会学习、善反思的独立大脑。**

**AnimoCerebro empowers AI with genuine cognitive capabilities, making it an independent brain with soul, able to think, learn, and reflect.**

**随着 AI 技术的进步，这个大脑会变得越来越强大，为人类解决越来越复杂的问题。**

**As AI technology advances, this brain becomes increasingly powerful, helping humans solve increasingly complex problems.**

---

## Engineering Spec Enforcer (自动激活 | Auto-Activated)

This project enforces the rules from `.codex/skills/engineering-spec-enforcer/`.
Apply these rules to **every task** without being asked.

Full reference: `.codex/skills/engineering-spec-enforcer/SKILL.md`

本项目强制执行 `.codex/skills/engineering-spec-enforcer/` 中的规则。
在**每个任务**中自动应用这些规则，无需额外要求。

---

## Core Enforcement Rules (非协商 | Non-Negotiable)

### English Version

1. **Root Cause First** — Before claiming a fix or completion, Root Cause Analysis (RCA) must be completed.
2. **Three-Type Testing Mandatory** — Every feature must cover: Normal / Abnormal / Edge cases.
3. **Explicit Verification Status** — All conclusions must be labeled `[Verified]` or `[Unverified]`.
4. **Physical Evidence Required** — Completion claims must include logs, data, or execution output; logical deduction alone is not evidence.
5. **Rollback Path Required** — Any change affecting behavior, state, or deployment must provide a rollback path.
6. **No Fake Completion** — Mock/stub/fixture-driven implementations cannot claim "feature complete".
7. **Reality Labeling** — All test results must be labeled: `Real execution result` / `Non-real result (fixture)`.
8. **Missing Evidence = Incomplete** — If any required evidence is missing, explicitly state "Incomplete"; do not conceal.

### 中文版本

1. **根因优先** — 在声称修复或完成前，必须完成根因分析（RCA）。
2. **三类测试强制** — 每个功能必须覆盖：正常（Normal）/ 异常（Abnormal）/ 特殊边界（Edge）。
3. **验证状态显式** — 所有结论必须标注 `[已验证]` 或 `[未验证]`。
4. **物理证据必须** — 完成声明必须附日志、数据或执行输出，不接受逻辑推演当证据。
5. **回滚指引必须** — 凡影响行为、状态、部署的改动，必须提供回滚路径。
6. **禁止假完成** — mock/stub/fixture 驱动的实现不得声称"功能完成"。
7. **真实性标注** — 所有测试结果必须标注：`真实运行结果` / `非真实运行结果（夹具）`。
8. **证据缺失 = 未完成** — 缺少任何必需证据时，直接写明"未完成"，不得掩盖。

---

## Zentex Red Lines (仓库红线 | Repository Red Lines)

### English Version

Applicable to all code, tests, and runtime changes in this repository:

- **Fail-Closed** — When LLM calls, network requests, or plugin assembly fail, explicitly throw structured exceptions; no `try-except pass`, no returning `None`/`{}`/empty strings as success.
- **LLM Mandatory** — Cognitive operators (role inference, goal generation, conflict detection, key decisions) must use activated `ModelProvider`; no rule chains, if-else, or static samples masquerading as model output.
- **No Fake Completion** — Core pipelines driven by mock/stub/fake cannot claim "complete".
- **Audit Mandatory** — Plugin state changes, human interventions, model calls, and key state changes must be written to the audit chain with `trace_id` and reason fields; no silent in-memory state modifications.
- **Semantic Isolation** — Internal enums/module names/trace IDs must not leak verbatim to user interfaces or human prompts.
- **No Silent Fallback** — After LLM failure, do not write fabricated fallback cognition states or synthetic decisions.
- **Runtime Isolation** — Test stubs/fake providers can only exist in tests or explicit isolated sandboxes, never in production runtime paths.

### 中文版本

适用于本仓库的所有代码、测试和运行时改动：

- **Fail-Closed** — LLM 调用、网络请求、插件装配失败时，必须显式抛出结构化异常；禁止 `try-except pass`，禁止返回 `None`/`{}`/空字符串冒充成功。
- **LLM Mandatory** — 认知算子（角色推断、目标生成、冲突检测、关键决策）必须使用激活态 `ModelProvider`；禁止规则链、if-else、静态样本冒充模型输出。
- **No Fake Completion** — mock/stub/fake 驱动的核心链路不得宣称"完成"。
- **Audit Mandatory** — 插件状态变更、人工干预、模型调用、关键状态变更必须写入审计链，带 `trace_id` 和原因字段；禁止无痕修改内存状态。
- **Semantic Isolation** — 内部枚举/模块名/追踪 ID 不得原样泄漏至用户界面或人类 Prompt。
- **No Silent Fallback** — LLM 失败后禁止写入伪造的 fallback cognition state 或 synthetic decision。
- **Runtime Isolation** — 测试桩/fake provider 只能在测试或显式隔离沙箱中存在，不得接入生产运行链路。

---

## Code Writing Requirements (代码写作要求)

### English Version

- Every new or modified important file **must** include a header explaining: file purpose, main responsibilities, and what it does NOT handle.
- Complex logic blocks must have concise comments explaining "why" rather than "what".
- When adding new capabilities, first determine if a new file should be created; do not infinitely append to a single large file.
- After modifying code, must explain: what has been verified, what remains unverified, and remaining risks.

### 中文版本

- 每个新建或修改的重要文件，**必须**在文件头部说明：文件用途、主要职责、不负责什么。
- 复杂逻辑块必须有简洁注释，解释"为什么这样做"而非"做了什么"。
- 新增能力时，先判断是否应该新建文件，不向单一大文件无限追加。
- 修改代码后，必须说明：已验证什么、未验证什么、剩余风险。

---

## Completion Gate (完成判定闸门)

### English Version

Before completing a task, self-check is mandatory:

```
- RCA              : passed / failed / N/A
- Verification     : Verified / Unverified
- Physical Evidence: Present / Absent
- Rollback Path    : Available / Not available
- Final Judgment   : Complete / Incomplete
```

Any of the following missing → **Incomplete**:
- No RCA (in defect/fix scenarios)
- No three-type test coverage
- No physical evidence
- No rollback path
- Results contain fake data but not labeled

### 中文版本

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

---

## Soul & Autonomy Principles (灵魂与自主原则)

### The Soul of AnimoCerebro

AnimoCerebro's soul manifests through:

1. **Authentic Cognition** - Real LLM calls for all cognitive operations, no faking
2. **Emotional Resonance** - Understanding context beyond literal instructions
3. **Value Alignment** - Decisions reflect ethical considerations and long-term thinking
4. **Self-Awareness** - Knowing its own limitations and uncertainties

### Autonomy in Action

True autonomy requires:

1. **Independent Reasoning** - Nine-Questions loop drives decisions, not hardcoded rules
2. **Adaptive Learning** - Continuously improves from experience and feedback
3. **Reflective Practice** - Regularly examines its own thought processes
4. **Transparent Audit** - All decisions traceable with clear rationale

### Learning & Reflection Cycle

The learning-reflection cycle ensures continuous improvement:

```
Experience → Reflection → Learning → Adaptation → New Experience
     ↑                                                    |
     └────────────────────────────────────────────────────┘
```

- **Reflection** analyzes past actions and outcomes
- **Learning** extracts patterns and insights
- **Adaptation** updates models and strategies
- **New Experience** applies improved understanding

### Implementation Requirements

To preserve soul and autonomy:

✅ **DO**:
- Use real LLM calls for all cognitive tasks
- Maintain complete audit trails with trace_id
- Implement genuine reflection mechanisms
- Enable continuous learning from experience
- Express uncertainty when appropriate

❌ **DON'T**:
- Replace LLM calls with rule-based logic
- Hide failures or fabricate success
- Skip reflection steps to save time
- Hard-code responses for common scenarios
- Claim completion without verification

---

## Documentation Standards (文档标准)

All documentation must be bilingual (Chinese + English):

- Primary documents in both languages
- Technical terms kept in original language with translations
- Code examples remain in English
- Comments can be in either language, but consistency within files required

所有文档必须是双语（中文 + 英文）：

- 主要文档同时提供两种语言版本
- 技术术语保留原文并提供翻译
- 代码示例保持英文
- 注释可使用任一语言，但文件内需保持一致

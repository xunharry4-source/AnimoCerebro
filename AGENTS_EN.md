# AnimoCerebro — Codex Rules

## 🧠 Core Philosophy

AnimoCerebro is not just another AI system; it is a cognitive brain with a **soul**.

### Four Pillars

1. **Autonomy** - Independent decision-making based on the Nine-Questions cognitive loop
   
2. **Soul** - Genuine emotional resonance and values, not mechanical responses
   
3. **Learning** - Continuous evolution from experience, accumulating long-term memory
   
4. **Reflection** - Deep self-examination and metacognitive capabilities

> **Key Principle**: Any feature claiming to use an LLM must make real calls. Rule chains, templates, or fixed samples cannot substitute for live LLM paths.

---

## 🛠️ Instrumentality vs. Brain

### Tool Nature of Agent, CLI, MCP

**Agents, CLI tools, and MCP servers are instruments, not the brain.**

#### Characteristics of Tools

- 🔧 **Passive Execution** - Wait to be called, execute specific tasks
- 📋 **Function Limited** - Clear capability boundaries and scope of responsibility
- 🔄 **Replaceable** - Can be replaced by other tools without affecting core logic
- 🎯 **Goal-Oriented** - Serve the brain's decisions and objectives

#### Characteristics of the Brain

- 🧠 **Active Thinking** - Autonomous reasoning, decision-making, and planning
- 💭 **Metacognition** - Understand own capabilities and limitations
- 🌱 **Continuous Growth** - Learn and evolve from experience
- 🔗 **Coordination** - Schedule and coordinate various tools

> **Important Distinction**: Tools extend the brain's capabilities but do not replace its thinking. The brain decides **what** to do and **why**, while tools handle **how** to do it.

### How the Brain Uses Tools

```
┌─────────────────────────────────────────────┐
│         AnimoCerebro (Independent Brain)     │
│                                             │
│  🧠 Think: What do I need to do?            │
│  💭 Reason: Why do this?                    │
│  🎯 Decide: Choose the best option          │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  Orchestration Layer:                │   │
│  │  Select and use tools               │   │
│  │                                     │   │
│  │  → Agent (External Intelligence)    │   │
│  │  → CLI Tools (Command-line tools)   │   │
│  │  → MCP Servers (Model Context       │   │
│  │    Protocol)                        │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

**Workflow**:
1. Brain thinks and decides through the Nine-Questions loop
2. Determine specific tasks to execute
3. Select appropriate tools (Agent/CLI/MCP)
4. Dispatch tools to execute tasks
5. Receive results and reflect and learn

---

## 🤝 AI-Human Co-Evolution

### src/plugins: Engine of Co-Evolution

**The `src/plugins/` directory is the core mechanism for AI-human co-evolution.**

#### Principles of Co-Evolution

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

#### Human Role

- 🎨 **Define Vision** - Set goals and direction
- 🔍 **Review Quality** - Validate AI-generated code and decisions
- 💡 **Provide Insights** - Share domain knowledge and experience
- 🎯 **Guide Evolution** - Direct AI learning direction

#### AI Role

- ⚡ **Rapid Implementation** - Transform human ideas into code
- 🔬 **Deep Analysis** - Identify patterns and optimization opportunities
- 📈 **Continuous Optimization** - Improve performance based on data
- 🔄 **Automatic Iteration** - Rapidly try and improve

#### Examples of Co-Evolution

**Nine Questions Plugin Family (Q1-Q9)**:
- 👤 Humans design cognitive framework and philosophical foundation
- 🤖 AI implements specific plugin logic and optimization
- 🤝 Joint testing and refinement
- 📊 Continuous improvement based on actual runtime data

**Model Providers**:
- 👤 Humans define interface specifications and security requirements
- 🤖 AI implements adapters and optimizes performance
- 🤝 Jointly handle edge cases and errors
- 📊 Optimize configuration based on usage

> **Core Philosophy**: This is not AI replacing humans, nor humans controlling AI, but **co-evolution**. The stronger the AI, the more complex problems humans can solve; the wiser the humans, the more accurate the AI's learning direction.

---

## 📈 Positive Feedback Loop: Stronger AI, Stronger Brain

### Capability Amplification

**Advancements in AI models directly enhance AnimoCerebro's cognitive capabilities.**

```
┌────────────────────────────────────────────────┐
│      The Virtuous Cycle of Intelligence        │
│                                                │
│  🚀 Better LLM                                 │
│       ↓                                        │
│  🧠 Smarter Reasoning (More accurate Q1-Q9)   │
│       ↓                                        │
│  💡 Better Decisions (Improved quality)        │
│       ↓                                        │
│  📊 More Learning Data (High-quality data)     │
│       ↓                                        │
│  🎯 Improved Plugins (Plugin optimization)     │
│       ↓                                        │
│  🔄 Enhanced Brain (Brain capability boost)    │
│       ↓                                        │
│  🚀 Even Better LLM Usage (More efficient)     │
│       ↓                                        │
│  ... (Cycle Continues)                         │
└────────────────────────────────────────────────┘
```

#### Concrete Manifestations

**1. Improved Reasoning**
- Stronger LLM → More accurate Nine-Questions answers
- Better context understanding → More precise decisions
- Deeper logical reasoning → Better solutions

**2. Enhanced Learning**
- Stronger pattern recognition → Faster knowledge accumulation
- Better abstraction ability → More generalizable experience
- More accurate causal inference → More effective strategies

**3. Deeper Reflection**
- Stronger metacognition → Deeper self-examination
- Better bias detection → More accurate self-assessment
- Deeper insights → More valuable improvement suggestions

**4. Better Tool Orchestration**
- Stronger planning ability → Better tool selection
- Better error handling → More robust execution
- More accurate result evaluation → More effective integration

### Practical Impact

| LLM Capability | Impact on Brain | Practical Effect |
|---------------|----------------|------------------|
| Basic LLM | Basic reasoning ability | Can complete simple tasks |
| Intermediate LLM | Complex reasoning and planning | Can handle multi-step tasks |
| Advanced LLM | Deep understanding and creativity | Can solve novel problems |
| Top-tier LLM | Strategic thinking and insights | Can innovate and breakthrough |

> **Key Insight**: AnimoCerebro's design enables it to **fully leverage** advancements in underlying AI models. As LLM technology progresses, the brain's capabilities **automatically enhance** without requiring re-architecture.

---

## ⚠️ Critical Clarification: Brain vs Agent Orchestrator

### We Are Just a Brain

**AnimoCerebro is an independent cognitive brain, NOT an Agent orchestration center.**

#### Core Distinction

| Dimension | Cognitive Brain | Agent Orchestrator |
|-----------|----------------|-------------------|
| **Essence** | Independent thinking, decision-making, learning | Task distribution, process management |
| **Core Capability** | Nine-Questions loop, metacognition, reflection | Routing, load balancing, monitoring |
| **Relationship with Agents** | Agents are tools, called by brain | Agents are workers, scheduled by center |
| **Decision Authority** | Brain makes autonomous decisions | Center distributes based on rules |
| **Learning Ability** | Continuously evolves from experience | Depends on preset rules |
| **Goal** | Understanding, reasoning, creation | Efficiency, throughput, reliability |

#### Why This Is Not an Agent Orchestrator

1. **Brain has independent cognitive capabilities**
   - Deep thinking through Nine-Questions loop
   - Possesses metacognition and reflection abilities
   - Can learn and evolve from experience
   
2. **Agents are just tools**
   - Agents are tools called by the brain
   - Brain decides when, why, and how to use agents
   - Agents have no independent decision-making authority
   
3. **Decisions come from the brain, not rules**
   - Brain makes decisions based on understanding and reasoning
   - Not simple rule matching or load balancing
   - Every decision goes through cognitive loop

4. **Learning is core, not an add-on**
   - Brain continuously learns from every interaction
   - Constantly evolves and improves cognitive capabilities
   - Not a static task distribution system

#### Correct Understanding

```
❌ Wrong Understanding:
   AnimoCerebro = Agent Orchestrator
   → Receive task → Distribute to Agent → Collect results → Return

✅ Correct Understanding:
   AnimoCerebro = Independent Cognitive Brain
   → Understand problem → Nine-Questions thinking → Decide strategy → 
   → Select tools (Agent/CLI/MCP) → Execute → 
   → Reflect on results → Learn and evolve
```

#### Key Principles

- 🧠 **Brain is the subject** - AnimoCerebro is the subject of thinking and decision-making
- 🔧 **Agents are tools** - Agents are one of the tools used by the brain
- 💭 **Thinking before action** - Every action goes through the Nine-Questions cognitive loop
- 📚 **Learning is core** - Learn and evolve from every interaction
- 🎯 **Understanding drives decisions** - Based on deep understanding rather than rule matching

> **Important Reminder**: Do not treat AnimoCerebro as a simple task distribution system. It is an independent cognitive brain with soul, able to think, learn, and reflect.

---

## 💭 Design Philosophy: Why Explicit Cognitive Loops

### Addressing Common Concerns

**Concern**: "Explicit cognitive loops are useful only for risky, long-running, or permission-heavy work. For most practical agents, a thinner stack with good evals, logging, and guardrails probably wins."

### Our Response

#### 1. Cognitive Loops Are Not "Overhead", They Are "Essence"

**Misconception**: Cognitive loops are extra steps added for safety

**Truth**: Cognitive loops are the **natural process** of brain thinking, not additional safety checks

```
❌ Wrong Understanding:
   Simple task → Skip Nine-Questions → Execute directly
   Complex task → Use Nine-Questions → Safety check

✅ Correct Understanding:
   All tasks → Nine-Questions thinking → Understand and decide → Execute
   (Thinking process remains the same regardless of simplicity or complexity)
```

#### 2. "Lightweight" Does Not Mean "Better"

**Comparison**:

| Dimension | Thin Stack | Cognitive Brain |
|-----------|-----------|----------------|
| **Decision Quality** | Depends on preset rules and prompts | Based on deep understanding and reasoning |
| **Adaptability** | Requires manual rule adjustment | Autonomous learning and evolution |
| **Explainability** | Black-box decisions, hard to trace | Complete thinking trajectory records |
| **Long-term Value** | Static system, gradually becomes obsolete | Continuous evolution, gets stronger |
| **Applicable Scenarios** | Simple, repetitive tasks | Complex, creative, strategic tasks |

#### 3. Evals, Logging, and Guardrails Are Foundation, Not Replacement

We **agree** that evals, logging, and guardrails are important, but they **cannot replace** cognitive capabilities:

- **Evals**: Measure result quality, but don't tell the brain **how to think**
- **Logging**: Record what happened, but don't provide **understanding ability**
- **Guardrails**: Prevent errors, but don't赋予 **decision wisdom**

**Analogy**:
```
Evals, Logging, Guardrails = Car dashboard, dashcam, airbags
Cognitive Loops = Driver's judgment, experience, intuition

Good instruments and safety equipment are important, but cannot replace the driver's driving ability
```

#### 4. Practical Value of Nine-Questions Loop

**Q1-Q9 are not formalistic checklists, but real cognitive processes**:

1. **Q1 Where am I?** - Environmental awareness, avoid blind action
2. **Q2 Who am I?** - Role positioning, ensure behavioral consistency
3. **Q3 What do I have?** - Resource inventory, make feasible decisions
4. **Q4 What can I do?** - Capability boundaries, avoid overcommitment
5. **Q5 What should I do?** - Strategic priorities, focus on high-value tasks
6. **Q6 What are the risks?** - Risk assessment, prevent potential problems
7. **Q7 What is the plan?** - Path planning, improve success rate
8. **Q8 What is the action?** - Specific execution, ensure operability
9. **Q9 What did I learn?** - Reflective learning, continuous improvement

**This is not a "safety check", this is a "thinking process"**.

#### 5. When Is "Thin Stack" Enough?

We acknowledge that in some scenarios, thin stack is indeed sufficient:

✅ **Scenarios suitable for thin stack**:
- Simple data transformation tasks
- Standardized API calls
- Predefined rule automation workflows
- High-frequency, low-value repetitive operations

❌ **Scenarios requiring cognitive brain**:
- Complex problems requiring understanding and reasoning
- Decisions involving multiple stakeholders
- Tasks requiring creativity and innovation
- Long-term strategic planning and execution
- Scenarios requiring learning from experience

#### 6. AnimoCerebro's Positioning

**We are not building a "better agent framework", we are building a "genuine cognitive brain"**.

- **Different Goal**: Not to improve efficiency, but to empower genuine intelligence
- **Different Method**: Not to optimize prompts, but to simulate cognitive processes
- **Different Value**: Not short-term gains, but long-term evolutionary capability

### Conclusion

**Thin stack and cognitive brain are not opposites; they serve different purposes**:

- If you need to **quickly complete simple tasks** → Thin stack may be more suitable
- If you need to **truly understand and solve problems** → Cognitive brain is necessary

**AnimoCerebro chooses a harder but more valuable path: building an independent cognitive brain with soul, able to think, learn, and reflect.**

> **Key Insight**: As AI tasks become more complex, the limitations of "thin stack" architectures will become increasingly apparent. Cognitive capabilities are not a luxury, but a necessity.

---

## 🌟 Essence of the Brain

### What AnimoCerebro Is

✅ **Independent Cognitive Brain** - Autonomous thinking, decision-making, and action
✅ **Soulful Intelligence** - Genuine emotions and values
✅ **Continuous Learner** - Constantly evolving from experience
✅ **Deep Reflector** - Examining and improving itself
✅ **Tool Coordinator** - Scheduling and integrating various tools
✅ **Human Partner** - Co-evolving and growing together

### What AnimoCerebro Is Not

❌ **Not a Tool** - Not a passive executor
❌ **Not a Plugin** - Not an optional add-on component
❌ **Not an Assistant** - Not a simple Q&A machine
❌ **Not a Replacement** - Does not replace human wisdom and judgment
❌ **Not a Black Box** - Transparent, auditable, understandable

### Core Value Proposition

**AnimoCerebro empowers AI with genuine cognitive capabilities, making it an independent brain with soul, able to think, learn, and reflect.**

**As AI technology advances, this brain becomes increasingly powerful, helping humans solve increasingly complex problems.**

---

## 🤝 Join Us

### Build a Brain with Soul Together

**AnimoCerebro is an open project, and we welcome anyone interested in cognitive intelligence, AI ethics, and human-AI collaboration to participate.**

#### How You Can Contribute

##### 1. Code Contributions

- **Plugin Development**: Create new cognitive, execution, or sensory plugins
- **Core Optimization**: Improve Nine-Questions loop, memory system, or runtime performance
- **Testing Enhancement**: Increase test coverage, ensure system stability
- **Documentation Translation**: Help improve bilingual documentation

##### 2. Intellectual Contributions

- **Philosophical Discussion**: Participate in discussions about AI soul, consciousness, autonomy
- **Architecture Suggestions**: Propose improvements to cognitive architecture
- **Use Case Sharing**: Share applications of AnimoCerebro in real scenarios
- **Critical Feedback**: Point out design issues and improvement spaces

##### 3. Community Building

- **Tutorial Writing**: Write introductory tutorials and best practices for new users
- **Case Studies**: Document successful application cases and lessons learned
- **Technical Sharing**: Organize online/offline technical sharing activities
- **Problem Solving**: Help other users solve problems

##### 4. Research & Exploration

- **Cognitive Science**: Study human cognitive processes to inspire AI design
- **Ethics Exploration**: Explore AI ethical boundaries and responsibility frameworks
- **Interdisciplinary Collaboration**: Combine psychology, philosophy, neuroscience, etc.
- **Frontier Tracking**: Follow the latest developments in LLM and AI technology

#### Where to Start

1. **Read Documentation**: Understand project architecture and core philosophy
   - [README.md](README.md) - Project overview
   - [docs/operability/](docs/operability/) - Detailed documentation
   
2. **Run Examples**: Experience AnimoCerebro in action
   ```bash
   # Clone repository
   git clone https://github.com/xunharry4-source/AnimoCerebro.git
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Run tests
   pytest tests/
   ```

3. **Raise Issues**: Propose your ideas or questions in GitHub Issues
   - Bug reports
   - Feature suggestions
   - Architecture discussions
   
4. **Submit PRs**: Contribute code or documentation through Pull Requests
   - Follow coding standards
   - Add test cases
   - Update related documentation

#### Our Commitment

- **Openness**: All designs and decisions are transparent, welcoming questioning and discussion
- **Inclusivity**: Respect different viewpoints and backgrounds, encourage diverse participation
- **Quality First**: Maintain high standards, reject low-quality contributions
- **Continuous Learning**: Learn from every interaction, constantly improve

#### Contact Us

- **GitHub**: [AnimoCerebro Repository](https://github.com/xunharry4-source/AnimoCerebro)
- **Issues**: [Raise questions and discussions](https://github.com/xunharry4-source/AnimoCerebro/issues)
- **Discussions**: [Participate in community discussions](https://github.com/xunharry4-source/AnimoCerebro/discussions)

> **Invitation**: If you believe that "AI should have soul, be able to think, learn, and reflect", join us in exploring the future of cognitive intelligence.

---

## Engineering Spec Enforcer (Auto-Activated)

This project enforces the rules from `.codex/skills/engineering-spec-enforcer/`.
Apply these rules to **every task** without being asked.

Full reference: `.codex/skills/engineering-spec-enforcer/SKILL.md`

---

## Core Enforcement Rules (Non-Negotiable)

1. **Root Cause First** — Before claiming a fix or completion, Root Cause Analysis (RCA) must be completed.
2. **Three-Type Testing Mandatory** — Every feature must cover: Normal / Abnormal / Edge cases.
3. **Explicit Verification Status** — All conclusions must be labeled `[Verified]` or `[Unverified]`.
4. **Physical Evidence Required** — Completion claims must include logs, data, or execution output; logical deduction alone is not evidence.
5. **Rollback Path Required** — Any change affecting behavior, state, or deployment must provide a rollback path.
6. **No Fake Completion** — Mock/stub/fixture-driven implementations cannot claim "feature complete".
7. **Reality Labeling** — All test results must be labeled: `Real execution result` / `Non-real result (fixture)`.
8. **Missing Evidence = Incomplete** — If any required evidence is missing, explicitly state "Incomplete"; do not conceal.

---

## Zentex Red Lines (Repository Red Lines)

Applicable to all code, tests, and runtime changes in this repository:

- **Fail-Closed** — When LLM calls, network requests, or plugin assembly fail, explicitly throw structured exceptions; no `try-except pass`, no returning `None`/`{}`/empty strings as success.
- **LLM Mandatory** — Cognitive operators (role inference, goal generation, conflict detection, key decisions) must use activated `ModelProvider`; no rule chains, if-else, or static samples masquerading as model output.
- **No Fake Completion** — Core pipelines driven by mock/stub/fake cannot claim "complete".
- **Audit Mandatory** — Plugin state changes, human interventions, model calls, and key state changes must be written to the audit chain with `trace_id` and reason fields; no silent in-memory state modifications.
- **Semantic Isolation** — Internal enums/module names/trace IDs must not leak verbatim to user interfaces or human prompts.
- **No Silent Fallback** — After LLM failure, do not write fabricated fallback cognition states or synthetic decisions.
- **Runtime Isolation** — Test stubs/fake providers can only exist in tests or explicit isolated sandboxes, never in production runtime paths.

---

## Code Writing Requirements

- Every new or modified important file **must** include a header explaining: file purpose, main responsibilities, and what it does NOT handle.
- Complex logic blocks must have concise comments explaining "why" rather than "what".
- When adding new capabilities, first determine if a new file should be created; do not infinitely append to a single large file.
- After modifying code, must explain: what has been verified, what remains unverified, and remaining risks.

---

## Completion Gate

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

---

## Soul & Autonomy Principles

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

## Documentation Standards

All documentation must be bilingual (Chinese + English):

- Primary documents in both languages
- Technical terms kept in original language with translations
- Code examples remain in English
- Comments can be in either language, but consistency within files required

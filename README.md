# AnimoCerebro

![AnimoCerebro Logo](docs/logo.jpeg)

> **⚠️ Project Status**: This project is currently in **active development and functional testing phase**. Core features are implemented but still undergoing testing and refinement. APIs and configurations may change. Use with caution in production environments.

[中文文档](README.zh.md)

## 🧠 A Cognitive Brain with Soul

AnimoCerebro is more than an AI system — it's a **cognitive brain with soul**, built on four fundamental pillars:

### The Four Pillars | 四大支柱

1. **🤖 Autonomy (自主)** - Independent decision-making through the Nine-Questions cognitive loop
   - Not just following instructions, but reasoning about context, constraints, and consequences
   - Making choices based on deep understanding rather than pattern matching

2. **💫 Soul (灵魂)** - Genuine emotional resonance and value alignment
   - Understanding the spirit behind requests, not just literal words
   - Expressing authentic uncertainty, curiosity, and ethical considerations
   - Building trust through transparency and honesty

3. **📚 Learning (学习)** - Continuous evolution from experience
   - Accumulating long-term memory across sessions
   - Adapting strategies based on outcomes and feedback
   - Growing smarter with each interaction

4. **🔍 Reflection (反思)** - Deep self-examination and metacognition
   - Analyzing its own thought processes and decisions
   - Identifying patterns, biases, and areas for improvement
   - Engaging in honest self-critique and course correction

> **Key Principle**: These aren't buzzwords — they're implemented through real mechanisms:
> - Real LLM calls (no rule-based faking)
> - Complete audit trails with trace_id
> - Genuine reflection loops
> - Continuous learning from experience

## Overview | 概览

AnimoCerebro is the **Brain** for Agents and Host Systems. It provides an **External Brain** for all AI species, including Agents and openCLaw. It empowers AI with **autonomy, reflection, learning, and self-upgrading** capabilities, enabling it to **act autonomously** based on the results of the "Nine Questions" cognitive loop.

AnimoCerebro 是 Agent 和宿主系统的**大脑**。它为所有 AI 物种（包括 Agent 和 openCLaw）提供**外挂大脑**。它赋予 AI **自主、反思、学习和自我升级**的能力，使其能够基于“九问”认知循环的结果**自主行动**。

AnimoCerebro is responsible for reasoning, role inference, goal generation, risk assessment, memory accumulation, delegation advice, and long-term experience exchange. It is the core engine for AI to achieve high-level cognition and independent action.

AnimoCerebro 负责推理、角色推断、目标生成、风险评估、记忆积累、委托建议和长期经验交换。它是 AI 实现高级认知和独立行动的核心引擎。

**🎉 Major Version Update (v2.1.0-alpha)**: This project has undergone a significant architectural evolution with enhanced modularity, plugin architecture, and autonomous decision-making capabilities.

**Latest Update - Nine Questions Refactoring (30% Complete)**:
- 🔄 **Major Nine Questions Framework Refactoring** in progress
- ✅ Q1 (Evidence), Q3 (Inventory), Q8 (Planning), Q9 (Action) - Complete
- 🔄 Q2, Q4-Q7 - In progress or planned
- 🆕 External Connectors System for third-party integrations
- 🆕 Enhanced Agent system with protocol documentation
- 📊 See [Nine Questions Refactoring Progress](docs/NINE_QUESTIONS_REFACTORING_PROGRESS.md) for details 

**New in v2.0**:
- 🆕 Autonomous Control System (G31A) - Stimulus-driven task management
- 🆕 Multi-Zentex Collaboration Protocol (G36) - Cross-instance coordination
- 🆕 Soul Migration & Continuity (G34) - Encrypted identity transfer
- 🆕 Governance & Observability - Unified error system and trace replay
- 🆕 Kernel Runtime Refactoring - Domain-driven architecture
- 🆕 Foundation Framework - Contract-first design

See [RELEASE_NOTES_v2.0.md](docs/RELEASE_NOTES_v2.0.md) for comprehensive details or [INDEX.md](docs/INDEX.md) for documentation navigation.

**🎉 主要版本更新 (v2.0)**: 本项目经历了重大的架构演进，具有增强的模块化、插件架构和自主决策能力。

**v2.0 新特性**:
- 🆕 自主控制系统 (G31A) - 刺激驱动的任务管理
- 🆕 多实例协作协议 (G36) - 跨实例协调
- 🆕 灵魂迁移与连续性 (G34) - 加密身份传输
- 🆕 治理与可观测性 - 统一错误系统和追踪回放
- 🆕 内核运行时重构 - 领域驱动架构
- 🆕 基础框架 - 契约优先设计

详见[RELEASE_NOTES_v2.0.md](docs/RELEASE_NOTES_v2.0.md)获取完整详情，或查看[INDEX.md](docs/INDEX.md)了解文档导航。

## What It Is

AnimoCerebro is built around a **nine-question cognitive loop**, which drives AI's autonomous decision-making:

1. Where am I
2. Who am I
3. What do I have
4. What can I do
5. What am I allowed to do
6. What else can I do
7. What should I not do even if I can
8. What should I do
9. How should I do it

**AI can autonomously drive subsequent tasks based on the results of these nine questions, with clear goals and boundaries.**

## Positioning

AnimoCerebro is:

- **The Core Brain for AI**: Providing reasoning, learning, reflection, and self-evolutionary capabilities for Agents.
- **A Universal External Brain**: Capable of attaching to openCLaw, various Agent frameworks, or existing host systems.
- **An Autonomous Behavior Engine**: Enabling autonomous decisions and actions based on cognitive analysis.
- **A Long-term Experience Layer**: Empowering AI with continuous learning across tasks and time.

Do not treat it as:

- a mandatory customer-facing reply engine
- a hard takeover layer
- a reason to rewrite a working host architecture

## Current Protocol

The current public protocol is a layered protocol for registration, capability discovery, delegation, receipts, escalations, experience exchange, and host adaptation.

Primary protocol docs:

- [Protocol Design](docs/zmsp_protocol_design.md)
- [Functional Modules](docs/operability/FUNCTION_MODULES.md)
- [Startup Guide](docs/启动指南.md)
- [Configuration Guide](docs/配置指南.md)

## Documentation Map

### 📚 Quick Navigation
- **[🗺️ Documentation Index](docs/INDEX.md)** - Complete documentation navigation guide
- **[📝 Release Notes v2.0](docs/RELEASE_NOTES_v2.0.md)** - What's new in the latest version

### Core Documentation
- [Quick Start & Startup](docs/operability/STARTUP_AND_TEST.md) - One-click startup methods
- [Functional Modules](docs/operability/FUNCTION_MODULES.md) - Module architecture overview
- [Runtime & Implementation](docs/operability/RUNTIME_AND_TESTS.md) - Detailed runtime architecture
- [Latest Directory Map](docs/operability/LATEST_DIRECTORY_MAP.md) - Current project structure
- [Plugin Guides](docs/operability/PLUGIN_GUIDES.md) - Plugin development guides

### Integration & Protocols
- [Protocol Design](docs/zmsp_protocol_design.md) - ZMSP protocol specification
- [Agent Integration](Agent/README.md) - Standard protocol for external agents
- [Agent Integration Guide](Agent/INTEGRATION_GUIDE.md) - How to connect your system

### Progress & Reports
- [Project Progress Report](docs/项目进度报告.md) - Architecture & progress tracking
- [Translation Status](docs/TRANSLATION_STATUS_REPORT.md) - Documentation translation progress

## Integration Model

AnimoCerebro is designed for minimal intrusion.

- Your host keeps its own execution architecture.
- AnimoCerebro provides reasoning, memory, coordination, and audit.
- The adapter layer registers the host, syncs capabilities, receives delegated work, and writes back results.

## Technical Specifications

### Module Independence Principle

All modules in AnimoCerebro follow strict independence principles:

1. **Module Autonomy**: Each module operates independently with clear boundaries
2. **Plugin-Based Upgrades**: Module functionality can be extended and upgraded through plugins without modifying core code
3. **Code Isolation**: Plugins must remain independent from each other - no cross-plugin dependencies allowed

### Plugin Architecture

AnimoCerebro implements a dual-plugin system:

#### External Plugins (`plugins/`)

**Purpose**: Connect external functionalities as components to extend brain capabilities

**Key Characteristics**:
- Serve as bridges between external systems and the brain
- Enable the brain to acquire additional capabilities from outside sources
- **STRICT RULE**: External plugins are **PROHIBITED** from importing or calling any code from `src/` directory
- Must interact with the brain exclusively through defined APIs and protocols
- Designed for third-party integrations and custom extensions

**Example Use Cases**:
- Custom data source connectors
- Third-party service integrations
- Specialized tool adapters

#### Internal Plugins (`src/plugins/`)

**Purpose**: Enable internal self-iteration and system upgrades

**Key Characteristics**:
- Part of the core system's self-evolution mechanism
- Can access and interact with `src/zentex/` core modules
- Support hot-reload and dynamic upgrading
- Implement core cognitive functions (e.g., Q1-Q9 nine questions)
- Managed by the internal plugin registry system

**Example Use Cases**:
- Nine Questions cognitive loop implementations
- Model provider adapters (Gemini, OpenAI, Claude)
- Cognitive tools, sensory processing, simulation engines
- Internal system enhancements and optimizations

### Plugin Development Rules

1. **Independence**: Each plugin must be self-contained with no dependencies on other plugins
2. **Clear Interfaces**: Plugins communicate through well-defined APIs only
3. **Upgrade Safety**: Plugin upgrades must not break existing functionality
4. **Isolation Boundary**: External plugins (`plugins/`) cannot import from `src/`; internal plugins (`src/plugins/`) can access core modules

## Current Capabilities

- Nine-question brain loop (Q1-Q9 complete implementation)
- Resident and daemon modes
- Web console with real-time dashboard
- SQLite-based persistent storage
- Plugin system with hot-reload support
- Delegation, receipt, escalation, and experience exchange
- Host adapter support for OpenClaw and custom integrations

## Truthfulness Boundary

For any product path that claims to use an LLM, AnimoCerebro does not allow rule-based logic, template assembly, fixed samples, fake transports, stubbed completions, or any code that only pretends to call an LLM to stand in for the real live LLM path.

If a feature requires a live LLM, the live call must actually happen. When credentials, network, provider health, or response validity fail, the system must fail or degrade truthfully and label the result as non-live or non-real where applicable.

The same standard applies to testing: any test that does not execute the real project logic under test is invalid and forbidden. Mocks or stubs may isolate external dependencies, but they cannot replace the product's own core logic and still be counted as proof.

## 📦 Installation

### Environment Preparation

Before installing, ensure your environment meets the following requirements:
- **Python**: 3.10 or higher
- **Node.js**: 18+ LTS version (for web console)
- **npm**: 9+ 
- **API Keys**: You will need API keys from providers like Google (Gemini), OpenAI, or Anthropic (Claude) for full cognitive capabilities.

### One-Click Installation

Install both backend and frontend dependencies in one go:

```bash
make install
```

*Behind the scenes, this runs `./scripts/setup_env.sh`.*

### Manual Install

If you prefer manual steps:

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Frontend
cd src/admin-portal && npm install
```

## 🚀 Quick Start

### One-Click Start

Start both backend and frontend (Vite dev server + Uvicorn):

```bash
make dev
```

*Behind the scenes, this runs `./scripts/dev_all.sh`.*

Access:
- Frontend: http://127.0.0.1:5173
- Backend: http://127.0.0.1:8000
- API Docs: http://127.0.0.1:8000/docs

### Restart Development Environment

If ports are occupied or processes are stuck:

```bash
make restart-dev
```

This will clean up old processes and restart everything cleanly.

### Manual Start

Start components separately:

```bash
# Start everything using script (wrapped by make dev)
./scripts/dev_all.sh

# Start backend only
export PYTHONPATH=src
python -m uvicorn zentex.web_console.dev_server:app --reload --ws websockets-sansio --host 127.0.0.1 --port 8000

# Start frontend (hot reload)
cd src/admin-portal && npm run dev
```

## ⚙️ Configuration

The system is configured via YAML files and environment variables. The primary configuration directory is `config/`.

- **Model Providers**: `config/provider_tools.yml` defines API bases, models, and environment variable names for LLM providers.
- **API Keys**: Store your API keys in a `.env` file at the project root (recommended) or set them as environment variables.
- **System Settings**: Local runtime state and environment variables can be used to further tune the brain's behavior.

### LLM API Key Configuration

**Method 1: Using `.env` file (Recommended)**

Create a `.env` file in the project root directory:

```bash
# .env file at project root
GEMINI_API_KEY=your-gemini-key-here
OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
```

**Method 2: Environment Variables**

```bash
export GEMINI_API_KEY=your-key-here
export OPENAI_API_KEY=sk-your-key
export ANTHROPIC_API_KEY=your-key-here
```

The system automatically loads `.env` file and resolves API keys based on the `api_key_env` field in `config/provider_tools.yml`.

Example `config/provider_tools.yml` entry:

```yaml
gemini:
  provider_name: gemini
  api_base: https://generativelanguage.googleapis.com/v1beta
  api_key_env: GEMINI_API_KEY
  default_model: gemini-1.5-pro
  timeout_seconds: 30
```

## LLM Providers

The system supports these LLM providers through `config/provider_tools.yml`:

- `openai_compat`: OpenAI-compatible endpoint (default: localhost:8317/v1)
- `openai`: OpenAI API (api.openai.com/v1)
- `chatgpt`: Alternative OpenAI endpoint
- `gemini`: Google Gemini API (generativelanguage.googleapis.com)
- `claude`: Anthropic Claude API (api.anthropic.com/v1)

Configure API keys in `.env` file or environment variables (see Configuration section above).

**Note**: The system also supports `GOOGLE_API_KEY` as an alias for `GEMINI_API_KEY` for compatibility.

## Testing

Run all tests:

```bash
make test
```

This executes:
- **Python tests**: 90 test files, 291+ test cases
- **Frontend tests**: React component tests

Run specific test suites:

```bash
# Backend tests only
make backend-test

# Frontend tests only
make frontend-test

# WebSocket integration tests
pytest tests/web_console/test_events_stream_integration.py -m integration
```

## Repository Structure

- **`src/zentex/`**: Core backend source code and services
  - Cognition, memory, safety, runtime, tasks, upgrade modules
  - Web console API implementation
  - This is the main source code directory
  
- **`src/plugins/`**: Internal plugin system (upgradable)
  - Q1-Q9 nine questions plugins (complete implementation)
  - Model providers (Gemini, OpenAI, Anthropic adapters)
  - Cognitive, sensory, simulation, execution plugins
  - Plugins can be independently developed and upgraded
  
- **`src/admin-portal/`**: Web management frontend
  - React + Vite + TypeScript
  - Real-time dashboard, agent management, task tracking
  - Plugin and MCP management interfaces
  
- **`scripts/`**: Startup and management scripts
  - `dev_all.sh`: One-click start all services
  - `restart_dev.sh`: Clean restart development environment
  - `setup_env.sh`: Environment initialization
  - `test_all.sh`: Run all tests
  - Various migration and utility scripts
  
- **`Agent/`**: Independent agents for testing and integration examples
  - Standard protocol implementations
  - Integration guides for external systems
  
- **`tests/`**: Automated end-to-end and unit tests
  - 90 test files covering all major modules
  - WebSocket, runtime, plugin, agent tests
  
- **`docs/`**: Comprehensive technical documentation
  - Operability guides, startup instructions
  - Architecture details, plugin development guides
  - Project progress reports
  
- **`config/`**: Central system configuration files
  - Provider tools configuration
  - System settings

## Next Reading

- [Startup Guide](docs/operability/STARTUP_AND_TEST.md) - Detailed startup instructions
- [Quick Start & Test](docs/operability/STARTUP_AND_TEST.md) - One-click commands
- [Functional Implementation](docs/operability/FUNCTION_MODULES.md) - Feature overview
- [Latest Directory Map](docs/operability/LATEST_DIRECTORY_MAP.md) - Current project structure
- [Project Summary](docs/operability/RUNTIME_AND_TESTS.md) - Implementation overview
- More documentation can be found in the `docs/` directory.

## Contact

**Let's build a soulful brain together!**

- Join the discussion via [GitHub Issues](https://github.com/xunharry4-source/AnimoCerebro/issues) or [GitHub Discussions](https://github.com/xunharry4-source/AnimoCerebro/discussions).
- If you have any ideas or suggestions, feel free to submit a Pull Request or open an Issue.

## License

This project is licensed under the [GNU GPL v3](LICENSE).

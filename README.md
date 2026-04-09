# AnimoCerebro

![AnimoCerebro Logo](docs/logo.jpeg)

[Chinese README](README.zh.md)

## Overview

AnimoCerebro is the **Brain** for Agents and Host Systems. It provides an **External Brain** for all AI species, including Agents and openCLaw. It empowers AI with **autonomy, reflection, learning, and self-upgrading** capabilities, enabling it to **act autonomously** based on the results of the "Nine Questions" cognitive loop.

AnimoCerebro is responsible for reasoning, role inference, goal generation, risk assessment, memory accumulation, delegation advice, and long-term experience exchange. It is the core engine for AI to achieve high-level cognition and independent action.

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

The current public protocol is no longer a single `Z-JSON` packet. It is now a layered protocol for registration, capability discovery, delegation, receipts, escalations, experience exchange, and host adaptation.

Primary protocol docs:

- [Protocol Overview](当前对接协议.md)
- [Core Foundations](docs/architecture/CORE_FOUNDATIONS.md)
- [Help Guide](帮助文档.md)
- [Deployment And Integration](详细部署与集成说明.md)

## Documentation Map

- [Technical Whitepaper](WHITEPAPER.md) (Design Philosophy)
- [Quick Start & Startup](docs/operability/STARTUP_AND_TEST.md) (One-Click methods)
- [Runtime & Implementation](docs/operability/RUNTIME_AND_TESTS.md) (Detailed architecture)
- [Functional Modules](docs/operability/FUNCTION_MODULES.md) (Feature breakdown)
- [Core Foundations](docs/architecture/CORE_FOUNDATIONS.md) (Cognitive loop & layers)
- [GitHub Public Scope](docs/operability/GITHUB_PUBLIC_SCOPE.md) (File inclusion rules)
- [Agent Integration](Agent/README.md) (Standard protocol for external agents)
- [Agent Integration Guide](Agent/INTEGRATION_GUIDE.md) (How to connect your system)

## Integration Model

AnimoCerebro is designed for minimal intrusion.

- Your host keeps its own execution architecture.
- AnimoCerebro provides reasoning, memory, coordination, and audit.
- The adapter layer registers the host, syncs capabilities, receives delegated work, and writes back results.

## Current Capabilities

- Brain loop
- Resident and daemon modes
- Local cloud-audit service
- Web console
- Long-term memory via JSONL or SQLite
- Delegation, receipt, escalation, and experience exchange
- Host adapter support for OpenClaw

## Truthfulness Boundary

For any product path that claims to use an LLM, AnimoCerebro does not allow rule-based logic, template assembly, fixed samples, fake transports, stubbed completions, or any code that only pretends to call an LLM to stand in for the real live LLM path.

If a feature requires a live LLM, the live call must actually happen. When credentials, network, provider health, or response validity fail, the system must fail or degrade truthfully and label the result as non-live or non-real where applicable.

The same standard applies to testing: any test that does not execute the real project logic under test is invalid and forbidden. Mocks or stubs may isolate external dependencies, but they cannot replace the product's own core logic and still be counted as proof.

## 📦 Installation

### Environment Preparation

Before installing, ensure your environment meets the following requirements:
- **Python**: 3.11 or higher
- **Node.js**: LTS version (for web console)
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
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

# Frontend
cd src/admin-portal && npm install
```

## 🚀 Quick Start

### One-Click Start

Start both backend and frontend (Vite dev server + Uvicorn):

```bash
make start
```

*Behind the scenes, this runs `./scripts/dev_all.sh`.*

### Manual Start

Start components separately:

```bash
# Start everything using script (wrapped by make start)
./scripts/dev_all.sh

# Start backend only
animocerebro

# Start frontend (hot reload)
cd src/admin-portal && npm run dev
```

## ⚙️ Configuration

The system is configured via YAML files. The primary configuration directory is `config/`.

- **Model Providers**: `config/provider_tools.yml` defines API bases, models, and environment variable keys for LLM providers.
- **System Settings**: Local runtime state and environment variables can be used to further tune the brain's behavior.

Example `config/provider_tools.yml` entry:

```yaml
gemini:
  provider_name: gemini
  api_base: https://generativelanguage.googleapis.com/v1beta
  api_key_env: GEMINI_API_KEY
  default_model: gemini-1.5-pro
```

## LLM Providers

`animocerebro_vision.yaml` now supports these `llm.provider` values:

- `google`: Gemini, default env `GOOGLE_API_KEYS`
- `openai` or `openapi`: OpenAI-compatible chat completions, default env `OPENAI_API_KEY`
- `anthropic` or `claude`: Claude Messages API, default env `ANTHROPIC_API_KEY`

You can now configure keys in three normal ways:

1. Directly in the config file
2. Via a local `credentials_file`
3. Via environment variable as a compatibility path

Example:

```yaml
llm:
  provider: gemini
  model: gemini-3.1-flash-lite-preview
  api_keys:
    - your-key-here
```

Or:

```yaml
llm:
  provider: gemini
  model: gemini-3.1-flash-lite-preview
  credentials_file: .animocerebro/llm_keys.json
```

Where `.animocerebro/llm_keys.json` may contain either:

```json
{"api_keys": ["your-key-here"]}
```

or:

```json
{"api_key": "your-key-here"}
```

Start with zero arguments:

```bash
animocerebro
```

Run one cycle:

```bash
animocerebro run --state-dir .animocerebro/state --config animocerebro_vision.yaml --pretty
```

Run resident mode:

```bash
animocerebro run --state-dir .animocerebro/state --config animocerebro_vision.yaml --resident --interval 60
```

Start the web console:

```bash
animocerebro web start --state-dir .animocerebro/state --config animocerebro_vision.yaml --host 127.0.0.1 --port 8899
```

## Integration Model

AnimoCerebro is designed for minimal intrusion:
- **Execution stays with the Host**: Your system keeps full control.
- **Brain as an Advisor**: AnimoCerebro provides reasoning, delegation advice, and memory.
- **Standard Protocol**: Connect via REST/WebSocket using the `Agent/` standard interface.

See [Agent Integration Guide](Agent/INTEGRATION_GUIDE.md) for more details.

## OpenClaw

OpenClaw is a primary host adapter legacy. While `integrations/` is now consolidated into the standardized `Agent/` hub, the protocol remains compatible.

See:
- [OpenClaw Integration Guide](docs/integrations/OPENCLAW_INTEGRATION_GUIDE.md)
- [OpenClaw Host Adapter Protocol](docs/integrations/OPENCLAW_HOST_ADAPTER_PROTOCOL.md)
- [OpenClaw Host Adapter Architecture](docs/integrations/OPENCLAW_HOST_ADAPTER_ARCHITECTURE.md)

## Repository Structure

- `src/zentex`: core backend and services (cognition, memory, safety, etc.)
- `src/plugins`: functional plugin implementations (model providers, sensory, simulation, etc.)
- `src/admin-portal`: web management frontend
- `Agent/`: independent agents for testing and integration examples
- `tests/`: automated end-to-end and unit tests
- `scripts/`: primary startup, development, and maintenance scripts
- `docs/`: comprehensive technical architecture and operability docs
- `config/`: central system configuration files

## Next Reading

- [Overview & Quick Start](docs/operability/STARTUP_AND_TEST.md)
- [Functional Implementation](docs/operability/FUNCTION_MODULES.md)
- [Core Foundations](docs/architecture/CORE_FOUNDATIONS.md)
- More documentation can be found in the `docs/` directory.

## Contact

**Let's build a soulful brain together!**

- Join the discussion via [GitHub Issues](https://github.com/xunharry4-source/AnimoCerebro/issues) or [GitHub Discussions](https://github.com/xunharry4-source/AnimoCerebro/discussions).
- If you have any ideas or suggestions, feel free to submit a Pull Request or open an Issue.

## License

This project is licensed under the [GNU GPL v3](LICENSE).

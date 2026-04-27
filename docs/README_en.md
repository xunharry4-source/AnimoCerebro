# AnimoCerebro Documentation Center

> **Project Status**: Production Ready | v2.0 | 90 Test Files | 291+ Test Cases

This documentation center provides complete technical documentation navigation for the AnimoCerebro project.

---

## 🚀 Quick Start

### Must-Read for New Users
- [Project Overview](../README.md) - Understand what AnimoCerebro is
- [Quick Start Guide](operability/STARTUP_AND_TEST.md) - One-click startup and testing
- [Installation Guide](#installation-and-configuration) - Environment preparation and dependency installation

### Common Commands
```bash
# One-click install
make install

# One-click start
make dev

# Run tests
make test

# Restart development environment
make restart-dev
```

---

## 📚 Documentation Categories

### 1️⃣ Getting Started

For developers new to AnimoCerebro.

- **[Quick Start](operability/STARTUP_AND_TEST.md)** - 5-minute onboarding guide
- **[Installation Guide](#installation-and-configuration)** - Detailed environment configuration steps
- **[Configuration Guide](#configuration-management)** - System configuration and API key setup
- **[Troubleshooting](#common-issues)** - Common problems and solutions

### 2️⃣ Architecture

Deep understanding of system architecture and design principles.

- **[Major Version Update](MAJOR_VERSION_UPDATE.md)** - v2.0 architecture evolution ([Chinese Version](MAJOR_VERSION_UPDATE_ZH.md))
- **[Function Modules Overview](operability/FUNCTION_MODULES.md)** - Core module responsibility division
- **[Directory Structure Map](operability/LATEST_DIRECTORY_MAP.md)** - Latest project directory details
- **[ThinkLoop Deep Dive](operability/THINK_LOOP_DEEP_DIVE.md)** - Nine-stage cognitive loop
- **[Runtime & Tests](operability/RUNTIME_AND_TESTS.md)** - Runtime code architecture

#### Core Architecture Components
- **Nine Questions Cognitive Loop**: Q1-Q9 complete implementation
- **Dual Plugin System**: External plugins + Internal plugins
- **Agent Management**: Standardized protocol integration
- **Memory System**: Kuzu graph database backend
- **Safety Mechanisms**: Risk assessment and conflict detection

### 3️⃣ Core Modules

Detailed technical implementation documentation.

#### Runtime System (`src/zentex/runtime/`)
- BrainRuntime - Runtime orchestrator
- ThinkLoop - Nine-stage cognitive executor
- WorkingMemory - Working memory controller
- Metacognition - Metacognition controller
- Transcript - Event stream storage

#### Cognition Module (`src/zentex/cognition/`)
- Social Mind
- Counterfactual Simulation

#### Task System (`src/zentex/tasks/`)
- Task decomposition engine
- Task execution management

#### Learning System (`src/zentex/learning/`)
- G16 Learning Engine (DSPy integration)
- Budget management
- Sandbox execution

#### Upgrade System (`src/zentex/upgrade/`)
- Controlled self-evolution
- Plugin evolution runtime
- Evidence tracking

#### Memory System (`src/zentex/memory/`)
- Enhanced memory service
- Kuzu graph database backend
- Memory consolidation engine

#### Reflection System (`src/zentex/reflection/`)
- Metacognitive reflection
- Pattern analysis
- [Full Documentation](../../src/zentex/reflection/DOCUMENTATION.md)

#### Safety Module (`src/zentex/safety/`)
- Risk detection
- Conflict resolution
- Policy enforcement

#### Environment Awareness (`src/zentex/environment/`)
- Environment fingerprinting
- Change detection

### 4️⃣ Plugin Development

AnimoCerebro adopts a dual plugin system architecture.

#### Plugin Development General Guide
- **[Plugin Development Index](operability/PLUGIN_GUIDES.md)** - Function-organized development specifications

#### External Plugins (`plugins/`)
**Purpose**: Connect external functions, extend brain capabilities
- ❌ **Prohibited**: Import `src/` directory code
- ✅ **Required**: Interact through standard APIs

Use cases:
- Custom data source connectors
- Third-party service integration
- Specialized tool adapters

#### Internal Plugins (`src/plugins/`)
**Purpose**: System internal self-iteration and upgrade
- ✅ **Allowed**: Access `src/zentex/` core modules
- ✅ **Supported**: Hot-reload and dynamic upgrade

##### Nine Questions Plugin Family (Q1-Q9)
Located in `src/plugins/nine_questions/` (69+ files)

| Question | Plugin Directory | Responsibility |
|------|---------|------|
| Q1 | q1_where_am_i | Environment awareness |
| Q2 | q2_who_am_i | Role hypothesis |
| Q3 | q3_what_do_i_have | Resource inventory |
| Q4 | q4_what_can_i_do | Capability boundaries |
| Q5 | q5_allowed | Constraint checking |
| Q6 | q6_consequences | Risk assessment |
| Q7 | q7_alternatives | Alternative solutions |
| Q8 | q8_priority | Priority decision |
| Q9 | q9_action | Action confirmation |

##### Other Internal Plugins
- **Model Providers**: Gemini, OpenAI, Claude adapters
- **Cognitive Tools**: Cognitive tool plugins
- **Sensory**: Sensory plugins
- **Execution**: CLI, MCP execution plugins
- **Simulation**: Simulation plugins
- **Weights**: Weight plugins

#### Plugin Feature Documentation
Detailed function-level development specifications located in `operability/plugin_features/`:

- [Risk Assessment](operability/plugin_features/risk_assessment.md)
- [Evidence Ranking](operability/plugin_features/evidence_ranking.md)
- [Decision Summary](operability/plugin_features/decision_summary.md)
- [Cognitive Conflict Detection](operability/plugin_features/cognitive_conflict_detection.md)
- [Gemini Reasoning Foundation](operability/plugin_features/model_provider_gemini.md)
- [Webhook Signal Ingestion](operability/plugin_features/sensory_ingest_webhook.md)
- [Prompt Injection Sanitization](operability/plugin_features/sensory_sanitize_basic_prompt_injection_sanitizer.md)
- [Environment Event Interpretation](operability/plugin_features/sensory_interpret_generic_environment.md)
- [System Execution Domain](operability/plugin_features/execution_system.md)
- [Browser Execution Domain](operability/plugin_features/execution_browser.md)
- [General Thinking Sandbox](operability/plugin_features/simulation_general.md)
- [Market Impact Prediction](operability/plugin_features/simulation_market.md)
- [Subjective Weight Preferences](operability/plugin_features/weights_subjective_preferences.md)
- [Identity & Experience Package](operability/plugin_features/identity_package_loader.md)

### 5️⃣ Agent Integration

External Agents接入 AnimoCerebro through standard protocols.

#### Agent Management Guide
- **[Agent & MCP Management](operability/AGENT_AND_MCP.md)** - Heterogeneous Agent and MCP tool management
- **[Agent Integration Protocol](../Agent/docs/README.md)** - Standard HTTP/WebSocket interfaces
- **[Agent Architecture Document](../Agent/docs/ARCHITECTURE.md)** - Complete Agent system design
- **[Integration Guide](../Agent/docs/INTEGRATION_GUIDE.md)** - How to connect your system

#### Standard Protocol Interfaces
External Agents must implement the following endpoints:
```
POST /handshake  - Capability discovery
POST /execute    - Task execution
GET  /status     - Health check
```

#### Test Agent Examples
The project provides two complete test Agents:
- **Calculator Agent** (Port 9001) - Mathematical calculations
- **Data Generator Agent** (Port 9002) - Random data generation

Startup:
```bash
./Agent/start_calculator.sh
./Agent/start_data_generator.sh
```

### 6️⃣ Social Media Automation

Intelligent posting system based on Playwright + LangGraph + CrewAI.

#### Core Documentation
- **[Social Posting Architecture](../Agent/docs/social_posting/ARCHITECTURE.md)** - Module boundaries and data flow
- **[Workflows](../Agent/docs/social_posting/FLOW.md)** - Posting process details
- **[Node Descriptions](../Agent/docs/social_posting/NODES.md)** - LangGraph node design
- **[Startup Guide](../Agent/docs/social_posting/STARTUP.md)** - Environment configuration and startup
- **[Testing Guide](../Agent/docs/social_posting/TESTING.md)** - Testing methods and verification

#### Features
- **X.com Auto-posting** - With permalink verification
- **Reddit Smart Posting** - Community rule checking + Flair selection
- **GitHub Discussion** - GraphQL API creation and verification
- **AnimoCerebro Promotion Assistant** - Multi-community customized content
- **Community Rule Manager** - Automatic caching and updating

#### Tech Stack
- Playwright Stealth Chrome - Bypass detection
- LangGraph - Workflow orchestration
- CrewAI - Content creation collaboration
- OCR (Tesseract) - Visual recognition
- LLM - Popup translation and content generation

### 7️⃣ Web Console

FastAPI backend + React frontend management interface.

#### Backend API (`src/zentex/web_console/`)
- **18 API Routers** - Complete RESTful API
- **WebSocket Real-time Event Stream** - Real-time monitoring
- **Largest File**: `dev_server.py` (74.6KB)
- **Largest Router**: `nine_questions.py` (98.9KB)

#### Frontend Pages (`src/admin-portal/`)
- **React + Vite + TypeScript**
- **26+ Nine Questions Page Components**
- **Real-time Command Center** - System status monitoring
- **Agent Management Interface**
- **Task Tracking Interface**
- **Plugin Management Interface**
- **MCP Management Interface**
- **Audit Replay Interface**

#### API Documentation
Access after starting backend: http://127.0.0.1:8000/docs

### 8️⃣ Testing

#### Test Overview
- **90 Test Files**
- **291+ Test Cases**
- **Coverage**: >80%

#### Test Categories
- **Runtime Tests** (`tests/runtime/`)
- **Plugin Tests** (`tests/plugins/`)
- **Web Console Tests** (`tests/web_console/`)
- **Agent Tests** (`tests/agents/`)
- **Learning System Tests** (`tests/learning/`)
- **Upgrade System Tests** (`tests/upgrade/`)
- **Memory System Tests** (`tests/memory/`)
- **Reflection System Tests** (`tests/reflection/`)
- **Cognition Module Tests** (`tests/cognition/`)
- **Safety Module Tests** (`tests/safety/`)
- **MCP Tests** (`tests/mcp/`)
- **CLI Tests** (`tests/cli/`)
- **Environment Awareness Tests** (`tests/environment/`)
- **Core Module Tests** (`tests/core/`)

#### Running Tests
```bash
# All tests
make test

# Backend tests only
make backend-test

# Frontend tests only
make frontend-test

# Specific test
pytest tests/web_console/test_agent_lifecycle.py
```

### 9️⃣ Configuration Management

#### Environment Variables
Create `.env` file in project root:
```bash
GEMINI_API_KEY=your-gemini-key-here
OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
```

#### Provider Configuration
Configuration file: `config/provider_tools.yml`

Supported LLM Providers:
- `openai_compat` - OpenAI compatible endpoints
- `openai` - OpenAI API
- `gemini` - Google Gemini API
- `claude` - Anthropic Claude API

### 🔟 Operability

- **[Startup Guide](operability/STARTUP_AND_TEST.md)** - Detailed startup instructions
- **[Agent & MCP Management](operability/AGENT_AND_MCP.md)** - Operations guide
- **[Function Module Description](operability/FUNCTION_MODULES.md)** - Module responsibility boundaries
- **[Directory Structure](operability/LATEST_DIRECTORY_MAP.md)** - Project structure reference

---

## 📊 Project Statistics

### Code Scale
| Metric | Count |
|------|------|
| Test Files | 90 |
| Test Cases | 291+ |
| Backend Routers | 18 |
| Frontend Pages | 26+ Nine Questions pages |
| Nine Questions Plugins | 69+ files |
| Largest File | dev_server.py (74.6KB) |
| Largest Router | nine_questions.py (98.9KB) |

### Core Module Status
| Module | Files | Status |
|------|--------|------|
| Runtime | 13 | ✅ Production Ready |
| Nine Questions | 69+ | ✅ Production Ready |
| Web Console | 18 routers | ✅ Production Ready |
| Admin Portal | 26+ pages | ✅ Production Ready |
| Tests | 90 files | ✅ Comprehensive Coverage |
| Learning | 12 | ✅ Production Ready |
| Upgrade | 18 | ✅ Production Ready |
| Memory | 11 | ✅ Production Ready |
| Reflection | 11 | ✅ Production Ready |
| Agent | 6 | ✅ Production Ready |
| Task | 22 | ✅ Production Ready |
| MCP | 6 | ✅ Production Ready |

---

## 🔗 Related Resources

### Product Documentation
- [Zentex Product Feature Document](../Zentex_产品功能文档/) - Complete product specifications
  - 01_System_Overall_Definition.md
  - 02_Core_Architecture.md
  - 03_Runtime_Main_Chain.md
  - 04_Simulation_Learning.md
  - 05_Collaborative_Execution.md
  - 06_Social_and_Business.md
  - 07_Infrastructure.md
  - 08_Cloud_Audit.md
  - 09_Web_Console.md
  - 10_Implementation_Plan.md

### Protocol Design
- [ZMSP Protocol Design](zmsp_protocol_design.md) - Memory sharing protocol

### External Links
- [GitHub Issues](https://github.com/xunharry4-source/AnimoCerebro/issues)
- [GitHub Discussions](https://github.com/xunharry4-source/AnimoCerebro/discussions)

---

## 📝 Documentation Maintenance

### Documentation Standards
All documents should follow these standards:
1. **Clear Titles** - Accurately reflect content
2. **Overview Section** - Explain document purpose and scope
3. **Prerequisites** - List required knowledge
4. **Structured Content** - Use headings, lists, code blocks
5. **Related Document Links** - Easy navigation
6. **Last Updated Date** - Maintain timeliness

### Contributing to Documentation
Welcome to submit documentation improvements:
1. Fork the project
2. Create a branch
3. Modify or add documentation
4. Submit Pull Request

### Documentation TODOs
- [ ] Supplement detailed API documentation for each module
- [ ] Add more practical use cases
- [ ] Improve troubleshooting guide
- [ ] Create video tutorials
- [ ] Translate more documents into Chinese

---

## ⚠️ Authenticity Boundaries

AnimoCerebro strictly adheres to authenticity principles:

- **LLM calls must be real executions** - No rule chains, templates, or fixed samples as substitutes
- **Failures must explicitly throw** - No `try-except pass` or fake success returns
- **Test results must be labeled** - Distinguish "real run results" from "non-real results (fixtures)"
- **Missing evidence = Incomplete** - Directly state "incomplete" when physical evidence is missing

See: [Engineering Spec Enforcer](.codex/skills/engineering-spec-enforcer/SKILL.md)

---

**Last Updated**: 2026-04-27  
**Maintainer**: AnimoCerebro Team  
**License**: GNU GPL v3

# AnimoCerebro Documentation Index

**Version**: 2.1.0-alpha  
**Last Updated**: April 29, 2026  
**Status**: 🔄 Active Development - Nine Questions Refactoring (30% Complete)

---

## 🚨 Latest Update: Nine Questions Framework Refactoring

**Major refactoring of the core Nine Questions cognitive engine is now 30% complete!**

📊 **[View Detailed Progress Report](NINE_QUESTIONS_REFACTORING_PROGRESS.md)**

### What's Completed (30%)
- ✅ **Q1 Evidence Collection** - Enhanced data gathering and validation
- ✅ **Q3 Runtime Inventory** - Separated internal/external task planners
- ✅ **Q8 Task Planning** - Major refactoring with dual planning system
- ✅ **Q9 Action Execution** - Improved action planning algorithms

### What's In Progress
- 🔄 **Q2 Interpretation** - Semantic analysis improvements
- 🔄 **Q4 Capabilities** - Dynamic capability registration
- 🔄 **Q5-Q7 Risk & Constraints** - Assessment refinements

### New Features in This Update
- 🆕 External Connectors System for third-party integrations
- 🆕 Enhanced Agent protocol with bilingual documentation
- 🆕 Comprehensive test coverage (50+ new test files)
- 🔒 Security improvements for sensitive data handling

---

## 📚 Quick Start

### For New Users
1. **[README.md](../README.md)** - Project overview and getting started
2. **[STARTUP_AND_TEST.md](operability/STARTUP_AND_TEST.md)** - One-click startup guide
3. **[RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md)** - What's new in v2.0
4. **[NINE_QUESTIONS_REFACTORING_PROGRESS.md](NINE_QUESTIONS_REFACTORING_PROGRESS.md)** - Latest refactoring progress

### For Developers
1. **[FUNCTION_MODULES.md](operability/FUNCTION_MODULES.md)** - Module architecture overview
2. **[PLUGIN_GUIDES.md](operability/PLUGIN_GUIDES.md)** - Plugin development guide
3. **[RUNTIME_AND_TESTS.md](operability/RUNTIME_AND_TESTS.md)** - Runtime architecture and testing

---

## 🎯 Core Documentation

### Architecture & Design
- **[Nine Questions Refactoring Progress](NINE_QUESTIONS_REFACTORING_PROGRESS.md)** - ⭐ NEW: Detailed refactoring status
- **[MAJOR_VERSION_UPDATE.md](MAJOR_VERSION_UPDATE.md)** - v2.0 architectural evolution (English)
- **[MAJOR_VERSION_UPDATE_ZH.md](MAJOR_VERSION_UPDATE_ZH.md)** - v2.0 架构演进（中文）
- **[RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md)** - Comprehensive release notes

### Core Philosophy
- **[AGENTS_CORE_PHILOSOPHY_UPDATE.md](AGENTS_CORE_PHILOSOPHY_UPDATE.md)** - Four pillars: Autonomy, Soul, Learning, Reflection

---

## 📖 Operational Guides

### Getting Started
- **[STARTUP_AND_TEST.md](operability/STARTUP_AND_TEST.md)** - Startup guide and testing procedures
- **[FUNCTION_MODULES.md](operability/FUNCTION_MODULES.md)** - Functional modules overview
- **[RUNTIME_AND_TESTS.md](operability/RUNTIME_AND_TESTS.md)** - Runtime environment and testing
- **[LATEST_DIRECTORY_MAP.md](operability/LATEST_DIRECTORY_MAP.md)** - Current project structure

### Integration & Protocols
- **[AGENT_AND_MCP.md](operability/AGENT_AND_MCP.md)** - Agent and MCP integration guide
- **[PLUGIN_GUIDES.md](operability/PLUGIN_GUIDES.md)** - Plugin development guides
- **[THINK_LOOP_DEEP_DIVE.md](operability/THINK_LOOP_DEEP_DIVE.md)** - Deep dive into thinking loops

### Plugin Features (32 Documents)
Located in `docs/operability/plugin_features/`:
- Cognitive conflict detection
- Decision summary mechanisms
- Evidence ranking systems
- Execution browser integration
- Memory consolidation
- Model providers (Gemini, OpenAI-compatible, Ollama)
- Risk assessment frameworks
- Sensory processing
- Simulation engines
- Subjective preference weights

---

## 🧪 Testing & Quality Assurance

### Test Documentation
- Test coverage reports in `tests/ci_acceptance/`
- Clinical tests for Q1-Q9 questions
- Integration tests for external connectors
- Performance benchmarks

### Test Categories
- **Nine Questions Tests**: Q1-Q9 clinical validation
- **External Connectors**: MongoDB, Gemini CLI, GitHub/Notion MCP
- **Agent System**: Auth, adapters, lifecycle management
- **Task Management**: Execution, persistence, scheduling
- **Audit & Observability**: Trace replay, audit trails

---

## 📊 Progress Reports

### Translation Status
- **[TRANSLATION_STATUS_REPORT.md](TRANSLATION_STATUS_REPORT.md)** - Overall translation progress
- **[DOCS_TRANSLATION_PROGRESS.md](DOCS_TRANSLATION_PROGRESS.md)** - Documentation translation details
- **[BILINGUAL_UPDATE_REPORT.md](BILINGUAL_UPDATE_REPORT.md)** - Bilingual update summary

### Development Progress
- **[COMPLETION_REPORT_20260427.md](COMPLETION_REPORT_20260427.md)** - Completion status report
- **[FINAL_PROGRESS_SUMMARY_20260427.md](FINAL_PROGRESS_SUMMARY_20260427.md)** - Final progress summary
- **[DOCUMENTATION_PROGRESS_REPORT.md](DOCUMENTATION_PROGRESS_REPORT.md)** - Documentation progress

---

## 🛠️ Developer Resources

### Configuration
- Background execution settings (`config/background_execution.yml`)
- Provider tools configuration (`config/provider_tools.yml`)
- Storage configuration (`config/storage.toml`)

### Scripts
- Deployment scripts in `scripts/`
- Validation tools including `scripts/validate_docs.py`

### Examples
- Plugin examples in `plugins/examples/`
  - Echo Connector (minimal example)
  - MongoDB CRUD Connector (database operations)

---

## 🔍 Find Documentation By Topic

### I want to...

**Understand the Architecture**
→ Read [MAJOR_VERSION_UPDATE.md](MAJOR_VERSION_UPDATE.md) or [FUNCTION_MODULES.md](operability/FUNCTION_MODULES.md)

**Start Using the System**
→ Follow [STARTUP_AND_TEST.md](operability/STARTUP_AND_TEST.md)

**Develop Plugins**
→ Check [PLUGIN_GUIDES.md](operability/PLUGIN_GUIDES.md) and [plugins/CONNECTOR_GUIDE.md](../plugins/CONNECTOR_GUIDE.md)

**Integrate External Systems**
→ See [AGENT_AND_MCP.md](operability/AGENT_AND_MCP.md) and [External Connectors Guide](../plugins/CONNECTOR_GUIDE.md)

**Understand Nine Questions**
→ Read [NINE_QUESTIONS_REFACTORING_PROGRESS.md](NINE_QUESTIONS_REFACTORING_PROGRESS.md) and [THINK_LOOP_DEEP_DIVE.md](operability/THINK_LOOP_DEEP_DIVE.md)

**Run Tests**
→ Follow [RUNTIME_AND_TESTS.md](operability/RUNTIME_AND_TESTS.md)

**Contribute to Development**
→ Review progress reports and check open issues on GitHub

---

## 📁 Directory Structure

```
docs/
├── INDEX.md                          # This file - documentation index
├── NINE_QUESTIONS_REFACTORING_PROGRESS.md  # ⭐ NEW: Refactoring progress
├── RELEASE_NOTES_v2.0.md            # Release notes
├── MAJOR_VERSION_UPDATE*.md         # Architecture docs (EN/CN)
├── AGENTS_CORE_PHILOSOPHY_UPDATE.md # Core philosophy
├── TRANSLATION_*.md                 # Translation progress reports
├── *_PROGRESS_*.md                  # Development progress reports
│
└── operability/                      # Operational guides
    ├── STARTUP_AND_TEST.md          # Getting started
    ├── FUNCTION_MODULES.md          # Module overview
    ├── RUNTIME_AND_TESTS.md         # Runtime & testing
    ├── AGENT_AND_MCP.md             # Integration guide
    ├── PLUGIN_GUIDES.md             # Plugin development
    ├── THINK_LOOP_DEEP_DIVE.md      # Thinking loops
    └── plugin_features/             # Feature-specific docs (32 files)
        ├── cognitive_conflict_detection*.md
        ├── decision_summary*.md
        ├── evidence_ranking*.md
        ├── execution_*.md
        ├── memory_consolidation*.md
        ├── model_provider_*.md
        ├── risk_assessment*.md
        ├── sensory_*.md
        ├── simulation_*.md
        └── weights_subjective_preferences*.md
```

---

## 🌐 Language Policy

This project maintains bilingual documentation:

### Large Documents (>20KB): Separate Files
- English: `FILENAME.md`
- Chinese: `FILENAME_ZH.md`

### Smaller Documents (<20KB): Bilingual in Single File
- Both languages in one file with clear section markers

### Examples
- ✅ Separate: `MAJOR_VERSION_UPDATE.md` / `MAJOR_VERSION_UPDATE_ZH.md`
- ✅ Separate: `STARTUP_AND_TEST.md` / `STARTUP_AND_TEST_ZH.md`
- ✅ Bilingual: Most plugin feature documents

---

## 📈 Documentation Statistics

| Category | Count | Description |
|----------|-------|-------------|
| Core Docs | 15+ | Architecture, philosophy, releases |
| Operational Guides | 6+ | How-to guides and tutorials |
| Plugin Features | 32 | Feature-specific documentation |
| Progress Reports | 10+ | Translation and development status |
| Test Documentation | Embedded | Within test files and directories |
| **Total** | **65+** | **Markdown documents** |

---

## 🔗 Related Resources

### Code Documentation
- Inline code comments throughout `src/zentex/`
- Module README files in major subsystems
- API documentation via docstrings

### External Resources
- [GitHub Repository](https://github.com/xunharry4-source/AnimoCerebro)
- [Issues & Bug Reports](https://github.com/xunharry4-source/AnimoCerebro/issues)
- [Discussions](https://github.com/xunharry4-source/AnimoCerebro/discussions)

---

## 📝 Contributing to Documentation

When adding or updating documentation:

1. **Follow Language Policy**: Use separate files for large docs, bilingual for small
2. **Update INDEX.md**: Add links to new documents here
3. **Maintain Consistency**: Use consistent formatting and terminology
4. **Include Examples**: Provide code examples where applicable
5. **Cross-Reference**: Link related documents
6. **Keep Current**: Update when features change

---

## ⚠️ Important Notes

### Authenticity Principle
All documentation reflects real implementation and testing results. We adhere to strict honesty standards:
- No fabricated test results
- No false success claims
- Clear indication of work-in-progress status
- Transparent about limitations and known issues

### Version Tracking
- Documentation version matches software version
- Change history maintained in commit logs
- Breaking changes clearly marked with migration guides

---

**Last Updated**: April 29, 2026  
**Maintained by**: AnimoCerebro Development Team  
**License**: GNU GPL v3

# AnimoCerebro v2.0 Documentation Index

**Version**: 2.0.0  
**Last Updated**: April 29, 2026  
**Status**: ✅ Current Release

---

## 📚 Quick Start

### For New Users
1. **[README.md](../README.md)** - Project overview and getting started
2. **[STARTUP_AND_TEST.md](operability/STARTUP_AND_TEST.md)** - One-click startup guide
3. **[RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md)** - What's new in v2.0

### For Developers
1. **[FUNCTION_MODULES.md](operability/FUNCTION_MODULES.md)** - Module architecture overview
2. **[PLUGIN_GUIDES.md](operability/PLUGIN_GUIDES.md)** - Plugin development guide
3. **[RUNTIME_AND_TESTS.md](operability/RUNTIME_AND_TESTS.md)** - Runtime architecture and testing

### Documentation Organization
- **[README_STRUCTURE.md](README_STRUCTURE.md)** - Complete docs directory structure and organization

---

## 🎯 Core Documentation

### Architecture & Design
- **[MAJOR_VERSION_UPDATE.md](MAJOR_VERSION_UPDATE.md)** - v2.0 architectural evolution (English)
- **[MAJOR_VERSION_UPDATE_ZH.md](MAJOR_VERSION_UPDATE_ZH.md)** - v2.0 架构演进（中文）
- **[RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md)** - Comprehensive release notes with all new features
- **[LATEST_DIRECTORY_MAP.md](operability/LATEST_DIRECTORY_MAP.md)** - Current project structure (English)
- **[LATEST_DIRECTORY_MAP_ZH.md](operability/LATEST_DIRECTORY_MAP_ZH.md)** - 项目目录结构（中文）

### Philosophy & Principles
- **[AGENTS_CORE_PHILOSOPHY_UPDATE.md](AGENTS_CORE_PHILOSOPHY_UPDATE.md)** - Core philosophy: Autonomy, Soul, Learning, Reflection
- **[THINK_LOOP_DEEP_DIVE.md](operability/THINK_LOOP_DEEP_DIVE.md)** - Nine-question cognitive loop deep dive

### Integration & Protocols
- **[AGENT_AND_MCP.md](operability/AGENT_AND_MCP.md)** - Agent integration and MCP protocol
- **[zmsp_protocol_design.md](zmsp_protocol_design.md)** - ZMSP protocol design

---

## 🚀 New v2.0 Modules Documentation

### 1. Autonomous Control System (G31A)
**Location**: `src/zentex/autonomy/`

**Key Features**:
- Stimulus aggregation and task state machine
- Priority-based task ranking with risk assessment
- Nine-question cognitive mapping (Q1, Q3, Q4, Q8, Q9)
- Full audit trail for autonomous decisions

**Documentation**:
- See [RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md#1-autonomous-control-system-g31a)
- Code: `src/zentex/autonomy/autonomous_loop.py`

---

### 2. Multi-Zentex Collaboration Protocol (G36)
**Location**: `src/zentex/collaboration/`

**Key Features**:
- Cross-instance delegated command execution
- Secure communication with heartbeat monitoring
- Experience exchange for collective learning
- 25+ exception types with recovery strategies

**Documentation**:
- See [RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md#2-multi-zentex-collaboration-protocol-g36)
- Code: `src/zentex/collaboration/organization_protocol.py` (46.3KB)

---

### 3. Soul Migration & Continuity (G34)
**Location**: `src/zentex/continuity/`

**Key Features**:
- AES-GCM-256 encrypted soul snapshots
- PBKDF2-HMAC-SHA256 key derivation (200K iterations)
- Continuity verification with identity kernel binding
- Tamper-proof backup packages

**Documentation**:
- See [RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md#3-soul-migration--continuity-g34)
- Code: `src/zentex/continuity/soul_migration.py`

---

### 4. Governance & Observability
**Location**: `src/zentex/governance/`

**Key Features**:
- Unified error system with cross-module codes
- Trace observability with replay capabilities
- Architecture redline matrix enforcement
- Multi-audience error messages

**Documentation**:
- See [RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md#4-governance--observability)
- Code: `src/zentex/governance/unified_errors.py`

---

### 5. Kernel Runtime (Domain-Driven Architecture)
**Location**: `src/zentex/kernel/`

**Sub-domains**:
- **Cognition Flow** (`kernel/cognition_flow/`) - Cognitive processing pipeline
- **Flow Domain** (`kernel/flow_domain/`) - Think loop and turn protocol
- **Session Domain** (`kernel/session_domain/`) - Session lifecycle management
- **State Domain** (`kernel/state_domain/`) - Self model, working memory, meta-cognition

**Core Services**:
- Identity Kernel (G6) - `identity_kernel.py` (18.6KB)
- Value Engine - `value_engine.py` (18.7KB)
- Self-Refactor - `self_refactor.py` (20.2KB)
- Self-Coding - `self_coding.py` (15.2KB)
- External Brain - `external_brain.py` (12.3KB)
- And 30+ more runtime components

**Documentation**:
- See [RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md#5-kernel-runtime-refactoring)
- Main service: `src/zentex/kernel/service.py` (111.0KB)

---

### 6. Foundation Framework
**Location**: `src/zentex/foundation/`

**Components**:
- **Contracts** - Typed interface definitions
- **Identity** - Identity services and contracts
- **Meta** - Capability registry and feature families
- **Specs** - Technical specifications for plugins, execution, etc.

**Documentation**:
- See [RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md#6-foundation-framework)
- README: `src/zentex/foundation/README.md`

---

### 7. Audit & Tracing
**Location**: `src/zentex/audit/`

**Features**:
- Immutable brain transcript chain
- Cross-session trace storage
- Integrity verification
- Replay support

**Documentation**:
- See [RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md#7-audit--tracing)
- Code: `src/zentex/audit/trace_store.py` (32.0KB)

---

### 8. Background Task Management
**Location**: `src/zentex/background_tasks/`

**Features**:
- Priority-based task queue
- Real-time monitoring
- Failure recovery

**Documentation**:
- See [RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md#8-background-task-management)

---

## 📖 Operational Guides

### Startup & Testing
- **[STARTUP_AND_TEST.md](operability/STARTUP_AND_TEST.md)** - Quick start commands (English)
- **[STARTUP_AND_TEST_ZH.md](operability/STARTUP_AND_TEST_ZH.md)** - 快速启动指南（中文）

### Functional Modules
- **[FUNCTION_MODULES.md](operability/FUNCTION_MODULES.md)** - Module responsibilities and architecture (Bilingual)
- **[RUNTIME_AND_TESTS.md](operability/RUNTIME_AND_TESTS.md)** - Runtime implementation details (English)
- **[RUNTIME_AND_TESTS_ZH.md](operability/RUNTIME_AND_TESTS_ZH.md)** - 运行时实现详情（中文）

### Plugin Development
- **[PLUGIN_GUIDES.md](operability/PLUGIN_GUIDES.md)** - Plugin development guides (Bilingual)
- **Plugin Features**: See `docs/operability/plugin_features/` directory

### Agent Integration
- **[AGENT_AND_MCP.md](operability/AGENT_AND_MCP.md)** - Agent and MCP integration guide (Bilingual)

### Deep Dives
- **[THINK_LOOP_DEEP_DIVE.md](operability/THINK_LOOP_DEEP_DIVE.md)** - Nine-question loop deep dive (Bilingual)

---

## 📊 Progress Reports

### Translation Progress
- **[TRANSLATION_STATUS_REPORT.md](TRANSLATION_STATUS_REPORT.md)** - Overall translation status
- **[DOCS_TRANSLATION_PROGRESS.md](DOCS_TRANSLATION_PROGRESS.md)** - Detailed translation progress
- **[TRANSLATION_PROGRESS_UPDATE_20260427.md](TRANSLATION_PROGRESS_UPDATE_20260427.md)** - Latest update

### Completion Reports
- **[COMPLETION_REPORT_20260427.md](COMPLETION_REPORT_20260427.md)** - Documentation completion report
- **[FINAL_SUMMARY_20260427.md](FINAL_SUMMARY_20260427.md)** - Final summary of translation work
- **[FINAL_PROGRESS_SUMMARY_20260427.md](FINAL_PROGRESS_SUMMARY_20260427.md)** - Mid-term progress summary

### Specific Module Reports
- **[FUNCTION_MODULES_BILINGUAL_COMPLETE.md](FUNCTION_MODULES_BILINGUAL_COMPLETE.md)** - Function modules bilingual completion
- **[THINK_LOOP_BILINGUAL_COMPLETE.md](THINK_LOOP_BILINGUAL_COMPLETE.md)** - Think loop bilingual completion
- **[PLUGIN_GUIDES_BILINGUAL_COMPLETE.md](PLUGIN_GUIDES_BILINGUAL_COMPLETE.md)** - Plugin guides bilingual completion
- **[README_EN_CREATION_COMPLETE.md](README_EN_CREATION_COMPLETE.md)** - English README creation report

### Historical Reports
- **[BILINGUAL_UPDATE_REPORT.md](BILINGUAL_UPDATE_REPORT.md)** - Bilingual update report
- **[DOCUMENTATION_PROGRESS_REPORT.md](DOCUMENTATION_PROGRESS_REPORT.md)** - Documentation progress report
- **[DOCUMENTATION_SUMMARY.md](DOCUMENTATION_SUMMARY.md)** - Documentation summary
- **[TODAY_SUMMARY_20260427.md](TODAY_SUMMARY_20260427.md)** - Daily summary

---

## 🛠️ Development Resources

### Templates & Standards
- **[DOCUMENTATION_TEMPLATES.md](DOCUMENTATION_TEMPLATES.md)** - Documentation templates and standards
- **[DOCUMENTATION_TODO.md](DOCUMENTATION_TODO.md)** - Documentation TODO list

### Philosophy Updates
- **[AGENTS_CORE_PHILOSOPHY_UPDATE.md](AGENTS_CORE_PHILOSOPHY_UPDATE.md)** - Core philosophy updates

---

## 🔍 Finding What You Need

### By Role

**For End Users**:
- Start with [README.md](../README.md)
- Check [STARTUP_AND_TEST.md](operability/STARTUP_AND_TEST.md) for quick start
- Read [RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md) for new features

**For Developers**:
- Review [FUNCTION_MODULES.md](operability/FUNCTION_MODULES.md) for architecture
- Follow [PLUGIN_GUIDES.md](operability/PLUGIN_GUIDES.md) for plugin development
- Study [RUNTIME_AND_TESTS.md](operability/RUNTIME_AND_TESTS.md) for implementation details

**For Integrators**:
- Read [AGENT_AND_MCP.md](operability/AGENT_AND_MCP.md) for integration protocols
- Check [zmsp_protocol_design.md](zmsp_protocol_design.md) for protocol details

**For Architects**:
- Study [MAJOR_VERSION_UPDATE.md](MAJOR_VERSION_UPDATE.md) for v2.0 architecture
- Review [LATEST_DIRECTORY_MAP.md](operability/LATEST_DIRECTORY_MAP.md) for structure
- Explore kernel domain documentation in `src/zentex/kernel/*/README.md`

### By Topic

**New v2.0 Features**:
- [RELEASE_NOTES_v2.0.md](RELEASE_NOTES_v2.0.md) - Complete feature list
- [MAJOR_VERSION_UPDATE.md](MAJOR_VERSION_UPDATE.md) - Architectural overview

**Cognitive Loop**:
- [THINK_LOOP_DEEP_DIVE.md](operability/THINK_LOOP_DEEP_DIVE.md)
- Nine questions implementation: `src/zentex/nine_questions/`

**Plugins**:
- [PLUGIN_GUIDES.md](operability/PLUGIN_GUIDES.md)
- Plugin features: `docs/operability/plugin_features/`

**Security & Governance**:
- Governance module: `src/zentex/governance/`
- Safety module: `src/zentex/safety/`
- Audit module: `src/zentex/audit/`

**Collaboration**:
- Collaboration protocol: `src/zentex/collaboration/`
- Multi-agent coordination: `src/zentex/kernel/inter_agent.py`

---

## 📝 Documentation Conventions

### Language Policy
- All core documents are bilingual (English + Chinese)
- Small documents (< 20KB): Single file with both languages
- Large documents (> 20KB): Separate files (_ZH.md for Chinese)

### File Naming
- English: `DOCUMENT_NAME.md`
- Chinese: `DOCUMENT_NAME_ZH.md` or included in same file

### Directory Structure
```
docs/
├── *.md                    # Top-level documentation
├── operability/            # Operational guides
│   ├── *.md               # Bilingual operational docs
│   └── plugin_features/   # Plugin-specific documentation
└── logo.jpeg              # Project logo
```

---

## 🔄 Keeping Documentation Updated

### When to Update Docs
1. **New Features**: Add to RELEASE_NOTES and relevant module docs
2. **API Changes**: Update FUNCTION_MODULES and integration guides
3. **Architecture Changes**: Update MAJOR_VERSION_UPDATE and LATEST_DIRECTORY_MAP
4. **Bug Fixes**: Document in release notes if significant

### Documentation Workflow
1. Create/update technical documentation in code comments
2. Extract to markdown docs in `docs/` directory
3. Ensure bilingual coverage (English + Chinese)
4. Update index and navigation links
5. Commit with clear commit message

---

## 📞 Getting Help

### Documentation Issues
- Missing information? → Open an issue on GitHub
- Incorrect information? → Submit a PR with corrections
- Need clarification? → Ask in GitHub Discussions

### Contributing to Docs
1. Fork the repository
2. Make your changes
3. Ensure bilingual coverage
4. Submit a pull request
5. Follow documentation templates

---

## 📈 Documentation Statistics

| Metric | Value |
|--------|-------|
| Total Documents | 24+ files |
| Bilingual Coverage | 26% (9/34 core docs) |
| High Priority Docs | 100% complete (5/5) |
| Medium Priority Docs | 22% complete (4/18) |
| Total Lines | ~5000+ lines |
| Languages | English, Chinese |

---

## 🎯 Next Steps for Documentation

### Short-term (Q2 2026)
- [ ] Complete medium priority documents (14 remaining)
- [ ] Add detailed API documentation for all new v2.0 modules
- [ ] Create visual diagrams for architecture
- [ ] Add more code examples and tutorials

### Medium-term (Q3 2026)
- [ ] Translate low priority documents (11 remaining)
- [ ] Create video tutorials
- [ ] Build interactive documentation site
- [ ] Add multi-language support beyond English/Chinese

### Long-term (2026 H2)
- [ ] Achieve 80-90% bilingual coverage
- [ ] Complete plugin feature documentation
- [ ] Create comprehensive user manual
- [ ] Build searchable documentation portal

---

## 🙏 Acknowledgments

This documentation represents extensive work by the AnimoCerebro team and community contributors. Special thanks to everyone who has contributed to making these docs comprehensive and accessible.

---

**Last Updated**: April 29, 2026  
**Maintained by**: AnimoCerebro Documentation Team  
**Next Review**: May 2026

# Documentation Directory Structure

This directory contains all documentation for the AnimoCerebro project.

## 📁 Directory Organization

### Root Level (`docs/`)
Core documentation files organized by category:

#### 🚀 Release & Version Information
- `RELEASE_NOTES_v2.0.md` - Comprehensive v2.0 release notes
- `MAJOR_VERSION_UPDATE.md` - Major version update overview (English)
- `MAJOR_VERSION_UPDATE_ZH.md` - 主要版本更新概览（中文）

#### 📚 Documentation Index & Navigation
- `INDEX.md` - Main documentation index and navigation guide
- `README.md` - Documentation overview (legacy, see INDEX.md)
- `README_en.md` - English documentation summary

#### 🎯 Core Philosophy & Architecture
- `AGENTS_CORE_PHILOSOPHY_UPDATE.md` - Core philosophy: Autonomy, Soul, Learning, Reflection

#### 📊 Progress & Status Reports
**Translation Progress:**
- `TRANSLATION_STATUS_REPORT.md` - Overall translation status
- `DOCS_TRANSLATION_PROGRESS.md` - Detailed translation progress
- `TRANSLATION_PROGRESS_UPDATE_20260427.md` - Latest translation update

**Completion Reports:**
- `COMPLETION_REPORT_20260427.md` - Documentation completion report
- `FINAL_SUMMARY_20260427.md` - Final summary of translation work
- `FINAL_PROGRESS_SUMMARY_20260427.md` - Mid-term progress summary
- `TODAY_SUMMARY_20260427.md` - Daily summary

**Module-Specific Reports:**
- `FUNCTION_MODULES_BILINGUAL_COMPLETE.md` - Function modules bilingual completion
- `THINK_LOOP_BILINGUAL_COMPLETE.md` - Think loop bilingual completion
- `PLUGIN_GUIDES_BILINGUAL_COMPLETE.md` - Plugin guides bilingual completion
- `README_EN_CREATION_COMPLETE.md` - English README creation report
- `BILINGUAL_UPDATE_REPORT.md` - Bilingual update report

**Historical Reports:**
- `DOCUMENTATION_PROGRESS_REPORT.md` - Historical progress report
- `DOCUMENTATION_SUMMARY.md` - Documentation summary

#### 📝 Templates & Standards
- `DOCUMENTATION_TEMPLATES.md` - Documentation templates and standards
- `DOCUMENTATION_TODO.md` - Documentation TODO list

---

### Operational Guides (`docs/operability/`)
Practical guides for using and developing with AnimoCerebro:

#### Quick Start & Testing
- `STARTUP_AND_TEST.md` - Startup and testing guide (English)
- `STARTUP_AND_TEST_ZH.md` - 启动和测试指南（中文）

#### Architecture & Modules
- `FUNCTION_MODULES.md` - Functional modules overview (bilingual)
- `RUNTIME_AND_TESTS.md` - Runtime architecture details (English)
- `RUNTIME_AND_TESTS_ZH.md` - 运行时架构详情（中文）
- `LATEST_DIRECTORY_MAP.md` - Current project structure (English)
- `LATEST_DIRECTORY_MAP_ZH.md` - 当前项目结构（中文）

#### Integration & Protocols
- `AGENT_AND_MCP.md` - Agent integration and MCP protocol (bilingual)
- `PLUGIN_GUIDES.md` - Plugin development guides (bilingual)
- `THINK_LOOP_DEEP_DIVE.md` - Nine-question cognitive loop deep dive (bilingual)

#### Plugin Features (`docs/operability/plugin_features/`)
Detailed documentation for individual plugin features (32 files).

---

## 📋 Document Categories

### By Priority

**High Priority (Core Documentation):**
1. `INDEX.md` - Main navigation
2. `RELEASE_NOTES_v2.0.md` - What's new
3. `operability/STARTUP_AND_TEST.md` - Quick start
4. `operability/FUNCTION_MODULES.md` - Architecture
5. `operability/PLUGIN_GUIDES.md` - Plugin development

**Medium Priority (Operational Guides):**
- `operability/RUNTIME_AND_TESTS.md`
- `operability/LATEST_DIRECTORY_MAP.md`
- `operability/AGENT_AND_MCP.md`
- `operability/THINK_LOOP_DEEP_DIVE.md`

**Reference (Progress Reports & History):**
- All `*_REPORT*.md` files
- All `*_SUMMARY*.md` files
- All `*_COMPLETE.md` files

---

## 🌐 Language Policy

### Bilingual Documents
Documents available in both English and Chinese:

**Separate Files (>20KB):**
- `MAJOR_VERSION_UPDATE.md` / `MAJOR_VERSION_UPDATE_ZH.md`
- `operability/STARTUP_AND_TEST.md` / `operability/STARTUP_AND_TEST_ZH.md`
- `operability/RUNTIME_AND_TESTS.md` / `operability/RUNTIME_AND_TESTS_ZH.md`
- `operability/LATEST_DIRECTORY_MAP.md` / `operability/LATEST_DIRECTORY_MAP_ZH.md`

**Single File (<20KB):**
- `operability/FUNCTION_MODULES.md` (contains both languages)
- `operability/AGENT_AND_MCP.md` (contains both languages)
- `operability/PLUGIN_GUIDES.md` (contains both languages)
- `operability/THINK_LOOP_DEEP_DIVE.md` (contains both languages)

### English-Only Documents
- `RELEASE_NOTES_v2.0.md`
- `INDEX.md`
- `README_en.md`
- Most progress reports (internal use)

---

## 🗂️ File Naming Conventions

### English Documents
- Standard: `DOCUMENT_NAME.md`
- Examples: `INDEX.md`, `RELEASE_NOTES_v2.0.md`

### Chinese Documents
- Suffix: `DOCUMENT_NAME_ZH.md`
- Examples: `MAJOR_VERSION_UPDATE_ZH.md`, `STARTUP_AND_TEST_ZH.md`

### Reports & Summaries
- Format: `TYPE_DATE.md` or `TYPE_TOPIC.md`
- Examples: `COMPLETION_REPORT_20260427.md`, `TRANSLATION_STATUS_REPORT.md`

---

## 📊 Statistics

| Category | Count | Notes |
|----------|-------|-------|
| Core Documentation | 5 | Index, releases, philosophy |
| Operational Guides | 10 | Startup, modules, integration |
| Progress Reports | 15+ | Translation and completion reports |
| Plugin Features | 32 | Individual plugin docs |
| **Total** | **65+** | All markdown files |

---

## 🔄 Maintenance Guidelines

### When to Update
1. **New Features**: Add to RELEASE_NOTES and relevant module docs
2. **API Changes**: Update FUNCTION_MODULES and integration guides
3. **Architecture Changes**: Update MAJOR_VERSION_UPDATE and LATEST_DIRECTORY_MAP
4. **Bug Fixes**: Document in release notes if significant

### Adding New Documents
1. Determine the appropriate category
2. Follow naming conventions
3. Ensure bilingual coverage if user-facing
4. Update INDEX.md with new document link
5. Commit with clear message

### Archiving Old Reports
- Keep all reports for historical reference
- Mark outdated reports with `[ARCHIVED]` prefix if needed
- Maintain chronological order in filenames

---

## 🔗 Quick Links

### For Users
- [Getting Started](operability/STARTUP_AND_TEST.md)
- [What's New](RELEASE_NOTES_v2.0.md)
- [Documentation Index](INDEX.md)

### For Developers
- [Architecture Overview](operability/FUNCTION_MODULES.md)
- [Plugin Development](operability/PLUGIN_GUIDES.md)
- [Runtime Details](operability/RUNTIME_AND_TESTS.md)

### For Integrators
- [Agent Integration](operability/AGENT_AND_MCP.md)
- [Plugin Development](operability/PLUGIN_GUIDES.md)

---

## 📞 Support

- **Documentation Issues**: Open an issue on GitHub
- **Questions**: Join GitHub Discussions
- **Contributions**: Submit a pull request

---

**Last Updated**: April 29, 2026  
**Maintained by**: AnimoCerebro Documentation Team

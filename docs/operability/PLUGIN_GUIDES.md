# 功能级插件开发指南索引 | Function-Level Plugin Development Guide Index

## 中文版本

本文档按**功能**而不是按**插件家族**组织插件开发规范。原因很明确：同一个插件家族下可以承载多个完全不同的功能，而开发者真正需要回答的是“我要扩展哪个功能，它的边界、回退链和默认版本是什么”。

家族目录下的 `DEVELOPMENT_GUIDE.md` 仍然保留，但它们现在只是**二级参考**：

- 一级入口：按功能查规范
- 二级入口：进入对应插件家族，查看通用契约与家族红线

### 使用规则

- 先按功能找到目标条目。
- 再确认该功能所属插件家族和实现目录。
- 再阅读对应家族目录下的 `DEVELOPMENT_GUIDE.md`。
- 若功能级规则与家族级规则冲突，以更严格的边界为准。

### 当前功能级开发规范

以下条目已拆分为独立功能文档。总索引只负责导航，不再承载所有细节。

#### 风险评估

- [risk_assessment.md](plugin_features/risk_assessment.md)

#### 证据排序

- [evidence_ranking.md](plugin_features/evidence_ranking.md)

#### 决策摘要

- [decision_summary.md](plugin_features/decision_summary.md)

#### 认知冲突监控

- [cognitive_conflict_detection.md](plugin_features/cognitive_conflict_detection.md)

#### Gemini 推理底座

- [model_provider_gemini.md](plugin_features/model_provider_gemini.md)

#### Webhook 信号摄取

- [sensory_ingest_webhook.md](plugin_features/sensory_ingest_webhook.md)

#### 提示注入净化

- [sensory_sanitize_basic_prompt_injection_sanitizer.md](plugin_features/sensory_sanitize_basic_prompt_injection_sanitizer.md)

#### 环境事件解释

- [sensory_interpret_generic_environment.md](plugin_features/sensory_interpret_generic_environment.md)

#### 系统执行域

- [execution_system.md](plugin_features/execution_system.md)

#### 浏览器执行域

- [execution_browser.md](plugin_features/execution_browser.md)

#### 通用思维沙盒

- [simulation_general.md](plugin_features/simulation_general.md)

#### 市场影响预测

- [simulation_market.md](plugin_features/simulation_market.md)

#### 主观权重偏好

- [weights_subjective_preferences.md](plugin_features/weights_subjective_preferences.md)

#### 身份与经验包

- [identity_package_loader.md](plugin_features/identity_package_loader.md)

### 家族指南仍然保留，但只作为二级规范

以下文档仍然有效，但应在明确功能之后再查阅：

- [src/plugins/model_providers/DEVELOPMENT_GUIDE.md](../../src/plugins/model_providers/DEVELOPMENT_GUIDE.md)
- [src/plugins/cognitive/DEVELOPMENT_GUIDE.md](../../src/plugins/cognitive/DEVELOPMENT_GUIDE.md)
- [src/plugins/execution/DEVELOPMENT_GUIDE.md](../../src/plugins/execution/DEVELOPMENT_GUIDE.md)
- [src/plugins/sensory/DEVELOPMENT_GUIDE.md](../../src/plugins/sensory/DEVELOPMENT_GUIDE.md)
- [src/plugins/simulation/DEVELOPMENT_GUIDE.md](../../src/plugins/simulation/DEVELOPMENT_GUIDE.md)
- [src/plugins/weights/DEVELOPMENT_GUIDE.md](../../src/plugins/weights/DEVELOPMENT_GUIDE.md)

---

## English Version

This document organizes plugin development specifications by **function** rather than by **plugin family**. The reason is clear: the same plugin family can carry multiple completely different functions, and what developers really need to answer is "which function am I extending, what are its boundaries, fallback chain, and default version".

The `DEVELOPMENT_GUIDE.md` files in family directories are still retained, but they are now only **secondary references**:

- Primary entry: Look up specifications by function
- Secondary entry: Enter the corresponding plugin family to view general contracts and family redlines

### Usage Rules

- First, find the target entry by function.
- Then confirm the plugin family and implementation directory for that function.
- Then read the `DEVELOPMENT_GUIDE.md` in the corresponding family directory.
- If there is a conflict between function-level rules and family-level rules, the stricter boundary prevails.

### Current Function-Level Development Specifications

The following entries have been split into independent function documents. The main index is only responsible for navigation and no longer carries all details.

#### Risk Assessment

- [risk_assessment.md](plugin_features/risk_assessment.md)

#### Evidence Ranking

- [evidence_ranking.md](plugin_features/evidence_ranking.md)

#### Decision Summary

- [decision_summary.md](plugin_features/decision_summary.md)

#### Cognitive Conflict Detection

- [cognitive_conflict_detection.md](plugin_features/cognitive_conflict_detection.md)

#### Gemini Reasoning Foundation

- [model_provider_gemini.md](plugin_features/model_provider_gemini.md)

#### Webhook Signal Ingestion

- [sensory_ingest_webhook.md](plugin_features/sensory_ingest_webhook.md)

#### Prompt Injection Sanitization

- [sensory_sanitize_basic_prompt_injection_sanitizer.md](plugin_features/sensory_sanitize_basic_prompt_injection_sanitizer.md)

#### Environment Event Interpretation

- [sensory_interpret_generic_environment.md](plugin_features/sensory_interpret_generic_environment.md)

#### System Execution Domain

- [execution_system.md](plugin_features/execution_system.md)

#### Browser Execution Domain

- [execution_browser.md](plugin_features/execution_browser.md)

#### General Thinking Sandbox

- [simulation_general.md](plugin_features/simulation_general.md)

#### Market Impact Prediction

- [simulation_market.md](plugin_features/simulation_market.md)

#### Subjective Weight Preferences

- [weights_subjective_preferences.md](plugin_features/weights_subjective_preferences.md)

#### Identity & Experience Package

- [identity_package_loader.md](plugin_features/identity_package_loader.md)

### Family Guides Still Retained as Secondary Specifications

The following documents are still valid but should be consulted after clarifying the function:

- [src/plugins/model_providers/DEVELOPMENT_GUIDE.md](../../src/plugins/model_providers/DEVELOPMENT_GUIDE.md)
- [src/plugins/cognitive/DEVELOPMENT_GUIDE.md](../../src/plugins/cognitive/DEVELOPMENT_GUIDE.md)
- [src/plugins/execution/DEVELOPMENT_GUIDE.md](../../src/plugins/execution/DEVELOPMENT_GUIDE.md)
- [src/plugins/sensory/DEVELOPMENT_GUIDE.md](../../src/plugins/sensory/DEVELOPMENT_GUIDE.md)
- [src/plugins/simulation/DEVELOPMENT_GUIDE.md](../../src/plugins/simulation/DEVELOPMENT_GUIDE.md)
- [src/plugins/weights/DEVELOPMENT_GUIDE.md](../../src/plugins/weights/DEVELOPMENT_GUIDE.md)

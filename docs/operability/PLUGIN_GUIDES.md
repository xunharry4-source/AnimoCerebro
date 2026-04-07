# 功能级插件开发指南索引

本文档按**功能**而不是按**插件家族**组织插件开发规范。原因很明确：同一个插件家族下可以承载多个完全不同的功能，而开发者真正需要回答的是“我要扩展哪个功能，它的边界、回退链和默认版本是什么”。

家族目录下的 `DEVELOPMENT_GUIDE.md` 仍然保留，但它们现在只是**二级参考**：

- 一级入口：按功能查规范
- 二级入口：进入对应插件家族，查看通用契约与家族红线

## 使用规则

- 先按功能找到目标条目。
- 再确认该功能所属插件家族和实现目录。
- 再阅读对应家族目录下的 `DEVELOPMENT_GUIDE.md`。
- 若功能级规则与家族级规则冲突，以更严格的边界为准。

## 当前功能级开发规范

以下条目已拆分为独立功能文档。总索引只负责导航，不再承载所有细节。

### 风险评估

- [risk_assessment.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/risk_assessment.md)

### 证据排序

- [evidence_ranking.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/evidence_ranking.md)

### 决策摘要

- [decision_summary.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/decision_summary.md)

### 认知冲突监控

- [cognitive_conflict_detection.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/cognitive_conflict_detection.md)

### Gemini 推理底座

- [model_provider_gemini.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/model_provider_gemini.md)

### Webhook 信号摄取

- [sensory_ingest_webhook.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/sensory_ingest_webhook.md)

### 提示注入净化

- [sensory_sanitize_basic_prompt_injection_sanitizer.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/sensory_sanitize_basic_prompt_injection_sanitizer.md)

### 环境事件解释

- [sensory_interpret_generic_environment.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/sensory_interpret_generic_environment.md)

### 系统执行域

- [execution_system.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/execution_system.md)

### 浏览器执行域

- [execution_browser.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/execution_browser.md)

### 通用思维沙盒

- [simulation_general.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/simulation_general.md)

### 市场影响预测

- [simulation_market.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/simulation_market.md)

### 主观权重偏好

- [weights_subjective_preferences.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/weights_subjective_preferences.md)

### 身份与经验包

- [identity_package_loader.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/plugin_features/identity_package_loader.md)

## 家族指南仍然保留，但只作为二级规范

以下文档仍然有效，但应在明确功能之后再查阅：

- [src/plugins/model_providers/DEVELOPMENT_GUIDE.md](/Users/harry/Documents/git/AnimoCerebro/src/plugins/model_providers/DEVELOPMENT_GUIDE.md)
- [src/plugins/cognitive/DEVELOPMENT_GUIDE.md](/Users/harry/Documents/git/AnimoCerebro/src/plugins/cognitive/DEVELOPMENT_GUIDE.md)
- [src/plugins/execution/DEVELOPMENT_GUIDE.md](/Users/harry/Documents/git/AnimoCerebro/src/plugins/execution/DEVELOPMENT_GUIDE.md)
- [src/plugins/sensory/DEVELOPMENT_GUIDE.md](/Users/harry/Documents/git/AnimoCerebro/src/plugins/sensory/DEVELOPMENT_GUIDE.md)
- [src/plugins/simulation/DEVELOPMENT_GUIDE.md](/Users/harry/Documents/git/AnimoCerebro/src/plugins/simulation/DEVELOPMENT_GUIDE.md)
- [src/plugins/weights/DEVELOPMENT_GUIDE.md](/Users/harry/Documents/git/AnimoCerebro/src/plugins/weights/DEVELOPMENT_GUIDE.md)

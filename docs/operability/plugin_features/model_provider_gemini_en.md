# Gemini Reasoning Foundation Plugin Feature Description

- **Feature Key**: `model_provider:gemini`
- **Display Name**: Gemini Reasoning Foundation
- **Plugin Family**: `model_providers`
- **Implementation Directory**: `src/plugins/model_providers/`
- **Concurrency Mode**: Single plugin
- **Current Purpose**: Provide real LLM inference capability for critical brain stages
- **Default/Fallback Direction**: Fallback to previous stable formal version model plugin; if no available plugin, main brain fail-closed
- **Management Redline**: Absolutely prohibited from rule-based fallback, absolutely prohibited from returning fake JSON to impersonate model results
- **Family-level Specification**:
  - [Model Providers DEVELOPMENT_GUIDE](../../../src/plugins/model_providers/DEVELOPMENT_GUIDE.md)

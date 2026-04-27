# Prompt Injection Sanitization Plugin Feature Description

- **Feature Key**: `sensory_sanitize:basic_prompt_injection_sanitizer`
- **Display Name**: Prompt Injection Sanitization
- **Plugin Family**: `sensory`
- **Implementation Directory**: `src/plugins/sensory/`
- **Concurrency Mode**: Single plugin
- **Current Purpose**: Clean raw input and mark injection risks
- **Default/Fallback Direction**: Fallback to system default sanitizer; if no sanitizer, raw signals are absolutely not allowed to enter main brain
- **Management Redline**: Sanitization chain cannot be bypassed
- **Family-level Specification**:
  - [Sensory DEVELOPMENT_GUIDE](../../../src/plugins/sensory/DEVELOPMENT_GUIDE.md)

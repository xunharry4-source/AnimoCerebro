# Subjective Weight Preferences Plugin Feature Description

- **Feature Key**: `weights:subjective_preferences`
- **Display Name**: Subjective Weight Preferences
- **Plugin Family**: `weights`
- **Implementation Directory**: `src/plugins/weights/`
- **Concurrency Mode**: Multi-plugin candidates, but only one weight package activated at a time
- **Current Purpose**: Adjust subjective preferences for risk, cost, creativity, continuity, etc.
- **Default/Fallback Direction**: Fallback to `default_conservative_weight`
- **Management Redline**: Must immediately rollback after audit rejection
- **Family-level Specification**:
  - [Weights DEVELOPMENT_GUIDE](../../../src/plugins/weights/DEVELOPMENT_GUIDE.md)

# Cognitive Conflict Detection Plugin Feature Description

- **Feature Key**: `cognitive_conflict_detection`
- **Display Name**: Cognitive Conflict Detection
- **Plugin Family**: `cognitive`
- **Implementation Directory**: `src/plugins/cognitive/`
- **Concurrency Mode**: Multi-plugin
- **Current Purpose**: Concurrently detect semantic conflicts, budget conflicts and other cognitive risks
- **Default/Fallback Direction**: Keep other activated detectors; if all fail, fallback to default formal version detector set
- **Management Redline**: All detectors are only allowed to output internal conflict reports, prohibited from directly driving execution actions
- **Family-level Specification**:
  - [Cognitive DEVELOPMENT_GUIDE](../../../src/plugins/cognitive/DEVELOPMENT_GUIDE.md)

# System Execution Domain Plugin Feature Description

- **Feature Key**: `execution:system`
- **Display Name**: System Execution Domain
- **Plugin Family**: `execution`
- **Implementation Directory**: `src/plugins/execution/`
- **Concurrency Mode**: Single plugin
- **Current Purpose**: Controlled execution of local system capabilities
- **Default/Fallback Direction**: Fallback to system default formal version executor; fail-closed when no available executor
- **Management Redline**: Cannot bypass SafetyGate
- **Family-level Specification**:
  - [Execution DEVELOPMENT_GUIDE](../../../src/plugins/execution/DEVELOPMENT_GUIDE.md)

# Browser Execution Domain Plugin Feature Description

- **Feature Key**: `execution:browser`
- **Display Name**: Browser Execution Domain
- **Plugin Family**: `execution`
- **Implementation Directory**: `src/plugins/execution/`
- **Concurrency Mode**: Single plugin
- **Current Purpose**: Controlled execution in browser environment
- **Default/Fallback Direction**: Fallback to default browser executor; still must go through SafetyGate and CloudAudit
- **Management Redline**: Cannot bypass CloudAudit
- **Family-level Specification**:
  - [Execution DEVELOPMENT_GUIDE](../../../src/plugins/execution/DEVELOPMENT_GUIDE.md)

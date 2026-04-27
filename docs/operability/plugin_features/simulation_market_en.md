# Market Impact Prediction Plugin Feature Description

- **Feature Key**: `simulation:market`
- **Display Name**: Market Impact Prediction
- **Plugin Family**: `simulation`
- **Implementation Directory**: `src/plugins/simulation/`
- **Concurrency Mode**: Single plugin
- **Current Purpose**: Perform domain-specific rehearsal for market-related consequences
- **Default/Fallback Direction**: Fallback to general thinking sandbox `ThoughtSandbox`
- **Management Redline**: If final conclusion depends on LLM, must fail-closed
- **Family-level Specification**:
  - [Simulation DEVELOPMENT_GUIDE](../../../src/plugins/simulation/DEVELOPMENT_GUIDE.md)

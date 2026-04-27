# General Thinking Sandbox Plugin Feature Description

- **Feature Key**: `simulation:general,system,cloud,browser,code,market`
- **Display Name**: General Thinking Sandbox
- **Plugin Family**: `simulation`
- **Implementation Directory**: `src/plugins/simulation/`
- **Concurrency Mode**: Single plugin
- **Current Purpose**: Provide side-effect-free general counterfactual rehearsal
- **Default/Fallback Direction**: Itself is the general fallback sandbox; if unavailable, rehearsal chain explicitly interrupts
- **Management Redline**: Absolutely cannot produce physical side effects
- **Family-level Specification**:
  - [Simulation DEVELOPMENT_GUIDE](../../../src/plugins/simulation/DEVELOPMENT_GUIDE.md)

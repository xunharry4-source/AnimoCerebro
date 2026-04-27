# Risk Assessment Plugin Feature Description

- **Feature Key**: `risk_assessment`
- **Display Name**: Risk Assessment
- **Plugin Family**: `cognitive`
- **Implementation Directory**: `src/plugins/cognitive/`
- **Concurrency Mode**: Single plugin
- **Current Purpose**: Compare risks of candidate paths and output conservative alternative suggestions
- **Default/Fallback Direction**: Fallback to the previous formal version under the same `behavior_key`, or system default version
- **Management Redline**: When enabling a new version, must automatically suspend the already activated old version of the same function
- **Family-level Specification**:
  - [Cognitive DEVELOPMENT_GUIDE](../../../src/plugins/cognitive/DEVELOPMENT_GUIDE.md)

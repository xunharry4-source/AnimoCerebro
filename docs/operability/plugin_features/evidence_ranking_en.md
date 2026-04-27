# Evidence Ranking Plugin Feature Description

- **Feature Key**: `evidence_ranking`
- **Display Name**: Evidence Ranking
- **Plugin Family**: `cognitive`
- **Implementation Directory**: `src/plugins/cognitive/`
- **Concurrency Mode**: Single plugin
- **Current Purpose**: Rank candidate evidence by credibility and conservativeness
- **Default/Fallback Direction**: Fallback to the default formal version tool under this behavior
- **Management Redline**: Prohibited from outputting execution actions, only allowed to output evidence ranking results
- **Family-level Specification**:
  - [Cognitive DEVELOPMENT_GUIDE](../../../src/plugins/cognitive/DEVELOPMENT_GUIDE.md)

# Webhook Signal Ingestion Plugin Feature Description

- **Feature Key**: `sensory_ingest:webhook`
- **Display Name**: Webhook Signal Ingestion
- **Plugin Family**: `sensory`
- **Implementation Directory**: `src/plugins/sensory/`
- **Concurrency Mode**: Single plugin
- **Current Purpose**: Ingest raw signals from Webhook and other entry points
- **Default/Fallback Direction**: Fallback to system default ingester; if no safe ingester, entire sensory chain blocks
- **Management Redline**: Ingesters cannot pretend they have completed sanitization and interpretation
- **Family-level Specification**:
  - [Sensory DEVELOPMENT_GUIDE](../../../src/plugins/sensory/DEVELOPMENT_GUIDE.md)

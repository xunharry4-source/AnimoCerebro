# Memory Consolidation Plugin Feature Description

**Feature Key**: `memory_consolidation`

**Display Name**: Offline Memory Consolidation

**Plugin Family**: `cognitive`

**Implementation Directory**: `src/plugins/cognitive/`

**Concurrency Mode**: Multi-plugin concurrent (`supports_multiple_plugins = true`)

**Current Purpose**:
- Parallel analysis of memory fragments during sleep organization, reflection post-processing, memory governance review and todo cleanup phases
- Extract experience candidates eligible for promotion
- Clean up low-value noise that can be forgotten
- Provide structured input for LLM to generate high-value compressed summaries

**Default/Fallback Direction**:
- Default analysis plugin: `failure-mode-cluster`
- Default cleanup plugin: `expired-assumption-cleaner`
- If LLM call fails, this consolidation cycle must fail and back off, absolutely not allowed to use string truncation or regex to replace semantic compression

**Management Redlines**:
- Can only run offline, strictly prohibited from blocking online hot paths
- Strictly prohibited from cleaning `identity_role_pack`, `identity_constraint_pack`, `identity_experience_pack`
- Workers must verify `brain_scope`, `lease_id` and `snapshot_version` before submitting results

**Family-level Reference**:
- [src/plugins/cognitive/DEVELOPMENT_GUIDE.md](../../../src/plugins/cognitive/DEVELOPMENT_GUIDE.md)

# Cognitive Tool Interface

This document is the implementation-facing bridge for the `G41` cognitive tool workstream.

## Scope

The cognitive tool interface is limited to:

- read-only reasoning helpers
- structured tool registration
- deterministic selection/orchestration
- explicit trigger and do-not-use rules
- no external side effects

It does not cover:

- browser control
- file writes
- deployment
- remote execution
- host takeover

## Current Runtime Objects

- `CognitiveToolSpec`
- `CognitiveToolRegistry`
- `CognitiveToolOrchestrator`
- `CognitiveToolInvocation`
- `CognitiveToolResult`

## Current Default Tools

- `code_read`
- `workspace_search`
- `semantic_code_navigator`
- `patch_plan_builder`

## Guardrails

- tools must declare trigger conditions
- tools must stay read-only
- tool outputs are reasoning inputs, not execution commands
- orchestration reports must remain explainable and serializable

## Related Docs

- [项目计划/14A-认知工具通用技术接口方案.md](/Users/harry/Documents/git/zentex/项目计划/14A-认知工具通用技术接口方案.md)
- [src/zentex/runtime/cognitive_tools.py](/Users/harry/Documents/git/zentex/src/zentex/runtime/cognitive_tools.py)
- [src/zentex/runtime/runtime.py](/Users/harry/Documents/git/zentex/src/zentex/runtime/runtime.py)

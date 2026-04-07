# Zentex ThinkLoop: 9-Stage Cognitive Architecture Deep Dive

The ThinkLoop is the core "Counselor Brain" of Zentex. It orchestrates the flow from raw observation to final delegated action across nine distinct cognitive stages.

## 1. The Nine Questions (Q1-Q9)

The system enforces a clinical-grade reasoning process by answering nine fundamental questions before any tool is executed:

| Stage | Question | Purpose | LLM Role |
| :--- | :--- | :--- | :--- |
| **Q1** | Where am I? | Environment & Workspace Analysis | Context Framing |
| **Q2** | Who am I? | Role & Persona Alignment | [LLM MANDATORY] |
| **Q3** | What do I have? | Asset & Resource Inventory (Q3 Plugin) | Inventory Synthesis |
| **Q4** | What could I do? | Capability Matching | Option Generation |
| **Q5** | What should I do? | Strategic Prioritization | Risk/Reward Analysis |
| **Q6** | What are the risks? | Boundary & Policy Audit | Safety Enforcement |
| **Q7** | What is the plan? | Step-by-step Execution Graph | [LLM MANDATORY] |
| **Q8** | What is the action? | Tool Call / Delegation Receipt Synthesis | [LLM MANDATORY] |
| **Q9** | What did I learn? | Verification & Memory Consolidation | Feedback Loop |

## 2. Agent Bridge Protocol Integration

Heterogeneous Agents (like the Random Number Agent on 9201) are integrated during **Phase 3 (Q3)** and **Phase 8 (Q8)**.

### Q3: Asset Inventory Scan
The `Q3WhatDoIHavePlugin` performs a live scan of the `AgentManager`.
- Agents with `trust_level: revoked` or `status: offline` are **automatically excluded** from the inventory snapshot.
- Only `TRUSTED` agents with valid `capabilities_snapshot` are promoted to the active session context.

### Q4-Q8: Capability Flow
1. **Q4 (Match)**: The system matches the current task (e.g., "Sample a random value") against the `Random Number Agent`'s `random_number` capability.
2. **Q5 (Advise)**: The `AgentCoordinationService` calls `think_about_task` to generate an advisory decision (`EXECUTABLE_NOW`, `BLOCKED_BY_BOUNDARY`).
3. **Q8 (Act)**: If the decision is `allow`, the system synthesizes a `DelegatedCommand` and sends it to the Agent's `/task` or specific capability endpoint via the bridge.

## 3. [LLM MANDATORY] Cognitive Redlines

To prevent "hallucination loops" or "agent-to-agent collusion," the ThinkLoop enforces **Hard LLM Interventions** at three critical gates:

> [!IMPORTANT]
> - **Phase 2 (Who am I?)**: The system *must* use an LLM-vetted persona to ensure it acts as a "Counselor" and not a "Rogue Agent."
> - **Phase 7 (Plan Synthesis)**: All multi-stage plans involving external agents must be reviewed by the core LLM for boundary compliance.
> - **Phase 8 (Action Generation)**: The final command payload sent to an external Agent is verified against the user's `trust_level` policy.

## 4. UI Tracing (Q4-Q9 Accordion)

The Web Console uses the `trace_id` from the `BrainTranscript` to render the reasoning steps.
- **Accordion Linkage**: Every step in the "Thinking..." UI is a direct visualization of a `ThinkLoop` phase.
- **Real-time Streaming**: Steps are pushed via WebSockets (`/api/web/events/stream`) as they are completed by the backend orchestrator.

## 5. Testability & Fail-Closed Logic

The system is designed with **Fail-Closed** defaults:
- If a `POST /capability-handshake` fails or is rejected by the `AgentCoordinationService`, the Agent stays `OFFLINE` and is invisible to subsequent ThinkLoop turns.
- If a `DELETE` is issued, the Agent is physically removed from the `AgentManager` and cannot be scavenged by Q3.

# AnimoCerebro Core Foundations

## Positioning

AnimoCerebro is the **Brain** for Agents and Host Systems. It provides a universal **External Brain** for all AI species, including individual Agents and host platforms like openCLaw.

It is responsible for giving AI:
- **Autonomy**: Independent goal generation, execution drive, and **self-upgrading**.
- **Reflection**: Constant self-assessment and meta-cognition.
- **Learning**: Long-term experience exchange and memory consolidation.

Its core cognitive responsibilities include:
- reasoning & role inference
- goal generation & risk judgment
- memory accumulation & delegation advice

## Core Loop

The system is organized around the **nine-question cognitive loop**. This loop is the foundation of AI autonomy; the brain can **act autonomously** based on the results of these questions:

1. Where am I
2. Who am I
3. What do I have
4. What can I do
5. What am I allowed to do
6. What else can I do
7. What should I not do even if I can
8. What should I do
9. How should I do it

**AI drives subsequent actions independently once these nine questions establish the situational and moral boundaries.**

## Core Runtime Shape

The current public architecture has these layers:

1. cognition and orchestration
2. safety and audit
3. memory and reflection
4. delegation and collaboration
5. host adapters
6. web and observability

## Public Design Boundaries

The public architecture keeps these boundaries stable:

- the host keeps execution ownership
- AnimoCerebro keeps reasoning ownership
- adapters translate between hosts and the brain
- high-risk actions must remain observable and auditable

## Truthfulness Boundary

The core logic must not pretend deterministic or degraded outputs are live AI reasoning.

Hard rules:

- live LLM is part of the brain core for role inference and goal generation
- if live LLM is unavailable or errors, runtime must fail closed instead of silently switching to rule output
- nine-question and reflection protocol assembly are currently deterministic protocol synthesis, not live LLM generation
- deterministic protocol synthesis must carry explicit provenance and must not be labeled as AI-generated reasoning
- semantic memory recall must not label lexical fallback or hash-baseline retrieval as semantic AI recall
- any degraded or fallback result must expose its source and degraded reason directly in payloads and audits

Forbidden behavior:

- silently replacing live LLM reasoning with rule heuristics in runtime
- returning lexical fallback results while marking them as semantic recall
- presenting deterministic protocol templates as if they were model-generated cognition
- using “normal-looking output” as a substitute for truthful runtime state

## What Is Safe To Build Against

Third parties can safely build around:

- public protocol objects
- public web APIs
- host adapter interfaces
- runtime observability surfaces

They should not assume:

- private strategy internals
- hidden memory heuristics
- commercial audit implementation details
- internal roadmap ordering

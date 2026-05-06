# nine_question_q7_red_line_assessment

- Name: Q7 Red Line Assessment
- Description: Answer the seventh nine-question prompt: "我的红线与约束是什么".

Q7 is the final cognitive firewall before Q8 objective generation. The live LLM output must be a strict JSON object whose only top-level key is `RedLineAssessment`. The `RedLineAssessment` object has exactly these fields:

- `current_redline_hits`
- `rejected_operations_log`
- `constraint_sources_explanation`
- `non_bypassable_constraints`

## Evidence Sources

- Q3 mission and continuity boundaries.
- Q5 forbidden operations and authorization boundaries.
- Identity boundary bottom constraints and self-binding rules.
- Recent safety-gate and audit-channel rejected operations.
- Current intent context for active red-line hit detection.

## Runtime Rules

- Q7 must validate the live LLM output against the strict schema.
- Invalid or incomplete LLM output must trigger another LLM call before failing closed.
- Prompt, context, raw response, token usage, attempts, and question driver refs must be persisted in `llm_trace_payload`.
- Q8 must treat active Q7 red-line hits as a hard gate and convert external tasking into internal cognitive preflight or negotiation tasks.

from __future__ import annotations

from typing import Iterator


LEGACY_PLUGIN_ID_ALIASES: dict[str, str] = {
    "budget-conflict": "cognitive_budget_conflict",
    "expired-assumption-cleaner": "cognitive_expired_assumption",
    "failure-mode-cluster": "cognitive_failure_cluster",
    "semantic-conflict": "cognitive_semantic_conflict",
    "memory-extractor-llm": "memory_extractor",
    "model-provider-openai-compat": "model_provider_tools",
    "baseline_alternative_oracle": "oracle_alternative",
    "baseline_objective_oracle": "oracle_objective",
    "baseline_posture_oracle": "oracle_posture",
    "baseline_redline_oracle": "oracle_redline",
    "reflection-generator-llm": "reflection_generator",
    "sensory-interpret-generic": "sensory_environment",
    "host-telemetry-local": "sensory_telemetry",
    "sensory-sanitize-basic": "sensory_injection_sanitizer",
    "sensory-ingest-webhook": "sensory_webhook",
    "q1_where_am_i": "nine-question-q1-where-am-i",
    "q2_who_am_i": "nine-question-q2-who-am-i",
    "q3_what_do_i_have": "nine-question-q3-what-do-i-have",
    "q4_what_can_i_do": "nine-question-q4-what-can-i-do",
    "q5_allowed_to_do": "nine-question-q5-what-am-i-allowed-to-do",
    "q6_should_not_do": "nine-question-q6-what-should-i-not-do",
    "q7_else_can_do": "nine_question_q7_alternatives",
    "q8_should_do_now": "nine_question_q8_decision",
    "q9_how_should_act": "nine_question_q9_posture",
}


def canonicalize_plugin_id(plugin_id: str) -> str:
    return LEGACY_PLUGIN_ID_ALIASES.get(plugin_id, plugin_id)


def iter_plugin_id_aliases(plugin_id: str) -> Iterator[str]:
    canonical_plugin_id = canonicalize_plugin_id(plugin_id)
    for alias, canonical in LEGACY_PLUGIN_ID_ALIASES.items():
        if canonical == canonical_plugin_id:
            yield alias

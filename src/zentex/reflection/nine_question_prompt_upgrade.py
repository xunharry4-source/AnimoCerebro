from __future__ import annotations

from importlib import import_module

from plugins.nine_questions.prompt_upgrade_contract import NineQuestionPromptUpgradeContract


_QUESTION_SERVICE_MODULES: dict[str, str] = {
    "q1": "plugins.nine_questions.q1_where_am_i.service",
    "q2": "plugins.nine_questions.q2_who_am_i.service",
    "q3": "plugins.nine_questions.q3_what_do_i_have.service",
    "q4": "plugins.nine_questions.q4_what_can_i_do.service",
    "q5": "plugins.nine_questions.q5_what_am_i_allowed_to_do.service",
    "q6": "plugins.nine_questions.q6_what_should_i_not_do.service",
    "q7": "plugins.nine_questions.q7_what_else_can_i_do.service",
    "q8": "plugins.nine_questions.q8_what_should_i_do_now.service",
    "q9": "plugins.nine_questions.q9_how_should_i_act.service",
}


def get_prompt_upgrade_contract(question_id: str) -> NineQuestionPromptUpgradeContract:
    qid = str(question_id).strip().lower()
    module_name = _QUESTION_SERVICE_MODULES[qid]
    module = import_module(module_name)
    factory = getattr(module, "get_prompt_upgrade_contract")
    return factory()


def list_prompt_upgrade_contracts() -> dict[str, NineQuestionPromptUpgradeContract]:
    return {
        question_id: get_prompt_upgrade_contract(question_id)
        for question_id in _QUESTION_SERVICE_MODULES
    }

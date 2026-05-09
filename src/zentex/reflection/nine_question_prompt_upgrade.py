from __future__ import annotations

from importlib import import_module

from zentex.common.nine_questions_prompts import NineQuestionPromptUpgradeContract


_QUESTION_CONTRACT_MODULES: dict[str, str] = {
    "q1": "plugins.nine_questions.q1_where_am_i.prompt_contract",
    "q2": "plugins.nine_questions.q2_asset_inventory.prompt_contract",
    "q3": "plugins.nine_questions.q3_role_inference.prompt_contract",
    "q4": "plugins.nine_questions.q4_what_can_i_do.prompt_contract",
    "q5": "plugins.nine_questions.q5_what_am_i_allowed_to_do.prompt_contract",
    "q6": "plugins.nine_questions.q6_what_should_i_not_do.prompt_contract",
    "q7": "plugins.nine_questions.q7_what_else_can_i_do.prompt_contract",
    "q8": "plugins.nine_questions.q8_what_should_i_do_now.prompt_contract",
    "q9": "plugins.nine_questions.q9_how_should_i_act.prompt_contract",
}


def get_prompt_upgrade_contract(question_id: str) -> NineQuestionPromptUpgradeContract:
    qid = str(question_id).strip().lower()
    module_name = _QUESTION_CONTRACT_MODULES[qid]
    module = import_module(module_name)
    factory = getattr(module, "get_prompt_upgrade_contract")
    return factory()


def list_prompt_upgrade_contracts() -> dict[str, NineQuestionPromptUpgradeContract]:
    return {
        question_id: get_prompt_upgrade_contract(question_id)
        for question_id in _QUESTION_CONTRACT_MODULES
    }

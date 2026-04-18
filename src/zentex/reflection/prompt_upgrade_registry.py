from __future__ import annotations

from importlib import import_module
from typing import Any


_MODULE_PROMPT_SERVICE_MODULES: tuple[str, ...] = (
    "zentex.tasks.core.service",
    "zentex.tasks.verification.service",
    "zentex.upgrade.llm.service",
    "zentex.upgrade.skills.service",
    "zentex.upgrade.service",
    "zentex.cognition.service",
    "zentex.memory.consolidation.service",
)


def list_module_prompt_upgrade_contracts() -> dict[str, Any]:
    contracts: dict[str, Any] = {}
    for module_name in _MODULE_PROMPT_SERVICE_MODULES:
        module = import_module(module_name)
        factory = getattr(module, "list_prompt_upgrade_contracts")
        for contract in factory():
            contracts[str(contract.prompt_id)] = contract
    return contracts


def get_module_prompt_upgrade_contract(prompt_id: str) -> Any:
    normalized = str(prompt_id).strip()
    contracts = list_module_prompt_upgrade_contracts()
    return contracts[normalized]


def list_all_prompt_upgrade_contracts() -> dict[str, Any]:
    from zentex.reflection.nine_question_prompt_upgrade import list_prompt_upgrade_contracts

    contracts = list_module_prompt_upgrade_contracts()
    contracts.update(list_prompt_upgrade_contracts())
    return contracts


def get_any_prompt_upgrade_contract(contract_id: str) -> Any:
    normalized = str(contract_id).strip().lower()
    all_contracts = list_all_prompt_upgrade_contracts()
    return all_contracts[normalized]

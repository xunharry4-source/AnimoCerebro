from __future__ import annotations

from dataclasses import replace
from importlib import import_module
from pathlib import Path

from zentex.kernel.prompt_contracts import ALL_CONTRACTS, build_contract_summary, validate_cross_q_consistency


def _resolve_symbol(symbol: str):
    module_name, function_name = symbol.rsplit(".", 1)
    module = import_module(module_name)
    return getattr(module, function_name)


def test_prompt_contract_registry_covers_all_nine_questions_with_real_builders() -> None:
    summary = build_contract_summary()

    assert summary["contract_status"] == "passed"
    assert summary["question_count"] == 9
    assert summary["consistency_errors"] == []
    assert set(summary["questions"]) == {f"q{index}" for index in range(1, 10)}

    for question_id, contract in ALL_CONTRACTS.items():
        assert contract.question_id == question_id
        assert contract.purpose
        assert contract.outputs
        assert contract.anti_drift_directives
        assert contract.max_total_prompt_chars > 0
        assert Path(contract.prompt_file_path).exists(), contract.prompt_file_path
        assert callable(_resolve_symbol(contract.prompt_builder_symbol))
        for field in contract.outputs:
            assert field.field_name
            assert field.intent
            assert field.field_type in {"text", "list_text", "structured", "number", "boolean"}

    q8 = summary["questions"]["q8"]
    assert q8["max_total_prompt_chars"] == 4000
    assert {item["field_name"] for item in q8["output_fields"]} == {"objective_profile", "task_queue"}
    assert {source["source_question"] for source in q8["input_sources"]} == {f"q{index}" for index in range(1, 8)}

    q9 = summary["questions"]["q9"]
    assert {item["field_name"] for item in q9["output_fields"]} == {
        "evaluation_profile",
        "evolution_profile",
        "escalation_profile",
    }
    assert any(source["source_question"] == "q8" and "task_queue" in source["fields"] for source in q9["input_sources"])


def test_prompt_contract_registry_fails_closed_on_bad_cross_question_reference() -> None:
    bad_q8 = replace(
        ALL_CONTRACTS["q8"],
        inputs=(replace(ALL_CONTRACTS["q8"].inputs[0], fields=("missing_field",)),) + ALL_CONTRACTS["q8"].inputs[1:],
    )
    broken_registry = {**ALL_CONTRACTS, "q8": bad_q8}

    errors = validate_cross_q_consistency(broken_registry)

    assert errors == ["q8 references q1.missing_field which is not in upstream outputs"]

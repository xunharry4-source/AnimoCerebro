from __future__ import annotations

from pathlib import Path

import pytest

from zentex.foundation.specs.model_provider import ModelProviderCallerContext
from zentex.launcher.config import load_yaml_config
from zentex.llm.service import get_service as get_llm_service


def test_llm_real_runtime_strict_success() -> None:
    """
    真实 LLM 单独验收测试（严格模式）：
    - 必须通过 zentex.llm.service.get_service() 正式入口调用
    - 必须真实请求模型并返回可解析 JSON
    - 必须显式走 Gemini，不能被默认 provider 配置影响
    - provider/model 不能是空值或默认占位值
    """
    pytest.importorskip("google.genai", reason="Gemini real-runtime acceptance test requires google-genai")

    provider_config = load_yaml_config(Path("config") / "provider_tools.yml")
    configured_model = str(
        (((provider_config.get("providers") or {}).get("gemini") or {}).get("default_model") or "")
    ).strip()

    assert configured_model, "Gemini default_model is missing in config/provider_tools.yml"
    llm_service = get_llm_service()

    call = llm_service.generate_json(
        prompt=(
            "Return JSON with keys: "
            "ping (string, must be 'pong'), "
            "runtime_check (string, must be 'real_llm')."
        ),
        context={"source": "ci_acceptance", "test_case": "llm_real_runtime"},
        caller_context=ModelProviderCallerContext(
            source_module="tests.ci_acceptance.test_llm_real_runtime",
            invocation_phase="ci_acceptance_llm_real_runtime",
            question_driver_refs=["LLM_REAL_RUNTIME"],
            decision_id="ci_acceptance:llm_real_runtime",
            trace_id="ci-acceptance-trace-llm-real-runtime",
        ),
        source_module="tests.ci_acceptance.test_llm_real_runtime",
        invocation_phase="ci_acceptance_llm_real_runtime",
        decision_id="ci_acceptance:llm_real_runtime",
        model_provider="gemini",
        max_output_tokens=128,
        metadata={
            "ci_acceptance": True,
            "strict_real_runtime": True,
            "expected_provider": "gemini",
        },
    )

    assert call.provider_key and str(call.provider_key).strip(), "LLM provider_key is empty"
    assert str(call.provider_key).strip() == "gemini", f"Unexpected LLM provider_key: {call.provider_key!r}"
    assert call.model and str(call.model).strip(), "LLM model is empty"
    assert str(call.model).strip() != "default-model", "LLM model fallback 'default-model' is not allowed in strict real-runtime test"
    assert str(call.model).strip() == str(configured_model).strip(), (
        f"Unexpected Gemini model: {call.model!r}, expected configured model {configured_model!r}"
    )

    output = call.output
    assert isinstance(output, dict), "LLM output must be a JSON object"
    assert output.get("ping") == "pong", f"Unexpected LLM ping value: {output!r}"
    assert output.get("runtime_check") == "real_llm", f"Unexpected LLM runtime_check value: {output!r}"

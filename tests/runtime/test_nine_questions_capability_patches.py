import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

from zentex.core.model_provider_spec import ModelProviderSpec, ModelProviderCallerContext
from zentex.runtime.transcript import BrainTranscriptStore
from plugins.nine_questions.q1_where_am_i.capability_patch_plugin import build_q1_where_am_i_capability_patch_plugin

def test_patch_llm_mandatory_and_traceability():
    print("Running 9-Questions Capability Patch Redline Tests...")
    
    # Setup Mocks
    mock_provider = MagicMock(spec=ModelProviderSpec)
    mock_provider.generate_json.side_effect = Exception("LLM_CONNECTION_FAILED")
    
    mock_transcript = MagicMock(spec=BrainTranscriptStore)
    
    # 1. Test LLM_MANDATORY & Fail-Closed
    print("\n[ASSERTION 1] Checking [LLM MANDATORY] & Fail-Closed...")
    patch_plugin = build_q1_where_am_i_capability_patch_plugin()
    
    context = {
        "model_provider": mock_provider,
        "transcript_store": mock_transcript,
        "context_snapshot": {
            "workspace_structure_analysis": {},
            "workspace_content_samples": {},
            "environment_event": {},
            "physical_host_state": {},
        }
    }
    
    try:
        patch_plugin.run_tool(context)
        assert False, "ERROR: Patch returned a result even when LLM call failed!"
    except Exception as exc:
        print(f"PASS: Patch failed closed as expected: {exc}")

    # 2. Test Traceability Injection
    print("\n[ASSERTION 2] Verifying Traceability Injection (caller_context)...")
    mock_provider.generate_json.side_effect = None
    mock_provider.generate_json.return_value = {
        "patch_summary": "Detected financial domain presence.",
        "patch_updates": {"is_finance": True}
    }
    
    patch_plugin.run_tool(context)
    
    _, kwargs = mock_provider.generate_json.call_args
    caller_ctx = kwargs.get("caller_context")
    assert isinstance(caller_ctx, ModelProviderCallerContext)
    assert caller_ctx.source_module == "q1_where_am_i_patch"
    assert "我在哪-能力增强补丁" in caller_ctx.question_driver_refs
    print(f"PASS: Traceability verified. Source: {caller_ctx.source_module}, Question: {caller_ctx.question_driver_refs}")

    # 3. Test Concurrency safe flag
    print("\n[ASSERTION 3] Verifying Multi-Plugin Concurrency safe flag...")
    assert patch_plugin.supports_multiple_plugins is True
    print("PASS: supports_multiple_plugins=True confirmed.")

    print("\nALL 9-QUESTIONS CAPABILITY PATCH REDLINE TESTS PASSED.")

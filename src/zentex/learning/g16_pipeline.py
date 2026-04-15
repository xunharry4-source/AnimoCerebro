from __future__ import annotations

import uuid
import json
from typing import Any, Dict, List, Optional
from typing_extensions import Self

import dspy

from zentex.foundation.specs.model_provider import ModelProviderCallerContext, ModelProviderSpec
from zentex.foundation.specs.cognitive_tool_spec import CognitiveToolSpec
from zentex.plugins.contracts import PluginLifecycleStatus, PluginHealthStatus
from zentex.learning.g16_models import SandboxValidationResult, ToolKnowledgeRecord
from zentex.learning.sandbox import ThoughtSandbox
from zentex.kernel import BrainTranscriptEntryType, BrainTranscriptStore
from zentex.llm.service import LLMService

from zentex.learning.dspy_adapter import ZentexDSPyLM
from zentex.learning.g16_dspy_signatures import ToolDistillationModule, ToolCriticModule

MAX_ATTEMPTS = 3
MAX_CPU_SEC = 2.0
MAX_MEM_MB = 100.0

async def run_g16_dynamic_tool_self_study(
    *,
    doc_url: str,
    provider: ModelProviderSpec | None = None,
    llm_service: LLMService | None = None,
    model_provider_key: str | None = None,
    store: BrainTranscriptStore,
    trace_id: str,
) -> Optional[ToolKnowledgeRecord]:
    """
    Execute G16 Tool Self-Study pipeline using Voyager Iterative loop and DSPy:
    1. Distill tool info from documentation using DSPy (with error回放 if failed).
    2. Sandbox verification of distilled tool.
    3. Return validated ToolKnowledgeRecord for promotion or feed error back to DSPy.
    """
    sandbox = ThoughtSandbox()
    caller = ModelProviderCallerContext(
        source_module="zentex.learning.g16_pipeline",
        invocation_phase="g16_tool_distillation",
        question_driver_refs=["G16", "Voyager", "DSPy"],
        trace_id=trace_id,
        decision_id=None,
    )

    # Initialize DSPy LM with our adapter
    zentex_lm = ZentexDSPyLM(
        provider=provider,
        llm_service=llm_service,
        model_provider_key=model_provider_key,
        caller_context=caller,
    )
    dspy.settings.configure(lm=zentex_lm)
    
    distiller = ToolDistillationModule()
    critic = ToolCriticModule()
    
    feedback_history = "None"
    
    for attempt in range(MAX_ATTEMPTS):
        store.write_entry(
            session_id="learning_engine",
            turn_id=f"g16_learning_attempt_{attempt + 1}",
            entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
            payload={"kind": "attempt_started", "attempt": attempt + 1, "feedback": feedback_history},
            source="zentex.learning.g16_pipeline",
            trace_id=trace_id,
        )

        try:
            prediction = distiller(doc_url=doc_url, feedback_history=feedback_history)
            
            # DSPy OutputField returns strings by default; parse them if they are strings
            input_schema = json.loads(prediction.input_schema) if isinstance(prediction.input_schema, str) else prediction.input_schema
            output_schema = json.loads(prediction.output_schema) if isinstance(prediction.output_schema, str) else prediction.output_schema
            test_cases = json.loads(prediction.test_cases) if isinstance(prediction.test_cases, str) else prediction.test_cases
            
            record = ToolKnowledgeRecord(
                tool_name=prediction.tool_name,
                description=prediction.description,
                usage_example=prediction.usage_example,
                input_schema=input_schema,
                output_schema=output_schema,
                source_ref=doc_url,
            )
        except Exception as exc:
            store.write_entry(
                session_id="learning_engine",
                turn_id=f"g16_learning_attempt_{attempt + 1}",
                entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
                payload={"kind": "retry", "reason": f"DSPy or LLM parsing error: {str(exc)}"},
                source="zentex.learning.g16_pipeline",
                trace_id=trace_id,
            )
            feedback_history = f"Error generating or parsing JSON schemas: {str(exc)}. Please fix JSON formatting."
            continue

        # 2a. Pre-Sandbox Critic Review
        critique_res = critic(
            doc_url=doc_url,
            proposed_tool_name=record.tool_name,
            proposed_code_schema=json.dumps(record.input_schema),
            proposed_test_cases=json.dumps(test_cases)
        )
        
        is_approved_str = str(critique_res.is_approved).strip().lower()
        if is_approved_str not in ["true", "1", "yes"]:
            feedback_history = f"Pre-sandbox Critic rejected the code: {critique_res.critique_feedback}. Please fix."
            store.write_entry(
                session_id="learning_engine",
                turn_id=f"g16_learning_attempt_{attempt + 1}",
                entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
                payload={"kind": "retry", "reason": "critic_rejected", "critique": critique_res.critique_feedback},
                source="zentex.learning.g16_pipeline",
                trace_id=trace_id,
            )
            continue

        spec = CognitiveToolSpec(
            plugin_id=f"g16_candidate_{uuid.uuid4().hex[:8]}",
            version="0.1.0",
            feature_code="g16.dynamic_study",
            is_concurrency_safe=True,
            lifecycle_status=PluginLifecycleStatus.CANDIDATE,
            health_status=PluginHealthStatus.HEALTHY,
            rollback_conditions=["sandbox_failed"],
            revocation_reasons=[],
            tool_type="dynamic_self_study",
            purpose=record.description,
            input_schema=record.input_schema,
            output_schema=record.output_schema,
            required_context=["dynamic_evaluation"],
            trigger_conditions=["manual_trigger"],
            behavior_key="identity_transform",
            do_not_use_when=["sandbox_active"],
            read_only=True,
            side_effect_free=True,
        )

        # 3. Sandbox Verification (Actor-Critic loop validation)
        validation = await sandbox.verify_tool_registration(spec, test_cases)
        
        if validation.is_safe:
            # 4. Performance Optimization Check
            cpu = validation.performance_metrics.get("cpu_sec", 0.0)
            mem = validation.performance_metrics.get("mem_mb", 0.0)
            
            if cpu > MAX_CPU_SEC or mem > MAX_MEM_MB:
                feedback_history = f"Code functional but failed optimization targets! CPU: {cpu}s (Max {MAX_CPU_SEC}s), Mem: {mem}MB (Max {MAX_MEM_MB}MB). Rewrite code to perfectly meet resource constraints."
                store.write_entry(
                    session_id="learning_engine",
                    turn_id=f"g16_learning_attempt_{attempt + 1}",
                    entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
                    payload={"kind": "retry", "reason": "performance_overload", "metrics": validation.performance_metrics},
                    source="zentex.learning.g16_pipeline",
                    trace_id=trace_id,
                )
                continue

            store.write_entry(
                session_id="learning_engine",
                turn_id="g16_learning_success",
                entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
                payload={"kind": "completed", "attempt_needed": attempt + 1, "tool_name": record.tool_name},
                source="zentex.learning.g16_pipeline",
                trace_id=trace_id,
            )
            return record
        else:
            feedback_history = f"Attempt {attempt + 1} Sandbox validation failed: {validation.security_events}. Please fix the logical errors."
            store.write_entry(
                session_id="learning_engine",
                turn_id=f"g16_learning_attempt_{attempt + 1}",
                entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
                payload={"kind": "retry", "reason": feedback_history},
                source="zentex.learning.g16_pipeline",
                trace_id=trace_id,
            )

    store.write_entry(
        session_id="learning_engine",
        turn_id="g16_learning_exhausted",
        entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
        payload={"kind": "aborted", "reason": "Max attempts exhausted"},
        source="zentex.learning.g16_pipeline",
        trace_id=trace_id,
    )
    return None

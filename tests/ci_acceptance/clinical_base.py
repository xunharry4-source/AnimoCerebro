import asyncio
import logging
import json
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass

@dataclass
class MockToolResponse:
    output_text: str
    usage: Dict[str, int]
    raw_response: Dict[str, Any]

class ClinicalStubTool:
    """
    仿真 LLM 插件：返回符合各问 Pydantic 模型要求的 JSON。
    """
    def call(self, invocation: Any) -> MockToolResponse:
        prompt = invocation.prompt
        # Q1: 我在哪
        if "q1_where_am_i" in prompt or "q1" in prompt:
            res = {
                "primary_domain": "workspace_clinical_test",
                "secondary_domains": ["testing"],
                "confidence": 0.95,
                "reasoning_summary": "Located in Zentex internal workspace.",
                "uncertainties": ["none"],
                "suggested_first_step": "Validate Q1.",
                "host_runtime_type": "macOS_sandbox",
                "host_runtime_reason": "Clinical test"
            }
        # Q8: 我该做什么
        elif "q8" in prompt:
             res = {
                "objective_profile": {
                    "current_mission": "Validate Q8 synchronization.",
                    "primary_objectives": ["verify_task_persistence"],
                    "secondary_objectives": [],
                    "completion_conditions": ["tasks_visible"],
                    "pause_conditions": [],
                    "escalation_conditions": [],
                    "current_phase_tasks": ["sync_test_task"],
                    "priority_order": ["sync_test_task"]
                },
                "task_queue": {
                    "next_self_tasks": [
                        {"description": "Q8 Clinical Sync Task", "metadata": {"source": "q8"}}
                    ],
                    "blocked_self_tasks": [],
                    "proactive_actions": []
                }
            }
        else:
            # 默认返回一个最简兼容结构 (假设大多数问需要 reasoning_summary 和 primary_domain)
            res = {
                "primary_domain": "general_clinical",
                "confidence": 1.0,
                "reasoning_summary": "Clinical stub response",
                "uncertainties": ["none"],
                "suggested_first_step": "Continue"
            }
        
        return MockToolResponse(
            output_text=json.dumps(res),
            usage={"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
            raw_response={"mock": True}
        )

def patch_llm_service_with_stub(llm_service: Any):
    """将 LLMService 注入 Stub Tool"""
    stub = ClinicalStubTool()
    if hasattr(llm_service, "_gateway"):
        gw = llm_service._gateway
        # 覆盖所有 key
        for k in list(gw._tools.keys()):
            gw._tools[k] = stub
        gw._tools["ollama"] = stub
        gw._tools["default"] = stub
        print("[Clinical] LLMService gateway tools patched with ClinicalStubTool.")

from __future__ import annotations

from types import SimpleNamespace

import pytest

from zentex.agents.service import get_service as get_agent_service
from zentex.audit.service import get_service as get_audit_service
from zentex.environment.service import get_service as get_environment_service
from zentex.foundation.service import get_service as get_foundation_service
from zentex.learning.service import get_service as get_learning_service
from zentex.llm.service import get_service as get_llm_service
from zentex.memory.service import get_memory_service
from zentex.nine_questions.service import NineQuestionService
from zentex.plugins.service import get_service as get_plugin_service
from zentex.reflection.service import get_service as get_reflection_service
from zentex.safety.service import get_service as get_safety_service
from zentex.tasks.service import get_service as get_task_service
from zentex.tasks.service import LLMTaskDecomposerPlugin
from zentex.web_console.di_container import WebConsoleContainer


@pytest.fixture()
def real_ci_runtime() -> SimpleNamespace:
    """真实运行时：只使用业务入口初始化，不手动 new 核心服务。"""
    WebConsoleContainer.initialize()
    facade = WebConsoleContainer.get_kernel_service()
    kernel_service = facade._get_kernel_service()

    llm_service = get_llm_service()
    plugin_service = get_plugin_service()
    foundation_service = get_foundation_service()
    environment_service = get_environment_service()
    audit_service = get_audit_service()
    safety_service = get_safety_service()
    learning_service = get_learning_service()
    memory_service = get_memory_service()
    reflection_service = get_reflection_service()
    task_service = get_task_service()
    agent_service = get_agent_service()
    agent_service.transcript_store = kernel_service.transcript_store
    task_service.attach_dependencies(
        plugin_service=plugin_service,
        transcript_store=kernel_service.transcript_store,
    )
    # 真实拆解链路：任务服务必须绑定 LLM 拆解器，禁止使用未实现占位拆解器。
    task_service.decomposer = LLMTaskDecomposerPlugin(
        llm_service=llm_service,
        transcript_store=kernel_service.transcript_store,
        session_id="task-management",
    )

    kernel_service.attach_dependencies(
        plugins_service=plugin_service,
        llm_service=llm_service,
        foundation_service=foundation_service,
        environment_service=environment_service,
        safety_service=safety_service,
        audit_service=audit_service,
        learning_service=learning_service,
        memory_service=memory_service,
        reflection_service=reflection_service,
        agent_service=agent_service,
        task_service=task_service,
    )

    plugin_service.register_discovered_plugins()
    plugin_service.rehydrate_registered_plugins()
    if callable(getattr(plugin_service, "attach_cognitive_services", None)):
        plugin_service.attach_cognitive_services(
            llm_service=llm_service,
            audit_service=audit_service,
            memory_service=memory_service,
            reflection_service=reflection_service,
            learning_service=learning_service,
            transcript_store=kernel_service.transcript_store,
        )

    nine_question_service = NineQuestionService(
        facade=facade,
        state_manager=facade.get_nine_question_state_manager(),
    )

    return SimpleNamespace(
        facade=facade,
        nine_question_service=nine_question_service,
        reflection_service=reflection_service,
        memory_service=memory_service,
        learning_service=learning_service,
        audit_service=audit_service,
        safety_service=safety_service,
        agent_service=agent_service,
        task_service=task_service,
    )

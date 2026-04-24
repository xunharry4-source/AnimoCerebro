from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_attach_dependencies_real(real_ci_runtime) -> None:
    """功能：验证 attach_dependencies 可调用。"""
    real_ci_runtime.task_service.attach_dependencies(plugin_service=None, transcript_store=None)
    suffix = unique_suffix()
    created = await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="attach"))
    assert created.task_id, "attach_dependencies 之后任务服务应仍可正常创建任务"

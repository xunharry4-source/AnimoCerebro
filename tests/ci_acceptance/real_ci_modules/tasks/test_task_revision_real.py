from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_revision_real(real_ci_runtime) -> None:
    """功能：验证 revision 属性对外可读。"""
    before = real_ci_runtime.task_service.revision
    suffix = unique_suffix()
    await real_ci_runtime.task_service.create_task(task_payload(suffix=suffix, title_prefix="rev"))
    after = real_ci_runtime.task_service.revision
    assert isinstance(before, int) and isinstance(after, int), "revision 必须是整数"

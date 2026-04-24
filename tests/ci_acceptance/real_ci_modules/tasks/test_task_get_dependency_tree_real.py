from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_get_dependency_tree_real(real_ci_runtime) -> None:
    """功能：验证 get_dependency_tree 返回依赖树。"""
    suffix = unique_suffix()
    a = await real_ci_runtime.task_service.create_task(task_payload(suffix=f"{suffix}a", title_prefix="tree"))
    b = await real_ci_runtime.task_service.create_task(task_payload(suffix=f"{suffix}b", title_prefix="tree"))
    real_ci_runtime.task_service.add_dependency(b.task_id, a.task_id)
    tree = real_ci_runtime.task_service.get_dependency_tree(b.task_id)
    assert isinstance(tree, dict) and tree.get("task_id") == b.task_id
    deps = tree.get("dependencies", [])
    assert any(dep.get("task_id") == a.task_id for dep in deps), "依赖树未包含新增依赖"

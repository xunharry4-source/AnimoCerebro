from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import task_payload, unique_suffix


@pytest.mark.asyncio
async def test_task_get_dependency_tree_real(real_ci_runtime) -> None:
    """功能：验证 get_dependency_tree 返回依赖树。"""
    suffix = unique_suffix()
    source_module = f"ci_tree_{suffix}"
    a = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=f"{suffix}a", title_prefix="tree", source_module=source_module)
    )
    b = await real_ci_runtime.task_service.create_task(
        task_payload(suffix=f"{suffix}b", title_prefix="tree", source_module=source_module)
    )
    try:
        real_ci_runtime.task_service.add_dependency(b.task_id, a.task_id)
        tree = real_ci_runtime.task_service.get_dependency_tree(b.task_id)
        assert isinstance(tree, dict) and tree.get("task_id") == b.task_id
        deps = tree.get("dependencies", [])
        assert [dep.get("task_id") for dep in deps] == [a.task_id], "依赖树未精确包含新增依赖"
        queried_b = real_ci_runtime.task_service.get_task(b.task_id)
        assert queried_b is not None and queried_b.depends_on == [a.task_id], "依赖落库后查询结果不一致"
    finally:
        real_ci_runtime.task_service.bulk_delete([b.task_id, a.task_id], force=True)

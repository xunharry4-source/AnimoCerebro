from __future__ import annotations

import pytest

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


@pytest.mark.asyncio
async def test_task_decompose_and_dispatch_mission_real(real_ci_runtime) -> None:
    """功能：验证 decompose_and_dispatch_mission 真实拆解并落库可查询。"""
    suffix = unique_suffix()
    mission = await real_ci_runtime.task_service.create_task(
        {
            "title": f"mission-{suffix}",
            "task_type": "mission",
            "originator_id": "ci_real_modules",
            "idempotency_key": f"mission-{suffix}",
            "metadata": {"source_module": "ci_real_tasks", "kind": "mission"},
            "remarks": "将任务拆解为可执行子任务，先分析再执行再验证。",
        }
    )

    created_ids = [mission.task_id]
    try:
        await real_ci_runtime.task_service.decompose_and_dispatch_mission(mission)

        # 查询校验1：父任务应记录子任务ID
        queried_mission = real_ci_runtime.task_service.get_task(mission.task_id)
        assert queried_mission is not None
        assert len(queried_mission.subtask_ids) > 0, "拆解后 mission 必须产生子任务"
        created_ids.extend(queried_mission.subtask_ids)

        # 查询校验2：每个子任务都能查到且 parent_task_id 正确
        for subtask_id in queried_mission.subtask_ids:
            subtask = real_ci_runtime.task_service.get_task(subtask_id)
            assert subtask is not None, f"子任务查询失败: {subtask_id}"
            assert subtask.parent_task_id == mission.task_id, "子任务 parent_task_id 不一致"

        # 查询校验3：按 parent_task_id 分页查询可精确命中全部子任务
        listed = real_ci_runtime.task_service.list_tasks(
            parent_task_id=mission.task_id,
            limit=len(queried_mission.subtask_ids),
            offset=0,
        )
        listed_ids = {item.task_id for item in listed}
        assert listed_ids == set(queried_mission.subtask_ids), "按父任务分页查询未精确覆盖全部子任务"

        # 查询校验4：依赖树可查询（至少根节点可用）
        tree = real_ci_runtime.task_service.get_dependency_tree(mission.task_id)
        assert tree.get("task_id") == mission.task_id
    finally:
        real_ci_runtime.task_service.bulk_delete(created_ids, force=True)

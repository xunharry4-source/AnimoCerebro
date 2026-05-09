from __future__ import annotations


def test_learning_list_directions_real(real_ci_runtime) -> None:
    """功能：验证 list_directions 返回方向列表。"""
    rows = real_ci_runtime.learning_service.list_directions()
    assert isinstance(rows, list)
    assert len(rows) > 0, "学习方向列表不应为空"
    first = rows[0]
    assert isinstance(first, dict), "方向条目应为字典"
    assert "direction_id" in first, "方向条目缺少 direction_id"
    assert "description" in first, "方向条目缺少 description"

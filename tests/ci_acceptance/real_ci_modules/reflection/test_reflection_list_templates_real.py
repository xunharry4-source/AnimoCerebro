from __future__ import annotations


def test_reflection_list_templates_real(real_ci_runtime) -> None:
    """功能：验证 list_templates 查询结果结构并命中新创建模板。"""
    svc = real_ci_runtime.reflection_service
    tpl = svc.create_template(
        name="tpl-list-real",
        description="ci",
        template_data={"sections": ["a"]},
    )
    rows = svc.list_templates()
    # 预期：返回列表，元素具备 template_id/name 字段，且包含刚创建模板。
    assert isinstance(rows, list)
    assert any(getattr(item, "template_id", "") == tpl.template_id for item in rows)

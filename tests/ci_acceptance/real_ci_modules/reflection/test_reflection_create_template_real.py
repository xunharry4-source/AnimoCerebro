from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_create_template_real(real_ci_runtime) -> None:
    """功能：验证 create_template 成功创建模板并可查询。"""
    suffix = unique_suffix()
    tpl = real_ci_runtime.reflection_service.create_template(
        name=f"tpl-{suffix}",
        description="ci template",
        template_data={"sections": ["a", "b"]},
    )
    assert tpl.template_id
    queried = real_ci_runtime.reflection_service.get_template(tpl.template_id)
    assert queried is not None and queried.template_id == tpl.template_id

from __future__ import annotations

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_reflection_get_template_real(real_ci_runtime) -> None:
    """功能：验证 get_template 查询模板。"""
    svc = real_ci_runtime.reflection_service
    suffix = unique_suffix()
    tpl = svc.create_template(
        name=f"tpl-get-{suffix}",
        description="ci",
        template_data={"sections": ["x"]},
    )
    got = svc.get_template(tpl.template_id)
    assert got is not None and got.template_id == tpl.template_id
    assert got.name == f"tpl-get-{suffix}"
    assert got.description == "ci"

# Subjective Weight 插件开发指南

本指南适用于 `src/plugins/weights/` 下的所有主观权重插件。该家族直接影响主脑的决策倾向，必须严格执行漂移回退与审计拒绝规则。

## 一、核心契约与继承底座

- 所有新插件必须最终继承 [BasePluginSpec](../../zentex/core/plugin_base.py)，并直接实现 [SubjectiveWeightPlugin](../../plugins/weights/subjective_weight_plugin.py)。
- 插件物理代码必须放在 `src/plugins/weights/` 下。
- 必须声明并提供：
  - `risk_tolerance`
  - `cost_sensitivity`
  - `creativity_bias`
  - `continuity_bias`
  - `rationale_tags`
  - `rollback_conditions`

## 二、专属架构红线与边界

- 权重插件只能影响内部排序和偏好，绝对不能直接生成执行命令。
- 权重漂移过大时必须被拒绝，绝对禁止“先挂上去再观察”。
- G25 理性审计拒绝后必须立即回退，绝对不能继续把脏权重留在活动链路里。

## 三、健康探针与失败隔离

- 权重装配失败、参数越界、审计拒绝必须被显式捕获。
- 失败时只能回退到保守默认权重，不能返回半残缺配置继续运行。
- 如果插件提供探针，必须反映当前权重包是否仍满足装配边界。

示例：

```python
try:
    validated = SubjectiveWeightPlugin.model_validate(payload)
    audit_client.evaluate(validated)
except Exception:
    active_plugin = default_conservative_weight
    raise
```

## 四、触发回滚的判定条件

以下情况必须触发回滚：

- Pydantic 校验失败
- 风险参数严重越界
- G25 理性审计拒绝
- 当前权重包与正式环境的连续性偏好冲突

默认兜底说明：

- 默认回退目标是 `default_conservative_weight`
- 如果任何候选权重包不安全，必须显式标记 `weight_fallback_occurred=True`

## 五、强制反作弊测试要求

- 必须至少覆盖：
  - 参数越界
  - 审计拒绝
  - fallback 标志被正确置位
  - 前端告警真实读取接口返回值，而不是写死变量

测试模板：

```python
import pytest

from plugins.weights.subjective_weight_plugin import RationalAuditRejectError


def test_weight_plugin_rolls_back_when_audit_rejects() -> None:
    assembler = WeightPluginAssembler(audit_client=mock_audit)
    mock_audit.evaluate.side_effect = RationalAuditRejectError("unsafe drift")

    with pytest.raises(RationalAuditRejectError):
        assembler.mount_plugin(candidate_plugin)

    assert assembler.active_plugin.plugin_id == "default_conservative_weight"
```

任何没有断言“最终活跃插件已回退到保守默认权重”的测试，视为无效。

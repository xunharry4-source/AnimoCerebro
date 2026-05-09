# Simulation 插件开发指南

本指南适用于 `src/plugins/simulation/` 下的所有模拟器插件。该家族负责无副作用地预演后果，是主脑阻止灾难动作的最后一道虚拟防线。

## 一、核心契约与继承底座

- 所有新插件必须最终继承 [BasePluginSpec](../../zentex/core/plugin_base.py)，并直接实现 [SimulationDomainPlugin](../../zentex/core/simulation_spec.py)。
- 插件物理代码必须放在 `src/plugins/simulation/` 下。
- 必须实现：
  - `simulate_action(intent, context) -> SimulationResult`
- 必须声明：
  - `supported_domains`
  - `rollback_conditions`
  - `health_status` / `health_probe`

## 二、专属架构红线与边界

- 绝对禁止产生任何物理副作用。
- 绝对禁止调用执行域插件或任何外部写操作。
- 模拟器只能返回“预测”，不能直接决定执行。
- 如果最终比较结论依赖大模型，必须走激活态 `ModelProvider`，绝对禁止本地规则瞎编最优分支。

## 三、健康探针与失败隔离

- 模拟器内部异常必须显式抛出，由总线决定是否回退到 `ThoughtSandbox`。
- 不允许吞掉崩溃后返回一个假装合理的 `SimulationResult`。
- `health_probe()` 必须说明该预测器是否还能稳定服务当前 domain。

示例：

```python
def simulate_action(self, intent, context):
    if "execute_action" in context:
        raise RuntimeError("simulation context leaked execution handle")
    return SimulationResult(
        is_safe=False,
        predicted_impacts=["detected high uncertainty"],
        veto_reason="requires replanning",
        replan_required=True,
    )
```

## 四、触发回滚的判定条件

以下情况必须触发撤销、降级或回退：

- 产生了真实副作用迹象
- 返回值不满足 `SimulationResult` 契约
- 特定领域预测器崩溃或长期超时
- 最终 OutcomeComparison 阶段的大模型不可用

默认兜底说明：

- 合法回退是切回内置通用沙盒 `ThoughtSandbox`。
- 如果连通用沙盒都不可用，则主脑必须显式中断预演，而不是伪造“最优方案”。

## 五、强制反作弊测试要求

- 必须至少覆盖：
  - 特定领域预测器崩溃后回退到 `ThoughtSandbox`
  - LLM 429/500 时最终比较结论 fail-closed
  - 上下文中不得出现执行句柄
  - 多模拟器并发结果被正确汇总

测试模板：

```python
import pytest


def test_simulation_falls_back_to_thought_sandbox() -> None:
    crashing_plugin = ...
    crashing_plugin.simulate_action.side_effect = RuntimeError("boom")

    result = orchestrator.simulate(intent=intent, plugins=[crashing_plugin], fallback=sandbox)

    assert result.is_safe is not None
    assert result.veto_reason is not None
```

任何不能证明“没有物理副作用”的测试，都不允许作为验收依据。

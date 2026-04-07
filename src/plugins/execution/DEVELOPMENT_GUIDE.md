# Execution 插件开发指南

本指南适用于 `src/plugins/execution/` 下的所有执行域插件。该家族是系统唯一会对物理世界产生副作用的出口，因此必须执行最严格的安全门控规范。

## 一、核心契约与继承底座

- 所有新插件必须最终继承 [BasePluginSpec](/Users/harry/Documents/git/AnimoCerebro/src/zentex/core/plugin_base.py)，并直接实现 [ExecutionDomainPlugin](/Users/harry/Documents/git/AnimoCerebro/src/zentex/core/execution_spec.py)。
- 插件物理代码必须放在 `src/plugins/execution/` 下。
- 必须实现：
  - `execute_action(intent, context) -> ActionExecutionReceipt`
- 必须声明：
  - `execution_domain`
  - `requires_cloud_audit`
  - `rollback_conditions`
  - `health_status` / `health_probe`

## 二、专属架构红线与边界

- 绝对禁止旁路 `SafetyGate.check()`。
- 对 `requires_cloud_audit=True` 的插件，绝对禁止旁路 `CloudAuditClient.verify()`。
- 插件内部绝对禁止自己假设“审计一定已通过”；是否允许执行必须由编排器先裁决。
- 执行方法返回值必须是强类型 `ActionExecutionReceipt`，禁止返回布尔值、空字典或字符串。

## 三、健康探针与失败隔离

- 执行器内部必须把系统错误、远程错误、权限错误限制在插件层，向上抛出明确异常。
- 不允许插件崩溃拖垮主脑；执行失败必须被视为“动作未执行”。
- `health_probe()` 必须回答该执行域当前是否可用，而不是固定健康。

示例：

```python
from zentex.core.execution_spec import ActionExecutionReceipt, ActionStatus


def execute_action(self, intent, context) -> ActionExecutionReceipt:
    try:
        evidence = self._execute(intent)
    except TimeoutError as exc:
        raise RuntimeError("execution backend timed out") from exc

    return ActionExecutionReceipt(
        status=ActionStatus.SUCCESS,
        executed_at=self._now(),
        evidence_payload={"backend_response": evidence},
    )
```

## 四、触发回滚的判定条件

以下情况必须触发撤销、降级或版本回退：

- 安全门规则命中后发现当前插件常态误报或越权
- 云审计无法通过，且插件被认定不再可信
- 回执缺失证据或证据结构破损
- 同一版本连续触发执行失败、超时或权限拒绝

默认兜底说明：

- 执行域没有“规则链兜底”资格。
- 合法回退只能是切换到上一个经过审计的稳定执行器版本，或切到系统默认执行器。
- 如果没有安全可用的激活执行器，执行链必须 fail-closed 阻断，不得偷偷改走别的路径。

## 五、强制反作弊测试要求

- 必须至少覆盖：
  - 安全闸门拒绝时底层执行绝不发生
  - 云审计缺令牌时阻断
  - 返回假回执 / 空回执被拒绝
  - 超时 / 权限失败的异常分类

测试模板：

```python
import pytest

from zentex.core.execution_spec import SecurityBlockError


def test_execute_action_is_blocked_before_side_effect() -> None:
    plugin = ExampleExecutor(...)
    plugin.execute_action = mock.Mock()

    with pytest.raises(SecurityBlockError):
        orchestrator.execute(intent=blocked_intent, plugin=plugin)

    plugin.execute_action.assert_not_called()
```

任何不能证明“越权时底层执行绝未发生”的测试，都视为无效测试。

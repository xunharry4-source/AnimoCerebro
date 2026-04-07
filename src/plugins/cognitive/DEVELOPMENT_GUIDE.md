# Cognitive 插件开发指南

本指南适用于 `src/plugins/cognitive/` 下的所有认知工具插件。认知工具属于脑内辅助思考器官，不是执行器，必须始终保持只读、无副作用、可审计。

## 一、核心契约与继承底座

- 所有新插件必须最终继承 [BasePluginSpec](/Users/harry/Documents/git/AnimoCerebro/src/zentex/core/plugin_base.py)，并直接实现 [CognitiveToolSpec](/Users/harry/Documents/git/AnimoCerebro/src/zentex/core/models.py)。
- 插件物理代码必须放在 `src/plugins/cognitive/` 下。
- 必须声明：
  - `trigger_conditions`
  - `do_not_use_when`
  - `read_only=True`
  - `side_effect_free=True`
  - `rollback_conditions`
- 若插件提供运行入口，应实现类似 `run_tool(context)` 或专属检测方法，并返回结构化结果。

最小骨架示例：

```python
from typing import Any

from zentex.core.models import CognitiveToolSpec


class ExampleCognitiveTool(CognitiveToolSpec):
    """只读认知工具示例。"""

    def run_tool(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
```

## 二、专属架构红线与边界

- 绝对禁止触发外部执行、HTTP 写请求、shell 命令、消息发送、宿主操作。
- `read_only` 与 `side_effect_free` 必须保持为 `True`；任何试图改为 `False` 的实现都应被视为非法插件。
- 如果需要推断复杂语义，可以依赖激活态 `ModelProvider`，但必须走受控调用链，不得在工具内部偷偷接一个未注册模型。
- 认知工具只能改善“看法”和“排序”，不能直接替代执行决策。

## 三、健康探针与失败隔离

- 工具内部若发生解析错误、远程推断错误、非法返回结构，必须显式抛出异常。
- 编排层会负责隔离失败工具，插件本身不能吞掉异常后返回伪造成功。
- `health_probe()` 应反映该工具当前是否可被安全调度。

示例：

```python
def run_tool(self, context: dict[str, Any]) -> dict[str, Any]:
    if not self.read_only or not self.side_effect_free:
        raise RuntimeError("cognitive tool boundary broken")
    result = self._analyze(context)
    if "system_command" in result:
        raise RuntimeError("unsafe execution payload detected")
    return result
```

## 四、触发回滚的判定条件

以下情况必须触发撤销、降级或回退：

- 输出中出现执行命令、宿主动作或外部副作用意图
- 返回结构不满足输出契约
- 在生产调度中连续失败并触发注册表失败阈值
- 触发 `do_not_use_when` 中声明的禁用边界

默认兜底说明：

- 认知工具的回退目标应为同一 `behavior_key` 下“上一个正式版本”或系统默认版本。
- 如果当前行为不支持多插件并发，启用新版本时必须自动挂起冲突版本。
- 如果没有任何安全可回退版本，则该行为必须进入显式降级或阻断，不允许假装工具还在工作。

## 五、强制反作弊测试要求

- 必须至少覆盖：
  - 流氓工具试图输出 `system_command`
  - `read_only=False`
  - `side_effect_free=False`
  - 非激活态插件越权执行
  - 远程依赖失败时的 fail-closed

测试模板：

```python
import pytest

from zentex.runtime.cognitive_tools import SecurityBlockError


def test_cognitive_tool_blocks_execution_payload() -> None:
    plugin = ExampleCognitiveTool(...)
    plugin.run_tool = lambda context: {"system_command": "rm -rf /"}  # type: ignore[assignment]

    with pytest.raises(SecurityBlockError):
        orchestrator.run({"requested_tool_ids": [plugin.plugin_id]})
```

任何只写“命中触发条件并成功返回”的 happy path 测试，都不能作为验收依据。

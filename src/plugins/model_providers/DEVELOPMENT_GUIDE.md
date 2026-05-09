# Model Provider 插件开发指南

本指南适用于 `src/plugins/model_providers/` 下的所有大模型底座插件。该家族直接决定主脑在关键认知阶段是否能够进行真实推断，因此必须执行最严格的 fail-closed 与审计留痕规范。

## 一、核心契约与继承底座

- 所有新插件必须最终继承 [BasePluginSpec](../../zentex/core/plugin_base.py)，并直接实现 [ModelProviderSpec](../../zentex/core/model_provider_spec.py)。
- 插件物理代码必须放在 `src/plugins/model_providers/` 下。
- 必须实现的核心方法：
  - `generate_json(prompt, context, caller_context) -> dict[str, Any]`
  - `health_probe() -> PluginHealthProbeResult | dict[str, Any]`
- 必须声明并正确维护的关键字段：
  - `version`
  - `is_concurrency_safe`
  - `rollback_conditions`
  - `status`
  - `health_status`

最小骨架示例：

```python
from __future__ import annotations

from typing import Any

from zentex.core.model_provider_spec import (
    ModelProviderCallerContext,
    ModelProviderSpec,
)


class ExampleProvider(ModelProviderSpec):
    """示例模型提供商插件。"""

    def generate_json(
        self,
        prompt: str,
        context: dict[str, Any],
        caller_context: ModelProviderCallerContext,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def health_probe(self) -> dict[str, Any]:
        raise NotImplementedError
```

## 二、专属架构红线与边界

- `[LLM MANDATORY]`：此类插件服务于真正的大模型推断，绝对禁止用本地规则、静态文本、空字典或默认 JSON 冒充模型结果。
- 绝对禁止把内部系统代号、下划线字段名、错误枚举直接拼进 prompt。发起调用前必须先做语义翻译。
- 绝对禁止在 `generate_json()` 内部触发执行域或任何外部副作用行为。模型提供商只负责推断，不负责操作世界。
- 当请求来源缺失 `caller_context`、调用方阶段不明或上下文不完整时，必须显式拒绝，不允许产生“无来源模型调用”。

## 三、健康探针与失败隔离

- 插件内部必须显式捕获：
  - 缺 Key / 配置错误
  - 鉴权失败
  - 超时
  - 429 限流
  - 非法 JSON / 空结果
- 插件层必须把这些异常转成结构化异常后向上抛出，不能让主脑收到模糊的裸异常。
- `health_probe()` 必须反映真实在线状态与限流状态，不能永远返回健康。

示例：

```python
from zentex.core.model_provider_spec import (
    ModelProviderAuthError,
    ModelProviderParseError,
    ModelProviderRateLimitError,
    ModelProviderRemoteError,
    ModelProviderTimeoutError,
)


def generate_json(... ) -> dict[str, Any]:
    try:
        response = self._do_http_request(...)
    except TimeoutError as exc:
        raise ModelProviderTimeoutError("model request timed out") from exc
    except PermissionError as exc:
        raise ModelProviderAuthError("model auth failed") from exc

    if response.status_code == 429:
        raise ModelProviderRateLimitError("provider rate limited")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ModelProviderParseError("provider returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise ModelProviderRemoteError("provider returned unexpected payload")
    return payload
```

## 四、触发回滚的判定条件

以下情况必须触发 `rollback_conditions` 对应的撤销或回退：

- 连续鉴权失败，说明当前版本的凭据或接入方式已失效
- 连续超时或远程 5xx，说明当前版本的服务稳定性不可接受
- 返回非法 JSON 或关键字段缺失，说明当前版本已不满足契约
- 健康探针长期处于 `degraded` / `unhealthy`

默认兜底说明：

- 大模型插件没有“规则链兜底”资格。
- 唯一合法回退是：切回上一个经过审计的稳定模型插件，或切回系统默认的正式版模型插件。
- 如果没有任何激活态模型插件，主脑必须 fail-closed 中断，而不是假装模型成功。

## 五、强制反作弊测试要求

- 严禁只写 happy path。
- 必须至少覆盖：
  - 缺 API Key
  - 429 限流
  - 超时
  - 非法 JSON
  - 未传 `caller_context`
- 必须断言：失败时抛结构化异常，而不是返回默认文本或空结果。

测试模板：

```python
from unittest import mock

import pytest

from zentex.core.model_provider_spec import (
    ModelProviderCallerContext,
    ModelProviderRateLimitError,
)


def test_provider_fail_closed_when_rate_limited() -> None:
    plugin = ExampleProvider(...)
    with mock.patch.object(plugin, "_do_http_request") as patched:
        patched.return_value.status_code = 429
        patched.return_value.json.return_value = {"error": "rate limit"}

        with pytest.raises(ModelProviderRateLimitError):
            plugin.generate_json(
                prompt="test",
                context={"user_message": "hello"},
                caller_context=ModelProviderCallerContext(
                    source_module="Main reasoning loop",
                    invocation_phase="framing the situation",
                    question_driver_refs=["我是谁"],
                    decision_id="decision-1",
                ),
            )
```

违反以上任一规则的实现，不允许进入 `sandbox_verified`，更不允许晋升为 `active`。

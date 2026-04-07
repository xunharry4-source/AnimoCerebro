# 统一被测试对象接入文档

## 1. 目标

本文档定义 Zentex 如何接入一个“测试 Agent”。

接入目标只有一个：

- 让每个被测试对象都以统一的测试 Agent 形态接入，而不是让每个项目自己随意写测试入口。

统一流程固定为 4 步：

1. 测试 Agent 读取被测试对象信息
2. 测试 Agent 在 `run()` 内部调用 `TestableUtils` 节点生成 3 条测试数据
3. 测试 Agent 把测试输入传给 `target.executeTest(input)` 执行真实逻辑
4. 测试 Agent 在 `run()` 内部调用 `TestableUtils` 节点判定是否通过，并返回唯一合法测试结果

## 2. 接入位置

当前统一测试接口定义在：

- [src/zentex/testing/contract.py](/Users/harry/Documents/git/zentex/src/zentex/testing/contract.py)

公共导出在：

- [src/zentex/testing/__init__.py](/Users/harry/Documents/git/zentex/src/zentex/testing/__init__.py)

## 2.1 强制说明

以下两个文件属于稳定测试边界，默认禁止修改：

- [src/zentex/testing/contract.py](/Users/harry/Documents/git/zentex/src/zentex/testing/contract.py)
- [src/zentex/testing/testable_utils.py](/Users/harry/Documents/git/zentex/src/zentex/testing/testable_utils.py)

硬规则：

- 未经明确架构批准，禁止修改这两个文件的职责边界
- 未经明确架构批准，禁止修改 `TestableTarget` 的对外方法定义
- 未经明确架构批准，禁止修改 `TestableTarget.run()` 的主流程定义
- 未经明确架构批准，禁止修改 `TestableUtils` 的主流程定义
- 业务测试文件禁止直接调用 `TestableUtils`
- 业务测试结果只能以 `target.run()` 返回结果为准
- `TestableTarget` 的每个实现类都是一个测试 Agent
- `TestableUtils` 只是测试 Agent 内部节点，不是 Agent 本体
- 新需求优先通过新增目标实现类或新增文档说明解决，不允许直接破坏这两个文件的稳定边界

## 3. 必须实现的接口

所有被测试对象都必须通过实现 `TestableTarget` 的方式接入。每个实现类就是一个测试 Agent。

```python
class TestableTarget(ABC):
    @abstractmethod
    def getTargetMeta(self) -> TargetMeta:
        raise NotImplementedError

    @abstractmethod
    def executeTest(self, input: TestInput) -> TargetExecutionResult:
        raise NotImplementedError

    def run(self, *, run_id: str = "run-1") -> TestRunnerReport:
        ...
```

## 4. 各方法职责

### 4.1 `getTargetMeta()`

作用：

- 返回测试 Agent 所绑定被测试功能的唯一标识
- 返回当前被测试功能说明
- 返回功能类型
- 返回测试数据说明
- 返回测试数据 JSON 格式要求
- 返回被测试功能返回说明
- 返回被测试功能返回数据 JSON 格式说明
- 返回验证方法说明

返回对象：`TargetMeta`

字段：

- `id`
  中文：被测试功能唯一标识。
  English: Unique identifier of the tested feature.
- `feature_description`
  中文：当前被测试功能说明，告诉测试系统“现在到底在测什么”。
  English: Human-readable description of the feature being tested.
- `feature_type`
  中文：功能类型，例如 `service`、`api`、`page`、`node`。
  English: Feature type such as `service`, `api`, `page`, or `node`.
- `test_data_description`
  中文：测试数据说明，告诉 LLM 应该生成什么测试数据、为什么要生成这些数据、受什么约束。
  English: Describes what test data the LLM should generate, why it is needed, and which constraints apply.
  中文补充：生成测试例子时，LLM 会同时参考 `test_data_description` 和 `test_data_json_format`；前者负责说明生成目标与约束，后者负责规定生成结果的 JSON 格式。
  English note: During test case generation, the LLM uses `test_data_description` together with `test_data_json_format`; the former defines generation intent and constraints, while the latter defines the JSON structure.
- `test_data_json_format`
  中文：被测试功能接收的测试参数 JSON 格式，定义传给被测试功能的输入必须长什么样。
  English: Defines the JSON format of the test parameters accepted by the tested feature.
  中文补充：内容里必须带字段说明，明确每个字段的功能是干嘛的，并给例子，例如“这个字段是案件ID”“这个字段是任务说明”。
  中文强调：测试系统生成测试数据时，会直接按照这里的功能说明与字段示例来生成；所以这里必须写得清楚、具体、可执行。
  English note: Test data generation directly follows the feature descriptions and field examples defined here, so this section must be clear, concrete, and actionable.
  English note: It must include field-level descriptions explaining what each field is for, with examples such as “this field is case ID” or “this field is task description”.
- `output_description`
  中文：被测试功能返回说明，告诉测试系统返回结果代表什么、哪些返回值最关键。
  English: Explains what the feature returns and which returned values matter most.
- `output_json_format`
  中文：被测试功能输出的 JSON 格式说明，定义真实返回结果必须长什么样。
  English: Defines the JSON format of the output produced by the tested feature.
  中文补充：内容里必须带字段说明，明确每个输出字段代表什么，并给例子。
  中文强调：测试系统验证结果时，会直接按照这里的字段说明与字段示例判断输出是否正确；所以这里必须写得清楚、具体、可执行。
  English note: Result validation directly follows the field descriptions and examples defined here, so this section must be clear, concrete, and actionable.
  English note: It must include field-level descriptions explaining what each output field means, with examples.
- `validation_description`
  中文：验证方法说明，告诉测试系统怎么判断通过或失败。
  English: Explains how the test result should be judged as pass or fail.
  中文补充：这是验证规则本体。LLM 会根据测试例子的数据和 `output_json_format` 定义的返回数据进行比较，比较规则和最终判定直接来自这里。
  中文强调：这里必须写得清楚、详细、可执行，否则结果判定会失真。
  English note: This is the actual verdict rule set. The LLM compares the test case data with the returned data defined by `output_json_format`, and both comparison logic and final judgment come directly from this section.
  English note: This section must be clear, detailed, and actionable, otherwise verdict quality will drift.
- `llm_config`
  中文：测试 Agent 在 `run()` 内部调用真实 LLM 节点时使用的配置。
  English: Runtime LLM configuration used internally by `run()`.
- `case_store_path`
  中文：测试例子保存位置；CSV 一行一个 JSON 测试例子。
  English: Storage path for generated test cases; one JSON case per CSV row.

硬规则：

- `getTargetMeta()` 禁止只返回方法名
- `getTargetMeta()` 禁止只返回空壳 schema
- `getTargetMeta()` 禁止缺少 `feature_description / feature_type / test_data_description / test_data_json_format / output_description / output_json_format / validation_description`
- `getTargetMeta()` 禁止只写“会生成 JSON”这种空描述
- `test_data_json_format` 必须明确说明：
  - 顶层 JSON 类型
  - 顶层字段
  - 每个字段的类型
  - 每个字段的数据要求
  - 每个字段的功能说明
  - 每个字段的示例
- `output_json_format` 必须明确说明：
  - 顶层 JSON 类型
  - 顶层字段
  - 每个字段的类型
  - 每个字段的数据要求
  - 每个字段的功能说明
  - 每个字段的示例
- 如果缺少上述字段，`TestableUtils` 必须直接判测试失败，并返回 `invalid_getTargetMeta` 错误信息

示例：

```json
{
  "id": "order-service",
  "feature_description": "验证订单服务是否按输入场景返回正确 accepted 状态",
  "feature_type": "service",
  "test_data_description": {
    "summary": "生成订单服务测试输入，覆盖正常、异常、特殊场景",
    "current_resources": {
      "workspace": "/abs/path/to/workspace",
      "files": ["src/order.py", "tests/test_order.py"]
    },
    "rules": [
      "必须覆盖 正常/异常/特殊 三类输入",
      "禁止使用样例直接生成测试数据"
    ]
  },
  "test_data_json_format": {
    "top_level_type": "object",
    "top_level_fields": ["case_id", "case_type", "name", "payload", "expectation"],
    "field_spec": {
      "case_id": {
        "type": "string",
        "required": true,
        "rules": ["不能为空", "每条测试数据唯一"]
      },
      "case_type": {
        "type": "string",
        "required": true,
        "rules": ["只能是 正常/异常/特殊 之一"]
      },
      "name": {
        "type": "string",
        "required": true,
        "rules": ["不能为空", "必须能概括当前测试意图"]
      },
      "payload": {
        "type": "object",
        "required": true,
        "rules": ["必须符合目标输入要求", "必须是本次真实执行输入"]
      },
      "expectation": {
        "type": "object",
        "required": true,
        "rules": ["必须包含 summary/must_observe/must_not_observe"]
      }
    }
  },
  "output_description": {
    "summary": "订单服务返回 accepted 及错误信息"
  },
  "output_json_format": {
    "top_level_type": "object",
    "top_level_fields": ["accepted", "error_code"],
    "field_spec": {
      "accepted": {
        "type": "boolean",
        "required": true,
        "rules": ["标识本次请求是否被接受"]
      },
      "error_code": {
        "type": "string",
        "required": false,
        "rules": ["失败时给出错误码"]
      }
    }
  },
  "validation_description": {
    "how_to_validate": [
      "检查 accepted 字段",
      "检查输出是否符合输入场景"
    ],
    "pass_rules": ["3/3 全过才算通过"],
    "failure_rules": ["任意 1 条失败则整轮失败"]
  },
  "llm_config": {
    "config_path": "/abs/path/to/live-config.yaml"
  },
  "case_store_path": "/abs/path/to/.zentex/testable_cases/order-service.csv"
}
```

### 4.2 `executeTest(input)`

作用：

- 使用测试 Agent 在 `run()` 内部生成的测试输入执行真实逻辑
- 返回真实执行结果

返回对象：`TargetExecutionResult`

字段：

- `run_id`
- `case_id`
- `status`
- `output`
- `message`
- `logs`
- `side_effects`

示例：

```json
{
  "run_id": "run-order-service-0",
  "case_id": "CASE-EXCEPTION-001",
  "status": "passed",
  "output": {
    "accepted": false,
    "error_code": "invalid_quantity"
  },
  "message": "validation blocked",
  "logs": [],
  "side_effects": {
    "order_created": false
  }
}
```

### 4.3 `run()`

作用：

- 固定触发当前测试 Agent 的完整测试流程
- 内部顺序固定为：
  1. `getTargetMeta()`
  2. `TestableUtils` 根据轮测规则生成测试数据并保存到 CSV
  3. `executeTest(input)`
  4. `TestableUtils.judge_test_result(...)`
- 这是唯一合法测试入口

轮测硬规则：

- 首轮固定生成 3 个测试数据：
  - 1 个正常
  - 1 个异常
  - 1 个特殊
- 这 3 个里只要 1 个失败，整轮失败
- 如果上一轮失败，下一轮规则是：
  - LLM 新生成 1 个测试数据
  - 从历史已保存测试数据里随机取 2 个
  - 一共再跑 3 个
- 历史测试例子保存为 CSV；一行就是一个 JSON 测试例子

硬规则：

- 每个 `TestableTarget` 实现类就是一个测试 Agent
- 业务测试文件只能调用 `target.run()`
- 业务测试文件禁止直接调用 `TestableUtils`
- 子类禁止重写 `run()`
- 测试是否通过，只能看 `run()` 的返回结果

返回对象：`TestRunnerReport`

字段：

- `target`
- `summary`
- `cases`
- `executed_at`
- `case_id`
- `records`

`records` 中每条证据至少有：

- `type`
- `content`

示例：

```json
{
  "run_id": "run-order-service-0",
  "case_id": "CASE-NORMAL-001",
  "records": [
    {
      "type": "response",
      "content": {
        "http_status": 201
      }
    },
    {
      "type": "db_snapshot",
      "content": {
        "order_id": "order-001"
      }
    }
  ]
}
```

## 5. 测试平台如何调用

测试平台统一使用：

- `StandardTestRunner`
- `AdaptiveTestRunner`

### 5.1 标准执行器

适用场景：

- 测试数据已明确写在 `case.input_overrides`
- 不需要 LLM 生成输入

调用方式：

```python
from zentex.testing import StandardTestRunner

report = StandardTestRunner(run_id_prefix="local").run(target)
```

### 5.2 LLM 轮测执行器

适用场景：

- 测试数据必须由 LLM 根据“目标/参数要求/历史失败”动态生成

调用方式：

```python
from zentex.testing import AdaptiveTestRunner, LLMTestCaseGenerator

runner = AdaptiveTestRunner(
    run_id_prefix="adaptive",
    random_seed=7,
    generator=LLMTestCaseGenerator(client),
)
report = runner.run_with_persistence(target, "artifacts/test_cases.json")
```

## 6. LLM 轮测规则

### 6.1 首轮执行

首轮没有历史案例时：

- LLM 必须生成 3 个测试输入
- 这 3 个输入必须覆盖：
  - 1 个正常
  - 1 个异常
  - 1 个特殊
- 平台会把这 3 个输入保存到持久化文件

### 6.2 后续执行

如果上一轮全部通过：

- 平台复用历史样例池随机抽 3 个继续回归

如果上一轮 3 个中有任意 1 个失败：

- 整轮判定为失败
- 下一轮 LLM 只生成 1 个新输入
- 平台再从历史样例池随机抽 2 个旧输入
- 新输入 + 2 个旧输入共同构成下一轮 3 个测试

### 6.3 通过判定

硬规则：

- 每轮固定执行 3 个测试
- 只有 `3/3` 全部通过，整轮才算通过
- 只要 1 个失败，整轮就是失败

汇总字段：

- `all_three_passed`
- `delivery_ready`

这两个字段只有在 3 个测试全部通过时才为 `true`

## 7. 被测试对象最小接入示例

```python
from zentex.testing import (
    EvidenceBundle,
    EvidenceRecord,
    ParameterRequirement,
    RollbackResult,
    TargetExecutionResult,
    TargetMeta,
    TestCaseDefinition,
    TestContract,
    TestInput,
    TestableTarget,
    ValidationResult,
)


class OrderTarget(TestableTarget):
    def __init__(self) -> None:
        self._evidence = {}

    def getTargetMeta(self) -> TargetMeta:
        return TargetMeta(id="order-service", name="Order Service", type="service")

    def getTestSpec(self) -> TestContract:
        return TestContract(
            target=self.getTargetMeta(),
            test_description={"摘要": "订单服务测试"},
            parameter_requirements=[
                ParameterRequirement(
                    name="user_id",
                    type="string",
                    required=True,
                    description="下单用户",
                    rules=["不能为空"],
                    invalid_rules=["空字符串"],
                    special_rules=["风险用户"],
                ),
                ParameterRequirement(
                    name="quantity",
                    type="number",
                    required=True,
                    description="购买数量",
                    rules=["必须大于0"],
                    invalid_rules=["0", "-1"],
                    special_rules=["99"],
                ),
            ],
            goals={
                "功能目标": ["有效输入时创建订单"],
                "稳定性目标": ["无效输入时拦截"],
                "验证目标": ["边界输入时结果仍符合输入场景"],
            },
            cases=[
                TestCaseDefinition(
                    case_id="CASE-NORMAL-001",
                    name="正常下单",
                    case_type="正常",
                    description="有效输入创建订单",
                ),
                TestCaseDefinition(
                    case_id="CASE-EXCEPTION-001",
                    name="非法输入",
                    case_type="异常",
                    description="非法输入必须拦截",
                ),
                TestCaseDefinition(
                    case_id="CASE-SPECIAL-001",
                    name="边界输入",
                    case_type="特殊",
                    description="高风险输入进入人工复核",
                ),
            ],
        )

    def validateTestInput(self, input: TestInput) -> ValidationResult:
        errors = []
        if "user_id" not in input.payload:
            errors.append("user_id missing")
        if "quantity" not in input.payload:
            errors.append("quantity missing")
        return ValidationResult(valid=not errors, errors=errors)

    def executeTest(self, input: TestInput) -> TargetExecutionResult:
        quantity = int(input.payload["quantity"])
        user_id = str(input.payload["user_id"])
        if quantity <= 0 or not user_id:
            self._evidence[input.case_id] = [EvidenceRecord(type="response", content={"http_status": 422})]
            return TargetExecutionResult(
                run_id=input.run_id,
                case_id=input.case_id,
                status="passed",
                output={"accepted": False},
            )
        self._evidence[input.case_id] = [EvidenceRecord(type="response", content={"http_status": 201})]
        return TargetExecutionResult(
            run_id=input.run_id,
            case_id=input.case_id,
            status="passed",
            output={"accepted": True},
        )

    def collectEvidence(self, run_id: str, case_id: str) -> EvidenceBundle:
        return EvidenceBundle(run_id=run_id, case_id=case_id, records=self._evidence.get(case_id, []))

```

## 8. 接入检查清单

接入一个新的被测试对象前，必须确认：

- 已实现 `TestableTarget`
- `getTargetMeta()` 返回唯一 `id`
- `getTestSpec()` 包含 `被测试对象/测试说明/参数要求/目标/用例`
- `validateTestInput()` 会拦截非法输入
- `executeTest()` 执行真实逻辑，不是假成功
- `collectEvidence()` 返回真实证据
- 如果使用 LLM 轮测，已经接入 `LLMTestCaseGenerator`

## 9. 当前验证

当前接入文档对应的测试文件：

- [tests/core_logic/testing/test_standard_test_runner.py](/Users/harry/Documents/git/zentex/tests/core_logic/testing/test_standard_test_runner.py)
- [tests/core_logic/testing/test_adaptive_llm_runner.py](/Users/harry/Documents/git/zentex/tests/core_logic/testing/test_adaptive_llm_runner.py)

验证命令：

```bash
.venv/bin/python -m pytest -q tests/core_logic/testing/test_standard_test_runner.py tests/core_logic/testing/test_adaptive_llm_runner.py
```

最近一次验证结果：

- `7 passed`

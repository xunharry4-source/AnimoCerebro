# Plugin ID Constants

本模块集中管理所有认知插件的 `plugin_id` 常量，避免在代码中使用硬编码的字符串。

## 📁 文件位置

```
src/zentex/common/plugin_ids.py
```

## 🎯 设计目标

1. **统一管理**: 所有认知插件的 ID 集中在一个地方
2. **类型安全**: 使用常量而非字符串字面量，减少拼写错误
3. **易于维护**: 修改 plugin_id 时只需更新一处
4. **提供工具函数**: 辅助判断插件类型和分类

## 📦 可用的常量

### 九个问题插件 (Nine Questions)

```python
from zentex.common.plugin_ids import (
    NINE_QUESTION_Q1,  # "nine-question-q1-where-am-i"
    NINE_QUESTION_Q2,  # "nine-question-q2-asset-inventory"
    NINE_QUESTION_Q3,  # "nine-question-q3-who-am-i"
    NINE_QUESTION_Q4,  # "nine-question-q4-what-can-i-do"
    NINE_QUESTION_Q5,  # "nine-question-q5-what-am-i-allowed-to-do"
    NINE_QUESTION_Q6,  # "nine-question-q6-what-should-i-not-do"
    NINE_QUESTION_Q7,  # "nine_question_q7_alternatives"
    NINE_QUESTION_Q8,  # "nine_question_q8_decision"
    NINE_QUESTION_Q9,  # "nine_question_q9_posture"
)
```

### 认知分析插件 (Cognitive Analysis)

```python
from zentex.common.plugin_ids import (
    COGNITIVE_BUDGET_CONFLICT,        # "cognitive_budget_conflict"
    COGNITIVE_EXPIRED_ASSUMPTION,     # "cognitive_expired_assumption"
    COGNITIVE_FAILURE_CLUSTER,        # "cognitive_failure_cluster"
    COGNITIVE_SEMANTIC_CONFLICT,      # "cognitive_semantic_conflict"
)
```

### 记忆插件 (Memory)

```python
from zentex.common.plugin_ids import (
    MEMORY_EXTRACTOR,  # "memory_extractor"
)
```

### Oracle 插件 (Functional Layer)

```python
from zentex.common.plugin_ids import (
    ORACLE_ALTERNATIVE,  # "oracle_alternative"
    ORACLE_OBJECTIVE,    # "oracle_objective"
    ORACLE_POSTURE,      # "oracle_posture"
    ORACLE_REDLINE,      # "oracle_redline"
)
```

### 反思插件 (Reflection)

```python
from zentex.common.plugin_ids import (
    REFLECTION_GENERATOR,  # "reflection_generator"
)
```

## 🔧 工具函数

### 判断插件类型

```python
from zentex.common.plugin_ids import (
    is_cognitive_plugin,
    is_nine_question_plugin,
    get_nine_question_number,
    get_plugin_category,
)

# 检查是否为认知层插件
is_cognitive_plugin(NINE_QUESTION_Q1)  # True
is_cognitive_plugin(ORACLE_ALTERNATIVE)  # False (functional)

# 检查是否为九个问题插件
is_nine_question_plugin(NINE_QUESTION_Q1)  # True
is_nine_question_plugin(MEMORY_EXTRACTOR)  # False

# 获取问题编号
get_nine_question_number(NINE_QUESTION_Q1)  # 1
get_nine_question_number(NINE_QUESTION_Q5)  # 5
get_nine_question_number(MEMORY_EXTRACTOR)  # None

# 获取插件分类
get_plugin_category(NINE_QUESTION_Q1)  # "cognitive"
get_plugin_category(ORACLE_ALTERNATIVE)  # "functional"
```

### 插件列表

```python
from zentex.common.plugin_ids import (
    NINE_QUESTIONS_ALL,
    COGNITIVE_ANALYSIS_PLUGINS,
    MEMORY_PLUGINS,
    ORACLE_PLUGINS,
    REFLECTION_PLUGINS,
    ALL_COGNITIVE_PLUGINS,
)

# 遍历所有九个问题插件
for qid in NINE_QUESTIONS_ALL:
    print(qid)

# 检查插件是否在认知层列表中
if plugin_id in ALL_COGNITIVE_PLUGINS:
    # 处理认知插件
    pass
```

## 💡 使用示例

### 示例 1: 在插件服务中使用

```python
from zentex.common.plugin_ids import NINE_QUESTION_Q1

# ❌ 旧的写法（硬编码）
plugin = service.get_plugin("nine-question-q1-where-am-i")

# ✅ 新的写法（使用常量）
plugin = service.get_plugin(NINE_QUESTION_Q1)
```

### 示例 2: 批量操作九个问题插件

```python
from zentex.common.plugin_ids import NINE_QUESTIONS_ALL

# 检查所有九个问题插件的状态
for qid in NINE_QUESTIONS_ALL:
    status = service.get_plugin_status(qid)
    print(f"{qid}: {status}")
```

### 示例 3: 条件判断

```python
from zentex.common.plugin_ids import is_nine_question_plugin, get_nine_question_number

def handle_plugin_event(plugin_id: str):
    if is_nine_question_plugin(plugin_id):
        q_num = get_nine_question_number(plugin_id)
        print(f"处理第 {q_num} 个问题的事件")
    else:
        print(f"处理其他插件事件")
```

### 示例 4: 懒加载导入

```python
# 从 zentex.common 直接导入（懒加载）
from zentex.common import NINE_QUESTION_Q1, COGNITIVE_BUDGET_CONFLICT

print(NINE_QUESTION_Q1)  # "nine-question-q1-where-am-i"
```

## 🔄 迁移指南

如果你的代码中有硬编码的 plugin_id，可以按以下步骤迁移：

### 步骤 1: 识别硬编码字符串

```bash
# 搜索硬编码的 plugin_id
grep -r "nine-question-q1-where-am-i" src/
grep -r "cognitive_budget_conflict" src/
```

### 步骤 2: 添加导入

```python
from zentex.common.plugin_ids import (
    NINE_QUESTION_Q1,
    COGNITIVE_BUDGET_CONFLICT,
    # ... 其他需要的常量
)
```

### 步骤 3: 替换字符串

```python
# 之前
plugin_id = "nine-question-q1-where-am-i"

# 之后
plugin_id = NINE_QUESTION_Q1
```

## ⚠️ 注意事项

1. **不要修改常量值**: 这些常量应该与插件实现中的 `plugin_id` 保持一致
2. **Oracle 插件是 functional 层**: 虽然名字里有 "oracle"，但它们属于 functional 层而非 cognitive 层
3. **版本升级不影响 plugin_id**: 插件版本升级时，`plugin_id` 保持不变，只有 `version` 字段变化
4. **别名支持**: 系统通过 `plugin_ids.py` 中的 `LEGACY_PLUGIN_ID_ALIASES` 支持旧格式的别名

## 📝 添加新插件

如果需要添加新的认知插件常量：

1. 在 `plugin_ids.py` 中添加常量定义
2. 添加到相应的列表（如 `NINE_QUESTIONS_ALL`）
3. 更新 `PLUGIN_CATEGORY_MAP`
4. 在 `__init__.py` 中导出新常量
5. 更新本文档

## 🧪 测试

运行测试验证常量是否正确：

```bash
cd <repo-root>
PYTHONPATH=src:$PYTHONPATH python tests/common/test_plugin_ids.py
```

## 🔗 相关文件

- `src/zentex/common/plugin_ids.py` - 常量定义
- `src/zentex/common/__init__.py` - 导出配置
- `src/zentex/plugins/plugin_ids.py` - 别名映射和规范化
- `tests/common/test_plugin_ids.py` - 单元测试

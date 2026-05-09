# Service层重构计划 - 反思模块

## 🚨 当前问题

`src/zentex/reflection/service.py` (1016行) 包含了大量业务逻辑，违反了Service层职责分离原则。

### 违反的规范

**Development Practice: Service层职责与逻辑分离规范**
> - Service层只提供对外服务接口
> - 业务逻辑应放在专门模块
> - Service层只做编排和协调

### 当前service.py包含的业务逻辑

1. **反思内容生成逻辑** (~300行)
   - `_generate_decision_reflection()` 
   - `_generate_action_reflection()`
   - `_generate_outcome_reflection()`
   - `_generate_process_reflection()`
   - `_generate_strategy_reflection()`
   - `_generate_error_reflection()`
   - `_generate_success_reflection()`
   - `_generate_generic_reflection()`

2. **质量评估逻辑**
   - `_determine_reflection_depth()`
   - `_assess_reflection_quality()`

3. **数据同步逻辑**
   - `_sync_legacy_to_list()`
   - `_ensure_core_fixed_items()`
   - `_sync_list_to_legacy()`

4. **模板管理逻辑**
   - `_initialize_default_templates()`

5. **过滤逻辑**
   - `_matches_filters()`

## ✅ 正确的架构

```
zentex/reflection/
├── service.py              # Service层：仅服务编排 (~200行)
│   ├── ReflectionService
│   │   ├── generate_reflection()      # 编排调用
│   │   ├── get_reflection()           # 查询
│   │   ├── list_reflections()         # 列表
│   │   └── ...                        # 其他服务方法
│
├── llm_generator.py        # 业务逻辑：LLM驱动 (已有，397行)
│   └── LLMReflectionGenerator
│
├── rule_engine.py          # 业务逻辑：规则引擎 (新建，~300行)
│   └── RuleBasedReflectionEngine
│       └── 仅在tests/中使用
│
├── quality_assessor.py     # 业务逻辑：质量评估 (新建，~100行)
│   └── ReflectionQualityAssessor
│
├── data_sync.py            # 业务逻辑：数据同步 (新建，~150行)
│   └── ReflectionDataSync
│
└── template_manager.py     # 业务逻辑：模板管理 (新建，~100行)
    └── ReflectionTemplateManager
```

## 📋 重构步骤

### 步骤1：提取规则引擎（已完成✅）

已创建：`tests/reflection/rule_based_stub.py`

### 步骤2：创建质量评估器

```python
# src/zentex/reflection/quality_assessor.py
class ReflectionQualityAssessor:
    def determine_depth(self, context: Dict) -> ReflectionDepth:
        ...
    
    def assess_quality(self, content: Dict) -> ReflectionQuality:
        ...
```

### 步骤3：创建数据同步器

```python
# src/zentex/reflection/data_sync.py
class ReflectionDataSync:
    def sync_legacy_to_list(self, reflection: ReflectionRecord):
        ...
    
    def ensure_core_fixed_items(self, reflection: ReflectionRecord):
        ...
    
    def sync_list_to_legacy(self, reflection: ReflectionRecord):
        ...
```

### 步骤4：创建模板管理器

```python
# src/zentex/reflection/template_manager.py
class ReflectionTemplateManager:
    def initialize_default_templates(self):
        ...
    
    def get_template(self, template_id: str) -> ReflectionTemplate:
        ...
```

### 步骤5：精简service.py

删除所有私有业务逻辑方法，只保留：
- 公共API方法
- 依赖注入
- 服务编排逻辑

目标：从1016行减少到~200行

## 🎯 最终效果

### 重构前
```python
# service.py (1016行)
class ReflectionService:
    def generate_reflection(...):
        # 直接包含所有业务逻辑
        content = self._generate_decision_reflection(...)  # ❌ 业务逻辑在service
        depth = self._determine_reflection_depth(...)      # ❌ 业务逻辑在service
        ...
```

### 重构后
```python
# service.py (~200行)
class ReflectionService:
    def __init__(self):
        self._llm_generator = LLMReflectionGenerator()     # ✅ 依赖注入
        self._quality_assessor = ReflectionQualityAssessor()
        self._data_sync = ReflectionDataSync()
        self._template_mgr = ReflectionTemplateManager()
    
    def generate_reflection(...):
        # 仅做编排
        content = self._llm_generator.generate_reflection(...)  # ✅ 委托给专门模块
        depth = self._quality_assessor.determine_depth(...)     # ✅ 委托给专门模块
        reflection = self._create_record(...)
        self._data_sync.sync(reflection)                        # ✅ 委托给专门模块
        return reflection
```

## ⚠️ 注意事项

1. **保持向后兼容**：公共API不变
2. **逐步迁移**：一次一个模块
3. **充分测试**：每个模块迁移后运行测试
4. **文档更新**：更新所有相关文档

## 📊 预期收益

| 指标 | 重构前 | 重构后 | 改善 |
|------|--------|--------|------|
| service.py行数 | 1016 | ~200 | -80% |
| 业务逻辑集中度 | 分散 | 集中 | ✅ |
| 可测试性 | 低 | 高 | ✅ |
| 可维护性 | 低 | 高 | ✅ |
| 职责清晰度 | 模糊 | 清晰 | ✅ |

---

**状态**: 📝 计划阶段  
**优先级**: 高  
**预计工作量**: 2-3天

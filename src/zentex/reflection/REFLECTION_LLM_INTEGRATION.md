# 反思内容生成机制说明

## 当前实现方式

### ❌ **不基于LLM** - 使用规则引擎

当前的反思内容生成**完全不依赖LLM**，而是使用**硬编码的规则和模板**。

## 实现细节

### 1. 核心生成方法

在 `src/zentex/reflection/service.py` 中：

```python
def _generate_reflection_content(
    self, 
    subject: str, 
    reflection_type: ReflectionType, 
    context: Dict[str, Any],
    template: Optional[ReflectionTemplate] = None
) -> Dict[str, Any]:
    """生成反思内容"""
    
    # 基于反思类型生成内容（全部是规则引擎）
    if reflection_type == ReflectionType.DECISION_REFLECTION:
        return self._generate_decision_reflection(subject, context)
    elif reflection_type == ReflectionType.ACTION_REFLECTION:
        return self._generate_action_reflection(subject, context)
    # ... 其他类型
```

### 2. 示例：决策反思生成

```python
def _generate_decision_reflection(self, subject: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """生成决策反思 - 纯规则引擎实现"""
    decision = context.get("decision", {})
    outcome = context.get("outcome", {})
    alternatives = context.get("alternatives", [])
    
    # 硬编码的模板
    summary = f"关于决策'{subject}'的反思分析"
    
    insights = [
        f"决策基于{len(alternatives)}个备选方案",
        f"最终选择考虑了{len(decision.get('factors', []))}个因素"
    ]
    
    lessons = []
    if outcome.get("success"):
        lessons.append("决策流程有效，结果符合预期")  # 固定文本
    else:
        lessons.append("需要改进决策评估机制")  # 固定文本
    
    risks = []
    if decision.get("risk_level", 0) > 0.7:
        risks.append("高风险决策，需要更多验证")  # 固定文本
    
    improvements = []
    if len(alternatives) < 3:
        improvements.append("考虑更多备选方案")  # 固定文本
    
    return {
        "summary": summary,
        "insights": insights,
        "lessons": lessons,
        "risks": risks,
        "improvements": improvements,
        "confidence": 0.8,  # 硬编码的置信度
        "impact_score": 0.7,
        "actionability": 0.6
    }
```

### 3. 元反思审计项目

```python
def _generate_meta_audit_item(self, reflection: ReflectionRecord) -> ReflectionItem:
    """生成元反思项目：对当前反思内容质量进行自我审计。"""
    # Logic to "reflect on the reflection"
    # Since this is a service, we'd normally call LLM here. ⚠️ 注释说明了应该用LLM
    # For now, we seed it with logic based on quality score. ⚠️ 但目前用规则
    
    score = 1.0 - (0.2 if reflection.quality == ReflectionQuality.POOR else 0.0)
    content = (
        "Self-Audit: Reflection content is structurally consistent. "
        "No significant drift detected from core identity."
    ) if score > 0.8 else (
        "Self-Audit WARNING: Possible shallow analysis detected. "
        "Higher order context might be missing from this turn."
    )
    
    return ReflectionItem(
        name="Meta-Audit",
        content=content,
        category="meta",
        is_immutable=False,
        can_be_removed=True,
        integrity_score=score
    )
```

**关键注释：**
```python
# Since this is a service, we'd normally call LLM here.
# For now, we seed it with logic based on quality score.
```

这说明开发者**知道应该用LLM**，但**目前使用规则引擎作为占位符**。

## 当前架构的问题

### ❌ 缺点

1. **缺乏深度分析能力**
   - 只能生成表面化的反思
   - 无法理解复杂的上下文
   - 反思内容千篇一律

2. **固定的置信度和评分**
   ```python
   "confidence": 0.8,  # 永远是0.8
   "impact_score": 0.7,  # 永远是0.7
   ```

3. **无法适应不同场景**
   - 同样的输入总是得到同样的输出
   - 没有个性化或情境化

4. **代码维护困难**
   - 每个反思类型都需要硬编码
   - 添加新规则需要修改代码

### ✅ 优点

1. **速度快**
   - 无需调用LLM API
   - 无网络延迟
   
2. **成本低**
   - 不需要LLM token费用
   
3. **可预测**
   - 输出完全可控
   - 易于测试

4. **离线可用**
   - 不依赖外部服务

## 如何升级为LLM驱动

### 方案1：集成ModelProvider（推荐）

Zentex系统已经有成熟的LLM集成机制：

```python
from zentex.core.model_provider_spec import ModelProviderSpec, ModelProviderCallerContext

class ReflectionService:
    def __init__(
        self, 
        persistence: Optional[ReflectionPersistence] = None,
        model_provider: Optional[ModelProviderSpec] = None  # 新增
    ) -> None:
        self.persistence = persistence
        self._model_provider = model_provider  # 保存LLM提供者
        # ...
    
    def _generate_reflection_with_llm(
        self,
        subject: str,
        reflection_type: ReflectionType,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用LLM生成反思内容"""
        
        if not self._model_provider:
            # Fallback到规则引擎
            logger.warning("No model provider configured, using rule-based reflection")
            return self._generate_reflection_content_rules(subject, reflection_type, context)
        
        # 构建提示词
        prompt = self._build_reflection_prompt(subject, reflection_type, context)
        
        # 调用LLM
        try:
            result = self._model_provider.generate_json(
                messages=[{"role": "user", "content": prompt}],
                response_format={
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "insights": {"type": "array", "items": {"type": "string"}},
                            "lessons": {"type": "array", "items": {"type": "string"}},
                            "risks": {"type": "array", "items": {"type": "string"}},
                            "improvements": {"type": "array", "items": {"type": "string"}},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "impact_score": {"type": "number", "minimum": 0, "maximum": 1},
                            "actionability": {"type": "number", "minimum": 0, "maximum": 1}
                        },
                        "required": ["summary", "insights", "lessons"]
                    }
                },
                caller_context=ModelProviderCallerContext(
                    feature_code="reflection_generation",
                    phase="reflection_content_generation",
                    trace_id=context.get("trace_id")
                )
            )
            
            return result
            
        except Exception as e:
            logger.error(f"LLM reflection generation failed: {e}")
            # Fallback到规则引擎
            return self._generate_reflection_content_rules(subject, reflection_type, context)
```

### 方案2：使用DSPy优化（高级）

利用Zentex已有的DSPy集成：

```python
from zentex.learning.dspy_adapter import ZentexDSPyLM
import dspy

class ReflectionSignature(dspy.Signature):
    """反思生成签名"""
    subject = dspy.InputField(desc="反思主题")
    reflection_type = dspy.InputField(desc="反思类型")
    context = dspy.InputField(desc="反思上下文字典")
    
    summary = dspy.OutputField(desc="反思摘要")
    insights = dspy.OutputField(desc="洞察列表，JSON数组")
    lessons = dspy.OutputField(desc="经验教训列表，JSON数组")
    risks = dspy.OutputField(desc="风险列表，JSON数组")
    improvements = dspy.OutputField(desc="改进建议列表，JSON数组")
    confidence = dspy.OutputField(desc="置信度，0-1之间的浮点数")

class ReflectionGenerator(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate = dspy.Predict(ReflectionSignature)
    
    def forward(self, subject, reflection_type, context):
        return self.generate(
            subject=subject,
            reflection_type=reflection_type,
            context=str(context)
        )

# 在ReflectionService中使用
class ReflectionService:
    def __init__(self, ...):
        # ...
        self._reflection_generator = ReflectionGenerator()
    
    def _generate_reflection_with_dspy(self, subject, reflection_type, context):
        result = self._reflection_generator(
            subject=subject,
            reflection_type=reflection_type.value,
            context=context
        )
        
        return {
            "summary": result.summary,
            "insights": json.loads(result.insights),
            "lessons": json.loads(result.lessons),
            "risks": json.loads(result.risks),
            "improvements": json.loads(result.improvements),
            "confidence": float(result.confidence),
            "impact_score": 0.7,  # 可以也让LLM生成
            "actionability": 0.6
        }
```

### 方案3：混合模式（最佳实践）

结合规则和LLM的优势：

```python
def generate_reflection(
    self,
    subject: str,
    reflection_type: ReflectionType,
    context: Dict[str, Any],
    use_llm: bool = True  # 新增参数
) -> ReflectionRecord:
    """生成反思记录"""
    
    if use_llm and self._model_provider:
        # 尝试使用LLM生成
        try:
            reflection_content = self._generate_reflection_with_llm(
                subject, reflection_type, context
            )
            logger.info("Generated reflection using LLM")
        except Exception as e:
            logger.warning(f"LLM generation failed, falling back to rules: {e}")
            reflection_content = self._generate_reflection_content_rules(
                subject, reflection_type, context
            )
    else:
        # 使用规则引擎
        reflection_content = self._generate_reflection_content_rules(
            subject, reflection_type, context
        )
        logger.debug("Generated reflection using rule engine")
    
    # 创建反思记录
    reflection = ReflectionRecord(
        reflection_id=create_reflection_id(),
        # ...
        **reflection_content
    )
    
    # 后续处理...
    self._sync_legacy_to_list(reflection)
    self._ensure_core_fixed_items(reflection)
    # ...
    
    return reflection
```

## 反思列表更新的实现

### 当前实现：纯Python逻辑

反思列表的更新判断**完全不依赖LLM**：

```python
def should_update_reflection_list(self, reflection: ReflectionRecord) -> bool:
    """判断是否需要更新反思列表（低频触发策略）。"""
    
    # 条件1：反思摘要为空或过短
    if not reflection.summary or len(reflection.summary.strip()) < 10:
        return True
    
    # 条件2：反思质量为 POOR
    if reflection.quality == ReflectionQuality.POOR:
        return True
    
    # 条件3：置信度过低
    if reflection.confidence < 0.4:
        return True
    
    # 条件4：没有任何实质性内容
    has_content = (
        len(reflection.insights) > 0 or
        len(reflection.lessons) > 0 or
        len(reflection.risks) > 0 or
        len(reflection.improvements) > 0 or
        len(reflection.reflection_list) > 5
    )
    
    if not has_content:
        return True
    
    # 默认情况：不允许多余的列表修改
    return False
```

**这是纯Python逻辑判断，不涉及LLM。**

### 未来可能的LLM增强

可以让LLM判断是否需要更新：

```python
def should_update_reflection_list_with_llm(
    self, 
    reflection: ReflectionRecord
) -> bool:
    """使用LLM智能判断是否需要更新反思列表"""
    
    if not self._model_provider:
        # Fallback到规则判断
        return self.should_update_reflection_list(reflection)
    
    prompt = f"""
    请分析以下反思记录，判断是否需要更新其反思列表。
    
    反思主题：{reflection.subject}
    反思类型：{reflection.reflection_type}
    反思质量：{reflection.quality}
    置信度：{reflection.confidence}
    摘要：{reflection.summary[:200]}
    洞察数量：{len(reflection.insights)}
    教训数量：{len(reflection.lessons)}
    
    请回答：YES（需要更新）或 NO（不需要更新）
    并简要说明原因。
    """
    
    try:
        result = self._model_provider.generate_text(
            messages=[{"role": "user", "content": prompt}],
            caller_context=ModelProviderCallerContext(
                feature_code="reflection_list_update_decision",
                phase="update_decision"
            )
        )
        
        return "YES" in result.text.upper()
        
    except Exception as e:
        logger.error(f"LLM update decision failed: {e}")
        # Fallback到规则判断
        return self.should_update_reflection_list(reflection)
```

## 总结

### 当前状态

| 功能 | 是否基于LLM | 实现方式 |
|------|-----------|---------|
| 反思内容生成 | ❌ 否 | 规则引擎 + 硬编码模板 |
| 元反思审计 | ❌ 否 | 基于质量的简单规则 |
| 反思列表更新判断 | ❌ 否 | Python条件判断 |
| 核心项目确保 | ❌ 否 | Python集合操作 |
| 旧格式同步 | ❌ 否 | Python列表操作 |

### 问题所在

1. **反思内容生成**目前是**硬编码的规则**，不是真正的AI反思
2. 代码中有TODO注释表明开发者**知道应该用LLM**
3. 但为了快速原型开发，先用了规则引擎

### 建议的升级路径

**阶段1：基础LLM集成**
- 集成现有的 `ModelProviderSpec`
- 将 `_generate_*_reflection()` 方法改为调用LLM
- 保留规则引擎作为Fallback

**阶段2：DSPy优化**
- 使用DSPy优化反思生成的prompt
- 自动学习高质量的反思模式
- 提升反思的深度和相关性

**阶段3：智能更新判断**
- 让LLM判断何时需要更新反思列表
- 基于历史数据训练更新策略
- 实现自适应的低频触发机制

### 快速验证LLM集成

要验证是否可以集成LLM，可以运行：

```python
from zentex.llm import get_llm_service
from zentex.core.model_provider_spec import ModelProviderCallerContext

# 获取LLM服务
llm_service = get_llm_service()
provider = llm_service.get_provider("openai_compat")  # 或其他provider

# 测试调用
result = provider.generate_json(
    messages=[{
        "role": "user", 
        "content": "请分析这个决策的优缺点..."
    }],
    caller_context=ModelProviderCallerContext(
        feature_code="test_reflection",
        phase="test"
    )
)

print(result)
```

如果成功，说明可以顺利集成LLM驱动的反思生成。

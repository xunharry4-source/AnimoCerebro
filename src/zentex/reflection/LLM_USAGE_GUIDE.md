# LLM驱动的反思生成 - 使用指南

## 🎯 概述

反思模块现已升级为**LLM驱动**，能够生成深度、个性化的反思内容，而不是简单的规则模板。

## ✨ 核心特性

### 1. **深度分析能力**
- ✅ 基于具体上下文生成个性化洞察
- ✅ 结合行业经验和最佳实践
- ✅ 提供可操作的具体建议
- ✅ 真实评估置信度和影响力

### 2. **专业化提示词**
针对不同反思类型（决策、错误、成功等）提供专业化的分析指导：
- 决策反思：关注决策质量、风险评估、长期影响
- 错误反思：根因分析、影响评估、预防措施
- 成功反思：成功因素、可复制性、知识沉淀

### 3. **智能Fallback**
- 优先使用LLM生成
- LLM失败时自动回退到规则引擎
- 确保系统始终可用

## 🚀 快速开始

### 基础用法

```python
from zentex.reflection import ReflectionService
from zentex.reflection.models import ReflectionType

# 创建启用LLM的反思服务（默认就是True）
service = ReflectionService(use_llm=True)

# 生成决策反思
reflection = service.generate_reflection(
    subject="产品定价策略调整",
    reflection_type=ReflectionType.DECISION_REFLECTION,
    context={
        "decision": {
            "old_price": 100,
            "new_price": 120,
            "reason": "成本上涨",
            "risk_level": 0.7,
            "factors": ["成本控制", "市场竞争", "客户接受度"]
        },
        "outcome": {
            "success": True,
            "revenue_change": "+15%"
        },
        "alternatives": [
            {"option": "维持原价"},
            {"option": "小幅提价"},
            {"option": "分层定价"}
        ]
    }
)

# 查看LLM生成的深度反思
print(f"摘要: {reflection.summary}")
print(f"洞察: {reflection.insights}")
print(f"教训: {reflection.lessons}")
print(f"风险: {reflection.risks}")
print(f"改进: {reflection.improvements}")
print(f"置信度: {reflection.confidence:.2f}")
print(f"影响力: {reflection.impact_score:.2f}")
```

### 输出示例（LLM驱动 vs 规则引擎）

#### ❌ 规则引擎输出（旧版）
```json
{
  "summary": "关于决策'产品定价'的反思分析",
  "insights": [
    "决策基于3个备选方案",
    "最终选择考虑了4个因素"
  ],
  "lessons": ["决策流程有效，结果符合预期"],
  "risks": [],
  "improvements": [],
  "confidence": 0.8,
  "impact_score": 0.7
}
```

#### ✅ LLM驱动输出（新版）
```json
{
  "summary": "本次定价调整反映了成本压力与市场竞争的平衡考量，但可能忽略了客户价格敏感度的长期影响",
  "insights": [
    "提价20%虽然在短期内覆盖成本，但可能导致15-20%的客户流失",
    "竞争对手X在类似情况下选择了优化成本结构而非直接提价",
    "高价值客户对价格变化相对不敏感，但中低端客户可能转向替代品"
  ],
  "lessons": [
    "应该在提价前先进行小范围A/B测试验证市场反应",
    "可以考虑分层定价策略，为不同客户群体提供差异化方案"
  ],
  "risks": [
    "主要竞争对手可能在1-2个月内跟进降价策略",
    "社交媒体可能出现负面舆情，影响品牌形象"
  ],
  "improvements": [
    "建立动态定价模型，根据市场需求自动调整",
    "增加客户调研频率，实时监控价格敏感度变化"
  ],
  "confidence": 0.85,
  "impact_score": 0.92
}
```

## 🔧 配置选项

### 1. 启用/禁用LLM

```python
# 启用LLM（默认）
service = ReflectionService(use_llm=True)

# 禁用LLM，仅使用规则引擎
service = ReflectionService(use_llm=False)
```

### 2. 调整LLM参数

```python
service = ReflectionService(
    use_llm=True,
    llm_temperature=0.3,    # 温度：0-1，越低越确定
    llm_max_tokens=2048     # 最大token数
)
```

**参数说明：**
- `llm_temperature`: 
  - 0.0-0.3: 确定性高，适合技术分析
  - 0.3-0.7: 平衡创造性和准确性（推荐）
  - 0.7-1.0: 创造性高，适合头脑风暴

- `llm_max_tokens`:
  - 1024: 简短反思
  - 2048: 标准反思（推荐）
  - 4096: 深度反思

## 📊 不同反思类型的示例

### 1. 决策反思

```python
reflection = service.generate_reflection(
    subject="技术栈选型决策",
    reflection_type=ReflectionType.DECISION_REFLECTION,
    context={
        "decision": {
            "options": ["React", "Vue", "Angular"],
            "selected": "React",
            "criteria": ["性能", "生态", "团队熟悉度"],
            "risk_level": 0.4
        },
        "outcome": {"success": True},
        "alternatives": [...]
    }
)
```

**LLM会分析：**
- 选型的合理性
- 被忽略的因素
- 长期维护成本
- 团队学习曲线

### 2. 错误反思

```python
reflection = service.generate_reflection(
    subject="生产环境数据库宕机",
    reflection_type=ReflectionType.ERROR_REFLECTION,
    context={
        "error": {
            "type": "数据库连接池耗尽",
            "severity": "critical",
            "duration": "45分钟",
            "affected_users": 5000
        },
        "impact": {
            "revenue_loss": 100000,
            "customer_complaints": 500
        },
        "root_cause": "未设置连接超时"
    }
)
```

**LLM会分析：**
- 根本原因深度挖掘
- 系统性问题识别
- 监控盲点发现
- 具体预防措施

### 3. 成功反思

```python
reflection = service.generate_reflection(
    subject="用户增长突破100万",
    reflection_type=ReflectionType.SUCCESS_REFLECTION,
    context={
        "success": {
            "achievement": "用户数突破100万",
            "timeframe": "6个月",
            "key_metrics": {
                "monthly_growth": "18%",
                "retention_rate": "85%"
            }
        },
        "success_factors": [
            "产品体验优化",
            "精准营销",
            "口碑传播"
        ]
    }
)
```

**LLM会分析：**
- 关键成功因素识别
- 可复制性评估
- 运气vs能力的区分
- 经验标准化建议

## 🏗️ 架构设计

### 模块化设计

```
zentex/reflection/
├── llm_prompt.py         # ★ LLM 提问构建 & 内容预处理（唯一 prompt 出口）
├── llm_generator.py      # LLM 调用编排（委托提问给 llm_prompt.py）
├── service.py            # 对外服务接口（轻量）
├── models.py             # 数据模型
├── persistence.py        # 持久化层
└── ...
```

**设计原则：**
- ✅ `llm_prompt.py`: 唯一负责构建发给 LLM 的 prompt 字符串，以及预处理输入 context（截断、清理、序列化）
- ✅ `llm_generator.py`: 只做 LLM 调用编排和输出验证，不内联任何 prompt 字符串
- ✅ `service.py`: 仅提供服务编排，不包含业务逻辑
- ✅ 职责清晰，任何提问内容变更只改一个文件

**截断规则（由 `llm_prompt.py` 统一控制）：**
- context 整体 JSON 序列化上限：4000 字符
- 单个字段值上限：800 字符
- 反思主题（subject）上限：300 字符
- 嵌套层级超过 3 层时替换为长度说明占位文本

### 工作流程

```
用户调用 generate_reflection()
         ↓
service._generate_reflection_content()
         ↓
    是否启用LLM？
    ├─ Yes → LLMReflectionGenerator.generate_reflection()
    │          ↓
    │       llm_prompt.build_type_specific_guidance()   ← 专业指导段落
    │          ↓
    │       llm_prompt.build_reflection_prompt()        ← context 预处理 + prompt 组装
    │          ↓
    │       调用 LLM Service (generate_json)
    │          ↓
    │       验证和规范化输出 (_validate_and_normalize)
    │          ↓
    │       返回深度反思结果
    │
    └─ No/Fail → _generate_reflection_content_rules()
                 ↓
              规则引擎生成
                 ↓
              返回基础反思结果
```

## 🧪 测试

运行LLM反思测试：

```bash
cd <repo-root>
PYTHONPATH=src:$PYTHONPATH python tests/reflection/test_llm_reflection.py
```

测试覆盖：
- ✅ LLM服务初始化
- ✅ 决策反思生成
- ✅ 错误反思生成
- ✅ 成功反思生成
- ✅ Fallback机制
- ✅ 配置参数

## 💡 最佳实践

### 1. 提供丰富的上下文

```python
# ❌ 不好的做法：上下文不足
context = {"decision": {...}}

# ✅ 好的做法：提供完整上下文
context = {
    "decision": {
        "title": "...",
        "options": [...],
        "criteria": [...],
        "constraints": [...],
        "stakeholders": [...]
    },
    "outcome": {
        "success": True,
        "metrics": {...},
        "feedback": [...]
    },
    "alternatives": [...],
    "timeline": {...}
}
```

### 2. 选择合适的温度

```python
# 技术分析：低温度
service = ReflectionService(llm_temperature=0.2)

# 战略规划：中等温度
service = ReflectionService(llm_temperature=0.5)

# 创意 brainstorming：高温度
service = ReflectionService(llm_temperature=0.8)
```

### 3. 处理LLM失败

```python
try:
    reflection = service.generate_reflection(...)
    if reflection.confidence < 0.5:
        logger.warning("Low confidence reflection, consider manual review")
except Exception as e:
    logger.error(f"Reflection generation failed: {e}")
    # 系统会自动Fallback到规则引擎
```

## 📈 性能对比

| 指标 | 规则引擎 | LLM驱动 |
|------|---------|---------|
| 生成速度 | ⚡ 快 (<100ms) | 🐢 慢 (2-5s) |
| 内容深度 | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 个性化 | ❌ 无 | ✅ 强 |
| 置信度真实性 | ❌ 硬编码 | ✅ 真实评估 |
| 成本 | ✅ 免费 | 💰 LLM费用 |
| 可靠性 | ✅ 100% | ⚠️ 依赖网络 |

## 🎯 总结

LLM驱动的反思生成带来了质的飞跃：

1. ✅ **深度分析**：从表面统计到深度洞察
2. ✅ **个性化**：针对具体情境生成专属反思
3. ✅ **可操作性**：提供具体可行的改进建议
4. ✅ **真实评估**：置信度和评分基于实际分析
5. ✅ **可靠性**：智能Fallback确保系统可用性

**立即启用LLM驱动，让反思真正发挥AI的力量！**

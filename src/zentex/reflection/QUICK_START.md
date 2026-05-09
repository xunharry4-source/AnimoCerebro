# Zentex 反思模块 - 快速入门指南

## 5分钟快速开始

### 第1步：安装和导入

```python
from zentex.reflection import ReflectionManager
```

### 第2步：创建反思管理器

```python
# 基础配置
reflection_manager = ReflectionManager(
    storage_path="./my_reflections",     # 可选：存储路径
    enable_persistence=True,             # 可选：启用持久化
    backup_count=5                       # 可选：备份数量
)
```

### 第3步：获取统一接口

```python
# 获取标准化接口（推荐其他模块使用）
interface = reflection_manager.get_interface()
```

### 第4步：生成第一个反思

```python
# 生成决策反思
result = interface.generate_reflection({
    "subject": "技术选型决策",
    "reflection_type": "decision_reflection",
    "context": {
        "decision": {
            "factors": ["性能", "成本", "可维护性"],
            "risk_level": 0.6
        },
        "outcome": {
            "success": True,
            "achievement_rate": 0.85
        },
        "alternatives": [
            {"name": "方案A", "pros": ["高性能"], "cons": ["高成本"]},
            {"name": "方案B", "pros": ["低成本"], "cons": ["性能一般"]}
        ]
    }
})

if result["success"]:
    reflection_id = result["reflection"]["reflection_id"]
    print(f"✅ 反思生成成功: {reflection_id}")
else:
    print(f"❌ 生成失败: {result['error']}")
```

### 第5步：管理反思

```python
# 查看反思
reflection_info = interface.get_reflection(reflection_id)
print(f"反思主题: {reflection_info['reflection']['subject']}")
print(f"反思质量: {reflection_info['reflection']['quality']}")

# 验证反思
verify_result = interface.verify_reflection(reflection_id, "expert_user")
print(f"验证结果: {verify_result['success']}")

# 搜索相关反思
search_result = interface.search_reflections("技术选型")
print(f"找到 {search_result['count']} 个相关反思")
```

## 核心概念

### 反思类型

| 类型 | 说明 | 使用场景 |
|------|------|----------|
| `decision_reflection` | 决策反思 | 技术选型、架构决策、业务决策 |
| `action_reflection` | 行动反思 | 执行过程、操作步骤、行为模式 |
| `outcome_reflection` | 结果反思 | 项目结果、效果评估、成果分析 |
| `process_reflection` | 过程反思 | 工作流程、协作方式、管理过程 |
| `strategy_reflection` | 策略反思 | 战略规划、长期目标、发展方向 |
| `error_reflection` | 错误反思 | 故障分析、问题诊断、失败教训 |
| `success_reflection` | 成功反思 | 成功经验、最佳实践、复制模式 |

### 反思深度

```
surface → analytical → strategic → systemic
  ↓         ↓           ↓           ↓
表层反思 → 分析性反思 → 战略性反思 → 系统性反思
```

### 反思质量

- 🟢 **excellent**: 优秀 - 深度分析，丰富洞察，高可操作性
- 🔵 **good**: 良好 - 结构完整，有价值的洞察和教训
- 🟡 **fair**: 一般 - 基础分析，部分有价值的洞察
- 🔴 **poor**: 差 - 内容不足，分析肤浅

### 治理状态

- 🟢 **active**: 活跃 - 正常使用的反思
- ✅ **verified**: 已验证 - 经过专家验证的反思
- ⚠️ **suspect**: 可疑 - 数据或质量存疑的反思
- 📦 **archived**: 已归档 - 历史归档的反思
- 🚫 **deprecated**: 已废弃 - 不再使用的反思
- 👁️ **hidden**: 已隐藏 - 不对外显示的反思

## 常用操作

### 1. 生成不同类型的反思

```python
# 决策反思
decision_result = interface.generate_reflection({
    "subject": "数据库选型",
    "reflection_type": "decision_reflection",
    "context": {
        "decision": {
            "factors": ["性能", "成本", "扩展性"],
            "stakeholders": ["技术团队", "产品团队"]
        },
        "outcome": {"success": True, "performance_gain": 0.3}
    }
})

# 错误反思
error_result = interface.generate_reflection({
    "subject": "API响应超时",
    "reflection_type": "error_reflection",
    "context": {
        "error": {
            "type": "timeout",
            "root_cause": "数据库连接池耗尽"
        },
        "impact": {
            "severity": "medium",
            "affected_users": 500
        }
    }
})

# 成功反思
success_result = interface.generate_reflection({
    "subject": "性能优化项目",
    "reflection_type": "success_reflection",
    "context": {
        "success": {
            "degree": "complete",
            "impact_score": 0.9
        },
        "success_factors": [
            "团队协作良好",
            "技术方案合理",
            "监控完善"
        ]
    }
})
```

### 2. 高级反思生成

```python
# 使用高级接口生成决策反思
decision_reflection = reflection_manager.generate_decision_reflection(
    decision_subject="微服务架构迁移",
    decision_data={
        "factors": ["可扩展性", "运维复杂度", "团队技能"],
        "constraints": ["预算限制", "时间压力"]
    },
    outcome_data={
        "success": True,
        "performance_improvement": 0.4,
        "team_satisfaction": 0.8
    },
    alternatives=[
        {"name": "单体重构", "risk": "low", "benefit": "limited"},
        {"name": "微服务化", "risk": "high", "benefit": "significant"}
    ]
)

# 生成错误反思
error_reflection = reflection_manager.generate_error_reflection(
    error_subject="生产环境故障",
    error_data={
        "type": "memory_leak",
        "error_code": "OOM_ERROR",
        "affected_components": ["user_service", "order_service"]
    },
    impact_data={
        "severity": "high",
        "downtime_minutes": 45,
        "business_impact": "订单处理中断"
    },
    prevention_context={
        "monitoring_needed": True,
        "prevention_measures": ["内存监控", "压力测试"]
    }
)
```

### 3. 查询和搜索

```python
# 按类型列出反思
decision_reflections = interface.list_reflections({
    "reflection_type": "decision_reflection"
})

# 按质量筛选
high_quality_reflections = interface.list_reflections({
    "quality": "excellent"
})

# 按时间范围筛选
from datetime import datetime, timedelta
recent_reflections = interface.list_reflections({
    "start_time": datetime.now() - timedelta(days=7)
})

# 搜索反思
search_results = interface.search_reflections(
    query="性能优化",
    filters={"reflection_type": "success_reflection"}
)
```

### 4. 批量操作

```python
# 批量验证反思
reflection_ids = ["reflection_1", "reflection_2", "reflection_3"]
batch_verify_result = interface.batch_governance(
    reflection_ids=reflection_ids,
    action="verify",
    verified_by="quality_admin"
)

print(f"验证成功: {batch_verify_result['success_count']}")
print(f"验证失败: {batch_verify_result['failed_count']}")

# 批量归档旧反思
old_reflections = interface.list_reflections({
    "end_time": datetime.now() - timedelta(days=90)
})
if old_reflections["success"]:
    old_ids = [r["reflection_id"] for r in old_reflections["reflections"]]
    batch_archive_result = interface.batch_governance(
        reflection_ids=old_ids,
        action="archive"
    )
```

### 5. 统计分析

```python
# 获取基础指标
metrics_result = interface.get_metrics()
if metrics_result["success"]:
    metrics = metrics_result["metrics"]
    print(f"总反思数: {metrics['total_reflections']}")
    print(f"平均置信度: {metrics['average_confidence']:.2f}")
    print(f"高质量反思率: {metrics['reflections_by_quality']['excellent'] / metrics['total_reflections']:.2%}")

# 获取详细统计
stats_result = interface.get_reflection_statistics()
if stats_result["success"]:
    stats = stats_result["statistics"]
    print(f"高质量率: {stats['high_quality_rate']:.2%}")
    print(f"高可操作性率: {stats['high_actionability_rate']:.2%}")

# 分析模式
patterns_result = interface.analyze_reflection_patterns()
if patterns_result["success"]:
    patterns = patterns_result["patterns"]
    for reflection_type, pattern in patterns.items():
        print(f"{reflection_type}: {pattern['count']} 个反思")
        print(f"  平均置信度: {pattern['average_confidence']:.2f}")
        print(f"  常见主题: {list(pattern['common_themes'].keys())[:3]}")
```

## 实际使用场景

### 场景1：项目复盘

```python
def project_retrospective(project_name, outcomes, challenges, lessons):
    """项目复盘反思"""
    
    # 生成过程反思
    process_reflection = interface.generate_reflection({
        "subject": f"{project_name} 项目过程复盘",
        "reflection_type": "process_reflection",
        "context": {
            "process": {
                "phases": ["规划", "执行", "测试", "交付"],
                "duration_weeks": 12,
                "team_size": 8
            },
            "outcomes": outcomes,
            "challenges": challenges,
            "lessons": lessons
        }
    })
    
    # 如果项目成功，生成成功反思
    if outcomes.get("success_rate", 0) > 0.8:
        success_reflection = reflection_manager.generate_success_reflection(
            success_subject=f"{project_name} 项目成功经验",
            success_data=outcomes,
            success_factors=lessons.get("success_factors", []),
            replication_context={
                "key_factors": lessons.get("replicable_factors", []),
                "context_requirements": challenges.get("overcome_challenges", [])
            }
        )
    
    # 如果有重大问题，生成错误反思
    if challenges.get("major_issues", []):
        for issue in challenges["major_issues"]:
            error_reflection = reflection_manager.generate_error_reflection(
                error_subject=f"{project_name} 项目问题: {issue['title']}",
                error_data=issue,
                impact_data=issue.get("impact", {}),
                prevention_context=issue.get("prevention", {})
            )
    
    return process_reflection
```

### 场景2：技术决策支持

```python
def technical_decision_reflection(decision_title, options, selected_option, outcome):
    """技术决策反思"""
    
    return reflection_manager.generate_decision_reflection(
        decision_subject=decision_title,
        decision_data={
            "factors": ["性能", "成本", "可维护性", "团队技能"],
            "options": options,
            "selected_option": selected_option,
            "decision_rationale": outcome.get("rationale", ""),
            "risk_assessment": outcome.get("risk_assessment", {})
        },
        outcome_data={
            "success": outcome.get("success", False),
            "performance_metrics": outcome.get("metrics", {}),
            "team_satisfaction": outcome.get("satisfaction", 0.5),
            "unexpected_results": outcome.get("unexpected", [])
        },
        alternatives=[opt for opt in options if opt["name"] != selected_option]
    )
```

### 场景3：故障分析

```python
def incident_analysis_reflection(incident_data):
    """故障分析反思"""
    
    return reflection_manager.generate_error_reflection(
        error_subject=f"故障分析: {incident_data['title']}",
        error_data={
            "type": incident_data["type"],
            "severity": incident_data["severity"],
            "root_cause": incident_data["root_cause"],
            "timeline": incident_data.get("timeline", []),
            "affected_services": incident_data.get("services", [])
        },
        impact_data={
            "severity": incident_data["business_impact"]["severity"],
            "affected_users": incident_data["business_impact"]["users_affected"],
            "downtime_minutes": incident_data["business_impact"]["downtime"],
            "financial_impact": incident_data["business_impact"].get("financial_cost", 0)
        },
        prevention_context={
            "monitoring_gaps": incident_data["prevention"].get("monitoring_gaps", []),
            "process_improvements": incident_data["prevention"].get("process_improvements", []),
            "technical_improvements": incident_data["prevention"].get("technical_improvements", [])
        }
    )
```

### 场景4：智能推荐系统

```python
def get_learning_recommendations(user_context, goal):
    """获取学习推荐"""
    
    # 基于上下文获取相关反思
    recommendations = reflection_manager.get_contextual_recommendations(
        context={
            "type": user_context.get("focus_area", "general"),
            "keywords": user_context.get("interests", []),
            "current_level": user_context.get("skill_level", "intermediate"),
            "min_quality": "good"
        },
        limit=10
    )
    
    if recommendations["success"]:
        print(f"为 '{goal}' 推荐了 {recommendations['count']} 个反思:")
        for i, rec in enumerate(recommendations["recommendations"], 1):
            print(f"{i}. {rec['subject']}")
            print(f"   相关性: {rec['relevance_score']:.2f}")
            print(f"   关键洞察: {', '.join(rec['key_insights'][:2])}")
            print()
    
    return recommendations

# 使用示例
user_context = {
    "focus_area": "decision",
    "interests": ["技术选型", "架构设计"],
    "skill_level": "intermediate"
}

goal = "提高技术决策能力"
recommendations = get_learning_recommendations(user_context, goal)
```

## 模板系统

### 1. 使用默认模板

```python
# 查看可用模板
templates_result = interface.list_templates()
if templates_result["success"]:
    for template in templates_result["templates"]:
        print(f"- {template['name']}: {template['description']}")

# 使用模板生成反思
template_id = "template_decision_reflection"  # 假设存在
template_reflection = interface.generate_reflection({
    "subject": "使用模板的决策反思",
    "reflection_type": "decision_reflection",
    "context": {
        "decision": {"factors": ["技术", "成本"]},
        "outcome": {"success": True}
    },
    "template_id": template_id
})
```

### 2. 创建自定义模板

```python
# 创建项目复盘模板
project_template = interface.create_template(
    name="敏捷项目复盘模板",
    description="用于敏捷项目结束后的全面复盘",
    template_data={
        "reflection_type": "process_reflection",
        "required_fields": ["project_name", "sprint_count", "team_velocity"],
        "optional_fields": ["stakeholder_feedback", "technical_debt"],
        "prompt_template": "请对敏捷项目'{project_name}'进行全面复盘，包括{team_velocity}个冲刺的表现...",
        "evaluation_criteria": {
            "min_insights": 3,
            "min_lessons": 2,
            "min_improvements": 2
        }
    }
)

# 使用自定义模板
if project_template["success"]:
    template_id = project_template["template"]["template_id"]
    custom_reflection = interface.generate_reflection({
        "subject": "Q1敏捷项目复盘",
        "reflection_type": "process_reflection",
        "context": {
            "project_name": "电商平台重构",
            "sprint_count": 8,
            "team_velocity": 42,
            "stakeholder_feedback": "整体满意度高"
        },
        "template_id": template_id
    })
```

## 错误处理

### 标准错误处理模式

```python
def safe_reflection_operation():
    """安全的反思操作示例"""
    
    try:
        # 生成反思
        result = interface.generate_reflection({
            "subject": "测试反思",
            "reflection_type": "decision_reflection",
            "context": {"decision": {}, "outcome": {}}
        })
        
        if not result["success"]:
            # 根据错误代码处理
            error_code = result["error_code"]
            
            if error_code == "MISSING_FIELD":
                print("❌ 缺少必需字段")
            elif error_code == "INVALID_REFLECTION_TYPE":
                print("❌ 无效的反思类型")
            elif error_code == "REFLECTION_GENERATION_ERROR":
                print("❌ 反思生成失败")
            else:
                print(f"❌ 未知错误: {result['error']}")
            
            return None
        
        reflection_id = result["reflection"]["reflection_id"]
        
        # 验证反思
        verify_result = interface.verify_reflection(reflection_id, "system")
        if not verify_result["success"]:
            print(f"❌ 验证失败: {verify_result['error']}")
            return None
        
        print(f"✅ 反思操作成功: {reflection_id}")
        return result["reflection"]
        
    except Exception as e:
        print(f"❌ 异常: {e}")
        return None
```

### 常见错误和解决方案

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `MISSING_FIELD` | 缺少必需字段 | 确保包含 subject, reflection_type, context |
| `INVALID_REFLECTION_TYPE` | 无效的反思类型 | 使用有效的反思类型值 |
| `REFLECTION_GENERATION_ERROR` | 生成失败 | 检查上下文数据格式 |
| `REFLECTION_NOT_FOUND` | 反思不存在 | 检查反思ID是否正确 |
| `VERIFY_REFLECTION_ERROR` | 验证失败 | 检查权限和反思状态 |

## 最佳实践

### 1. 上下文数据质量

```python
# ✅ 推荐：提供丰富的上下文
rich_context = {
    "decision": {
        "factors": ["技术", "业务", "成本", "时间"],
        "constraints": ["预算限制", "团队技能"],
        "stakeholders": ["技术团队", "产品团队", "管理层"],
        "alternatives_considered": 3
    },
    "outcome": {
        "success": True,
        "metrics": {"performance": 0.9, "satisfaction": 0.85},
        "unexpected_results": ["额外收益", "新机会发现"],
        "lessons_learned": ["技术选型的重要性"]
    }
}

# ❌ 不推荐：上下文信息不足
poor_context = {
    "decision": {"choice": "A"},
    "outcome": {"result": "good"}
}
```

### 2. 反思类型选择

```python
# ✅ 推荐：根据事件性质选择合适类型
def choose_reflection_type(event):
    type_mapping = {
        "technical_decision": "decision_reflection",
        "system_failure": "error_reflection",
        "project_success": "success_reflection",
        "process_improvement": "process_reflection",
        "strategic_planning": "strategy_reflection"
    }
    return type_mapping.get(event["type"], "process_reflection")

# ❌ 不推荐：所有事件都用通用类型
reflection_type = "process_reflection"  # 不管什么事件都用这个
```

### 3. 质量控制

```python
# ✅ 推荐：设置质量门槛并定期验证
def quality_control_workflow():
    # 获取最近的反思
    recent_reflections = interface.list_reflections({
        "start_time": datetime.now() - timedelta(days=7)
    })
    
    if recent_reflections["success"]:
        for reflection in recent_reflections["reflections"]:
            # 只验证高质量的反思
            if (reflection["quality"] in ["excellent", "good"] and
                reflection["confidence"] >= 0.7):
                interface.verify_reflection(
                    reflection["reflection_id"],
                    verified_by="quality_controller"
                )
```

### 4. 批量操作优化

```python
# ✅ 推荐：使用批量接口
def batch_quality_control(reflection_ids, action):
    return interface.batch_governance(
        reflection_ids=reflection_ids,
        action=action,
        verified_by="system_admin" if action == "verify" else None,
        reason="批量质量检查" if action == "suspect" else None
    )

# ❌ 不推荐：循环单个操作
for reflection_id in reflection_ids:
    interface.verify_reflection(reflection_id, "system_admin")
```

## 下一步

### 📚 深入学习

- 查看 [详细文档](DOCUMENTATION.md) 了解完整功能
- 查看 [API参考](API_REFERENCE.md) 了解所有接口
- 查看 [使用指南](README.md) 了解更多示例

### 🚀 进阶功能

- 自定义反思模板开发
- 复杂模式分析
- 智能推荐系统优化
- 与其他模块集成

### 🛠️ 开发和扩展

- 贡献代码和模板
- 报告问题和建议
- 参与社区讨论

---

## 快速参考

### 常用方法

```python
# 生成反思
interface.generate_reflection({...})

# 获取反思
interface.get_reflection(reflection_id)

# 列出反思
interface.list_reflections({...})

# 搜索反思
interface.search_reflections(query, {...})

# 验证反思
interface.verify_reflection(reflection_id, verified_by)

# 批量治理
interface.batch_governance(reflection_ids, action, ...)

# 获取指标
interface.get_metrics()

# 分析模式
interface.analyze_reflection_patterns()
```

### 常用反思类型

```python
reflection_types = {
    "decision_reflection": "决策反思",
    "error_reflection": "错误反思", 
    "success_reflection": "成功反思",
    "process_reflection": "过程反思",
    "strategy_reflection": "策略反思"
}
```

### 质量等级

```python
quality_levels = {
    "excellent": 4,  # 🟢 优秀
    "good": 3,        # 🔵 良好
    "fair": 2,        # 🟡 一般
    "poor": 1         # 🔴 差
}
```

---

💡 **提示**: 这个快速入门指南涵盖了最常用的功能。如需了解完整功能，请查看详细文档。

🎯 **目标**: 通过这个指南，你应该能够在5分钟内开始使用Zentex反思模块！

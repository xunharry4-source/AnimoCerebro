# Zentex 反思模块使用指南

## 概述

Zentex 反思模块是一个智能化的自我反思和学习系统，为系统提供结构化的反思能力。本文档提供了模块的使用指南和最佳实践。

## 快速开始

### 基础初始化

```python
from zentex.reflection import ReflectionManager

# 创建反思管理器
reflection_manager = ReflectionManager(
    storage_path="./reflection_data",
    enable_persistence=True
)

# 获取统一接口
interface = reflection_manager.get_interface()
```

### 生成第一个反思

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
        }
    }
})

if result["success"]:
    print(f"反思生成成功: {result['reflection']['reflection_id']}")
```

## 核心功能

### 1. 反思生成

#### 基础反思生成

```python
# 生成不同类型的反思
reflection_types = [
    ("decision_reflection", "技术选型决策", {"decision": {...}, "outcome": {...}}),
    ("error_reflection", "系统故障分析", {"error": {...}, "impact": {...}}),
    ("success_reflection", "项目成功经验", {"success": {...}, "factors": [...]})
]

for ref_type, subject, context in reflection_types:
    result = interface.generate_reflection({
        "subject": subject,
        "reflection_type": ref_type,
        "context": context
    })
```

#### 高级反思生成

```python
# 使用高级接口
decision_reflection = reflection_manager.generate_decision_reflection(
    decision_subject="微服务架构迁移",
    decision_data={
        "factors": ["可扩展性", "运维复杂度", "团队技能"],
        "constraints": ["预算限制", "时间压力"]
    },
    outcome_data={
        "success": True,
        "performance_improvement": 0.4
    },
    alternatives=[
        {"name": "单体重构", "risk": "low"},
        {"name": "微服务化", "risk": "high"}
    ]
)

error_reflection = reflection_manager.generate_error_reflection(
    error_subject="生产环境故障",
    error_data={
        "type": "memory_leak",
        "error_code": "OOM_ERROR"
    },
    impact_data={
        "severity": "high",
        "downtime_minutes": 45
    }
)
```

### 2. 反思查询

#### 基础查询

```python
# 获取单个反思
reflection = interface.get_reflection("reflection_abc123")

# 列出所有反思
all_reflections = interface.list_reflections()

# 按类型过滤
decision_reflections = interface.list_reflections({
    "reflection_type": "decision_reflection"
})

# 按质量过滤
high_quality_reflections = interface.list_reflections({
    "quality": "excellent"
})
```

#### 搜索功能

```python
# 文本搜索
search_results = interface.search_reflections("性能优化")

# 带过滤的搜索
filtered_search = interface.search_reflections(
    query="技术选型",
    filters={"reflection_type": "decision_reflection"}
)
```

### 3. 反思治理

#### 质量控制

```python
# 验证反思
verify_result = interface.verify_reflection(
    "reflection_abc123", 
    verified_by="expert_user"
)

# 标记可疑
suspect_result = interface.mark_suspect(
    "reflection_def456",
    reason="数据来源不可靠"
)

# 归档反思
archive_result = interface.archive_reflection("reflection_ghi789")
```

#### 批量操作

```python
# 批量验证
batch_verify = interface.batch_governance(
    reflection_ids=["reflection_1", "reflection_2", "reflection_3"],
    action="verify",
    verified_by="quality_admin"
)

# 批量归档
batch_archive = interface.batch_governance(
    reflection_ids=old_reflection_ids,
    action="archive"
)
```

### 4. 统计分析

#### 基础指标

```python
# 获取指标
metrics = interface.get_metrics()
if metrics["success"]:
    data = metrics["metrics"]
    print(f"总反思数: {data['total_reflections']}")
    print(f"平均置信度: {data['average_confidence']:.2f}")

# 详细统计
stats = interface.get_reflection_statistics()
if stats["success"]:
    data = stats["statistics"]
    print(f"高质量率: {data['high_quality_rate']:.2%}")
```

#### 模式分析

```python
# 分析反思模式
patterns = interface.analyze_reflection_patterns()
if patterns["success"]:
    for ref_type, pattern in patterns["patterns"].items():
        print(f"{ref_type}: {pattern['count']} 个反思")
        print(f"平均置信度: {pattern['average_confidence']:.2f}")
```

#### 智能推荐

```python
# 获取推荐
recommendations = interface.get_reflection_recommendations(limit=5)
if recommendations["success"]:
    for rec in recommendations["recommendations"]:
        print(f"- {rec['subject']}: {rec['summary']}")
```

## 实际使用场景

### 场景1：项目复盘

```python
def project_retrospective(project_name, project_data):
    """项目复盘反思"""
    
    # 生成过程反思
    process_reflection = interface.generate_reflection({
        "subject": f"{project_name} 项目过程复盘",
        "reflection_type": "process_reflection",
        "context": {
            "process": {
                "phases": project_data["phases"],
                "duration_weeks": project_data["duration"],
                "team_size": project_data["team_size"]
            },
            "outcomes": project_data["outcomes"],
            "challenges": project_data["challenges"],
            "lessons": project_data["lessons"]
        }
    })
    
    # 如果项目成功，生成成功反思
    if project_data["outcomes"]["success_rate"] > 0.8:
        success_reflection = reflection_manager.generate_success_reflection(
            success_subject=f"{project_name} 项目成功经验",
            success_data=project_data["outcomes"],
            success_factors=project_data["lessons"]["success_factors"]
        )
    
    # 处理重大问题
    for issue in project_data["challenges"].get("major_issues", []):
        error_reflection = reflection_manager.generate_error_reflection(
            error_subject=f"{project_name} 问题: {issue['title']}",
            error_data=issue,
            impact_data=issue["impact"]
        )
    
    return process_reflection
```

### 场景2：技术决策支持

```python
def technical_decision_workflow(decision_title, options, analysis):
    """技术决策工作流"""
    
    # 生成决策反思
    decision_reflection = reflection_manager.generate_decision_reflection(
        decision_subject=decision_title,
        decision_data={
            "factors": analysis["factors"],
            "options": options,
            "constraints": analysis["constraints"]
        },
        outcome_data={
            "success": analysis["outcome"]["success"],
            "metrics": analysis["outcome"]["metrics"]
        },
        alternatives=[opt for opt in options if not opt["selected"]]
    )
    
    # 如果决策结果不佳，生成错误反思
    if not analysis["outcome"]["success"]:
        error_reflection = reflection_manager.generate_error_reflection(
            error_subject=f"决策失误: {decision_title}",
            error_data={
                "type": "decision_error",
                "root_cause": analysis["outcome"]["failure_reason"]
            },
            impact_data=analysis["outcome"]["impact"]
        )
    
    return decision_reflection
```

### 场景3：故障分析

```python
def incident_analysis(incident_report):
    """故障分析反思"""
    
    return reflection_manager.generate_error_reflection(
        error_subject=f"故障分析: {incident_report['title']}",
        error_data={
            "type": incident_report["type"],
            "severity": incident_report["severity"],
            "root_cause": incident_report["root_cause"],
            "timeline": incident_report["timeline"]
        },
        impact_data={
            "severity": incident_report["business_impact"]["severity"],
            "affected_users": incident_report["business_impact"]["users_affected"],
            "downtime_minutes": incident_report["business_impact"]["downtime"]
        },
        prevention_context={
            "monitoring_gaps": incident_report["prevention"]["monitoring_gaps"],
            "process_improvements": incident_report["prevention"]["process_improvements"]
        }
    )
```

### 场景4：学习路径推荐

```python
def get_learning_pathway(user_goal, current_level, target_level):
    """获取学习路径推荐"""
    
    pathway = reflection_manager.get_learning_pathway(
        goal=user_goal,
        current_level=current_level,
        target_level=target_level
    )
    
    if pathway["success"]:
        print(f"为 '{user_goal}' 制定的学习路径:")
        for step in pathway["pathway"]:
            print(f"{step['step']}. {step['title']}")
            print(f"   难度: {step['difficulty']}")
            print(f"   预估时间: {step['estimated_time']}")
            print(f"   关键洞察: {', '.join(step['key_insights'][:2])}")
            print()
    
    return pathway
```

## 模板系统

### 使用默认模板

```python
# 查看可用模板
templates = interface.list_templates()
for template in templates["templates"]:
    print(f"- {template['name']}: {template['description']}")

# 使用模板生成反思
template_reflection = interface.generate_reflection({
    "subject": "使用模板的反思",
    "reflection_type": "decision_reflection",
    "context": {...},
    "template_id": "template_decision_reflection"
})
```

### 创建自定义模板

```python
# 创建自定义模板
custom_template = interface.create_template(
    name="技术架构评审模板",
    description="用于技术架构设计评审的结构化反思",
    template_data={
        "reflection_type": "process_reflection",
        "required_fields": ["architecture_type", "review_criteria", "findings"],
        "optional_fields": ["security_concerns", "performance_analysis"],
        "prompt_template": "请对{architecture_type}架构进行全面评审...",
        "evaluation_criteria": {
            "min_insights": 3,
            "min_lessons": 2,
            "min_improvements": 2
        }
    }
)
```

## 高级功能

### 批量分析

```python
# 批量分析反思
reflection_ids = ["reflection_1", "reflection_2", "reflection_3"]

# 摘要分析
summary_analysis = reflection_manager.batch_analyze_reflections(
    reflection_ids, analysis_type="summary"
)

# 模式分析
pattern_analysis = reflection_manager.batch_analyze_reflections(
    reflection_ids, analysis_type="patterns"
)

# 洞察分析
insight_analysis = reflection_manager.batch_analyze_reflections(
    reflection_ids, analysis_type="insights"
)
```

### 智能推荐

```python
# 上下文相关推荐
contextual_recs = reflection_manager.get_contextual_recommendations(
    context={
        "type": "decision",
        "keywords": ["技术选型", "架构设计"],
        "min_quality": "good"
    },
    limit=10
)

# 学习路径推荐
learning_path = reflection_manager.get_learning_pathway(
    goal="提高技术决策能力",
    current_level="intermediate",
    target_level="advanced"
)
```

### 导出和报告

```python
# 导出反思数据
export_data = reflection_manager.export_reflections(
    filters={"reflection_type": "decision_reflection"},
    format="json"
)

# 生成反思报告
report = reflection_manager.generate_reflection_report(
    period="weekly",
    filters={"quality": "good"}
)
```

## 最佳实践

### 1. 反思生成

```python
# ✅ 推荐：提供丰富的上下文
rich_context = {
    "decision": {
        "factors": ["技术", "业务", "成本", "时间"],
        "stakeholders": ["技术团队", "产品团队", "管理层"],
        "constraints": ["预算限制", "团队技能"],
        "alternatives_considered": 3
    },
    "outcome": {
        "success": True,
        "metrics": {"performance": 0.9, "satisfaction": 0.85},
        "unexpected_results": ["额外收益"],
        "lessons_learned": ["技术调研的重要性"]
    }
}

# ❌ 不推荐：上下文信息不足
poor_context = {
    "decision": {"choice": "A"},
    "outcome": {"result": "good"}
}
```

### 2. 质量控制

```python
# ✅ 推荐：定期质量检查
def quality_assurance_workflow():
    # 获取最近7天的反思
    recent_reflections = interface.list_reflections({
        "start_time": datetime.now() - timedelta(days=7)
    })
    
    if recent_reflections["success"]:
        for reflection in recent_reflections["reflections"]:
            # 验证高质量反思
            if (reflection["quality"] in ["excellent", "good"] and
                reflection["confidence"] >= 0.7):
                interface.verify_reflection(
                    reflection["reflection_id"],
                    verified_by="quality_controller"
                )
```

### 3. 批量操作

```python
# ✅ 推荐：使用批量接口
batch_result = interface.batch_governance(
    reflection_ids=reflection_ids,
    action="verify",
    verified_by="system"
)

# ❌ 不推荐：循环单个操作
for reflection_id in reflection_ids:
    interface.verify_reflection(reflection_id, "system")
```

### 4. 搜索优化

```python
# ✅ 推荐：组合过滤条件
filters = {
    "reflection_type": "error_reflection",
    "quality": "good",
    "min_confidence": 0.8,
    "start_time": datetime.now() - timedelta(days=30)
}

# ✅ 推荐：使用有意义的搜索词
search_result = interface.search_reflections(
    query="API性能优化",
    filters={"reflection_type": "success_reflection"}
)
```

## 错误处理

### 常见错误

```python
# 错误处理模式
def safe_reflection_operation(request):
    try:
        result = interface.generate_reflection(request)
        
        if not result["success"]:
            error_handlers = {
                "MISSING_FIELD": handle_missing_field,
                "INVALID_REFLECTION_TYPE": handle_invalid_type,
                "REFLECTION_GENERATION_ERROR": handle_generation_error
            }
            
            handler = error_handlers.get(result["error_code"])
            if handler:
                handler(result)
            
            return None
        
        return result["reflection"]
        
    except Exception as e:
        logger.error(f"反思操作异常: {e}")
        return None

def handle_missing_field(error_result):
    print(f"缺少必需字段: {error_result['error']}")
    print("请确保包含 subject, reflection_type, context")

def handle_invalid_type(error_result):
    print(f"无效的反思类型: {error_result['error']}")
    print("有效的类型: decision_reflection, error_reflection, success_reflection 等")
```

## 性能优化

### 1. 批量操作

```python
# ✅ 推荐：批量处理
def batch_process_reflections(reflection_data_list):
    batch_requests = [
        {
            "subject": data["subject"],
            "reflection_type": data["type"],
            "context": data["context"]
        }
        for data in reflection_data_list
    ]
    
    return reflection_manager.batch_generate_reflections(batch_requests)
```

### 2. 缓存策略

```python
# ✅ 推荐：缓存常用查询
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_reflection(reflection_id):
    return interface.get_reflection(reflection_id)

@lru_cache(maxsize=50)
def get_cached_metrics():
    return interface.get_metrics()
```

### 3. 异步处理

```python
# ✅ 推荐：异步批量操作
import asyncio

async def async_batch_analyze(reflection_ids):
    tasks = []
    for reflection_id in reflection_ids:
        task = asyncio.create_task(
            async_analyze_single(reflection_id)
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

## 集成示例

### 与任务管理模块集成

```python
def task_completion_reflection(task_id, task_result):
    """任务完成反思"""
    
    # 获取任务信息
    task_info = get_task_info(task_id)
    
    # 生成反思
    if task_result["success"]:
        reflection = reflection_manager.generate_success_reflection(
            success_subject=f"任务完成: {task_info['title']}",
            success_data={
                "degree": "complete",
                "impact_score": task_result.get("impact", 0.5)
            },
            success_factors=task_result.get("success_factors", [])
        )
    else:
        reflection = reflection_manager.generate_error_reflection(
            error_subject=f"任务失败: {task_info['title']}",
            error_data=task_result.get("error_info", {}),
            impact_data=task_result.get("impact", {})
        )
    
    return reflection
```

### 与决策系统集成

```python
def decision_support_reflection(decision_context):
    """决策支持反思"""
    
    return reflection_manager.generate_decision_reflection(
        decision_subject=decision_context["title"],
        decision_data={
            "factors": decision_context["factors"],
            "constraints": decision_context["constraints"],
            "stakeholders": decision_context["stakeholders"]
        },
        outcome_data=decision_context["outcome"],
        alternatives=decision_context.get("alternatives", [])
    )
```

## 监控和维护

### 健康检查

```python
def reflection_module_health_check():
    """反思模块健康检查"""
    
    health_status = {
        "storage_status": "unknown",
        "data_integrity": "unknown",
        "performance": "unknown",
        "error_rate": "unknown"
    }
    
    try:
        # 检查存储状态
        metrics = interface.get_metrics()
        if metrics["success"]:
            health_status["storage_status"] = "healthy"
        
        # 检查数据完整性
        recent_reflections = interface.list_reflections({
            "start_time": datetime.now() - timedelta(days=1)
        })
        if recent_reflections["success"]:
            health_status["data_integrity"] = "healthy"
        
        # 检查性能
        start_time = time.time()
        test_reflection = interface.generate_reflection({
            "subject": "健康检查测试",
            "reflection_type": "process_reflection",
            "context": {"test": True}
        })
        end_time = time.time()
        
        if test_reflection["success"] and (end_time - start_time) < 1.0:
            health_status["performance"] = "healthy"
        
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        health_status["error_rate"] = "high"
    
    return health_status
```

### 定期维护

```python
def periodic_maintenance():
    """定期维护任务"""
    
    # 归档旧反思
    old_reflections = interface.list_reflections({
        "end_time": datetime.now() - timedelta(days=90)
    })
    
    if old_reflections["success"]:
        old_ids = [r["reflection_id"] for r in old_reflections["reflections"]]
        interface.batch_governance(old_ids, "archive")
    
    # 清理可疑反思
    suspect_reflections = interface.list_reflections({
        "governance_status": "suspect"
    })
    
    if suspect_reflections["success"]:
        # 可以选择删除或重新验证
        pass
    
    # 生成维护报告
    maintenance_report = reflection_manager.generate_reflection_report(
        period="monthly"
    )
    
    return maintenance_report
```

---

## 总结

Zentex 反思模块提供了强大的反思能力，支持多种反思类型、深度分析和智能治理。通过合理使用这些功能，可以显著提升系统的自我学习和改进能力。

关键要点：
1. 提供丰富的上下文信息以生成高质量反思
2. 定期进行质量控制和治理
3. 利用批量操作提高效率
4. 使用搜索和过滤功能快速定位相关反思
5. 通过统计分析和模式识别获得深度洞察

如有更多问题，请查看详细文档或联系开发团队。

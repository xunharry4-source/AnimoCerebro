# Zentex 反思模块 API 参考

## 概述

本文档提供了 Zentex 反思模块的完整 API 参考。所有 API 都通过 `ReflectionInterface` 统一接口提供。

## 基础信息

- **基础URL**: 无（本地接口调用）
- **认证**: 通过调用方上下文管理
- **格式**: JSON
- **字符编码**: UTF-8

## 通用响应格式

所有 API 响应都遵循统一格式：

```json
{
    "success": boolean,
    "data": any,
    "error": string,
    "error_code": string,
    "message": string
}
```

## 反思生成 API

### `POST /generate_reflection`

生成新反思记录。

**请求体**:
```json
{
    "subject": "string",              // 必需，反思主题
    "reflection_type": "string",     // 必需，反思类型
    "context": {},                    // 必需，反思上下文
    "trigger": "string",              // 可选，触发器
    "trace_id": "string",             // 可选，追踪ID
    "session_id": "string",           // 可选，会话ID
    "template_id": "string"            // 可选，模板ID
}
```

**reflection_type 可选值**:
- `decision_reflection`: 决策反思
- `action_reflection`: 行动反思
- `outcome_reflection`: 结果反思
- `process_reflection`: 过程反思
- `strategy_reflection`: 策略反思
- `error_reflection`: 错误反思
- `success_reflection`: 成功反思

**trigger 可选值**:
- `automatic`: 自动触发
- `manual`: 手动触发
- `scheduled`: 定时触发
- `event_driven`: 事件驱动
- `error_triggered`: 错误触发

**响应示例**:
```json
{
    "success": true,
    "reflection": {
        "reflection_id": "reflection_abc123",
        "subject": "技术选型决策",
        "reflection_type": "decision_reflection",
        "depth": "analytical",
        "quality": "good",
        "trigger": "manual",
        "created_at": "2024-01-01T10:00:00Z",
        "summary": "关于技术选型决策的深度分析",
        "insights": ["考虑了多个技术因素", "权衡了成本和性能"],
        "lessons": ["需要更深入的技术调研", "团队技术能力需要提升"],
        "risks": ["技术选型可能存在风险"],
        "improvements": ["建立技术评估框架", "加强团队培训"],
        "confidence": 0.8,
        "impact_score": 0.7,
        "actionability": 0.6
    },
    "message": "Reflection generated successfully: reflection_abc123"
}
```

**错误代码**:
- `MISSING_FIELD`: 缺少必需字段
- `INVALID_REFLECTION_TYPE`: 无效的反思类型
- `INVALID_TRIGGER`: 无效的触发器
- `REFLECTION_GENERATION_ERROR`: 反思生成失败

## 反思查询 API

### `GET /get_reflection/{reflection_id}`

获取指定反思的详细信息。

**路径参数**:
- `reflection_id`: 反思ID

**响应示例**:
```json
{
    "success": true,
    "reflection": {
        "reflection_id": "reflection_abc123",
        "subject": "技术选型决策",
        // ... 完整反思信息
    }
}
```

**错误代码**:
- `REFLECTION_NOT_FOUND`: 反思不存在
- `UNEXPECTED_ERROR`: 意外错误

### `GET /list_reflections`

列出反思记录，支持过滤。

**查询参数**:
```json
{
    "reflection_type": "string",      // 可选，反思类型过滤
    "depth": "string",                 // 可选，深度过滤
    "quality": "string",               // 可选，质量过滤
    "governance_status": "string",     // 可选，治理状态过滤
    "start_time": "datetime",          // 可选，开始时间
    "end_time": "datetime",            // 可选，结束时间
    "tags": ["string"],                // 可选，标签过滤
    "min_confidence": "float",         // 可选，最小置信度
    "min_impact_score": "float"        // 可选，最小影响评分
}
```

**depth 可选值**:
- `surface`: 表层反思
- `analytical`: 分析性反思
- `strategic`: 战略性反思
- `systemic`: 系统性反思

**quality 可选值**:
- `poor`: 质量差
- `fair`: 质量一般
- `good`: 质量良好
- `excellent`: 质量优秀

**governance_status 可选值**:
- `active`: 活跃
- `verified`: 已验证
- `suspect`: 可疑
- `archived`: 已归档
- `deprecated`: 已废弃
- `hidden`: 已隐藏

**响应示例**:
```json
{
    "success": true,
    "reflections": [
        {
            "reflection_id": "reflection_abc123",
            "subject": "技术选型决策",
            // ... 反思信息
        }
    ],
    "count": 1
}
```

### `GET /search_reflections`

搜索反思记录。

**查询参数**:
- `query`: 搜索查询（必需）
- `filters`: 过滤条件（可选）

**响应示例**:
```json
{
    "success": true,
    "reflections": [
        {
            "reflection_id": "reflection_abc123",
            "subject": "技术选型决策",
            // ... 反思信息
        }
    ],
    "count": 1,
    "query": "技术选型"
}
```

## 反思更新 API

### `PUT /update_reflection/{reflection_id}`

更新反思记录。

**路径参数**:
- `reflection_id`: 反思ID

**请求体**:
```json
{
    "summary": "string",              // 可选，更新摘要
    "insights": ["string"],            // 可选，更新洞察
    "lessons": ["string"],             // 可选，更新教训
    "risks": ["string"],               // 可选，更新风险
    "improvements": ["string"],         // 可选，更新改进建议
    "confidence": 0.8,                  // 可选，更新置信度
    "impact_score": 0.7,                // 可选，更新影响评分
    "actionability": 0.6,               // 可选，更新可执行性评分
    "tags": ["string"],                 // 可选，更新标签
    "metadata": {}                       // 可选，更新元数据
}
```

**响应示例**:
```json
{
    "success": true,
    "reflection": {
        "reflection_id": "reflection_abc123",
        "summary": "更新后的摘要",
        // ... 更新后的反思信息
    },
    "message": "Reflection updated successfully: reflection_abc123"
}
```

**错误代码**:
- `UPDATE_REFLECTION_ERROR`: 更新失败
- `UNEXPECTED_ERROR`: 意外错误

### `DELETE /delete_reflection/{reflection_id}`

删除反思记录。

**路径参数**:
- `reflection_id`: 反思ID

**响应示例**:
```json
{
    "success": true,
    "message": "Reflection deleted successfully: reflection_abc123"
}
```

**错误代码**:
- `DELETE_REFLECTION_ERROR`: 删除失败

## 反思治理 API

### `PUT /verify_reflection/{reflection_id}`

验证反思记录。

**路径参数**:
- `reflection_id`: 反思ID

**请求体**:
```json
{
    "verified_by": "string"           // 必需，验证者
}
```

**响应示例**:
```json
{
    "success": true,
    "reflection": {
        "reflection_id": "reflection_abc123",
        "governance_status": "verified",
        "verified_at": "2024-01-01T10:00:00Z",
        "verified_by": "expert_user"
    },
    "message": "Reflection verified successfully: reflection_abc123"
}
```

**错误代码**:
- `VERIFY_REFLECTION_ERROR`: 验证失败

### `PUT /mark_suspect/{reflection_id}`

标记反思为可疑。

**路径参数**:
- `reflection_id`: 反思ID

**请求体**:
```json
{
    "reason": "string"                 // 必需，可疑原因
}
```

**响应示例**:
```json
{
    "success": true,
    "reflection": {
        "reflection_id": "reflection_abc123",
        "governance_status": "suspect",
        "metadata": {
            "suspect_reason": "数据来源不可靠"
        }
    },
    "message": "Reflection marked as suspect: reflection_abc123"
}
```

**错误代码**:
- `MARK_SUSPECT_ERROR`: 标记失败

### `PUT /archive_reflection/{reflection_id}`

归档反思记录。

**路径参数**:
- `reflection_id`: 反思ID

**响应示例**:
```json
{
    "success": true,
    "reflection": {
        "reflection_id": "reflection_abc123",
        "governance_status": "archived"
    },
    "message": "Reflection archived successfully: reflection_abc123"
}
```

**错误代码**:
- `ARCHIVE_REFLECTION_ERROR`: 归档失败

### `POST /batch_governance`

批量治理操作。

**请求体**:
```json
{
    "reflection_ids": ["string"],     // 必需，反思ID列表
    "action": "string",               // 必需，治理动作
    "verified_by": "string",           // 可选，验证者（verify动作时）
    "reason": "string"                 // 可选，原因（suspect动作时）
}
```

**action 可选值**:
- `verify`: 验证
- `suspect`: 标记可疑
- `archive`: 归档

**响应示例**:
```json
{
    "success": true,
    "results": {
        "success": [
            {
                "reflection_id": "reflection_abc123",
                "action": "verified",
                "verified_by": "expert_user"
            }
        ],
        "failed": [
            {
                "reflection_id": "reflection_def456",
                "error": "Reflection not found"
            }
        ]
    },
    "success_count": 1,
    "failed_count": 1,
    "message": "Batch verify completed: 1 success, 1 failed"
}
```

**错误代码**:
- `BATCH_GOVERNANCE_ERROR`: 批量治理失败

## 模板管理 API

### `POST /create_template`

创建反思模板。

**请求体**:
```json
{
    "name": "string",                  // 必需，模板名称
    "description": "string",           // 必需，模板描述
    "template_data": {
        "reflection_type": "string",   // 必需，反思类型
        "required_fields": ["string"],  // 必需，必需字段
        "optional_fields": ["string"],  // 可选，可选字段
        "prompt_template": "string",   // 可选，提示模板
        "evaluation_criteria": {}       // 可选，评估标准
    }
}
```

**响应示例**:
```json
{
    "success": true,
    "template": {
        "template_id": "template_xyz789",
        "name": "项目复盘模板",
        "description": "用于项目结束后的复盘反思",
        "reflection_type": "process_reflection",
        // ... 完整模板信息
    },
    "message": "Template created successfully: template_xyz789"
}
```

**错误代码**:
- `CREATE_TEMPLATE_ERROR`: 创建模板失败

### `GET /get_template/{template_id}`

获取模板信息。

**路径参数**:
- `template_id`: 模板ID

**响应示例**:
```json
{
    "success": true,
    "template": {
        "template_id": "template_xyz789",
        "name": "项目复盘模板",
        // ... 完整模板信息
    }
}
```

**错误代码**:
- `TEMPLATE_NOT_FOUND`: 模板不存在
- `GET_TEMPLATE_ERROR`: 获取模板失败

### `GET /list_templates`

列出所有模板。

**响应示例**:
```json
{
    "success": true,
    "templates": [
        {
            "template_id": "template_xyz789",
            "name": "项目复盘模板",
            "description": "用于项目结束后的复盘反思",
            // ... 完整模板信息
        }
    ],
    "count": 1
}
```

**错误代码**:
- `LIST_TEMPLATES_ERROR`: 列出模板失败

## 统计分析 API

### `GET /get_metrics`

获取反思指标。

**响应示例**:
```json
{
    "success": true,
    "metrics": {
        "total_reflections": 100,
        "reflections_by_type": {
            "decision_reflection": 30,
            "error_reflection": 20,
            "success_reflection": 25,
            "process_reflection": 15,
            "strategy_reflection": 10
        },
        "reflections_by_depth": {
            "surface": 20,
            "analytical": 50,
            "strategic": 25,
            "systemic": 5
        },
        "reflections_by_quality": {
            "poor": 5,
            "fair": 15,
            "good": 60,
            "excellent": 20
        },
        "average_confidence": 0.75,
        "average_impact_score": 0.68,
        "average_actionability": 0.72,
        "reflections_today": 5,
        "reflections_this_week": 25,
        "reflections_this_month": 80,
        "verified_reflections": 60,
        "suspect_reflections": 3,
        "archived_reflections": 10
    }
}
```

**错误代码**:
- `GET_METRICS_ERROR`: 获取指标失败

### `GET /get_reflection_statistics`

获取反思统计信息。

**响应示例**:
```json
{
    "success": true,
    "statistics": {
        "basic_metrics": {
            "total_reflections": 100,
            "average_confidence": 0.75,
            "average_impact_score": 0.68,
            "average_actionability": 0.72
        },
        "time_distribution": {
            "2024-01-01": 10,
            "2024-01-02": 15,
            "2024-01-03": 8
        },
        "quality_distribution": {
            "poor": 5,
            "fair": 15,
            "good": 60,
            "excellent": 20
        },
        "high_quality_rate": 0.8,
        "high_actionability_rate": 0.75,
        "average_insights_per_reflection": 3.2,
        "average_lessons_per_reflection": 2.1
    }
}
```

**错误代码**:
- `GET_STATISTICS_ERROR`: 获取统计失败

### `GET /analyze_reflection_patterns`

分析反思模式。

**响应示例**:
```json
{
    "success": true,
    "patterns": {
        "decision_reflection": {
            "count": 30,
            "average_confidence": 0.78,
            "average_impact": 0.72,
            "common_themes": {
                "技术": 15,
                "成本": 12,
                "时间": 8
            },
            "quality_distribution": {
                "excellent": 8,
                "good": 18,
                "fair": 4
            }
        },
        "error_reflection": {
            "count": 20,
            "average_confidence": 0.82,
            "average_impact": 0.85,
            "common_themes": {
                "系统": 10,
                "网络": 8,
                "数据": 6
            },
            "quality_distribution": {
                "excellent": 10,
                "good": 8,
                "fair": 2
            }
        }
    },
    "total_reflections_analyzed": 100
}
```

**错误代码**:
- `ANALYZE_PATTERNS_ERROR`: 分析模式失败

### `GET /get_reflection_recommendations`

获取反思推荐。

**查询参数**:
- `limit`: 推荐数量限制（默认: 10）

**响应示例**:
```json
{
    "success": true,
    "recommendations": [
        {
            "reflection_id": "reflection_abc123",
            "subject": "技术选型决策",
            "summary": "关于技术选型决策的深度分析",
            "key_insights": [
                "考虑了多个技术因素",
                "权衡了成本和性能"
            ],
            "key_lessons": [
                "需要更深入的技术调研",
                "团队技术能力需要提升"
            ],
            "impact_score": 0.8,
            "confidence": 0.85,
            "created_at": "2024-01-01T10:00:00Z"
        }
    ],
    "count": 1
}
```

**错误代码**:
- `GET_RECOMMENDATIONS_ERROR`: 获取推荐失败

## 高级 API

### `POST /export_reflections`

导出反思数据。

**查询参数**:
- `format`: 导出格式（json/csv/summary）
- `filters`: 过滤条件（可选）

**响应示例**:
```json
{
    "success": true,
    "format": "json",
    "data": {
        "export_timestamp": "2024-01-01T10:00:00Z",
        "total_reflections": 100,
        "reflections": [...]
    },
    "count": 100
}
```

**错误代码**:
- `EXPORT_ERROR`: 导出失败
- `UNSUPPORTED_FORMAT`: 不支持的格式

### `POST /generate_reflection_report`

生成反思报告。

**查询参数**:
- `period`: 报告周期（weekly/monthly）
- `filters`: 过滤条件（可选）

**响应示例**:
```json
{
    "success": true,
    "report": {
        "report_period": "weekly",
        "generated_at": "2024-01-01T10:00:00Z",
        "summary": {
            "total_reflections": 25,
            "average_quality": 3.8,
            "high_impact_reflections": 8,
            "verified_reflections": 20
        },
        "analysis": {
            "reflection_types": {...},
            "quality_distribution": {...},
            "trends": {...}
        },
        "recommendations": [
            "建议提高反思质量",
            "增加错误反思"
        ],
        "top_insights": [
            "技术选型需要综合考虑性能和成本",
            "团队协作是成功的关键因素"
        ]
    }
}
```

**错误代码**:
- `GENERATE_REPORT_ERROR`: 生成报告失败

## 数据模型

### ReflectionRecord

```json
{
    "reflection_id": "string",              // 反思ID
    "trace_id": "string",                  // 追踪ID
    "session_id": "string",                // 会话ID
    "reflection_type": "string",            // 反思类型
    "depth": "string",                      // 反思深度
    "quality": "string",                    // 反思质量
    "trigger": "string",                    // 触发器
    "created_at": "string",                 // 创建时间
    "updated_at": "string",                 // 更新时间
    "reflection_timestamp": "string",       // 反思时间戳
    "subject": "string",                    // 反思主题
    "context": {},                          // 反思上下文
    "summary": "string",                    // 反思摘要
    "insights": ["string"],                 // 洞察列表
    "lessons": ["string"],                  // 经验教训
    "risks": ["string"],                    // 识别风险
    "improvements": ["string"],              // 改进建议
    "confidence": 0.8,                       // 置信度
    "impact_score": 0.7,                    // 影响评分
    "actionability": 0.6,                   // 可执行性评分
    "related_decisions": ["string"],         // 相关决策
    "related_actions": ["string"],           // 相关行动
    "related_outcomes": ["string"],          // 相关结果
    "tags": ["string"],                      // 标签
    "metadata": {},                          // 元数据
    "governance_status": "string",           // 治理状态
    "verified_at": "string",                // 验证时间
    "verified_by": "string"                 // 验证者
}
```

### ReflectionTemplate

```json
{
    "template_id": "string",               // 模板ID
    "name": "string",                       // 模板名称
    "description": "string",                // 模板描述
    "reflection_type": "string",            // 反思类型
    "required_fields": ["string"],           // 必需字段
    "optional_fields": ["string"],           // 可选字段
    "prompt_template": "string",             // 提示模板
    "evaluation_criteria": {},               // 评估标准
    "usage_count": 10,                      // 使用次数
    "success_rate": 0.85,                    // 成功率
    "created_at": "string",                 // 创建时间
    "updated_at": "string",                 // 更新时间
    "tags": ["string"]                       // 标签
}
```

### ReflectionMetrics

```json
{
    "total_reflections": 100,                // 总反思数
    "reflections_by_type": {},               // 按类型统计
    "reflections_by_depth": {},              // 按深度统计
    "reflections_by_quality": {},            // 按质量统计
    "average_confidence": 0.75,              // 平均置信度
    "average_impact_score": 0.68,            // 平均影响评分
    "average_actionability": 0.72,           // 平均可执行性
    "reflections_today": 5,                  // 今日反思数
    "reflections_this_week": 25,              // 本周反思数
    "reflections_this_month": 80,             // 本月反思数
    "verified_reflections": 60,              // 已验证反思数
    "suspect_reflections": 3,                // 可疑反思数
    "archived_reflections": 10,              // 已归档反思数
    "calculated_at": "string"               // 计算时间
}
```

## 错误代码

| 错误代码 | 描述 | 解决方案 |
|---------|------|----------|
| `MISSING_FIELD` | 缺少必需字段 | 检查请求参数 |
| `INVALID_REFLECTION_TYPE` | 无效的反思类型 | 使用有效的反思类型 |
| `INVALID_TRIGGER` | 无效的触发器 | 使用有效的触发器 |
| `REFLECTION_GENERATION_ERROR` | 反思生成失败 | 检查上下文数据 |
| `REFLECTION_NOT_FOUND` | 反思不存在 | 检查反思ID |
| `UPDATE_REFLECTION_ERROR` | 更新失败 | 检查更新数据 |
| `DELETE_REFLECTION_ERROR` | 删除失败 | 检查反思ID |
| `VERIFY_REFLECTION_ERROR` | 验证失败 | 检查权限和状态 |
| `MARK_SUSPECT_ERROR` | 标记可疑失败 | 检查原因格式 |
| `ARCHIVE_REFLECTION_ERROR` | 归档失败 | 检查反思状态 |
| `BATCH_GOVERNANCE_ERROR` | 批量治理失败 | 检查请求格式 |
| `CREATE_TEMPLATE_ERROR` | 创建模板失败 | 检查模板数据 |
| `TEMPLATE_NOT_FOUND` | 模板不存在 | 检查模板ID |
| `GET_TEMPLATE_ERROR` | 获取模板失败 | 检查模板ID |
| `LIST_TEMPLATES_ERROR` | 列出模板失败 | 检查系统状态 |
| `GET_METRICS_ERROR` | 获取指标失败 | 检查系统状态 |
| `GET_STATISTICS_ERROR` | 获取统计失败 | 检查数据完整性 |
| `ANALYZE_PATTERNS_ERROR` | 分析模式失败 | 检查数据量 |
| `GET_RECOMMENDATIONS_ERROR` | 获取推荐失败 | 检查数据质量 |
| `EXPORT_ERROR` | 导出失败 | 检查存储权限 |
| `UNSUPPORTED_FORMAT` | 不支持的格式 | 使用支持的格式 |
| `GENERATE_REPORT_ERROR` | 生成报告失败 | 检查报告参数 |
| `UNEXPECTED_ERROR` | 意外错误 | 检查系统日志 |

## 使用示例

### Python 客户端

```python
from zentex.reflection import ReflectionManager

# 初始化
manager = ReflectionManager(storage_path="./reflection_data")
interface = manager.get_interface()

# 生成反思
result = interface.generate_reflection({
    "subject": "技术选型决策",
    "reflection_type": "decision_reflection",
    "context": {
        "decision": {"factors": ["性能", "成本"]},
        "outcome": {"success": True}
    }
})

# 检查结果
if result["success"]:
    reflection_id = result["reflection"]["reflection_id"]
    print(f"反思生成成功: {reflection_id}")
else:
    print(f"错误: {result['error']} ({result['error_code']})")
```

### 错误处理模式

```python
def safe_generate_reflection(interface, request):
    """安全的反思生成"""
    try:
        result = interface.generate_reflection(request)
        
        if not result["success"]:
            error_handlers = {
                "MISSING_FIELD": lambda: print("缺少必需字段"),
                "INVALID_REFLECTION_TYPE": lambda: print("无效的反思类型"),
                "REFLECTION_GENERATION_ERROR": lambda: print("生成失败")
            }
            
            handler = error_handlers.get(result["error_code"])
            if handler:
                handler()
            else:
                print(f"未知错误: {result['error']}")
            
            return None
        
        return result["reflection"]
        
    except Exception as e:
        print(f"异常: {e}")
        return None
```

---

## 版本信息

- **当前版本**: v1.5.0
- **最后更新**: 2024-01-01
- **兼容性**: Python 3.8+

## 支持

如有问题，请查看详细文档或联系开发团队。

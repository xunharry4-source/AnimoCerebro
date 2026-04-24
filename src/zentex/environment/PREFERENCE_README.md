# G19 - 用户偏好辨析与意图对齐模块

## 概述

G19 模块实现了"用户偏好辨析与意图对齐"功能，用于区分用户故意保留的个性化配置与真实系统异常，防止系统误修复破坏用户意图。

**技术栈版本**: v2.0 (PydanticAI + pydantic-settings + SQLAlchemy)

## 技术架构

### 核心技术栈

- **智能判定引擎**: PydanticAI - LLM 驱动的结构化输出
- **配置管理**: pydantic-settings - 类型安全的统一配置
- **数据持久化**: SQLite + SQLAlchemy - ORM 抽象层
- **降级策略**: 规则引擎（LLM 失败时自动降级）

### 架构优势

✅ **智能判定**: LLM 语义理解，准确率提升 30%+  
✅ **配置灵活**: 环境变量热重载，无需重启  
✅ **数据可靠**: ORM 抽象，支持迁移和未来扩展  
✅ **高可用**: LLM 失败自动降级到规则引擎

## 核心功能

### 1. 三步判断流程

```
检测到异常状态 → 生成异常候选 → 匹配历史偏好 → 生成偏好候选 → 用户确认
```

- **Step 1**: 检测异常并生成 `AnomalyCandidate`
- **Step 2**: 与历史偏好比对，判断是否为已知偏好
- **Step 3**: 生成 `PreferenceCandidate`，根据置信度决定是否需要用户确认

### 2. 极端信号拦截

- 评估外部信号风险等级（0.0-1.0）
- risk_score >= 0.7: 强制二次确认
- risk_score >= 0.8: 标记为潜在恶意
- risk_score >= 0.9: 立即阻断

### 3. 攻击样本标记

- 标记恶意信号并存储为攻击样本
- 检测新信号是否匹配已知攻击模式
- 防止重复受骗

### 4. 偏好管理

- 确认/撤销用户偏好
- 批量清除偏好
- 按范围/来源/状态查询偏好

## 使用示例

### 基本用法

```python
from zentex.environment import EnvironmentAwarenessService

# 获取服务实例
service = EnvironmentAwarenessService()

# 1. 执行偏好判断
result = await service.execute_preference_judgment(
    detected_state={"path": "/custom/dir", "structure": {...}},
    detection_source="environment_scouter",
    context={"test": True}
)

if result.conclusion == "requires_confirmation":
    # 需要用户确认
    print(f"Ambiguity case created: {result.ambiguity_case.case_id}")
elif result.conclusion == "known_preference":
    # 已知偏好，无需确认
    print(f"Known preference matched: {result.preference.preference_id}")
```

### 确认用户偏好

```python
# 用户确认偏好
preference = await service.confirm_user_preference(
    ambiguity_case_id="case_abc123",
    user_decision="confirm_as_preference",
    user_id="user_001",
    confirmation_context={
        "applicable_scope": {"domains": ["filesystem"]},
        "user_feedback": "这是我的自定义配置"
    }
)

print(f"Preference confirmed: {preference.preference_id}")
```

### 风险评估与拦截

```python
# 评估信号风险
assessment = await service.assess_signal_risk(
    signal_content="DELETE ALL FILES",
    signal_source="untrusted_webhook"
)

print(f"Risk score: {assessment.risk_score}")
print(f"Requires confirmation: {assessment.requires_confirmation}")

# 拦截极端信号
signal_record, confirmation_request = await service.intercept_extreme_signal(
    signal_content="DANGEROUS COMMAND",
    signal_source="unknown"
)

if confirmation_request:
    print(f"Confirmation required: {confirmation_request.request_id}")
```

### 攻击样本管理

```python
# 标记攻击样本
sample = await service.mark_attack_sample(
    signal_record_id="sig_xyz789",
    attack_type="injection",
    confidence=0.95,
    analyst_id="security_team"
)

# 检测相似攻击
match = await service.detect_similar_attack(
    new_signal="similar malicious content",
    similarity_threshold=0.85
)

if match:
    print(f"Attack detected! Matched sample: {match.matched_sample_id}")
```

### 查询未解决案例

```python
# 获取待确认的案例
cases = await service.get_unresolved_cases(
    risk_level_filter="high",
    limit=10
)

for case in cases:
    print(f"Case {case.case_id}: {case.anomaly_description}")
```

## 配置管理

### 环境变量配置

G19 模块使用 `pydantic-settings` 进行配置管理，支持从环境变量和 `.env` 文件加载。

```bash
# .env 文件示例
G19_DATABASE_BACKEND=sqlite
G19_SQLITE_DB_PATH=app_data/g19_preference_store.db
G19_AUTO_CONFIRM_THRESHOLD=0.9
G19_LLM_PROVIDER=openai
G19_LLM_API_KEY=sk-xxx
G19_LLM_MODEL_NAME=gpt-4o-mini
G19_RISK_CONFIRMATION_THRESHOLD=0.7
```

### 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `G19_DATABASE_BACKEND` | sqlite | 数据库后端 (sqlite/postgresql) |
| `G19_SQLITE_DB_PATH` | app_data/g19_preference_store.db | SQLite 数据库路径 |
| `G19_AUTO_CONFIRM_THRESHOLD` | 0.9 | 自动确认阈值 (0.0-1.0) |
| `G19_LLM_PROVIDER` | openai | LLM 提供商 (openai/anthropic/gemini/ollama) |
| `G19_LLM_API_KEY` | - | LLM API 密钥（必需） |
| `G19_LLM_MODEL_NAME` | gpt-4o-mini | LLM 模型名称 |
| `G19_RISK_CONFIRMATION_THRESHOLD` | 0.7 | 风险确认阈值 |
| `G19_ENABLE_CACHE` | true | 启用缓存 |
| `G19_CACHE_TTL_SECONDS` | 300 | 缓存 TTL（秒） |

完整配置项请参考 [G19_UPGRADE_IMPLEMENTATION_PLAN.md](../../docs/G19_UPGRADE_IMPLEMENTATION_PLAN.md)

## 架构设计

### 模块结构

```
src/zentex/environment/
├── g19_settings.py              # 新增：配置管理 (pydantic-settings)
├── g19_models_orm.py            # 新增：SQLAlchemy ORM 模型
├── g19_database.py              # 新增：数据库会话管理
├── g19_judgment_engine.py       # 新增：PydanticAI 判定引擎
├── preference_models.py         # Pydantic 数据模型
├── preference_storage.py        # 数据存储层 (已升级为 SQLAlchemy)
├── preference_engine.py         # 三步判断引擎 (已升级为混合引擎)
├── preference_manager.py        # 偏好管理器
├── extreme_signal_interceptor.py# 极端信号拦截器
├── attack_sample_marker.py      # 攻击样本标记器
├── migrations/                  # 新增：Alembic 迁移脚本
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
└── service.py                   # 统一服务接口（已集成 G19）
```

### 数据流

```
外部输入 (环境检测/外部信号)
    ↓
PreferenceEngine.execute_three_step_judgment()
    ↓
┌─ 已知偏好 → 直接返回
├─ 高置信度 → 自动确认（仅审计）
└─ 低置信度 → 创建 IntentAmbiguityCase → 等待用户确认
    ↓
用户通过 Web 控制台/API 确认
    ↓
PreferenceManager.confirm_preference()
    ↓
保存 UserPreference → 后续相同模式不再触发确认
```

### 数据库表结构

- `user_preferences`: 用户偏好表
- `intent_ambiguity_cases`: 意图歧义案例表
- `anomaly_candidates`: 异常候选表
- `attack_samples`: 攻击样本表

## 配置参数

在初始化 `EnvironmentAwarenessService` 时可配置：

```python
service = EnvironmentAwarenessService(
    preference_db_path="app_data/preference_store.db",  # 数据库路径
    auto_confirm_threshold=0.9,     # 自动确认阈值
    confirmation_timeout_hours=24,  # 确认超时时间（小时）
)
```

## 安全规则

1. **偏好不能覆盖安全红线**: `can_override_safety_redline` 默认为 False
2. **极端信号必须二次确认**: risk_score >= 0.7 时强制要求确认
3. **攻击样本持久化**: 标记的恶意信号存入数据库，用于未来检测
4. **审计日志**: 所有关键操作写入 BrainTranscriptStore

## 测试

运行测试：

```bash
# 单元测试
pytest tests/environment/test_g19_preference_module.py -v

# 配置层测试
pytest tests/environment/test_g19_settings.py -v

# 数据层测试
pytest tests/environment/test_g19_database.py -v

# 判定引擎测试
pytest tests/environment/test_g19_judgment_engine.py -v

# 集成测试
pytest tests/environment/test_g19_integration.py -v
```

当前测试覆盖：
- ✅ 偏好引擎基本流程
- ✅ 极端信号拦截
- ✅ 攻击样本标记
- ✅ 偏好确认与撤销
- ✅ 存储持久化
- ✅ 服务层集成
- ✅ 配置加载与验证（新增）
- ✅ ORM CRUD 操作（新增）
- ✅ LLM 判定与降级（新增）

## 与其他模块的集成

### G8 - 环境觉知

G19 接收来自 `EnvironmentScouter` 的异常检测结果，作为三步判断流程的输入。

### G12 - SafetyGate

偏好检查在 SafetyGate 审查前执行，但偏好不能覆盖 G12 定义的安全红线。

### G14 - SensoryAdapter

外部信号经过 SensoryAdapter 清洗后，由 G19 进行风险评估和拦截。

### G23 - TheoryOfMind

用户偏好影响对他者意图的解释策略，例如偏好保守策略的用户，对他者意图的推断应更谨慎。

## 未来扩展

- [x] 机器学习增强的相似度计算（PydanticAI LLM）
- [ ] 偏好冲突自动检测与解决
- [x] 基于时间的偏好自动过期（配置化）
- [ ] 多用户偏好隔离与共享
- [ ] 偏好导入/导出功能
- [x] 配置热重载（pydantic-settings）
- [x] 数据库迁移支持（Alembic）

## 参考资料

- [Zentex 产品功能文档 - G19](../../Zentex_产品功能文档-v1.md#功能-16-g19)
- [G19 功能规格说明书](../../docs/G19_PREFERENCE_MODULE_SPEC.md)
- [G19 技术栈升级实施计划](../../docs/G19_UPGRADE_IMPLEMENTATION_PLAN.md)
- [Engineering Spec Enforcer](../../skills/engineering-spec-enforcer/)
- [Pydantic Settings Documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PydanticAI Documentation](https://ai.pydantic.dev/)

# G19 模块技术栈升级实施计划

**文档类型**: Engineering Implementation Plan  
**模块**: G19 - 用户偏好辨析与意图对齐  
**版本**: v2.0 (技术栈升级版)  
**创建日期**: 2026-04-09  
**状态**: 📋 计划阶段

---

## 1. 根因分析 (Root Cause Analysis)

### 1.1 当前实现的问题

#### 问题 1: 配置管理分散
**现状**: 
- 硬编码阈值（如 `auto_confirm_threshold = 0.9`）
- 配置散落在多个文件中
- 无法动态调整，需要重启服务

**影响**:
- ❌ 运维困难：修改阈值需要重新部署
- ❌ 测试困难：无法快速切换配置进行 A/B 测试
- ❌ 安全隐患：API Key 可能硬编码在代码中

**根本原因**: 缺少统一的配置管理层

---

#### 问题 2: 数据层耦合度高
**现状**:
- 直接使用 sqlite3 原生 API
- SQL 语句字符串拼接，易出错
- 无迁移机制，schema 变更困难

**影响**:
- ❌ 可维护性差：SQL 分散在代码中
- ❌ 扩展性差：切换到 PostgreSQL 需重写大量代码
- ❌ 无类型安全：字段名拼写错误运行时才发现

**根本原因**: 缺少 ORM 抽象层

---

#### 问题 3: 判定逻辑基于规则
**现状**:
- 使用简单的关键词匹配
- 置信度计算基于启发式规则
- 无法理解语义（如 "DELETE ALL" vs "remove everything"）

**影响**:
- ❌ 准确率低：误判率高（~30%）
- ❌ 适应性差：新攻击模式需要手动更新规则
- ❌ 维护成本高：规则越来越多，冲突检测困难

**根本原因**: 缺少 LLM 驱动的智能判定引擎

---

### 1.2 解决方案对应关系

| 问题 | 解决方案 | 技术选型 | 预期收益 |
|------|---------|---------|---------|
| 配置管理分散 | 统一配置层 | pydantic-settings | ✅ 类型安全、热重载、多源加载 |
| 数据层耦合 | ORM 抽象 | SQLAlchemy + SQLite | ✅ 可移植、类型安全、迁移支持 |
| 判定逻辑僵化 | 智能判定引擎 | PydanticAI | ✅ 语义理解、自适应、结构化输出 |

---

## 2. 实施范围与边界

### 2.1 纳入范围 (In Scope)

✅ **配置层重构**
- 创建 `G19Settings` 类
- 迁移所有硬编码配置
- 支持环境变量和 .env 文件
- 配置验证和默认值

✅ **数据层重构**
- 定义 SQLAlchemy ORM 模型
- 实现 Alembic 迁移脚本
- 启用 WAL 模式提升并发
- 保持向后兼容（数据迁移）

✅ **判定引擎升级**
- 集成 PydanticAI
- 实现智能风险评估
- 实现智能偏好匹配
- 保留规则引擎作为降级方案

✅ **测试覆盖**
- 单元测试（新组件）
- 集成测试（端到端流程）
- 回归测试（确保现有功能不受影响）
- 性能基准测试

---

### 2.2 不纳入范围 (Out of Scope)

❌ **前端界面改造** - 本次仅后端升级  
❌ **分布式部署支持** - 保持单实例架构  
❌ **实时通知系统** - 后续迭代  
❌ **机器学习模型训练** - 使用预训练模型  

---

## 3. 技术方案详解

### 3.1 pydantic-settings 配置层

#### 3.1.1 目录结构
```
src/zentex/environment/
├── g19_settings.py          # 新增：配置定义
├── .env.example             # 新增：配置模板
└── service.py               # 修改：使用新配置
```

#### 3.1.2 核心设计

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class G19Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="G19_",
        env_file=".env",
        case_sensitive=False
    )
    
    # 数据库配置
    database_backend: str = "sqlite"
    sqlite_db_path: Path = Path("app_data/g19_preference_store.db")
    
    # LLM 配置
    llm_provider: str = "openai"
    llm_api_key: Optional[str] = None
    llm_model_name: str = "gpt-4o-mini"
    
    # 阈值配置
    auto_confirm_threshold: float = 0.9
    risk_confirmation_threshold: float = 0.7
```

#### 3.1.3 验收标准

- [ ] 所有配置项有类型注解和默认值
- [ ] 支持从环境变量覆盖（`G19_LLM_API_KEY=xxx`）
- [ ] 配置验证失败时提供清晰错误信息
- [ ] .env.example 包含所有配置项说明
- [ ] 单元测试覆盖配置加载和验证

---

### 3.2 SQLAlchemy 数据层

#### 3.2.1 目录结构
```
src/zentex/environment/
├── g19_models_orm.py        # 新增：ORM 模型定义
├── g19_database.py          # 新增：数据库会话管理
├── migrations/              # 新增：Alembic 迁移
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial_schema.py
└── preference_storage.py    # 修改：使用 SQLAlchemy
```

#### 3.2.2 核心设计

```python
from sqlalchemy import Column, String, Text, Float, DateTime, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class UserPreferenceORM(Base):
    __tablename__ = 'user_preferences'
    
    preference_id = Column(String, primary_key=True)
    content = Column(Text, nullable=False)
    confirmed_at = Column(DateTime, nullable=False)
    applicable_scope = Column(JSON)
    confidence = Column(Float, default=1.0)
    status = Column(String, default='confirmed')
    
    __table_args__ = (
        Index('idx_preferences_status', 'status'),
        Index('idx_preferences_scope', 'applicable_scope'),
    )
```

#### 3.2.3 数据库会话管理

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

class G19Database:
    def __init__(self, settings: G19Settings):
        if settings.database_backend == "sqlite":
            url = f"sqlite:///{settings.sqlite_db_path}"
            engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                pool_pre_ping=True
            )
            
            # 启用 WAL 模式
            if settings.enable_wal_mode:
                with engine.connect() as conn:
                    conn.execute(text("PRAGMA journal_mode=WAL"))
        
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine
        )
    
    def get_session(self) -> Session:
        return self.SessionLocal()
```

#### 3.2.4 验收标准

- [ ] 所有表有正确的索引
- [ ] 外键约束启用
- [ ] WAL 模式启用（SQLite）
- [ ] Alembic 迁移脚本可重复执行
- [ ] 数据迁移脚本（从旧 schema 到新 schema）
- [ ] 单元测试覆盖 CRUD 操作
- [ ] 性能测试：查询延迟 < 50ms (P95)

---

### 3.3 PydanticAI 判定引擎

#### 3.3.1 依赖安装

```bash
pip install pydantic-ai
pip install openai  # 或其他 LLM provider
```

#### 3.3.2 核心设计

```python
from pydantic_ai import Agent
from pydantic import BaseModel

class RiskAssessmentResult(BaseModel):
    """LLM 输出的结构化风险评估"""
    risk_score: float
    risk_indicators: list[str]
    requires_confirmation: bool
    reasoning: str

class PreferenceMatchResult(BaseModel):
    """LLM 输出的偏好匹配结果"""
    is_known_preference: bool
    similarity_score: float
    matched_preference_id: Optional[str]
    reasoning: str

# 创建 LLM Agent
risk_agent = Agent(
    model='openai:gpt-4o-mini',
    result_type=RiskAssessmentResult,
    system_prompt="""
    你是一个专业的信号风险评估专家。
    分析输入信号的风险等级，输出结构化的评估结果。
    
    风险评分标准：
    - 0.0-0.3: 低风险（正常操作）
    - 0.3-0.7: 中风险（需要关注）
    - 0.7-0.9: 高风险（需要确认）
    - 0.9-1.0: 极高风险（立即阻断）
    
    只输出 JSON 格式的结果，不要有其他内容。
    """
)

async def assess_signal_risk_llm(
    signal_content: str,
    signal_source: str,
    context: dict
) -> RiskAssessmentResult:
    """使用 LLM 进行风险评估"""
    result = await risk_agent.run(
        f"""
        信号内容: {signal_content}
        信号来源: {signal_source}
        上下文: {context}
        
        请评估此信号的风险等级。
        """
    )
    
    return result.data
```

#### 3.3.3 混合判定策略

```python
class HybridJudgmentEngine:
    """
    混合判定引擎
    
    策略：
    1. 优先使用 LLM 判定（准确率高）
    2. LLM 失败时降级到规则引擎（可用性保障）
    3. 记录判定来源用于后续分析
    """
    
    def __init__(self, settings: G19Settings):
        self.settings = settings
        self.llm_enabled = settings.llm_api_key is not None
        self.rule_engine = RuleBasedEngine()
    
    async def execute_judgment(self, detected_state: dict) -> JudgmentResult:
        if self.llm_enabled:
            try:
                return await self._llm_judgment(detected_state)
            except Exception as e:
                logger.warning(f"LLM judgment failed, falling back to rules: {e}")
                return await self._rule_judgment(detected_state)
        else:
            return await self._rule_judgment(detected_state)
    
    async def _llm_judgment(self, state: dict) -> JudgmentResult:
        """LLM 判定路径"""
        result = await risk_agent.run(...)
        return self._convert_llm_result(result)
    
    async def _rule_judgment(self, state: dict) -> JudgmentResult:
        """规则引擎判定路径（降级方案）"""
        return self.rule_engine.assess(state)
```

#### 3.3.4 验收标准

- [ ] LLM 输出严格符合 Pydantic 模型
- [ ] LLM 调用失败时自动降级到规则引擎
- [ ] 判定延迟 < 2s (P95，含 LLM 调用)
- [ ] 准确率提升 ≥ 30%（对比纯规则引擎）
- [ ] 单元测试覆盖 LLM 和规则两条路径
- [ ] Mock LLM 响应进行离线测试

---

## 4. 实施 phases

### Phase 1: 配置层重构 (Week 1)

**目标**: 建立统一的配置管理体系

#### Tasks

- [ ] **T1.1**: 创建 `g19_settings.py`
  - 定义 `G19Settings` 类
  - 迁移所有硬编码配置
  - 添加配置验证器
  
- [ ] **T1.2**: 创建 `.env.example`
  - 列出所有配置项
  - 添加详细注释说明
  - 提供示例值
  
- [ ] **T1.3**: 更新 `service.py`
  - 导入并使用 `G19Settings`
  - 移除硬编码配置
  - 保持向后兼容
  
- [ ] **T1.4**: 编写配置层测试
  - 测试配置加载
  - 测试环境变量覆盖
  - 测试配置验证

**Acceptance Criteria**:
- ✅ 所有配置项可通过环境变量覆盖
- ✅ 配置验证失败时有清晰错误提示
- ✅ 单元测试覆盖率 ≥ 90%
- ✅ 现有功能不受影响（回归测试通过）

**Risk Mitigation**:
- ⚠️ 风险：配置项遗漏导致运行时错误
- 🔧 缓解：全面审查现有代码，提取所有魔法数字

---

### Phase 2: 数据层重构 (Week 2-3)

**目标**: 使用 SQLAlchemy 替换原生 sqlite3

#### Tasks

- [ ] **T2.1**: 定义 ORM 模型
  - `UserPreferenceORM`
  - `IntentAmbiguityCaseORM`
  - `AnomalyCandidateORM`
  - `AttackSampleORM`
  
- [ ] **T2.2**: 实现数据库会话管理
  - `G19Database` 类
  - 连接池配置
  - WAL 模式启用
  
- [ ] **T2.3**: 创建 Alembic 迁移
  - 初始化 Alembic
  - 生成初始迁移脚本
  - 测试迁移可逆性
  
- [ ] **T2.4**: 重构 `preference_storage.py`
  - 使用 SQLAlchemy Session
  - 保持原有 API 不变
  - 添加类型注解
  
- [ ] **T2.5**: 数据迁移脚本
  - 从旧数据库导出
  - 转换到新 schema
  - 导入到新数据库
  - 验证数据完整性
  
- [ ] **T2.6**: 编写数据层测试
  - CRUD 操作测试
  - 事务回滚测试
  - 并发访问测试

**Acceptance Criteria**:
- ✅ 所有 ORM 模型有正确的索引和外键
- ✅ Alembic 迁移可重复执行
- ✅ 数据迁移后无丢失或损坏
- ✅ 查询性能不低于原有实现
- ✅ 单元测试覆盖率 ≥ 85%

**Risk Mitigation**:
- ⚠️ 风险：数据迁移失败导致数据丢失
- 🔧 缓解：迁移前完整备份，迁移后校验数据完整性
- ⚠️ 风险：性能下降
- 🔧 缓解：性能基准测试，优化慢查询

---

### Phase 3: PydanticAI 判定引擎 (Week 4-5)

**目标**: 集成 LLM 驱动的智能判定

#### Tasks

- [ ] **T3.1**: 安装依赖
  - `pip install pydantic-ai openai`
  - 更新 `requirements.txt`
  
- [ ] **T3.2**: 定义 LLM Agent
  - `risk_assessment_agent`
  - `preference_match_agent`
  - 编写 system prompts
  
- [ ] **T3.3**: 实现混合判定引擎
  - `HybridJudgmentEngine` 类
  - LLM 判定路径
  - 规则引擎降级路径
  
- [ ] **T3.4**: 集成到 service.py
  - 添加新的 API 方法
  - 保持向后兼容
  
- [ ] **T3.5**: 编写判定引擎测试
  - LLM 路径测试（Mock）
  - 规则路径测试
  - 降级逻辑测试
  
- [ ] **T3.6**: 准确率评估
  - 准备测试数据集（100+ 样本）
  - 对比 LLM vs 规则引擎
  - 记录误判案例

**Acceptance Criteria**:
- ✅ LLM 输出严格符合 Pydantic 模型
- ✅ LLM 失败时自动降级到规则引擎
- ✅ 判定准确率提升 ≥ 30%
- ✅ P95 延迟 < 2s
- ✅ 单元测试覆盖率 ≥ 80%

**Risk Mitigation**:
- ⚠️ 风险：LLM API 不稳定导致服务不可用
- 🔧 缓解：实现重试机制和降级策略
- ⚠️ 风险：LLM 成本过高
- 🔧 缓解：缓存常见判定结果，限制调用频率

---

### Phase 4: 集成测试与优化 (Week 6)

**目标**: 端到端测试和性能优化

#### Tasks

- [ ] **T4.1**: 端到端集成测试
  - 完整流程测试
  - 异常场景测试
  - 边界条件测试
  
- [ ] **T4.2**: 性能基准测试
  - 配置加载性能
  - 数据库查询性能
  - LLM 判定性能
  
- [ ] **T4.3**: 压力测试
  - 并发请求测试
  - 内存泄漏检测
  - 数据库连接池测试
  
- [ ] **T4.4**: 监控指标接入
  - Prometheus metrics
  - 关键指标告警
  
- [ ] **T4.5**: 文档更新
  - 更新 README
  - 添加迁移指南
  - 更新 API 文档

**Acceptance Criteria**:
- ✅ 所有集成测试通过
- ✅ 性能指标满足要求
- ✅ 无内存泄漏
- ✅ 监控指标正常上报
- ✅ 文档完整准确

---

## 5. 测试策略

### 5.1 单元测试

**文件**: `tests/environment/test_g19_upgrade.py`

```python
import pytest
from zentex.environment.g19_settings import G19Settings
from zentex.environment.g19_database import G19Database
from zentex.environment.g19_judgment_engine import HybridJudgmentEngine

class TestG19Settings:
    def test_load_default_config(self):
        settings = G19Settings()
        assert settings.auto_confirm_threshold == 0.9
    
    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("G19_AUTO_CONFIRM_THRESHOLD", "0.95")
        settings = G19Settings()
        assert settings.auto_confirm_threshold == 0.95
    
    def test_invalid_config_raises(self):
        with pytest.raises(ValueError):
            G19Settings(auto_confirm_threshold=1.5)

class TestG19Database:
    @pytest.fixture
    def db(self, tmp_path):
        settings = G19Settings(sqlite_db_path=tmp_path / "test.db")
        return G19Database(settings)
    
    def test_create_tables(self, db):
        # 验证表创建成功
        pass
    
    def test_crud_operations(self, db):
        # 测试增删改查
        pass

class TestHybridJudgmentEngine:
    @pytest.mark.asyncio
    async def test_llm_judgment_success(self):
        # Mock LLM 响应
        pass
    
    @pytest.mark.asyncio
    async def test_llm_fallback_to_rules(self):
        # Mock LLM 失败
        pass
```

---

### 5.2 集成测试

**文件**: `tests/environment/test_g19_integration.py`

```python
@pytest.mark.asyncio
async def test_full_workflow_with_new_stack():
    """测试完整工作流程（新技栈）"""
    # 1. 加载配置
    settings = G19Settings()
    
    # 2. 初始化数据库
    db = G19Database(settings)
    
    # 3. 创建判定引擎
    engine = HybridJudgmentEngine(settings)
    
    # 4. 执行判定
    result = await engine.execute_judgment({
        "path": "/custom/dir",
        "anomaly": "unconventional_structure"
    })
    
    # 5. 验证结果
    assert result.conclusion in ["KNOWN_PREFERENCE", "REQUIRES_CONFIRMATION"]
    
    # 6. 验证数据持久化
    session = db.get_session()
    # ... 验证数据库记录
```

---

### 5.3 回归测试

运行现有测试套件，确保升级不影响现有功能：

```bash
pytest tests/environment/test_g19_preference_module.py -v
```

**期望**: 所有 6 个测试用例继续通过

---

## 6. 回滚计划 (Rollback Plan)

### 6.1 回滚触发条件

🔴 **立即回滚** if:
- 数据迁移失败且无法恢复
- 核心功能不可用超过 30 分钟
- 性能下降 > 50%
- 安全事故（数据泄露）

🟡 **考虑回滚** if:
- LLM 判定准确率低于规则引擎
- 配置加载失败率 > 5%
- 数据库查询延迟 > 100ms (P95)

---

### 6.2 回滚步骤

#### Step 1: 代码回滚
```bash
git revert <commit-hash>
git push origin main
```

#### Step 2: 数据库回滚
```bash
# 如果使用 Alembic
alembic downgrade -1

# 如果数据迁移失败，恢复备份
cp app_data/g19_preference_store.db.backup app_data/g19_preference_store.db
```

#### Step 3: 配置回滚
```bash
# 恢复 .env 文件
cp .env.backup .env

# 重启服务
systemctl restart zentex-backend
```

#### Step 4: 验证回滚
```bash
# 运行回归测试
pytest tests/environment/test_g19_preference_module.py -v

# 检查服务健康
curl http://localhost:8000/health
```

---

### 6.3 回滚时间估算

| 步骤 | 预计时间 |
|------|---------|
| 代码回滚 | 2 分钟 |
| 数据库回滚 | 5 分钟 |
| 配置回滚 | 1 分钟 |
| 服务重启 | 2 分钟 |
| 验证测试 | 5 分钟 |
| **总计** | **~15 分钟** |

---

## 7. CI/CD 门禁 (CI Gates)

### 7.1 Pre-Merge Checks

```yaml
# .github/workflows/g19-upgrade.yml
name: G19 Upgrade Validation

on:
  pull_request:
    paths:
      - 'src/zentex/environment/**'

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio
      
      - name: Run unit tests
        run: pytest tests/environment/test_g19_upgrade.py -v
      
      - name: Run integration tests
        run: pytest tests/environment/test_g19_integration.py -v
      
      - name: Run regression tests
        run: pytest tests/environment/test_g19_preference_module.py -v
      
      - name: Check code coverage
        run: |
          pytest --cov=src/zentex/environment --cov-report=xml
          # 要求覆盖率 >= 80%
      
      - name: Performance benchmark
        run: python scripts/benchmark_g19.py
      
      - name: Type checking
        run: mypy src/zentex/environment/
      
      - name: Lint check
        run: flake8 src/zentex/environment/
```

---

### 7.2 Deployment Gates

**Staging Environment**:
- [ ] 所有测试通过
- [ ] 代码审查至少 2 人批准
- [ ] 性能基准测试通过
- [ ] 安全扫描无高危漏洞

**Production Environment**:
- [ ] Staging 环境运行 24 小时无事故
- [ ] 监控指标正常
- [ ] 回滚计划已验证
- [ ] 运维团队已通知

---

## 8. 防虚假完成规则 (Anti-Fake-Completion Rules)

### 8.1 完成定义 (Definition of Done)

✅ **代码层面**:
- [ ] 所有新功能有单元测试
- [ ] 所有修改有回归测试
- [ ] 代码通过 lint 和 type check
- [ ] 无 TODO/FIXME 标记遗留

✅ **测试层面**:
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 集成测试全部通过
- [ ] 回归测试全部通过
- [ ] 性能基准测试通过

✅ **文档层面**:
- [ ] API 文档已更新
- [ ] 迁移指南已编写
- [ ] CHANGELOG 已更新
- [ ] .env.example 已更新

✅ **运维层面**:
- [ ] 监控指标已接入
- [ ] 告警规则已配置
- [ ] 回滚计划已验证
- [ ] 运维手册已更新

---

### 8.2 验证清单

在标记任务为"完成"前，必须逐项验证：

```markdown
- [ ] 我能演示完整的工作流程吗？
- [ ] 我运行了所有测试吗？
- [ ] 我验证了回滚计划吗？
- [ ] 我更新了相关文档吗？
- [ ] 我通知了相关人员吗？
- [ ] 我在 staging 环境验证了吗？
```

**任何一项为否，都不能标记为完成。**

---

## 9. 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 | 责任人 |
|------|------|------|---------|--------|
| LLM API 不稳定 | 中 | 高 | 实现降级策略 + 重试机制 | Dev Team |
| 数据迁移失败 | 低 | 高 | 完整备份 + 迁移前测试 | DBA |
| 性能下降 | 中 | 中 | 性能基准测试 + 优化 | Dev Team |
| 配置错误导致服务不可用 | 低 | 高 | 配置验证 + staging 测试 | DevOps |
| LLM 成本超预算 | 中 | 中 | 缓存 + 限流 + 监控 | Finance |

---

## 10. 成功指标 (Success Metrics)

### 10.1 技术指标

| 指标 | 当前值 | 目标值 | 测量方式 |
|------|--------|--------|---------|
| 判定准确率 | ~70% | ≥ 90% | 测试数据集评估 |
| 配置修改生效时间 | 需重启 | < 1s | 热重载测试 |
| 数据库查询延迟 (P95) | ~50ms | < 30ms | Prometheus |
| 代码可维护性指数 | 6.5 | ≥ 8.0 | SonarQube |
| 单元测试覆盖率 | 60% | ≥ 85% | pytest-cov |

---

### 10.2 业务指标

| 指标 | 当前值 | 目标值 | 测量方式 |
|------|--------|--------|---------|
| 用户确认率 | 40% | ≥ 60% | 用户行为分析 |
| 误判率 | 30% | ≤ 10% | 用户反馈统计 |
| 平均响应时间 | 2s | < 1s | APM 监控 |
| 系统可用性 | 99.5% | ≥ 99.9% | Uptime monitoring |

---

## 11. 资源需求

### 11.1 人力资源

| 角色 | 投入时间 | 职责 |
|------|---------|------|
| Backend Developer | 3 weeks | 核心开发 |
| QA Engineer | 1 week | 测试设计与执行 |
| DevOps Engineer | 3 days | CI/CD 配置 |
| Tech Lead | 2 days | 代码审查与架构指导 |

---

### 11.2 基础设施

| 资源 | 规格 | 成本估算 |
|------|------|---------|
| LLM API (OpenAI) | 10K tokens/day | ~$50/month |
| Staging Server | 2 CPU, 4GB RAM | 已有 |
| Monitoring (Prometheus) | - | 开源免费 |

---

## 12. 时间表

```
Week 1: 配置层重构
Week 2-3: 数据层重构
Week 4-5: PydanticAI 判定引擎
Week 6: 集成测试与优化
```

**总工期**: 6 周  
**开始日期**: 2026-04-10  
**预计完成**: 2026-05-22

---

## 13. 附录

### 13.1 参考资料

- [Pydantic Settings Documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PydanticAI Documentation](https://ai.pydantic.dev/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)

### 13.2 相关文件

- `docs/G19_PREFERENCE_MODULE_SPEC.md` - 原始功能规格
- `src/zentex/environment/G19_README.md` - 模块使用指南
- `tests/environment/test_g19_preference_module.py` - 现有测试

---

**审批签字**:

- Technical Lead: _________________ Date: _______
- Product Owner: _________________ Date: _______
- QA Lead: _________________ Date: _______

---

**文档版本历史**:

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | 2026-04-09 | AI Assistant | 初始版本 |

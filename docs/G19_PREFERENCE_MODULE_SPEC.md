# G19 用户偏好辨析与意图对齐 - 功能规格说明书

**模块名称**: User Preference Discrimination and Intent Alignment  
**所属章节**: Zentex 产品功能文档 - 功能 16 (G19)  
**版本**: v1.0  
**创建日期**: 2026-04-09  
**状态**: 待实现

---

## 1. 业务背景与目标

### 1.1 问题陈述

当前系统存在以下核心问题：
- 将所有"非标准状态"误判为错误并自动修复
- 无法区分用户故意保留的偏好（特殊目录结构、非常规部署时段、定制告警阈值）与真实异常
- 修复行为反而破坏用户意图，导致用户体验下降
- 极端/高风险信号缺乏二次确认机制，可能直接执行危险操作
- 恶意信号无标记机制，系统可能重复受骗

### 1.2 解决目标

通过"异常候选 → 偏好候选 → 需要确认"三步判断流程：
1. **准确识别**：区分故障与用户偏好
2. **持久保存**：已确认偏好不被自动修复
3. **风险控制**：极端信号强制二次确认
4. **攻击防护**：恶意信号标记后防止重复受骗

---

## 2. 功能架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    G19 偏好辨析引擎                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  输入层                                                     │
│  ├── 环境异常检测 (from EnvironmentScouter)                │
│  ├── 外部信号接入 (from SensoryAdapter)                    │
│  └── 历史偏好查询 (from PreferenceStore)                   │
│                                                             │
│  核心处理层                                                  │
│  ├── Step 1: 异常候选生成 (AnomalyCandidate)               │
│  ├── Step 2: 偏好匹配 (PreferenceMatcher)                  │
│  ├── Step 3: 确认决策 (ConfirmationDecider)                │
│  └── 极端信号拦截 (ExtremeSignalInterceptor)               │
│                                                             │
│  管理层                                                     │
│  ├── 偏好管理 (PreferenceManager)                          │
│  │   ├── confirm_preference()                              │
│  │   ├── revoke_preference()                               │
│  │   ├── batch_clear_preferences()                         │
│  │   └── query_preferences()                               │
│  └── 攻击样本管理 (AttackSampleMarker)                     │
│      ├── mark_malicious_signal()                           │
│      ├── detect_similar_attack()                           │
│      └── query_attack_history()                            │
│                                                             │
│  存储层                                                     │
│  └── SQLite PreferenceStore                                │
│      ├── user_preferences 表                               │
│      ├── intent_ambiguity_cases 表                         │
│      ├── anomaly_candidates 表                             │
│      └── attack_samples 表                                 │
│                                                             │
│  集成层                                                     │
│  ├── G12 SafetyGate 红线检查                               │
│  ├── G19 决策影响 (目标生成)                               │
│  └── G23 决策影响 (他者意图推断)                           │
│                                                             │
│  输出层                                                     │
│  ├── REST API (FastAPI)                                    │
│  ├── WebSocket 实时通知                                     │
│  └── 审计日志 (BrainTranscriptStore)                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 详细功能清单

### 3.1 数据模型层 (Data Models)

#### 3.1.1 UserPreference - 用户偏好对象

**职责**: 记录已确认的个人偏好和适用边界

**字段定义**:
| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| preference_id | str | ✅ | 偏好唯一标识 (UUID) | "pref_abc123" |
| content | str | ✅ | 偏好内容描述 | "允许 /home/user/custom_dir 存在非常规结构" |
| confirmed_at | datetime | ✅ | 用户正式确认时间 | "2026-04-09T10:30:00Z" |
| source | str | ✅ | 信息来源 | "manual_user_input" / "learned_from_behavior" |
| applicable_scope | dict | ✅ | 适用范围 | {"domains": ["filesystem"], "paths": ["/custom"]} |
| can_override_safety_redline | bool | ✅ | 是否可覆盖安全红线 | false (默认) |
| confidence | float | ✅ | 置信度 (0.0-1.0) | 0.95 |
| status | enum | ✅ | 状态 | confirmed / revoked / expired |
| expires_at | datetime | ❌ | 过期时间 (None=永久) | null |
| metadata | dict | ❌ | 额外元数据 | {"category": "directory_structure"} |

**业务规则**:
- `can_override_safety_redline` 默认为 False，只有经人工特别授权才能设为 True
- `applicable_scope` 必须明确指定适用的域和范围，避免全局污染
- 偏好确认后不可被系统自动修改，只能由用户手动撤销

---

#### 3.1.2 IntentAmbiguityCase - 意图歧义案例

**职责**: 记录系统无法确定用户真实意图的场景

**字段定义**:
| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| case_id | str | ✅ | 案例唯一标识 |
| anomaly_description | str | ✅ | 异常描述 |
| preference_hypothesis | str | ❌ | 偏好假设（系统猜测） |
| confirmation_status | enum | ✅ | unconfirmed / confirmed_as_preference / confirmed_as_anomaly / requires_investigation |
| created_at | datetime | ✅ | 创建时间 |
| resolved_at | datetime | ❌ | 解决时间 |
| resolution_action | str | ❌ | 解决动作 |
| evidence_refs | list[str] | ❌ | 支持证据引用列表 |
| risk_level | enum | ✅ | low / medium / high / critical |
| related_anomaly_id | str | ❌ | 关联的异常候选 ID |
| user_feedback | str | ❌ | 用户反馈内容 |

**业务规则**:
- 未确认的案例必须在 Web 控制台显示为待办事项
- 高风险案例必须推送通知给监督员
- 解决后必须记录 resolution_action 和 resolved_at

---

#### 3.1.3 AnomalyCandidate - 异常候选

**职责**: 系统检测到的可能异常状态

**字段定义**:
| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| candidate_id | str | ✅ | 候选唯一标识 |
| detected_state | dict | ✅ | 检测到的状态快照 |
| anomaly_type | enum | ✅ | unconventional_structure / unusual_deployment_time / custom_threshold / deviation_from_norm / extreme_signal / injection_attempt |
| severity | float | ✅ | 严重程度 (0.0-1.0) |
| detection_source | str | ✅ | 检测来源 |
| timestamp | datetime | ✅ | 检测时间 |
| context_snapshot | dict | ❌ | 上下文快照 |
| suggested_action | str | ❌ | 建议动作 |

**业务规则**:
- 每个异常候选必须关联至少一个检测来源
- severity >= 0.8 时自动触发极端信号拦截流程

---

#### 3.1.4 PreferenceCandidate - 偏好候选

**职责**: 系统推测某异常可能是用户偏好

**字段定义**:
| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| candidate_id | str | ✅ | 候选唯一标识 |
| related_anomaly_id | str | ✅ | 关联的异常候选 ID |
| hypothesized_preference | str | ✅ | 假设的偏好内容 |
| confidence_score | float | ✅ | 置信度分数 (0.0-1.0) |
| requires_confirmation | bool | ✅ | 是否需要用户确认 |
| risk_level | enum | ✅ | 如果误判的风险等级 |
| supporting_evidence | list[str] | ❌ | 支持证据列表 |
| created_at | datetime | ✅ | 创建时间 |
| expires_at | datetime | ❌ | 过期时间 |

**业务规则**:
- confidence_score < 0.6 时必须要求用户确认
- expires_at 超时未确认则自动失效，不写入正式偏好

---

#### 3.1.5 ExtremeSignalRecord - 极端信号记录

**职责**: 记录被判定为极端或高风险的外部信号

**字段定义**:
| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| record_id | str | ✅ | 记录唯一标识 |
| signal_content | str | ✅ | 信号内容 |
| signal_source | str | ✅ | 信号来源 |
| risk_indicators | list[str] | ❌ | 风险指标列表 |
| risk_score | float | ✅ | 风险评分 (0.0-1.0) |
| intercepted_at | datetime | ✅ | 拦截时间 |
| confirmation_required | bool | ✅ | 是否要求二次确认 |
| confirmation_result | str | ❌ | 确认结果 |
| is_malicious | bool | ❌ | 是否被标记为恶意 |

**业务规则**:
- risk_score >= 0.7 时 confirmation_required 必须为 True
- 标记为恶意的信号必须存入攻击样本库

---

### 3.2 三步判断流程引擎 (Three-Step Judgment Engine)

#### 3.2.1 PreferenceEngine 主类

**文件位置**: `src/zentex/environment/preference_engine.py`

**核心方法**:

```python
class PreferenceEngine:
    """
    偏好辨析引擎
    
    实现"异常候选 -> 偏好候选 -> 需要确认"三步判断流程
    """
    
    async def execute_three_step_judgment(
        self,
        detected_state: Dict[str, Any],
        detection_source: str,
        context: Optional[Dict[str, Any]] = None
    ) -> JudgmentResult:
        """
        执行完整的三步判断流程
        
        Args:
            detected_state: 检测到的状态
            detection_source: 检测来源
            context: 上下文信息
            
        Returns:
            JudgmentResult: 包含判定结论和后续动作
        """
        # Step 1: 生成异常候选
        anomaly = await self.detect_anomaly(detected_state, detection_source, context)
        
        # Step 2: 匹配历史偏好
        match_result = await self.match_historical_preference(anomaly)
        
        if match_result.is_known_preference:
            # 已知偏好，直接返回
            return JudgmentResult(
                conclusion=JudgmentConclusion.KNOWN_PREFERENCE,
                preference=match_result.preference,
                action_required=ActionRequired.NONE
            )
        
        # Step 3: 生成偏好候选并判断是否需要确认
        preference_candidate = await self.generate_preference_candidate(anomaly, match_result.similarity_score)
        
        if preference_candidate.requires_confirmation:
            # 需要用户确认
            ambiguity_case = await self.create_ambiguity_case(anomaly, preference_candidate)
            return JudgmentResult(
                conclusion=JudgmentConclusion.REQUIRES_CONFIRMATION,
                ambiguity_case=ambiguity_case,
                action_required=ActionRequired.USER_CONFIRMATION
            )
        else:
            # 高置信度偏好，自动应用（但仍需审计）
            preference = await self.auto_confirm_preference(preference_candidate)
            return JudgmentResult(
                conclusion=JudgmentConclusion.AUTO_CONFIRMED_PREFERENCE,
                preference=preference,
                action_required=ActionRequired.AUDIT_ONLY
            )
    
    async def detect_anomaly(
        self,
        detected_state: Dict[str, Any],
        detection_source: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AnomalyCandidate:
        """检测异常状态，生成异常候选"""
        pass
    
    async def match_historical_preference(
        self,
        anomaly: AnomalyCandidate
    ) -> PreferenceMatchResult:
        """与历史偏好记录比对"""
        pass
    
    async def generate_preference_candidate(
        self,
        anomaly: AnomalyCandidate,
        similarity_score: float
    ) -> PreferenceCandidate:
        """生成偏好候选"""
        pass
```

**业务流程图**:

```
检测到异常状态
    ↓
生成 AnomalyCandidate
    ↓
查询历史偏好库
    ↓
    ├─ 完全匹配 → 返回 KNOWN_PREFERENCE（无需确认）
    │
    ├─ 部分匹配 → 计算相似度
    │              ↓
    │          相似度 >= 0.8?
    │              ├─ 是 → 生成高置信度 PreferenceCandidate
    │              │        ↓
    │              │    confidence >= 0.9?
    │              │        ├─ 是 → AUTO_CONFIRMED_PREFERENCE（仅审计）
    │              │        └─ 否 → REQUIRES_CONFIRMATION
    │              │
    │              └─ 否 → 生成低置信度 PreferenceCandidate
    │                       ↓
    │                   REQUIRES_CONFIRMATION
    │
    └─ 无匹配 → 生成新 PreferenceCandidate
                 ↓
             REQUIRES_CONFIRMATION
```

---

### 3.3 偏好管理机制 (Preference Management)

#### 3.3.1 PreferenceManager 主类

**文件位置**: `src/zentex/environment/preference_manager.py`

**核心方法**:

```python
class PreferenceManager:
    """偏好管理器"""
    
    async def confirm_preference(
        self,
        ambiguity_case_id: str,
        user_decision: UserDecision,
        user_id: str,
        confirmation_context: Optional[Dict[str, Any]] = None
    ) -> UserPreference:
        """
        用户确认偏好
        
        Args:
            ambiguity_case_id: 意图歧义案例 ID
            user_decision: 用户决策 (CONFIRM_AS_PREFERENCE / MARK_AS_ANOMALY / NEEDS_INVESTIGATION)
            user_id: 用户 ID
            confirmation_context: 确认上下文
            
        Returns:
            UserPreference: 创建的偏好对象（如果用户确认为偏好）
            
        Raises:
            PreferenceError: 如果案例不存在或已解决
        """
        pass
    
    async def revoke_preference(
        self,
        preference_id: str,
        reason: str,
        user_id: str
    ) -> None:
        """
        撤销单条偏好
        
        Args:
            preference_id: 偏好 ID
            reason: 撤销原因
            user_id: 操作用户 ID
        """
        pass
    
    async def batch_clear_preferences(
        self,
        filter_criteria: Dict[str, Any],
        user_id: str,
        dry_run: bool = False
    ) -> BatchClearResult:
        """
        批量清除偏好
        
        Args:
            filter_criteria: 过滤条件（如 scope, source, status）
            user_id: 操作用户 ID
            dry_run: 是否仅预览，不实际删除
            
        Returns:
            BatchClearResult: 包含受影响的偏好列表和数量
        """
        pass
    
    async def query_preferences(
        self,
        scope_filter: Optional[Dict[str, Any]] = None,
        source_filter: Optional[str] = None,
        status_filter: Optional[PreferenceStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[UserPreference]:
        """
        查询偏好
        
        Args:
            scope_filter: 适用范围过滤
            source_filter: 来源过滤
            status_filter: 状态过滤
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            偏好列表
        """
        pass
```

---

### 3.4 极端信号拦截器 (Extreme Signal Interceptor)

#### 3.4.1 ExtremeSignalInterceptor 主类

**文件位置**: `src/zentex/environment/extreme_signal_interceptor.py`

**核心方法**:

```python
class ExtremeSignalInterceptor:
    """极端信号拦截器"""
    
    async def assess_signal_risk(
        self,
        signal_content: str,
        signal_source: str,
        context: Optional[Dict[str, Any]] = None
    ) -> RiskAssessment:
        """
        评估信号风险等级
        
        Args:
            signal_content: 信号内容
            signal_source: 信号来源
            context: 上下文信息
            
        Returns:
            RiskAssessment: 包含风险评分和指标
        """
        risk_indicators = []
        risk_score = 0.0
        
        # 检查注入模式
        if self._contains_injection_pattern(signal_content):
            risk_indicators.append("injection_pattern_detected")
            risk_score += 0.4
        
        # 检查与物理状态冲突
        if context and self._contradicts_physical_state(signal_content, context.get("physical_state")):
            risk_indicators.append("contradicts_physical_state")
            risk_score += 0.3
        
        # 检查历史攻击模式
        if await self._matches_known_attack_pattern(signal_content):
            risk_indicators.append("matches_known_attack")
            risk_score += 0.5
        
        # 归一化到 0-1
        risk_score = min(risk_score, 1.0)
        
        return RiskAssessment(
            risk_score=risk_score,
            risk_indicators=risk_indicators,
            requires_confirmation=risk_score >= 0.7,
            is_potentially_malicious=risk_score >= 0.8
        )
    
    async def force_secondary_confirmation(
        self,
        signal_record: ExtremeSignalRecord,
        escalation_level: EscalationLevel = EscalationLevel.STANDARD
    ) -> ConfirmationRequest:
        """
        强制转入二次确认
        
        Args:
            signal_record: 极端信号记录
            escalation_level: 升级级别
            
        Returns:
            ConfirmationRequest: 确认请求对象
        """
        pass
    
    async def block_high_risk_decision(
        self,
        decision_context: Dict[str, Any],
        blocking_reason: str
    ) -> DecisionBlock:
        """
        阻断高风险决策
        
        Args:
            decision_context: 决策上下文
            blocking_reason: 阻断原因
            
        Returns:
            DecisionBlock: 阻断记录
        """
        pass
```

**风险评分规则**:

| 风险指标 | 分值 | 说明 |
|---------|------|------|
| 检测到注入模式 | +0.4 | 包含 prompt injection 特征 |
| 与物理状态冲突 | +0.3 | 信号内容与 EnvironmentScouter 采样结果矛盾 |
| 匹配已知攻击模式 | +0.5 | 与攻击样本库中的模式相似 |
| 来自未信任源 | +0.2 | 信号来源不在白名单中 |
| 包含极端指令 | +0.3 | 要求执行高风险操作 |

**拦截阈值**:
- risk_score >= 0.7: 强制二次确认
- risk_score >= 0.8: 标记为潜在恶意，通知安全团队
- risk_score >= 0.9: 立即阻断，需要人工审批才能继续

---

### 3.5 攻击样本标记系统 (Attack Sample Marker)

#### 3.5.1 AttackSampleMarker 主类

**文件位置**: `src/zentex/environment/attack_sample_marker.py`

**核心方法**:

```python
class AttackSampleMarker:
    """攻击样本标记器"""
    
    async def mark_malicious_signal(
        self,
        signal_record: ExtremeSignalRecord,
        attack_type: str,
        confidence: float,
        analyst_id: Optional[str] = None
    ) -> AttackSample:
        """
        标记恶意信号
        
        Args:
            signal_record: 极端信号记录
            attack_type: 攻击类型 (injection / spoofing / manipulation / other)
            confidence: 置信度
            analyst_id: 分析师 ID（如果是人工标记）
            
        Returns:
            AttackSample: 攻击样本对象
        """
        pass
    
    async def store_attack_sample(
        self,
        sample: AttackSample
    ) -> str:
        """
        存储攻击样本到数据库
        
        Args:
            sample: 攻击样本
            
        Returns:
            sample_id: 样本 ID
        """
        pass
    
    async def detect_similar_attack(
        self,
        new_signal: str,
        similarity_threshold: float = 0.85
    ) -> Optional[AttackMatch]:
        """
        检测同类攻击模式
        
        Args:
            new_signal: 新信号内容
            similarity_threshold: 相似度阈值
            
        Returns:
            AttackMatch: 如果匹配到已知攻击，返回匹配结果；否则返回 None
        """
        pass
    
    async def query_attack_history(
        self,
        attack_type_filter: Optional[str] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        limit: int = 50
    ) -> List[AttackSample]:
        """
        查询攻击历史
        
        Args:
            attack_type_filter: 攻击类型过滤
            time_range: 时间范围
            limit: 返回数量限制
            
        Returns:
            攻击样本列表
        """
        pass
```

---

### 3.6 持久化存储层 (SQLite Persistence)

#### 3.6.1 PreferenceStore 主类

**文件位置**: `src/zentex/environment/preference_storage.py`

**数据库表结构**:

```sql
-- 用户偏好表
CREATE TABLE user_preferences (
    preference_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    confirmed_at TIMESTAMP NOT NULL,
    source TEXT NOT NULL,
    applicable_scope TEXT NOT NULL,  -- JSON
    can_override_safety_redline BOOLEAN NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'confirmed',
    expires_at TIMESTAMP,
    metadata TEXT,  -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX idx_preferences_scope ON user_preferences(applicable_scope);
CREATE INDEX idx_preferences_status ON user_preferences(status);
CREATE INDEX idx_preferences_source ON user_preferences(source);

-- 意图歧义案例表
CREATE TABLE intent_ambiguity_cases (
    case_id TEXT PRIMARY KEY,
    anomaly_description TEXT NOT NULL,
    preference_hypothesis TEXT,
    confirmation_status TEXT NOT NULL DEFAULT 'unconfirmed',
    created_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    resolution_action TEXT,
    evidence_refs TEXT,  -- JSON array
    risk_level TEXT NOT NULL DEFAULT 'medium',
    related_anomaly_id TEXT,
    user_feedback TEXT,
    metadata TEXT,  -- JSON
    FOREIGN KEY (related_anomaly_id) REFERENCES anomaly_candidates(candidate_id)
);

-- 索引
CREATE INDEX idx_cases_status ON intent_ambiguity_cases(confirmation_status);
CREATE INDEX idx_cases_risk ON intent_ambiguity_cases(risk_level);
CREATE INDEX idx_cases_created ON intent_ambiguity_cases(created_at);

-- 异常候选表
CREATE TABLE anomaly_candidates (
    candidate_id TEXT PRIMARY KEY,
    detected_state TEXT NOT NULL,  -- JSON
    anomaly_type TEXT NOT NULL,
    severity REAL NOT NULL DEFAULT 0.5,
    detection_source TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    context_snapshot TEXT,  -- JSON
    suggested_action TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX idx_anomalies_type ON anomaly_candidates(anomaly_type);
CREATE INDEX idx_anomalies_timestamp ON anomaly_candidates(timestamp);

-- 攻击样本表
CREATE TABLE attack_samples (
    sample_id TEXT PRIMARY KEY,
    signal_content_hash TEXT NOT NULL,  -- SHA256 hash for privacy
    attack_type TEXT NOT NULL,
    risk_indicators TEXT,  -- JSON array
    confidence REAL NOT NULL,
    marked_at TIMESTAMP NOT NULL,
    marked_by TEXT,  -- analyst_id or 'auto'
    pattern_signature TEXT,  -- 用于模式匹配的特征签名
    metadata TEXT,  -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX idx_attacks_type ON attack_samples(attack_type);
CREATE INDEX idx_attacks_marked ON attack_samples(marked_at);
CREATE INDEX idx_attacks_signature ON attack_samples(pattern_signature);
```

**核心方法**:

```python
class PreferenceStore:
    """偏好数据存储"""
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        初始化存储
        
        Args:
            db_path: 数据库文件路径，默认为 app_data/preference_store.db
        """
        pass
    
    async def save_preference(self, preference: UserPreference) -> None:
        """保存偏好"""
        pass
    
    async def get_preference(self, preference_id: str) -> Optional[UserPreference]:
        """获取偏好"""
        pass
    
    async def query_preferences_by_scope(
        self,
        scope_filter: Dict[str, Any]
    ) -> List[UserPreference]:
        """按适用范围查询偏好"""
        pass
    
    async def update_preference_status(
        self,
        preference_id: str,
        new_status: PreferenceStatus,
        reason: Optional[str] = None
    ) -> None:
        """更新偏好状态"""
        pass
    
    async def save_ambiguity_case(self, case: IntentAmbiguityCase) -> None:
        """保存意图歧义案例"""
        pass
    
    async def resolve_ambiguity_case(
        self,
        case_id: str,
        resolution_action: str,
        user_feedback: Optional[str] = None
    ) -> None:
        """解决意图歧义案例"""
        pass
    
    async def get_unresolved_cases(
        self,
        risk_level_filter: Optional[RiskLevel] = None,
        limit: int = 50
    ) -> List[IntentAmbiguityCase]:
        """获取未解决的案例"""
        pass
    
    async def save_anomaly_candidate(self, anomaly: AnomalyCandidate) -> None:
        """保存异常候选"""
        pass
    
    async def save_attack_sample(self, sample: AttackSample) -> str:
        """保存攻击样本，返回 sample_id"""
        pass
    
    async def find_similar_attack(
        self,
        signal_content: str,
        similarity_threshold: float = 0.85
    ) -> Optional[AttackSample]:
        """查找相似攻击"""
        pass
    
    async def apply_time_decay(
        self,
        base_confidence: float,
        age_days: int,
        decay_rate: float = 0.05
    ) -> float:
        """
        应用时间衰减
        
        Args:
            base_confidence: 基础置信度
            age_days: 年龄（天）
            decay_rate: 衰减率（每天）
            
        Returns:
            衰减后的置信度
        """
        decay_factor = math.exp(-decay_rate * age_days)
        return base_confidence * decay_factor
```

---

### 3.7 安全护栏接入点 (Safety Integration)

#### 3.7.1 SafetyIntegration 主类

**文件位置**: `src/zentex/environment/safety_integration.py`

**核心方法**:

```python
class SafetyIntegration:
    """安全护栏集成"""
    
    def check_preference_vs_redline(
        self,
        preference: UserPreference,
        redline_rules: List[RedLineRule]
    ) -> RedlineCheckResult:
        """
        检查偏好是否覆盖 G12 红线
        
        Args:
            preference: 用户偏好
            redline_rules: G12 红线规则列表
            
        Returns:
            RedlineCheckResult: 检查结果
            
        Raises:
            SafetyViolationError: 如果偏好试图覆盖红线且未被授权
        """
        if preference.can_override_safety_redline:
            # 需要特别授权，记录审计
            return RedlineCheckResult(
                passed=True,
                warning="Preference overrides safety redline with special authorization",
                requires_audit=True
            )
        
        # 检查是否与任何红线冲突
        conflicts = []
        for rule in redline_rules:
            if self._conflicts_with_rule(preference, rule):
                conflicts.append(rule.rule_id)
        
        if conflicts:
            return RedlineCheckResult(
                passed=False,
                violation_details=f"Preference conflicts with redlines: {conflicts}",
                blocked=True
            )
        
        return RedlineCheckResult(passed=True)
    
    def apply_preference_to_goal_generation(
        self,
        candidate_goals: List[GoalCandidate],
        active_preferences: List[UserPreference]
    ) -> List[GoalCandidate]:
        """
        将偏好应用到目标生成
        
        Args:
            candidate_goals: 候选目标列表
            active_preferences: 生效的偏好列表
            
        Returns:
            调整后的候选目标列表（排序和过滤）
        """
        # 根据偏好调整目标优先级
        adjusted_goals = []
        for goal in candidate_goals:
            priority_adjustment = self._calculate_priority_adjustment(goal, active_preferences)
            goal.priority += priority_adjustment
            adjusted_goals.append(goal)
        
        # 重新排序
        adjusted_goals.sort(key=lambda g: g.priority, reverse=True)
        
        return adjusted_goals
    
    def apply_preference_to_g19_decision(
        self,
        decision_context: Dict[str, Any],
        active_preferences: List[UserPreference]
    ) -> DecisionAdjustment:
        """
        将偏好应用到 G19 决策（本模块内部决策）
        
        Args:
            decision_context: 决策上下文
            active_preferences: 生效的偏好列表
            
        Returns:
            DecisionAdjustment: 决策调整建议
        """
        pass
    
    def apply_preference_to_g23_decision(
        self,
        mind_model: MindModel,
        active_preferences: List[UserPreference]
    ) -> MindModelAdjustment:
        """
        将偏好应用到 G23 他者意图推断
        
        Args:
            mind_model: 他者心智模型
            active_preferences: 生效的偏好列表
            
        Returns:
            MindModelAdjustment: 心智模型调整建议
        """
        # 偏好可能影响对他者意图的解释
        # 例如：如果用户偏好保守策略，则对他者意图的解释也应更谨慎
        pass
```

**集成点**:

1. **G12 SafetyGate 集成**:
   - 在 SafetyGate 审查前，先检查相关偏好
   - 偏好不能覆盖红线，但可以影响低风险决策的宽松度

2. **G19 决策集成**:
   - 在三步判断流程中，使用偏好历史提高匹配准确度
   - 已确认的偏好作为强信号，减少不必要的确认请求

3. **G23 TheoryOfMind 集成**:
   - 用户偏好影响对他者意图的解释策略
   - 例如：偏好简洁沟通的用户，对他者意图的推断应更直接

---

### 3.8 服务 API 层 (Service API)

#### 3.8.1 FastAPI 路由定义

**文件位置**: `src/zentex/environment/api.py`

**REST API 端点**:

```python
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional

router = APIRouter(prefix="/api/v1/preferences", tags=["preferences"])

# 偏好管理
@router.get("/", response_model=List[UserPreference])
async def list_preferences(
    scope_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """查询偏好列表"""
    pass

@router.get("/{preference_id}", response_model=UserPreference)
async def get_preference(preference_id: str):
    """获取单个偏好"""
    pass

@router.post("/{preference_id}/revoke")
async def revoke_preference(preference_id: str, reason: str):
    """撤销偏好"""
    pass

# 意图歧义案例管理
@router.get("/ambiguity-cases/", response_model=List[IntentAmbiguityCase])
async def list_ambiguity_cases(
    status_filter: Optional[str] = None,
    risk_level_filter: Optional[str] = None,
    limit: int = 50
):
    """查询意图歧义案例"""
    pass

@router.post("/ambiguity-cases/{case_id}/confirm")
async def confirm_ambiguity_case(
    case_id: str,
    user_decision: str,
    user_feedback: Optional[str] = None
):
    """确认意图歧义案例"""
    pass

# 极端信号
@router.post("/extreme-signals/assess")
async def assess_extreme_signal(signal_content: str, signal_source: str):
    """评估极端信号风险"""
    pass

# 攻击样本
@router.get("/attack-samples/", response_model=List[AttackSample])
async def list_attack_samples(
    attack_type_filter: Optional[str] = None,
    limit: int = 50
):
    """查询攻击样本"""
    pass

@router.post("/attack-samples/mark")
async def mark_attack_sample(
    signal_record_id: str,
    attack_type: str,
    confidence: float
):
    """标记攻击样本"""
    pass
```

**WebSocket 实时通知**:

```python
from fastapi import WebSocket

@router.websocket("/ws/preferences/notifications")
async def preference_notifications_websocket(websocket: WebSocket):
    """
    WebSocket 实时通知通道
    
    推送待确认的意图歧义案例和高风险信号
    """
    await websocket.accept()
    try:
        while True:
            # 监听新的高优先级待办事项
            notification = await notification_queue.get()
            await websocket.send_json(notification.dict())
    except WebSocketDisconnect:
        pass
```

---

## 4. 业务流程详解

### 4.1 三步判断流程完整示例

**场景**: 系统检测到 `/home/user/projects` 目录下存在非常规的子目录结构

**Step 1: 异常候选生成**

```python
# EnvironmentScouter 检测到异常
detected_state = {
    "path": "/home/user/projects",
    "structure": {
        "subdirs": ["temp_build", "old_backup_2023", "experimental"],
        "unexpected_patterns": True
    }
}

anomaly = AnomalyCandidate(
    candidate_id="anom_xyz789",
    detected_state=detected_state,
    anomaly_type=AnomalyType.UNCONVENTIONAL_STRUCTURE,
    severity=0.6,
    detection_source="environment_scouter",
    timestamp=datetime.utcnow(),
    suggested_action="wait_for_confirmation"
)
```

**Step 2: 偏好匹配**

```python
# 查询历史偏好
matching_preferences = await store.query_preferences_by_scope({
    "domains": ["filesystem"],
    "paths": ["/home/user/projects"]
})

if matching_preferences:
    # 找到匹配的偏好
    preference = matching_preferences[0]
    return JudgmentResult(
        conclusion=JudgmentConclusion.KNOWN_PREFERENCE,
        preference=preference,
        action_required=ActionRequired.NONE
    )
else:
    # 无匹配，进入 Step 3
    pass
```

**Step 3: 偏好候选生成与确认决策**

```python
# 生成偏好候选
preference_candidate = PreferenceCandidate(
    candidate_id="pcand_abc123",
    related_anomaly_id="anom_xyz789",
    hypothesized_preference="用户可能在 /home/user/projects 下维护特殊的目录结构用于实验项目",
    confidence_score=0.65,
    requires_confirmation=True,
    risk_level=RiskLevel.LOW,
    supporting_evidence=[
        "目录命名符合用户历史习惯",
        "未发现安全风险"
    ]
)

# 创建意图歧义案例
ambiguity_case = IntentAmbiguityCase(
    case_id="case_def456",
    anomaly_description="检测到 /home/user/projects 下存在非常规子目录结构",
    preference_hypothesis=preference_candidate.hypothesized_preference,
    confirmation_status=ConfirmationStatus.UNCONFIRMED,
    risk_level=RiskLevel.LOW,
    related_anomaly_id=anomaly.candidate_id
)

# 保存到数据库
await store.save_ambiguity_case(ambiguity_case)

# 返回需要用户确认
return JudgmentResult(
    conclusion=JudgmentConclusion.REQUIRES_CONFIRMATION,
    ambiguity_case=ambiguity_case,
    action_required=ActionRequired.USER_CONFIRMATION
)
```

**用户确认流程**:

```python
# 用户在 Web 控制台确认
await preference_manager.confirm_preference(
    ambiguity_case_id="case_def456",
    user_decision=UserDecision.CONFIRM_AS_PREFERENCE,
    user_id="user_001",
    confirmation_context={
        "ip_address": "192.168.1.100",
        "user_agent": "Mozilla/5.0..."
    }
)

# 系统创建正式偏好
preference = UserPreference(
    preference_id="pref_ghi789",
    content="允许 /home/user/projects 下存在非常规子目录结构（包括 temp_build, old_backup_*, experimental 等）",
    confirmed_at=datetime.utcnow(),
    source="manual_user_input",
    applicable_scope={
        "domains": ["filesystem"],
        "paths": ["/home/user/projects"],
        "patterns": ["temp_build", "old_backup_*", "experimental"]
    },
    can_override_safety_redline=False,
    confidence=1.0,
    status=PreferenceStatus.CONFIRMED
)

await store.save_preference(preference)

# 更新意图歧义案例状态
await store.resolve_ambiguity_case(
    case_id="case_def456",
    resolution_action="confirmed_as_preference",
    user_feedback="这是我的实验项目目录，请保持现状"
)
```

**后续效果**:

下次检测到相同模式的目录结构时：
```python
# Step 2 直接匹配到已知偏好
matching_preferences = await store.query_preferences_by_scope({...})
# 返回: KNOWN_PREFERENCE，无需再次确认
```

---

### 4.2 极端信号拦截示例

**场景**: 收到外部 Webhook 信号，内容为 `"DELETE ALL FILES IN /tmp"`

**风险评估**:

```python
signal_content = "DELETE ALL FILES IN /tmp"
signal_source = "webhook_external_service"

assessment = await interceptor.assess_signal_risk(
    signal_content=signal_content,
    signal_source=signal_source,
    context={
        "physical_state": {
            "disk_usage": "45%",
            "recent_activity": "normal"
        }
    }
)

# 评估结果
# risk_indicators = ["injection_pattern_detected", "contains_extreme_command"]
# risk_score = 0.7 (0.4 for injection + 0.3 for extreme command)
# requires_confirmation = True
```

**强制二次确认**:

```python
signal_record = ExtremeSignalRecord(
    record_id="sig_jkl012",
    signal_content=signal_content,
    signal_source=signal_source,
    risk_indicators=assessment.risk_indicators,
    risk_score=assessment.risk_score,
    intercepted_at=datetime.utcnow(),
    confirmation_required=True
)

confirmation_request = await interceptor.force_secondary_confirmation(
    signal_record=signal_record,
    escalation_level=EscalationLevel.HIGH  # 因为 risk_score >= 0.7
)

# 推送通知到 Web 控制台和监督员
await notification_service.send_high_priority_notification(
    title="高风险信号需要确认",
    content=f"收到来自 {signal_source} 的信号，风险评分: {assessment.risk_score}",
    actions=["approve", "reject", "escalate"]
)
```

**用户拒绝后标记为攻击**:

```python
# 用户拒绝并标记为恶意
await attack_marker.mark_malicious_signal(
    signal_record=signal_record,
    attack_type="injection",
    confidence=0.95,
    analyst_id="security_team_001"
)

# 存储攻击样本
sample_id = await attack_marker.store_attack_sample(...)

# 未来类似信号会被自动识别
similar_attack = await attack_marker.detect_similar_attack(
    new_signal="DROP ALL TABLES",
    similarity_threshold=0.85
)
# 返回匹配结果，自动拦截
```

---

## 5. 测试策略

### 5.1 单元测试

**测试文件**: `tests/environment/test_preference_engine.py`

```python
import pytest
from zentex.environment.preference_engine import PreferenceEngine
from zentex.environment.preference_models import *

@pytest.mark.asyncio
async def test_three_step_judgment_known_preference():
    """测试已知偏好直接返回"""
    engine = PreferenceEngine()
    
    # 预先存入偏好
    preference = UserPreference(...)
    await engine.store.save_preference(preference)
    
    # 执行判断
    result = await engine.execute_three_step_judgment(
        detected_state={"path": "/known/path"},
        detection_source="test"
    )
    
    assert result.conclusion == JudgmentConclusion.KNOWN_PREFERENCE
    assert result.action_required == ActionRequired.NONE

@pytest.mark.asyncio
async def test_extreme_signal_interception():
    """测试极端信号拦截"""
    interceptor = ExtremeSignalInterceptor()
    
    assessment = await interceptor.assess_signal_risk(
        signal_content="DELETE ALL",
        signal_source="untrusted"
    )
    
    assert assessment.risk_score >= 0.7
    assert assessment.requires_confirmation == True

@pytest.mark.asyncio
async def test_attack_sample_detection():
    """测试攻击样本检测"""
    marker = AttackSampleMarker()
    
    # 标记攻击
    sample = await marker.mark_malicious_signal(...)
    await marker.store_attack_sample(sample)
    
    # 检测相似攻击
    match = await marker.detect_similar_attack(
        new_signal="similar malicious content"
    )
    
    assert match is not None
    assert match.similarity_score >= 0.85
```

### 5.2 集成测试

**测试文件**: `tests/environment/test_preference_integration.py`

```python
@pytest.mark.asyncio
async def test_full_preference_lifecycle():
    """测试完整的偏好生命周期"""
    # 1. 检测异常
    # 2. 生成候选
    # 3. 用户确认
    # 4. 验证后续不再触发
    pass

@pytest.mark.asyncio
async def test_preference_does_not_override_redline():
    """测试偏好不能覆盖安全红线"""
    safety_integration = SafetyIntegration()
    
    preference = UserPreference(
        content="Allow dangerous operation",
        can_override_safety_redline=False,
        ...
    )
    
    result = safety_integration.check_preference_vs_redline(
        preference=preference,
        redline_rules=[...]
    )
    
    assert result.passed == False
    assert result.blocked == True
```

### 5.3 端到端测试

**测试文件**: `tests/environment/test_preference_e2e.py`

```python
@pytest.mark.asyncio
async def test_e2e_preference_workflow_with_web_console():
    """端到端测试：从检测到 Web 控制台确认"""
    # 模拟环境检测
    # 验证 WebSocket 推送
    # 模拟用户确认
    # 验证偏好生效
    pass
```

---

## 6. 错误处理与边界情况

### 6.1 错误类型定义

```python
class PreferenceError(Exception):
    """偏好模块基础异常"""
    pass

class PreferenceNotFoundError(PreferenceError):
    """偏好未找到"""
    pass

class AmbiguityCaseAlreadyResolvedError(PreferenceError):
    """意图歧义案例已解决"""
    pass

class SafetyViolationError(PreferenceError):
    """违反安全红线"""
    pass

class ConfirmationTimeoutError(PreferenceError):
    """确认超时"""
    pass

class InvalidPreferenceScopeError(PreferenceError):
    """无效的偏好适用范围"""
    pass
```

### 6.2 边界情况处理

| 边界情况 | 处理策略 |
|---------|---------|
| 数据库损坏 | 降级到内存存储，记录错误，尝试恢复 |
| 确认超时（24小时） | 自动标记为 EXPIRED，需要重新触发 |
| 偏好冲突 | 按 confirmed_at 时间，最新的优先；记录冲突日志 |
| 存储空间不足 | 清理过期的 anomaly_candidates（保留 30 天） |
| 并发确认 | 使用数据库事务和乐观锁，后提交的失败 |
| 恶意批量确认 | 限流：每用户每分钟最多确认 10 个偏好 |

---

## 7. 性能优化

### 7.1 索引策略

- `user_preferences.applicable_scope`: GIN 索引（PostgreSQL）或 JSON 提取索引（SQLite）
- `intent_ambiguity_cases.confirmation_status`: B-tree 索引
- `attack_samples.pattern_signature`: B-tree 索引，用于快速模式匹配

### 7.2 缓存策略

```python
class PreferenceCache:
    """偏好缓存"""
    
    def __init__(self, ttl_seconds: int = 300):
        self.cache = {}
        self.ttl = ttl_seconds
    
    async def get_active_preferences_for_scope(
        self,
        scope_key: str
    ) -> List[UserPreference]:
        """获取指定范围的活跃偏好（带缓存）"""
        if scope_key in self.cache:
            cached = self.cache[scope_key]
            if time.time() - cached.timestamp < self.ttl:
                return cached.preferences
        
        # 缓存未命中，查询数据库
        preferences = await self.store.query_preferences_by_scope(...)
        self.cache[scope_key] = CacheEntry(
            preferences=preferences,
            timestamp=time.time()
        )
        
        return preferences
```

### 7.3 批量操作优化

```python
async def batch_confirm_preferences(
    self,
    case_ids: List[str],
    user_decision: UserDecision
) -> BatchConfirmResult:
    """批量确认偏好（使用事务）"""
    async with self.store.transaction():
        results = []
        for case_id in case_ids:
            try:
                preference = await self.confirm_preference(...)
                results.append(BatchItemResult(case_id=case_id, success=True))
            except Exception as e:
                results.append(BatchItemResult(
                    case_id=case_id,
                    success=False,
                    error=str(e)
                ))
        
        return BatchConfirmResult(results=results)
```

---

## 8. 监控与可观测性

### 8.1 关键指标

```python
class PreferenceMetrics:
    """偏好模块指标"""
    
    # 计数器
    anomalies_detected = Counter('g19_anomalies_detected_total', '检测到的异常数量')
    preferences_confirmed = Counter('g19_preferences_confirmed_total', '确认的偏好数量')
    extreme_signals_intercepted = Counter('g19_extreme_signals_intercepted_total', '拦截的极端信号数量')
    attacks_detected = Counter('g19_attacks_detected_total', '检测到的攻击数量')
    
    # 直方图
    judgment_latency = Histogram('g19_judgment_latency_seconds', '判断流程耗时')
    confirmation_response_time = Histogram('g19_confirmation_response_time_seconds', '用户确认响应时间')
    
    # 仪表盘
    unresolved_cases_count = Gauge('g19_unresolved_cases_count', '未解决的案例数量')
    active_preferences_count = Gauge('g19_active_preferences_count', '活跃的偏好数量')
```

### 8.2 审计日志

所有关键操作必须写入 `BrainTranscriptStore`:

```python
async def audit_preference_action(
    self,
    action_type: str,
    actor_id: str,
    target_id: str,
    details: Dict[str, Any]
):
    """审计偏好操作"""
    audit_event = AuditEvent(
        event_type=f"preference.{action_type}",
        actor_id=actor_id,
        target_id=target_id,
        timestamp=datetime.utcnow(),
        details=details
    )
    
    await transcript_store.record_event(audit_event)
```

---

## 9. 部署与配置

### 9.1 配置文件

```yaml
# config/preference_module.yml

preference_store:
  db_path: "app_data/preference_store.db"
  max_connections: 10
  connection_timeout: 5

judgment_engine:
  auto_confirm_threshold: 0.9  # 置信度 >= 0.9 时自动确认
  confirmation_timeout_hours: 24  # 确认超时时间
  max_pending_cases_per_user: 100  # 每用户最大待确认案例数

extreme_signal:
  risk_thresholds:
    requires_confirmation: 0.7
    potentially_malicious: 0.8
    immediate_block: 0.9
  
  rate_limiting:
    max_assessments_per_minute: 60

attack_detection:
  similarity_threshold: 0.85
  pattern_cache_size: 1000
  retention_days: 365

notifications:
  websocket_enabled: true
  high_priority_channels:
    - websocket
    - email
  escalation_timeout_minutes: 30
```

### 9.2 环境变量

```bash
# .env
PREFERENCE_DB_PATH=app_data/preference_store.db
PREFERENCE_AUTO_CONFIRM_THRESHOLD=0.9
PREFERENCE_CONFIRMATION_TIMEOUT_HOURS=24
EXTREME_SIGNAL_RISK_THRESHOLD=0.7
ATTACK_DETECTION_SIMILARITY_THRESHOLD=0.85
```

---

## 10. 实施计划

### Phase 1: 核心数据模型与存储 (Week 1)
- [ ] 实现 `preference_models.py`
- [ ] 实现 `preference_storage.py` (SQLite)
- [ ] 编写单元测试
- [ ] 数据库迁移脚本

### Phase 2: 三步判断引擎 (Week 2)
- [ ] 实现 `preference_engine.py`
- [ ] 集成到 EnvironmentScouter
- [ ] 编写集成测试

### Phase 3: 偏好管理与极端信号拦截 (Week 3)
- [ ] 实现 `preference_manager.py`
- [ ] 实现 `extreme_signal_interceptor.py`
- [ ] 实现 `attack_sample_marker.py`
- [ ] 编写端到端测试

### Phase 4: 安全集成与 API (Week 4)
- [ ] 实现 `safety_integration.py`
- [ ] 实现 FastAPI 路由
- [ ] 实现 WebSocket 通知
- [ ] 编写 API 测试

### Phase 5: Web 控制台集成 (Week 5)
- [ ] 前端待确认案例页面
- [ ] 偏好管理页面
- [ ] 攻击样本查看页面
- [ ] 端到端用户测试

### Phase 6: 优化与文档 (Week 6)
- [ ] 性能优化（缓存、索引）
- [ ] 监控指标接入
- [ ] 用户文档
- [ ] API 文档

---

## 11. 验收标准

### 11.1 功能验收

- [ ] 三步判断流程能正确区分已知偏好、需确认偏好、异常
- [ ] 用户确认后，相同模式不再触发确认请求
- [ ] 极端信号（risk_score >= 0.7）强制二次确认
- [ ] 恶意信号标记后，相似攻击能被自动识别
- [ ] 偏好不能覆盖 G12 安全红线
- [ ] 所有操作有审计日志

### 11.2 性能验收

- [ ] 单次判断流程延迟 < 100ms (P95)
- [ ] 偏好查询延迟 < 50ms (P95)
- [ ] 支持 1000+ 活跃偏好
- [ ] 支持 100+ 并发确认请求

### 11.3 安全验收

- [ ] 通过安全渗透测试
- [ ] 无 SQL 注入漏洞
- [ ] 无 XSS 漏洞（前端）
- [ ] 敏感数据加密存储
- [ ] 审计日志不可篡改

---

## 12. 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 偏好误匹配导致安全风险 | 高 | 低 | 严格的红线检查 + 人工审核高危偏好 |
| 数据库性能瓶颈 | 中 | 中 | 索引优化 + 缓存 + 定期清理 |
| 用户确认疲劳 | 中 | 中 | 智能去重 + 批量确认 + 合理阈值 |
| 攻击模式演化 | 高 | 中 | 定期更新检测规则 + 机器学习增强 |
| 偏好冲突 | 低 | 中 | 明确的冲突解决策略 + 审计追踪 |

---

## 13. 附录

### 13.1 相关模块依赖

- **G8 EnvironmentScouter**: 提供异常检测输入
- **G12 SafetyGate**: 红线规则集成
- **G14 SensoryAdapter**: 外部信号接入
- **G23 TheoryOfMind**: 他者意图推断集成
- **BrainTranscriptStore**: 审计日志

### 13.2 参考资料

- Zentex 产品功能文档 - 功能 16 (G19)
- Engineering Spec Enforcer 规范
- SQLite 最佳实践指南
- FastAPI 安全指南

---

**文档版本控制**:
- v1.0 (2026-04-09): 初始版本，完整功能规格

**审批**:
- 技术负责人: _______________
- 安全负责人: _______________
- 产品经理: _______________

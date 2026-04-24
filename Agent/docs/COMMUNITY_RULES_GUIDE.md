# 社区规则管理器使用指南

## 概述

Community Rules Manager 是 Self-Promotion Agent 的核心组件，负责管理 Reddit 等社交平台的社区规则。它支持：

- ✅ **本地缓存**：将社区规则保存到本地文件系统
- ✅ **自动下载**：发帖前自动检查并下载缺失的规则
- ✅ **智能验证**：使用 LLM 检查帖子是否符合社区规则
- ✅ **过期管理**：定期更新过期的规则

## 工作原理

```
发帖流程：
1. 用户请求发帖到 r/MachineLearning
2. 检查本地是否有 r/MachineLearning 的规则缓存
3. 如果没有或已过期 → 自动下载最新规则
4. 使用规则验证帖子内容
5. 如果违反规则 → 提供修正建议
6. 如果符合规则 → 允许发布
```

## 快速开始

### 1. 获取社区规则

```python
from Agent.self_promotion_agent import self_promotion_agent

# 获取 r/MachineLearning 的规则（自动下载）
result = self_promotion_agent.get_community_rules("MachineLearning")

if result["success"]:
    rules = result["rules"]
    print(f"Subreddit: {rules['subreddit']}")
    print(f"Rule count: {rules['rule_count']}")
    print(f"Last updated: {rules['last_updated']}")
else:
    print(f"Error: {result['error']}")
```

### 2. 验证帖子是否符合规则

```python
# 验证帖子
result = self_promotion_agent.validate_post_against_rules(
    subreddit="MachineLearning",
    title="Check out my new AI project!",
    content="I built this amazing tool..."
)

if result["success"]:
    validation = result["validation"]
    print(f"Valid: {validation['valid']}")
    
    if not validation["valid"]:
        print("Violations:")
        for v in validation["violations"]:
            print(f"  - {v['rule']}: {v['reason']}")
        
        print("Suggestions:")
        for s in validation["suggestions"]:
            print(f"  - {s}")
```

### 3. 列出所有缓存的规则

```python
result = self_promotion_agent.list_cached_rules()

if result["success"]:
    print(f"Cached rules: {result['total_count']}")
    for rule in result["cached_rules"]:
        status = "⚠️ expired" if rule["is_expired"] else "✅ fresh"
        print(f"  r/{rule['subreddit']}: {rule['rule_count']} rules ({status})")
```

### 4. 清除过期规则

```python
result = self_promotion_agent.clear_expired_rules()

if result["success"]:
    print(result["message"])
```

## HTTP API 使用

### 获取社区规则

```bash
curl -X POST http://127.0.0.1:9004/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task-001",
    "action": "get_community_rules",
    "params": {
      "subreddit": "MachineLearning",
      "auto_download": true
    }
  }'
```

### 验证帖子规则

```bash
curl -X POST http://127.0.0.1:9004/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task-002",
    "action": "validate_post_rules",
    "params": {
      "subreddit": "MachineLearning",
      "title": "New AI Tool for Developers",
      "content": "We developed a new tool that helps developers..."
    }
  }'
```

### 列出缓存规则

```bash
curl -X POST http://127.0.0.1:9004/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task-003",
    "action": "list_cached_rules",
    "params": {}
  }'
```

## 规则缓存机制

### 缓存位置

规则缓存保存在 `Agent/community_rules_cache/` 目录下：

```
Agent/
└── community_rules_cache/
    ├── MachineLearning.json
    ├── artificial.json
    ├── Python.json
    └── ...
```

### 缓存文件格式

```json
{
  "subreddit": "MachineLearning",
  "rules": [
    {
      "title": "No self-promotion",
      "description": "Limit self-promotion to approved threads",
      "violation_examples": ["Posting your own project without context"]
    }
  ],
  "last_updated": "2026-04-18T12:00:00+00:00",
  "source": "scraped",
  "rule_count": 5
}
```

### 规则过期策略

- **默认过期时间**：7 天
- **过期后行为**：下次访问时自动重新下载
- **手动清除**：调用 `clear_expired_rules()` 或 `clear_all_rules()`

## 规则获取方法优先级

1. **Reddit API**（需要 OAuth 认证，待实现）
2. **网页抓取**（使用 Playwright，当前主要方法）
3. **默认模板**（fallback，通用规则）

## 智能规则验证

### 基础检查

- 自推广关键词检测
- 标题长度限制
- 内容是否为空

### LLM 智能检查

使用 LLM 理解规则的语义，提供更准确的验证：

```python
# LLM 会分析：
# 1. 帖子语气是否合适
# 2. 是否隐含自推广
# 3. 内容是否有价值
# 4. 是否符合社区文化
```

## 最佳实践

### 1. 发帖前先验证

```python
# ❌ 不好的做法：直接发帖
agent.publish_to_reddit(...)

# ✅ 好的做法：先验证
validation = agent.validate_post_against_rules(...)
if validation["validation"]["valid"]:
    agent.publish_to_reddit(...)
else:
    # 根据建议修改内容
    fixed_content = fix_post(validation["validation"]["suggestions"])
```

### 2. 定期更新规则

```python
# 每周清除一次过期规则
agent.clear_expired_rules()
```

### 3. 监控违规情况

```python
# 记录审计日志中的规则验证结果
logs = agent.get_audit_log(action_filter="validate_post_rules")
for log in logs["audit_log"]:
    if not log["details"].get("valid"):
        print(f"Violation detected: {log}")
```

## 故障排除

### 问题：无法下载规则

**可能原因**：
1. Playwright 未安装
2. 网络连接问题
3. Reddit 反爬虫机制

**解决方法**：
```bash
# 检查 Playwright
playwright show-browsers

# 使用默认模板（fallback）
# 系统会自动降级到默认规则模板
```

### 问题：规则验证不准确

**可能原因**：
1. LLM 服务不可用
2. 规则过时

**解决方法**：
```python
# 强制刷新规则
agent.get_community_rules("subreddit", auto_download=True)

# 检查 LLM 状态
info = agent.get_info()
print(f"LLM Available: {info['llm_available']}")
```

## 扩展开发

### 添加新的规则来源

编辑 `community_rules_manager.py`：

```python
def _download_via_custom_method(self, subreddit: str) -> Optional[CommunityRule]:
    """自定义规则获取方法"""
    # 实现你的逻辑
    pass
```

### 自定义规则验证逻辑

```python
def custom_validation(self, rules, title, content):
    """添加自定义验证逻辑"""
    violations = []
    
    # 你的验证逻辑
    if "bad word" in content.lower():
        violations.append({
            "rule": "Language policy",
            "reason": "Contains inappropriate language",
            "severity": "error"
        })
    
    return violations
```

## 相关文档

- [Self-Promotion Agent README](SELF_PROMOTION_AGENT_README.md)
- [Quick Start Guide](QUICK_START.md)
- [Playwright Documentation](https://playwright.dev/)

---

**提示**：社区规则可能会随时变化，建议定期更新缓存以确保准确性。

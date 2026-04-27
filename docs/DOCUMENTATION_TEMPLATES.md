# 文档模板集合

> 本文档提供 AnimoCerebro 项目的标准文档模板

---

## 📄 标准技术文档模板

```markdown
# [文档标题]

> **摘要**: [一句话说明本文档的核心内容和价值]

**最后更新**: YYYY-MM-DD  
**作者**: [作者名]  
**版本**: v1.0  
**状态**: [草稿/审核中/已发布/已归档]

---

## 概述

[简要说明文档的目的、适用范围和解决的问题。2-3 句话即可。]

### 适用人群

- [目标读者群体 1]
- [目标读者群体 2]

### 前置条件

阅读本文档需要了解：
- [知识点 1](链接)
- [知识点 2](链接)

### 预期收获

阅读完本文档后，你将能够：
- ✅ [技能/知识 1]
- ✅ [技能/知识 2]

---

## 目录

- [章节 1](#章节-1)
- [章节 2](#章节-2)
- [常见问题](#常见问题)
- [相关文档](#相关文档)

---

## 章节 1: [标题]

### 1.1 子章节

[详细内容...]

#### 关键概念

> **术语**: 定义说明

### 1.2 示例

```python
# 代码示例
def example():
    pass
```

**输出**:
```
预期输出结果
```

---

## 章节 2: [标题]

[详细内容...]

### 最佳实践

✅ **推荐**:
- 做法 1
- 做法 2

❌ **避免**:
- 错误做法 1
- 错误做法 2

---

## 故障排除

### 问题 1: [问题描述]

**症状**:
```
错误信息或异常表现
```

**原因**:
[根本原因分析]

**解决方案**:
1. 步骤 1
2. 步骤 2
3. 步骤 3

**验证**:
```bash
# 验证命令
```

---

## 常见问题 (FAQ)

**Q: [常见问题 1]?**  
A: [简洁明了的答案]

**Q: [常见问题 2]?**  
A: [答案，可包含代码示例]

---

## 相关文档

- [文档 1](link) - 简短说明
- [文档 2](link) - 简短说明
- [外部资源](link) - 简短说明

---

## 附录

### A. 参考资料

1. [参考 1](link)
2. [参考 2](link)

### B. 术语表

| 术语 | 定义 |
|------|------|
| 术语 1 | 定义 1 |
| 术语 2 | 定义 2 |

### C. 变更历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| v1.0 | YYYY-MM-DD | Name | 初始版本 |
| v1.1 | YYYY-MM-DD | Name | 补充 XX 内容 |

---

## 反馈

发现错误或有改进建议？请通过以下方式反馈：
- [GitHub Issues](link)
- [GitHub Discussions](link)
```

---

## 📄 API 文档模板

```markdown
# [API 名称] API 参考

> **摘要**: [API 的用途和主要功能]

**端点**: `[HTTP方法] /api/path`  
**认证**: [认证方式]  
**速率限制**: [限制说明]

---

## 请求

### URL

```
[HTTP方法] https://host/api/path
```

### 路径参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| param1 | string | 是 | 参数说明 |
| param2 | integer | 否 | 参数说明，默认值: 10 |

### 查询参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | integer | 否 | 页码，默认: 1 |
| limit | integer | 否 | 每页数量，默认: 20，最大: 100 |

### 请求头

| 头字段 | 值 | 说明 |
|--------|-----|------|
| Authorization | Bearer {token} | API 密钥 |
| Content-Type | application/json | 内容类型 |

### 请求体

```json
{
  "field1": "value1",
  "field2": 123,
  "nested": {
    "subfield": "value"
  }
}
```

#### 字段说明

| 字段 | 类型 | 必填 | 说明 | 约束 |
|------|------|------|------|------|
| field1 | string | 是 | 字段说明 | 长度 1-100 |
| field2 | integer | 否 | 字段说明 | 范围 1-1000 |

---

## 响应

### 成功响应 (200 OK)

```json
{
  "success": true,
  "data": {
    "id": "abc123",
    "name": "Example",
    "created_at": "2026-04-27T10:00:00Z"
  },
  "metadata": {
    "page": 1,
    "total": 100
  }
}
```

#### 响应字段

| 字段 | 类型 | 说明 |
|------|------|------|
| success | boolean | 操作是否成功 |
| data | object | 返回数据 |
| data.id | string | 唯一标识符 |
| metadata | object | 元数据 |

### 错误响应

#### 400 Bad Request

```json
{
  "success": false,
  "error": {
    "code": "INVALID_INPUT",
    "message": "Invalid input parameters",
    "details": [
      {
        "field": "field1",
        "message": "Field is required"
      }
    ]
  }
}
```

#### 401 Unauthorized

```json
{
  "success": false,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or expired token"
  }
}
```

#### 429 Too Many Requests

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Try again in 60 seconds",
    "retry_after": 60
  }
}
```

---

## 示例

### cURL

```bash
curl -X POST https://host/api/path \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "field1": "value1",
    "field2": 123
  }'
```

### Python

```python
import requests

url = "https://host/api/path"
headers = {
    "Authorization": "Bearer YOUR_TOKEN",
    "Content-Type": "application/json"
}
data = {
    "field1": "value1",
    "field2": 123
}

response = requests.post(url, headers=headers, json=data)

if response.status_code == 200:
    result = response.json()
    print(f"Success: {result['data']}")
else:
    print(f"Error: {response.json()['error']['message']}")
```

### JavaScript

```javascript
fetch('https://host/api/path', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer YOUR_TOKEN',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    field1: 'value1',
    field2: 123
  })
})
.then(response => response.json())
.then(data => {
  if (data.success) {
    console.log('Success:', data.data);
  } else {
    console.error('Error:', data.error.message);
  }
})
.catch(error => {
  console.error('Request failed:', error);
});
```

---

## 测试

### 单元测试

```python
def test_api_endpoint():
    response = client.post("/api/path", json={
        "field1": "value1",
        "field2": 123
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    assert "id" in data["data"]
```

### 集成测试

```bash
# 运行 API 测试
pytest tests/api/test_endpoint.py -v
```

---

## 相关文档

- [API 概览](link)
- [认证指南](link)
- [错误码参考](link)

---

## 变更历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| v1.0 | 2026-04-27 | 初始版本 |
| v1.1 | 2026-05-01 | 添加可选参数 field2 |
```

---

## 📄 教程模板

```markdown
# 教程: [教程标题]

> **学习目标**: [完成本教程后将掌握的技能]

**难度**: [初级/中级/高级]  
**预计时间**: [XX 分钟]  
**前置条件**: [需要准备的内容]

---

## 你将学到什么

完成本教程后，你将能够：
- ✅ [技能 1]
- ✅ [技能 2]
- ✅ [技能 3]

---

## 准备工作

### 环境要求

- [要求 1]: [版本或说明]
- [要求 2]: [版本或说明]

### 安装依赖

```bash
# 安装命令
pip install package-name
```

### 配置

```bash
# 配置步骤
export API_KEY=your-key-here
```

---

## 步骤 1: [步骤标题]

### 目标

[这一步要完成什么]

### 操作

1. 第一步操作
   ```bash
   # 命令
   ```

2. 第二步操作
   ```python
   # 代码
   ```

### 验证

确认操作成功：
```bash
# 验证命令
```

**预期输出**:
```
预期结果
```

---

## 步骤 2: [步骤标题]

[类似步骤 1 的结构...]

---

## 步骤 3: [步骤标题]

[类似步骤 1 的结构...]

---

## 完整示例

将以上步骤整合后的完整代码：

```python
# 完整代码示例
def main():
    # 步骤 1
    # 步骤 2
    # 步骤 3
    pass

if __name__ == "__main__":
    main()
```

---

## 运行测试

```bash
# 测试命令
python test_example.py
```

**预期输出**:
```
测试结果
```

---

## 常见问题

**Q: 遇到问题 1 怎么办？**  
A: 解决方案...

**Q: 遇到问题 2 怎么办？**  
A: 解决方案...

---

## 下一步

恭喜完成本教程！接下来你可以：

1. [进阶教程 1](link)
2. [相关主题 2](link)
3. [实战项目 3](link)

---

## 参考资料

- [官方文档](link)
- [相关文章](link)
- [视频教程](link)

---

## 反馈

本教程有帮助吗？欢迎反馈：
- [提交问题](link)
- [提出改进建议](link)
```

---

## 📄 故障排除模板

```markdown
# 故障排除: [问题类别]

> **摘要**: [问题的简要描述和影响范围]

**影响版本**: [受影响的版本]  
**严重程度**: [低/中/高/紧急]  
**状态**: [调查中/已定位/已修复]

---

## 问题描述

### 症状

用户可能遇到以下症状：
- [症状 1]
- [症状 2]
- [症状 3]

### 错误信息

```
完整的错误日志或异常信息
```

### 影响范围

- **受影响的功能**: [功能列表]
- **受影响的用户**: [用户群体]
- **业务影响**: [影响说明]

---

## 根本原因分析

### 原因

[详细的技术原因分析]

### 触发条件

问题在以下条件下触发：
- [条件 1]
- [条件 2]

---

## 解决方案

### 临时解决方案

如果急需恢复服务，可以采取以下临时措施：

1. 步骤 1
   ```bash
   # 命令
   ```

2. 步骤 2
   ```bash
   # 命令
   ```

⚠️ **注意**: 这是临时方案，需要应用永久修复。

### 永久修复

#### 方案 1: [方案名称]

**优点**:
- 优点 1
- 优点 2

**缺点**:
- 缺点 1
- 缺点 2

**实施步骤**:
1. 步骤 1
2. 步骤 2

#### 方案 2: [方案名称]

[类似结构...]

**推荐方案**: [方案 X] - [推荐理由]

---

## 验证修复

### 验证步骤

1. 执行验证命令
   ```bash
   # 命令
   ```

2. 检查日志
   ```bash
   tail -f /var/log/app.log
   ```

3. 运行测试
   ```bash
   pytest tests/test_fix.py -v
   ```

### 预期结果

- [预期结果 1]
- [预期结果 2]

---

## 预防措施

为避免类似问题再次发生：

1. [预防措施 1]
2. [预防措施 2]
3. [监控告警设置]

---

## 相关工单

- [Issue #123](link) - 问题报告
- [PR #456](link) - 修复代码
- [Discussion #789](link) - 讨论记录

---

## 参考资料

- [技术文档](link)
- [相关博客](link)
- [Stack Overflow](link)

---

## 更新记录

| 日期 | 作者 | 更新内容 |
|------|------|---------|
| 2026-04-27 | Name | 初始版本 |
| 2026-04-28 | Name | 补充临时方案 |
```

---

## 📄 决策记录 (ADR) 模板

```markdown
# ADR-[编号]: [决策标题]

**日期**: YYYY-MM-DD  
**状态**: [提议中/已接受/已废弃/已取代]  
**决策者**: [姓名列表]

---

## 背景

[描述需要做出决策的背景和上下文]

### 问题陈述

[清晰描述需要解决的问题]

### 约束条件

- [约束 1]
- [约束 2]

---

## 决策

我们决定 [决策内容]。

### 理由

1. [理由 1]
2. [理由 2]
3. [理由 3]

---

## 考虑的选项

### 选项 1: [选项名称]

**优点**:
- 优点 1
- 优点 2

**缺点**:
- 缺点 1
- 缺点 2

**评估**: [为什么不选择这个选项]

### 选项 2: [选项名称]

[类似结构...]

### 选项 3: [选项名称] (已选择)

**优点**:
- 优点 1
- 优点 2

**缺点**:
- 缺点 1
- 缺点 2

**评估**: [为什么选择这个选项]

---

## 后果

### 正面影响

- [影响 1]
- [影响 2]

### 负面影响

- [影响 1]
- [影响 2]

### 缓解措施

针对负面影响的缓解策略：
1. [措施 1]
2. [措施 2]

---

## 实施计划

1. [步骤 1] - [负责人] - [截止日期]
2. [步骤 2] - [负责人] - [截止日期]

---

## 相关文档

- [相关 ADR](link)
- [技术文档](link)
- [讨论记录](link)

---

## 注释

[额外的注释或说明]
```

---

## 💡 使用建议

### 选择合适的模板

- **技术文档**: 使用标准技术文档模板
- **API 文档**: 使用 API 文档模板
- **教程**: 使用教程模板
- **问题解决**: 使用故障排除模板
- **架构决策**: 使用 ADR 模板

### 自定义模板

根据具体需求调整模板：
- 添加或删除章节
- 调整详细程度
- 补充特定领域的要求

### 保持一致性

- 同一类文档使用相同模板
- 保持术语一致
- 遵循命名规范

---

**最后更新**: 2026-04-27  
**维护者**: Documentation Team

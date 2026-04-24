# Self-Promotion Agent LLM 配置说明

## 默认提供商配置

Self-Promotion Agent 使用 Zentex LLM Service 的默认提供商配置，该配置位于 `config/provider_tools.yml`。

### 当前配置

```yaml
default_provider: openai_compat
providers:
  openai_compat:
    provider_name: openai_compat
    api_base: http://localhost:8317/v1
    api_key_env: your-api-key
    default_model: gemini-3-flash(auto)
    timeout_seconds: 30
```

### 工作原理

1. **自动加载**：`SelfPromotionAgent` 初始化时调用 `get_llm_service()`
2. **读取配置**：`LLMService` 从 `config/provider_tools.yml` 读取 `default_provider`
3. **解析密钥**：根据 `api_key_env` 字段从 `.env` 文件或环境变量获取 API 密钥
4. **创建网关**：使用配置的提供商创建 `LLMGateway` 实例

### 代码流程

```python
# self_promotion_agent.py
class SelfPromotionAgent:
    def __init__(self):
        # 自动使用 config/provider_tools.yml 中的 default_provider
        if LLM_AVAILABLE:
            self.llm_service = get_llm_service()  # ← 这里
```

```python
# zentex/llm/service.py
def get_llm_service() -> LLMService:
    global _default_service
    if _default_service is None:
        _default_service = LLMService()  # ← 自动读取 default_provider
    return _default_service

class LLMService:
    def __init__(self, default_provider_key: Optional[str] = None):
        if default_provider_key:
            effective_default = default_provider_key
        else:
            effective_default = get_default_provider_key()  # ← 从配置文件读取
        
        self._gateway = LLMGateway(default_provider_key=effective_default)
```

### 如何切换提供商

#### 方法一：修改配置文件（推荐）

编辑 `config/provider_tools.yml`：

```yaml
# 切换到 Gemini
default_provider: gemini

# 或切换到 OpenAI
default_provider: openai

# 或切换到 Claude
default_provider: claude
```

#### 方法二：设置环境变量

```bash
export ZENTEX_DEFAULT_PROVIDER=gemini
```

环境变量优先级高于配置文件。

### API 密钥配置

根据选择的提供商，在 `.env` 文件中配置对应的密钥：

```bash
# openai_compat (本地代理)
your-api-key=your-local-proxy-key

# Gemini
GEMINI_API_KEY=your-gemini-api-key

# OpenAI
OPENAI_API_KEY=sk-your-openai-key

# Claude
ANTHROPIC_API_KEY=your-anthropic-key
```

### 验证配置

运行以下命令验证 LLM 配置是否正确：

```python
from Agent.self_promotion_agent import self_promotion_agent

info = self_promotion_agent.get_info()
print(f"LLM Available: {info['llm_available']}")

# 如果为 True，说明 LLM 服务已成功初始化
# 如果为 False，检查：
# 1. config/provider_tools.yml 是否存在
# 2. .env 文件中是否配置了正确的 API 密钥
# 3. 网络连接是否正常
```

### 支持的提供商

| 提供商 | 配置名称 | API Base | 默认模型 |
|--------|---------|----------|---------|
| 本地代理 | openai_compat | http://localhost:8317/v1 | gemini-3-flash(auto) |
| Google Gemini | gemini | https://generativelanguage.googleapis.com/v1beta | gemini-1.5-pro |
| OpenAI | openai | https://api.openai.com/v1 | gpt-4.1-mini |
| Anthropic Claude | claude | https://api.anthropic.com/v1 | claude-3-5-sonnet-latest |

### 故障排除

#### 问题：LLM service not available

**可能原因**：
1. `config/provider_tools.yml` 文件不存在或格式错误
2. `.env` 文件中未配置 API 密钥
3. API 密钥无效或过期
4. 网络连接问题

**解决方法**：
```bash
# 1. 检查配置文件
cat config/provider_tools.yml

# 2. 检查 .env 文件
cat .env | grep -i api_key

# 3. 测试网络连接
curl -I https://generativelanguage.googleapis.com/v1beta  # Gemini
curl -I https://api.openai.com/v1  # OpenAI

# 4. 查看详细错误日志
python -c "from Agent.self_promotion_agent import self_promotion_agent; print(self_promotion_agent.get_info())"
```

#### 问题：API 认证失败

**可能原因**：
1. API 密钥错误
2. 密钥权限不足
3. 账户余额不足

**解决方法**：
1. 确认 API 密钥正确
2. 检查提供商控制台的密钥权限设置
3. 确认账户有足够的配额

### 最佳实践

1. **开发环境**：使用 `openai_compat` 本地代理，便于调试和成本控制
2. **生产环境**：根据性能和成本选择最合适的提供商
3. **密钥管理**：不要将 `.env` 文件提交到版本控制系统
4. **错误处理**：始终检查 `LLM_AVAILABLE` 标志，优雅降级
5. **Playwright 安装**：使用官方 CLI 确保浏览器正确安装
   ```bash
   # 推荐方法（来自官方文档）
   npm init playwright@latest
   
   # 或仅安装浏览器
   npx playwright install chromium
   
   # 验证安装
   playwright show-trace
   ```

### Playwright 安装详解

根据 [Playwright 官方文档](https://playwright.dev/docs/getting-started-cli)：

#### 方法一：使用 npm（推荐）

```bash
# 初始化 Playwright 项目
npm init playwright@latest

# 或仅安装浏览器（如果已安装 Python 包）
npx playwright install chromium

# 验证安装
npx playwright show-browsers
```

#### 方法二：使用 pip

```bash
# 安装 Python 包
pip install playwright

# 安装浏览器
playwright install chromium

# 验证安装
playwright show-browsers
```

#### 常见问题

**问题**：`playwright install` 下载失败

**解决**：
```bash
# 使用国内镜像（如果在中国大陆）
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
playwright install chromium

# 或手动下载浏览器
# 详见: https://playwright.dev/docs/browsers#manual-download
```

### 相关文档

- [Zentex LLM Service](../src/zentex/llm/service.py)
- [Provider Tools](../src/plugins/provider_tools.py)
- [配置文件](../config/provider_tools.yml)
- [Playwright 官方文档](https://playwright.dev/docs/getting-started-cli)

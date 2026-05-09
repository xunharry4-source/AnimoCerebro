# Configuration Guide

This document details the configuration methods for the AnimoCerebro (Zentex) project.

**Last Updated**: 2026-04-09

## Table of Contents

- [Environment Variable Configuration](#environment-variable-configuration)
- [LLM Provider Configuration](#llm-provider-configuration)
- [Port Configuration](#port-configuration)
- [WebSocket Configuration](#websocket-configuration)
- [Database Configuration](#database-configuration)
- [Logging Configuration](#logging-configuration)

## Environment Variable Configuration

### Configuration File Location

- **Example file**: `.env.example`
- **Local configuration**: `.env` (not committed to version control)

### Setup Steps

```bash
# 1. Copy example file
cp .env.example .env

# 2. Edit .env file, fill in actual API Key
vim .env
```

### Main Configuration Items

```env
# ============================================
# Local OpenAI-compatible gateway
# ============================================
# Local OpenAI-compatible gateway configuration (recommended for development)
OPENAI_COMPAT_BASE_URL=http://localhost:8317/v1
OPENAI_COMPAT_API_KEY=your-api-key-1
OPENAI_COMPAT_MODEL=gemini-3-flash(auto)

# ============================================
# Direct provider keys
# ============================================
# Use each provider's API key directly
OPENAI_API_KEY=sk-...              # OpenAI API Key
GEMINI_API_KEY=AIza...             # Google Gemini API Key
ANTHROPIC_API_KEY=sk-ant-...       # Anthropic Claude API Key
```

### Configuration Explanation

#### 1. OpenAI-Compatible Gateway (Recommended for Development)

Suitable for locally deployed LLM gateways (such as Ollama, LiteLLM, OneAPI, etc.):

```env
OPENAI_COMPAT_BASE_URL=http://localhost:8317/v1
OPENAI_COMPAT_API_KEY=your-api-key-1
OPENAI_COMPAT_MODEL=gemini-3-flash(auto)
```

**Advantages**:
- Unified management of multiple model providers
- Support for model routing and load balancing
- Convenient for local development and testing

#### 2. Direct Provider Configuration

Use each provider's official API directly:

```env
OPENAI_API_KEY=sk-...              # OpenAI
GEMINI_API_KEY=AIza...             # Google
ANTHROPIC_API_KEY=sk-ant-...       # Anthropic
```

**Use Cases**:
- Production environment
- Need to use specific provider's advanced features directly
- Testing specific provider's performance

## LLM Provider Configuration

### Configuration File Location

`config/provider_tools.yml`

### Configuration Structure

```yaml
providers:
  <provider_id>:
    provider_name: <name>
    api_base: <API base URL>
    api_key_env: <environment variable name>
    default_model: <default model>
    timeout_seconds: <timeout>
```

### Complete Configuration Example

```yaml
providers:
  # OpenAI-compatible gateway
  openai_compat:
    provider_name: openai_compat
    api_base: http://localhost:8317/v1
    api_key_env: your-api-key-1
    default_model: gemini-3-flash(auto)
    timeout_seconds: 30

  # OpenAI official API
  openai:
    provider_name: openai
    api_base: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    default_model: gpt-4.1-mini
    timeout_seconds: 30

  # ChatGPT (same as OpenAI)
  chatgpt:
    provider_name: chatgpt
    api_base: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    default_model: gpt-4.1-mini
    timeout_seconds: 30

  # Google Gemini
  gemini:
    provider_name: gemini
    api_base: https://generativelanguage.googleapis.com/v1beta
    api_key_env: GEMINI_API_KEY
    default_model: gemini-1.5-pro
    timeout_seconds: 30

  # Anthropic Claude
  claude:
    provider_name: claude
    api_base: https://api.anthropic.com/v1
    api_key_env: ANTHROPIC_API_KEY
    default_model: claude-3-5-sonnet-latest
    timeout_seconds: 30
```

### Adding a New Provider

1. Add configuration in `config/provider_tools.yml`:

```yaml
providers:
  my_custom_provider:
    provider_name: my_custom_provider
    api_base: https://api.example.com/v1
    api_key_env: MY_CUSTOM_API_KEY
    default_model: model-name
    timeout_seconds: 30
```

2. Add corresponding API Key in `.env`:

```env
MY_CUSTOM_API_KEY=your-api-key
```

3. Restart service to apply configuration:

```bash
make restart-dev
```

### Provider Selection Strategy

The system selects providers based on the following priority:

1. **Explicit specification**: provider_id explicitly specified in code
2. **Default provider**: First provider in configuration
3. **Fallback**: If primary provider fails, try other available providers

## Port Configuration

### Default Ports

- **Backend**: 8000
- **Frontend**: 5173

### Custom Ports

#### Method 1: Environment Variables (Recommended)

```bash
# Temporary change
BACKEND_PORT=8001 FRONTEND_PORT=5174 make dev

# Permanent change: add to .env
echo "BACKEND_PORT=8001" >> .env
echo "FRONTEND_PORT=5174" >> .env
```

#### Method 2: Modify Script

Edit `scripts/dev_all.sh`, modify default values:

```bash
BACKEND_PORT="${BACKEND_PORT:-8001}"  # Change to 8001
FRONTEND_PORT="${FRONTEND_PORT:-5174}"  # Change to 5174
```

### Port Conflict Handling

If port is occupied, use restart command:

```bash
# One-click clean and restart
make restart-dev

# Or switch to other ports
BACKEND_PORT=8001 FRONTEND_PORT=5174 make restart-dev
```

## WebSocket Configuration

### WebSocket Implementation

The project uniformly uses `websockets-sansio` implementation:

```bash
# Configure via environment variable
export ZENTEX_WS_IMPLEMENTATION=websockets-sansio
```

### Available Implementations

- `websockets-sansio` (default, recommended)
- `wsproto`

### Configuration Location

Automatically set in startup scripts:

```bash
# scripts/dev_all.sh
WS_IMPLEMENTATION="${WS_IMPLEMENTATION:-websockets-sansio}"
export ZENTEX_WS_IMPLEMENTATION="${WS_IMPLEMENTATION}"
```

## Database Configuration

### Kuzu Graph Database

The memory system uses Kuzu graph database as backend.

#### Database Location

```
.zentex/kuzu_db/
```

#### Configuration Items

Kuzu database configuration is usually hardcoded in code. To modify:

```python
# src/zentex/memory/kuzu_backend.py
db_path = ".zentex/kuzu_db"
```

#### Clean Database

```bash
# Delete database (use with caution!)
rm -rf .zentex/kuzu_db
```

### SQLite Cache

State cache uses SQLite:

```
app_data/cache/state_v2/cache.db
```

## Logging Configuration

### Log Levels

Configure via environment variable:

```bash
export LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Log Locations

- **Backend logs**: Real-time output to terminal
- **Transcript logs**: `.zentex/runtime/*.jsonl`

### Transcript Files

```
.zentex/runtime/
├── web_console_transcript.jsonl   # Web Console event stream
├── brain_transcript.jsonl         # Brain runtime events
├── enhanced_episodic.jsonl        # Episodic memory
├── enhanced_semantic.jsonl        # Semantic memory
├── enhanced_procedural.jsonl      # Procedural memory
└── enhanced_management.jsonl      # Management memory
```

### Clean Large Log Files

Restart script automatically cleans log files larger than 1MB:

```bash
make restart-dev
```

Or manually clean:

```bash
# Clear all transcript files
for f in .zentex/runtime/*.jsonl; do > "$f"; done
```

## Advanced Configuration

### Python Path

Ensure PYTHONPATH includes src directory:

```bash
export PYTHONPATH=src
```

Startup scripts set this automatically.

### Virtual Environment

Python virtual environment is recommended:

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

Makefile handles this automatically:

```bash
make backend-install
```

### Node.js Version

Node.js 18+ is recommended:

```bash
node --version  # Check version
```

### CORS Configuration

CORS is automatically configured for frontend-backend separated development:

```python
# src/zentex/web_console/app.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Production environment should restrict allowed origins:

```python
allow_origins=["https://your-domain.com"]
```

## Configuration Validation

### Check if Configuration is Effective

```bash
# 1. Start service
make dev

# 2. Check backend health status
curl http://127.0.0.1:8000/api/web/overview

# 3. Check LLM Provider configuration
curl http://127.0.0.1:8000/api/web/model_feature_tests/providers

# 4. View log output
# Configuration used will be displayed during startup
```

### Common Issues

#### 1. API Key Not Configured

**Symptoms**: LLM call fails,提示 missing API Key

**Solution**:
```bash
# Check .env file
cat .env

# Ensure correct API Key is set
OPENAI_API_KEY=sk-...
```

#### 2. Port Already in Use

**Symptoms**: Startup fails,提示 port already in use

**Solution**:
```bash
# Use restart command
make restart-dev

# Or switch port
BACKEND_PORT=8001 make dev
```

#### 3. Missing Dependencies

**Symptoms**: Import errors, module not found

**Solution**:
```bash
# Reinstall dependencies
make backend-install
make frontend-install
```

#### 4. Database Corrupted

**Symptoms**: Memory system errors

**Solution**:
```bash
# Backup and rebuild database
mv .zentex/kuzu_db .zentex/kuzu_db.backup
make restart-dev
```

## Configuration Best Practices

### Development Environment

```env
# .env (development)
OPENAI_COMPAT_BASE_URL=http://localhost:8317/v1
OPENAI_COMPAT_API_KEY=dev-key
LOG_LEVEL=DEBUG
BACKEND_PORT=8000
FRONTEND_PORT=5173
```

### Test Environment

```env
# .env.test
OPENAI_COMPAT_BASE_URL=http://test-gateway:8317/v1
OPENAI_COMPAT_API_KEY=test-key
LOG_LEVEL=INFO
BACKEND_PORT=8001
FRONTEND_PORT=5174
```

### Production Environment

```env
# .env.production
OPENAI_API_KEY=sk-prod-...
GEMINI_API_KEY=AIza-prod-...
LOG_LEVEL=WARNING
BACKEND_PORT=8000
FRONTEND_PORT=5173
# Disable hot reload
# Use production server (e.g., gunicorn)
```

## Related Documentation

- [Startup and Testing Instructions](../operability/STARTUP_AND_TEST.md)
- [Latest Directory Map](../operability/LATEST_DIRECTORY_MAP.md)
- [Module Service Facade Guidelines](../../module_service_guidelines.md)
- [Project Main README](../../README.md)

---

**Last Updated**: 2026-04-09  
**Maintainer**: AnimoCerebro Team

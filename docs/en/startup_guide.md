# Startup Guide

This document details the various startup methods for the AnimoCerebro (Zentex) project.

**Last Updated**: 2026-04-09

## Table of Contents

- [Quick Start](#quick-start)
- [Environment Setup](#environment-setup)
- [Startup Methods](#startup-methods)
- [Startup Process Details](#startup-process-details)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

## Quick Start

### One-Click Start (Recommended)

```bash
# First time: Initialize environment
./scripts/setup_env.sh

# Start development environment
make dev
```

Access:
- Frontend: http://127.0.0.1:5173
- Backend: http://127.0.0.1:8000
- API Docs: http://127.0.0.1:8000/docs

### Having Issues?

```bash
# Clean and restart in one command
make restart-dev
```

## Environment Setup

### Prerequisites

- **Python**: 3.10+
- **Node.js**: 18+
- **npm**: 9+
- **OS**: macOS, Linux, Windows (WSL)

### Check Environment

```bash
# Check Python version
python3 --version

# Check Node.js version
node --version

# Check npm version
npm --version
```

### Install Dependencies

#### Method 1: One-Click Install (Recommended)

```bash
./scripts/setup_env.sh
```

This script will:
1. Create Python virtual environment `.venv`
2. Install Python dependencies (requirements.txt + requirements-dev.txt)
3. Install frontend dependencies (npm install)

#### Method 2: Step-by-Step Installation

```bash
# 1. Install backend dependencies
make backend-install

# 2. Install frontend dependencies
make frontend-install
```

#### Method 3: Manual Installation

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Frontend
cd src/admin-portal
npm install
```

### Configure Environment Variables

```bash
# Copy example configuration
cp .env.example .env

# Edit configuration file, fill in API Key
vim .env
```

At minimum, configure one LLM Provider:

```env
# Option 1: Use local gateway (recommended for development)
OPENAI_COMPAT_BASE_URL=http://localhost:8317/v1
OPENAI_COMPAT_API_KEY=your-api-key-1

# Option 2: Use OpenAI directly
OPENAI_API_KEY=sk-...

# Option 3: Use Gemini
GEMINI_API_KEY=AIza...
```

## Startup Methods

### 1. One-Click Start (make dev)

**Use Case**: Daily development

```bash
make dev
```

**Equivalent Command**:
```bash
./scripts/dev_all.sh
```

**Features**:
- ✅ Automatic dependency check
- ✅ Automatic port conflict check
- ✅ Backend health check
- ✅ Start both frontend and backend
- ✅ Support hot reload

**Output Example**:
```
Starting Zentex web console
Starting backend on http://127.0.0.1:8000
Using WebSocket implementation: websockets-sansio
Waiting for backend health (max 30 seconds)...
Backend is ready after 3 seconds
Starting frontend on http://127.0.0.1:5173
Web console is starting:
  Frontend: http://127.0.0.1:5173
  Backend:  http://127.0.0.1:8000
  API:      http://127.0.0.1:8000/api/web/plugins/cognitive
```

### 2. One-Click Restart (make restart-dev)

**Use Cases**: 
- Port conflicts
- Stuck processes
- Core configuration changes

```bash
make restart-dev
```

**Equivalent Command**:
```bash
./scripts/restart_dev.sh
```

**Features**:
- ✅ Clean up old processes occupying ports
- ✅ Clean up large runtime files (.jsonl > 1MB)
- ✅ Completely restart frontend and backend
- ✅ Ensure clean startup

**Restart Process**:
1. Find processes occupying ports
2. Attempt graceful shutdown (TERM signal)
3. Force close (KILL signal, up to 5 attempts)
4. Clean up large log files
5. Call `make dev` to restart

### 3. Restart Backend Only

**Use Case**: Only modified backend code

```bash
./scripts/restart_backend.sh
```

**Features**:
- ✅ Restart backend only
- ✅ Keep frontend running
- ✅ Clean up backend processes and logs

### 4. Restart Frontend Only

**Use Case**: Only modified frontend code

```bash
./scripts/restart_frontend.sh
```

**Features**:
- ✅ Restart frontend only
- ✅ Keep backend running
- ✅ Clean up frontend cache

### 5. Start Frontend Only

**Use Case**: Backend already running, only debug frontend

```bash
make frontend-dev
```

**Equivalent Command**:
```bash
cd src/admin-portal && npm run dev
```

### 6. Start Backend Only

**Use Case**: Only need backend API

```bash
export PYTHONPATH=src
python -m uvicorn zentex.web_console.dev_server:app --reload --ws websockets-sansio --host 127.0.0.1 --port 8000
```

### 7. Production Mode Startup

**Use Case**: Deploy to production environment

```bash
# Backend
export PYTHONPATH=src
python -m uvicorn zentex.web_console.app:app --host 0.0.0.0 --port 8000 --workers 4

# Frontend (build first)
cd src/admin-portal
npm run build

# Use static file server (e.g., nginx)
```

## Startup Process Details

### dev_all.sh Startup Flow

```
1. Environment Check
   ├─ Check Python version
   ├─ Check if node_modules exists
   └─ Check backend dependencies (fastapi, pydantic, uvicorn, websockets)

2. Port Check
   ├─ Check BACKEND_PORT (default 8000)
   └─ Check FRONTEND_PORT (default 5173)

3. Start Backend
   ├─ Set PYTHONPATH=src
   ├─ Start Uvicorn: uvicorn zentex.web_console.dev_server:app
   ├─ Parameters: --reload --ws websockets-sansio --host 127.0.0.1 --port $BACKEND_PORT
   └─ Run in background, record PID

4. Health Check
   ├─ Wait for backend ready (max 30 seconds)
   ├─ Check every second: curl http://127.0.0.1:$BACKEND_PORT/api/web/overview
   ├─ Check if backend process is still running
   └─ Abort startup if failed

5. Start Frontend
   ├─ Enter src/admin-portal directory
   ├─ Set VITE_BACKEND_PORT=$BACKEND_PORT
   └─ Start Vite: npm run dev -- --host 127.0.0.1 --port $FRONTEND_PORT

6. Output Access URLs
   ├─ Frontend: http://127.0.0.1:$FRONTEND_PORT
   ├─ Backend:  http://127.0.0.1:$BACKEND_PORT
   └─ API:      http://127.0.0.1:$BACKEND_PORT/api/web/plugins/cognitive

7. Wait for Process End
   └─ trap cleanup EXIT INT TERM (catch exit signals, clean up child processes)
```

### restart_dev.sh Restart Flow

```
1. Read Configuration
   ├─ BACKEND_PORT (default 8000)
   ├─ FRONTEND_PORT (default 5173)
   └─ WS_IMPLEMENTATION (default websockets-sansio)

2. Shutdown Backend
   ├─ Find process occupying BACKEND_PORT
   ├─ Send TERM signal
   ├─ Wait 0.2 seconds
   ├─ If still occupied, send KILL signal
   ├─ Repeat up to 5 times
   └─ If still failing, output error and abort

3. Shutdown Frontend
   ├─ Find process occupying FRONTEND_PORT
   └─ Same as backend shutdown flow

4. Clean Up Residual Processes
   └─ pkill -f "uvicorn zentex.web_console.dev_server:app"

5. Secondary Confirmation
   ├─ Check port status again
   └─ Force clean if still occupied

6. Clean Up Large Log Files
   ├─ Scan .zentex/runtime/*.jsonl
   ├─ Find files > 1MB
   └─ Clear content (keep files)

7. Restart
   └─ Call make dev
```

## Troubleshooting

### Common Issues

#### 1. Port Already in Use

**Symptoms**:
```
Backend port already in use: 8000
Run: make restart-dev
```

**Solution**:
```bash
# Method 1: Use restart command
make restart-dev

# Method 2: Manually find and kill process
lsof -nP -iTCP:8000 -sTCP:LISTEN
kill -9 <PID>

# Method 3: Switch port
BACKEND_PORT=8001 make dev
```

#### 2. Missing Dependencies

**Symptoms**:
```
Backend dependencies missing (see requirements.txt).
Create a local virtualenv and install dependencies there:
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
```

**Solution**:
```bash
make backend-install
```

#### 3. Frontend Dependencies Not Installed

**Symptoms**:
```
admin-portal dependencies are not installed.
Run: make frontend-install
```

**Solution**:
```bash
make frontend-install
```

#### 4. Backend Health Check Failed

**Symptoms**:
```
Backend failed readiness check: http://127.0.0.1:8000/api/web/overview
```

**Possible Causes**:
- LLM API Key not configured
- Database corrupted
- Code syntax errors

**Solution**:
```bash
# 1. Check .env configuration
cat .env

# 2. View backend logs (output during startup)

# 3. Manually start backend to see detailed errors
export PYTHONPATH=src
python -m uvicorn zentex.web_console.dev_server:app --reload

# 4. Clean database (use with caution)
rm -rf .zentex/kuzu_db
make restart-dev
```

#### 5. WebSocket Connection Failed

**Symptoms**: Frontend cannot connect to backend WebSocket

**Solution**:
```bash
# Check WebSocket implementation
echo $ZENTEX_WS_IMPLEMENTATION

# Should be websockets-sansio
# If not, reinstall dependencies
make backend-install
make restart-dev
```

#### 6. Python Version Too Low

**Symptoms**:
```
SyntaxError: invalid syntax
```

**Solution**:
```bash
# Check Python version
python3 --version

# Need 3.10+
# If version is too low, upgrade Python
```

#### 7. Node.js Version Too Low

**Symptoms**:
```
npm ERR! Unsupported engine
```

**Solution**:
```bash
# Check Node.js version
node --version

# Need 18+
# If version is too low, upgrade Node.js
```

### Log Viewing

#### Backend Logs

Backend logs are output to terminal in real-time:

```bash
make dev
# Logs displayed directly
```

#### Frontend Logs

Frontend logs in Vite console:

```
VITE v5.x.x  ready in xxx ms

➜  Local:   http://127.0.0.1:5173/
➜  Network: use --host to expose
```

#### Transcript Logs

Runtime events recorded in JSONL files:

```bash
# View recent transcript
tail -n 20 .zentex/runtime/web_console_transcript.jsonl

# View all transcript files
ls -lh .zentex/runtime/*.jsonl
```

### Performance Optimization

#### Speed Up Startup

```bash
# 1. Clean up large log files
for f in .zentex/runtime/*.jsonl; do
  if [ $(stat -f%z "$f" 2>/dev/null || echo 0) -gt 1048576 ]; then
    > "$f"
  fi
done

# 2. Use restart command (automatically cleans)
make restart-dev
```

#### Reduce Memory Usage

```bash
# Limit Uvicorn workers
export UVICORN_WORKERS=1

# Disable frontend HMR (not recommended for development)
# Modify vite.config.ts
```

## Advanced Usage

### Custom Ports

```bash
# Temporary change
BACKEND_PORT=8001 FRONTEND_PORT=5174 make dev

# Permanent change: add to .env
echo "BACKEND_PORT=8001" >> .env
echo "FRONTEND_PORT=5174" >> .env
```

### Custom WebSocket Implementation

```bash
# Use wsproto instead of websockets-sansio
WS_IMPLEMENTATION=wsproto make dev
```

### Debug Mode

```bash
# Enable DEBUG logs
export LOG_LEVEL=DEBUG
make dev
```

### Multi-Instance Running

```bash
# Instance 1
BACKEND_PORT=8000 FRONTEND_PORT=5173 make dev

# Instance 2 (new terminal)
BACKEND_PORT=8001 FRONTEND_PORT=5174 make dev
```

### Docker Deployment (Future)

```bash
# Build image (to be implemented)
docker build -t animocerebro .

# Run container
docker run -p 8000:8000 -p 5173:5173 animocerebro
```

### CI/CD Integration

```yaml
# .github/workflows/test.yml (example)
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Setup Node
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Install dependencies
        run: |
          ./scripts/setup_env.sh
      - name: Run tests
        run: make test
```

## Related Documentation

- [Configuration Guide](../en/configuration_guide.md)
- [Startup and Testing Instructions](../operability/STARTUP_AND_TEST.md)
- [Latest Directory Map](../operability/LATEST_DIRECTORY_MAP.md)
- [Project Main README](../../README.md)

## Quick Reference

### Common Commands Cheat Sheet

```bash
# Environment initialization
./scripts/setup_env.sh

# Start
make dev

# Restart
make restart-dev

# Test
make test

# Install dependencies
make backend-install
make frontend-install

# Custom ports
BACKEND_PORT=8001 FRONTEND_PORT=5174 make dev

# View help
make help
```

### Port Cheat Sheet

| Service | Default Port | Environment Variable |
|---------|-------------|---------------------|
| Backend | 8000 | BACKEND_PORT |
| Frontend | 5173 | FRONTEND_PORT |

### File Location Cheat Sheet

| File | Location |
|------|----------|
| Environment variables | `.env` |
| LLM configuration | `config/provider_tools.yml` |
| Startup script | `scripts/dev_all.sh` |
| Restart script | `scripts/restart_dev.sh` |
| Transcript | `.zentex/runtime/*.jsonl` |
| Database | `.zentex/kuzu_db/` |
| Cache | `app_data/cache/state_v2/` |

---

**Last Updated**: 2026-04-09  
**Maintainer**: AnimoCerebro Team

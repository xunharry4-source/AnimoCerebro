# Startup and Testing Guide

This document explains how to one-click start the frontend and how to one-click run frontend and backend tests in the current repository.

**Last Updated**: 2026-04-09

## Current Project Status

- ✅ Provides a runnable backend FastAPI Web Console entry point: `zentex.web_console.dev_server:app`
- ✅ One-click startup simultaneously launches backend (Uvicorn) and frontend (Vite), with dependency checking (Fail-Closed)
- ✅ One-click restart cleans up old processes occupying ports before re-executing one-click startup
- ✅ WebSocket implementation uniformly uses `websockets-sansio`
- ✅ Backend health check mechanism is完善, ensuring service availability
- ✅ Supports custom port configuration (BACKEND_PORT, FRONTEND_PORT)

## One-Click Commands

### One-Click Restart (Most Commonly Used)

Use this command first when you encounter the following situations:
- Frontend/backend process residues causing port occupancy
- Uvicorn reload stuck, frontend Vite hot update abnormal
- You want to "clean up first, then fully launch" to ensure the page binds to the real backend

```bash
make restart-dev
```

Equivalent to directly executing the script:

```bash
./scripts/restart_dev.sh
```

### One-Click Startup

Start both backend and frontend services:

```bash
make dev
```

Equivalent to:

```bash
./scripts/dev_all.sh
```

Access points after startup:
- Frontend: http://127.0.0.1:5173
- Backend: http://127.0.0.1:8000
- API Documentation: http://127.0.0.1:8000/docs

### Custom Port Configuration

You can customize ports through environment variables:

```bash
export BACKEND_PORT=8080
export FRONTEND_PORT=3000
make dev
```

## Testing Commands

### Run All Tests

Execute all backend and frontend tests:

```bash
make test
```

This will execute:
- Backend pytest tests
- Frontend component tests

### Run Backend Tests Only

```bash
make backend-test
```

Or directly use pytest:

```bash
pytest tests/ -v
```

### Run Frontend Tests Only

```bash
make frontend-test
```

Or enter the frontend directory to execute:

```bash
cd src/admin-portal && npm test
```

### Run Specific Test Files

```bash
# Run specific test file
pytest tests/web_console/test_api.py -v

# Run tests matching keywords
pytest tests/ -k "health" -v

# Run integration tests
pytest tests/web_console/test_events_stream_integration.py -m integration
```

## Environment Preparation

### Backend Dependencies

Install Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### Frontend Dependencies

Install Node.js dependencies:

```bash
cd src/admin-portal
npm install
```

### Complete Environment Setup

Use the provided setup script:

```bash
./scripts/setup_env.sh
```

Or use make command:

```bash
make install
```

## Troubleshooting

### Port Occupied

If you encounter port occupied errors:

```bash
# View processes occupying ports
lsof -i :8000  # Backend port
lsof -i :5173  # Frontend port

# Kill related processes
kill -9 <PID>
```

Or directly use one-click restart:

```bash
make restart-dev
```

### Dependency Issues

If you encounter dependency issues:

```bash
# Reinstall backend dependencies
pip install -r requirements.txt --force-reinstall

# Reinstall frontend dependencies
cd src/admin-portal && rm -rf node_modules package-lock.json && npm install
```

### WebSocket Connection Issues

Ensure using the correct WebSocket protocol:

```bash
# Check if websockets-sansio is installed
pip show websockets-sansio

# If not installed, reinstall
pip install websockets-sansio
```

## Development Workflow

### Daily Development

1. Start development environment: `make dev`
2. Make code changes
3. View real-time updates on frontend
4. Run tests: `make test`
5. Commit code after passing tests

### Debugging

#### Backend Debugging

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
make dev
```

#### Frontend Debugging

```bash
# Start frontend in debug mode
cd src/admin-portal && npm run dev -- --debug
```

### Performance Monitoring

Monitor service performance:

```bash
# View backend logs
tail -f logs/backend.log

# View frontend console output
# Check browser developer tools Console panel
```

## Deployment Considerations

### Production Deployment

For production environment, consider:

1. Use proper process management (systemd, supervisor, etc.)
2. Configure reverse proxy (nginx, etc.)
3. Set appropriate log levels
4. Enable monitoring and alerting
5. Configure backup strategies

### Health Checks

The system provides health check endpoints:

```bash
# Check backend health
curl http://127.0.0.1:8000/api/health

# Check detailed status
curl http://127.0.0.1:8000/api/health/detailed
```

## Additional Resources

- [Function Modules Documentation](FUNCTION_MODULES.md)
- [Plugin Development Guides](PLUGIN_GUIDES.md)
- [Runtime and Implementation Details](RUNTIME_AND_TESTS.md)
- [Latest Directory Map](LATEST_DIRECTORY_MAP.md)

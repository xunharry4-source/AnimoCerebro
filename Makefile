SHELL := /bin/zsh

.PHONY: help install backend-install frontend-install frontend-dev frontend-test backend-test test dev restart-dev self-promotion-install self-promotion-dev self-promotion-test

help:
	@echo "make install           One-click install: system deps + Python 3.12 + all dependencies"
	@echo "make backend-install   Create .venv and install Python deps"
	@echo "make frontend-install  Install admin-portal dependencies"
	@echo "make frontend-dev      Start Vite dev server"
	@echo "make frontend-test     Run frontend tests"
	@echo "make backend-install   Create .venv and install Python deps"
	@echo "make backend-test      Run Python tests"
	@echo "make test              Run backend + frontend tests"
	@echo "make dev               Start frontend + backend (uvicorn --ws websockets-sansio)"
	@echo "make restart-dev       Restart dev stack with the same WebSocket runtime contract"
	@echo ""
	@echo "Self-Promotion Agent:"
	@echo "make self-promotion-install   Install Self-Promotion Agent dependencies"
	@echo "make self-promotion-dev       Start Self-Promotion Agent server"
	@echo "make self-promotion-test      Run Self-Promotion Agent tests"

# One-click full stack installation
install:
	@echo "=========================================="
	@echo "  Starting one-click installation..."
	@echo "=========================================="
	@# Install system dependencies (swig for faiss-cpu)
	@if [[ "$$OSTYPE" == darwin* ]]; then \
		if ! command -v swig >/dev/null 2>&1; then \
			echo ">>> Installing swig via Homebrew..."; \
			brew install swig || true; \
		fi; \
	elif [[ "$$OSTYPE" == linux-gnu* ]]; then \
		if ! command -v swig >/dev/null 2>&1; then \
			echo ">>> Installing swig via apt-get..."; \
			sudo apt-get update -qq && sudo apt-get install -y -qq swig || true; \
		fi; \
	fi
	@# Setup Python environment
	@if [ ! -d ".venv" ]; then \
		echo ">>> Creating Python virtual environment..."; \
		python3 -m venv .venv; \
	fi
	@echo ">>> Installing Python dependencies..."
	@.venv/bin/python -m pip install --upgrade pip -q
	@.venv/bin/python -m pip install -r requirements-dev.txt
	@.venv/bin/python -m pip install "torch>=2.2"
	@patch -p0 < patches/transformers_torch_version.patch || true
	@# Install frontend dependencies
	@if [ -d "src/admin-portal" ]; then \
		echo ">>> Installing frontend dependencies..."; \
		cd src/admin-portal && npm install --silent; \
	fi
	@echo "=========================================="
	@echo "  ✓ Installation complete!"
	@echo "=========================================="
	@echo ""
	@echo "Next steps:"
	@echo "  • Start dev server: make dev"
	@echo "  • Run tests:        make test"
	@echo ""

backend-install:
	python3 -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt

frontend-install:
	cd src/admin-portal && npm install

frontend-dev:
	cd src/admin-portal && npm run dev

frontend-test:
	cd src/admin-portal && npm run test

backend-test:
	pytest test tests

test:
	./scripts/test_all.sh

dev:
	./scripts/dev_all.sh

restart-dev:
	./scripts/restart_dev.sh

# ==========================================
# Self-Promotion Agent Targets
# ==========================================

self-promotion-install:
	@echo "=========================================="
	@echo "  Installing Self-Promotion Agent..."
	@echo "=========================================="
	@# Install Python dependencies
	@if [ -d ".venv" ]; then \
		echo ">>> Installing FastAPI and dependencies..."; \
		.venv/bin/python -m pip install fastapi uvicorn[standard] pydantic httpx; \
	else \
		echo "⚠️  Virtual environment not found. Creating..."; \
		python3 -m venv .venv; \
		.venv/bin/python -m pip install --upgrade pip -q; \
		.venv/bin/python -m pip install fastapi uvicorn[standard] pydantic httpx; \
	fi
	@# Install Playwright using official CLI (recommended)
	@echo ">>> Installing Playwright..."
	@if command -v npm >/dev/null 2>&1; then \
		echo "   Method: npm CLI (recommended by Playwright docs)"; \
		npx playwright install chromium --with-deps || true; \
	elif [ -d ".venv" ]; then \
		echo "   Method: pip + playwright CLI"; \
		.venv/bin/python -m pip install playwright; \
		.venv/bin/python -m playwright install chromium --with-deps; \
	else \
		echo "❌ Neither npm nor virtual environment found"; \
		echo "   Please install Node.js or create a virtual environment first"; \
		exit 1; \
	fi
	@# Verify installation
	@echo ""
	@echo ">>> Verifying installation..."
	@if python -c "import playwright" 2>/dev/null; then \
		echo "✅ Playwright Python package installed"; \
		if python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(); p.stop()" 2>/dev/null; then \
			echo "✅ Chromium browser ready"; \
		else \
			echo "⚠️  Chromium browser not installed. Run: playwright install chromium"; \
		fi; \
	else \
		echo "❌ Playwright installation failed"; \
		exit 1; \
	fi
	@echo ""
	@echo "=========================================="
	@echo "  ✓ Self-Promotion Agent installed!"
	@echo "=========================================="
	@echo ""
	@echo "Next steps:"
	@echo "  • Configure API key in .env file"
	@echo "  • Start server: make self-promotion-dev"
	@echo "  • Run tests:    make self-promotion-test"
	@echo ""

self-promotion-dev:
	@echo "🚀 Starting Self-Promotion Agent server..."
	@./scripts/start_self_promotion_agent.sh

self-promotion-test:
	@echo "🧪 Running Self-Promotion Agent tests..."
	pytest Agent/test_self_promotion_agent.py -v

SHELL := /bin/zsh

.PHONY: help install start backend-install frontend-install frontend-dev frontend-test backend-test test dev restart-dev

help:
	@echo "make install           One-click installation for both backend and frontend"
	@echo "make start             One-click start for both backend and frontend"
	@echo "make frontend-install  Install admin-portal dependencies"
	@echo "make frontend-dev      Start Vite dev server"
	@echo "make frontend-test     Run frontend tests"
	@echo "make backend-install   Create .venv and install Python deps"
	@echo "make backend-test      Run Python tests"
	@echo "make test              Run backend + frontend tests"
	@echo "make dev               Start frontend + backend (uvicorn --ws websockets-sansio)"
	@echo "make restart-dev       Restart dev stack with the same WebSocket runtime contract"

install:
	./scripts/setup_env.sh

start: dev

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

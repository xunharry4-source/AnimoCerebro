#!/bin/bash

# AI Supervision System Quick Start Script
# This script demonstrates the complete AI supervision system

set -e

echo "=========================================="
echo "AI Supervision System - Quick Start"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_step() {
    echo -e "${BLUE}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Check Python version
print_step "Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    print_success "Python $PYTHON_VERSION detected"
else
    print_error "Python 3 is required but not installed"
    exit 1
fi

# Install dependencies if needed
print_step "Checking dependencies..."
if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
    print_warning "Virtual environment not found. Creating one..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -q -r requirements.txt
    print_success "Dependencies installed"
else
    print_success "Virtual environment exists"
fi

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run tests
print_step "Running supervision system tests..."
if python -m pytest tests/supervision/test_ai_supervisor.py -v --tb=short; then
    print_success "All tests passed!"
else
    print_error "Some tests failed"
    exit 1
fi

echo ""
print_step "Running demonstration..."
echo ""

# Run demo
python examples/ai_supervision_demo.py

echo ""
echo "=========================================="
echo "Quick Start Complete!"
echo "=========================================="
echo ""
echo -e "${GREEN}✓ AI Supervision System is ready!${NC}"
echo ""
echo "Next steps:"
echo "  1. View documentation: src/zentex/supervision/README.md"
echo "  2. Open dashboard: src/admin-portal/public/ai-supervision-dashboard.html"
echo "  3. Integrate with your application"
echo ""
echo "API Endpoints (when backend is running):"
echo "  - GET  /api/supervision/status"
echo "  - GET  /api/supervision/alerts"
echo "  - POST /api/supervision/alerts/{id}/acknowledge"
echo "  - GET  /api/supervision/executions"
echo "  - POST /api/supervision/intervention"
echo "  - GET  /api/supervision/dashboard"
echo ""

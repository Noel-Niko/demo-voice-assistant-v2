# Makefile for DA Staff Assessment Backend

.PHONY: help check-prereqs check-credentials qa prod dev test dashboard

# Default target
help:
	@echo "DA Staff Assessment Backend - Available commands:"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  ⚠️  IMPORTANT: You MUST run 'assume aad-mlops-prod-digitalassistantdo' first!"
	@echo "  make prod           - Start prod server with AWS secrets (RECOMMENDED - better data)"
	@echo "  make qa             - Start QA server with AWS secrets (nonprod)"
	@echo ""
	@echo "📊 Analytics:"
	@echo "  make dashboard      - Start metrics dashboard (port 8766)"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  make test           - Run all backend tests"
	@echo "  make test-watch     - Run tests in watch mode"
	@echo ""
	@echo "🔐 Credential Management:"
	@echo "  make check-credentials - Check if AWS credentials are available"
	@echo ""
	@echo "💡 This Makefile uses MLOps credentials and AWS Secrets Manager"
	@echo "⚠️  REMEMBER: Run 'assume' and select your profile BEFORE using qa/prod commands!"

# Check prerequisites
check-prereqs:
	@echo "🔍 Checking prerequisites..."
	@command -v aws >/dev/null 2>&1 || { echo "❌ AWS CLI not found. Install with: brew install awscli"; exit 1; }
	@command -v jq >/dev/null 2>&1 || { echo "❌ jq not found. Install with: brew install jq"; exit 1; }
	@command -v uv >/dev/null 2>&1 || { echo "❌ uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
	@command -v assume >/dev/null 2>&1 || { echo "❌ MLOps 'assume' command not found. Complete MLOps onboarding first."; exit 1; }
	@echo "✅ Prerequisites check complete"

# Check if AWS credentials are available (indicates assume was run)
check-credentials:
	@echo "🔍 Checking for AWS credentials..."
	@if ! aws sts get-caller-identity >/dev/null 2>&1; then \
		echo "❌ No valid AWS credentials found!"; \
		echo ""; \
		echo "🔧 You MUST run the following commands in this terminal first:"; \
		echo ""; \
		echo "   1. assume aad-mlops-prod-digitalassistantdo"; \
		echo "      (or for qa: assume aad-mlops-nonprod-digitalassistantdo)"; \
		echo ""; \
		echo "   2. Then run your make command again"; \
		echo ""; \
		exit 1; \
	fi
	@echo "✅ AWS credentials found"

# Run QA server with AWS secrets
qa: check-prereqs check-credentials
	@echo "🚀 Starting QA server with AWS Secrets Manager..."
	@chmod +x setup_env.sh
	@bash -c ' \
		set -e; \
		source setup_env.sh qa; \
		echo "🔑 Starting server on port 8765..."; \
		uv run uvicorn app.main:app --host 0.0.0.0 --port 8765 --reload; \
	' || { echo "❌ Server startup failed. Check the error messages above. If port is in use, try kill -9 $(lsof -ti :8765)"; }

# Run production server with AWS secrets
prod: check-prereqs check-credentials
	@echo "🚀 Starting production server with AWS Secrets Manager..."
	@chmod +x setup_env.sh
	@bash -c ' \
		set -e; \
		source setup_env.sh prod; \
		echo "🔑 Starting server on port 8765..."; \
		uv run uvicorn app.main:app --host 0.0.0.0 --port 8765 --reload; \
	' || { echo "❌ Server startup failed. Check the error messages above. If port is in use, try kill -9 $(lsof -ti :8765)"; }

# Run all tests
test:
	@echo "🧪 Running all backend tests..."
	@uv run pytest -v --tb=short

# Run tests in watch mode
test-watch:
	@echo "🧪 Running tests in watch mode..."
	@uv run pytest-watch -- -v --tb=short

# Run metrics dashboard (reads from /tmp conversation export files)
dashboard:
	@echo "Starting Metrics Dashboard on port 8766..."
	@echo "Reading from /tmp/conversation_data_*.json"
	@echo "Open http://localhost:8766 to view"
	@uv run uvicorn app.dashboard.server:dashboard_app --host 0.0.0.0 --port 8766 --reload

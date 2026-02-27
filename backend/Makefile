# Makefile for Voice Assistant Demo Backend

.PHONY: help run test test-watch dashboard

# Path to .env file (repo root)
DOTENV_FILE := $(shell \
	if [ -f ../.env ]; then echo "../.env"; \
	elif [ -f .env ]; then echo ".env"; \
	fi)

# Default target
help:
	@echo "Voice Assistant Demo - Available commands:"
	@echo ""
	@echo "  make run             - Start backend server (port 8765)"
	@echo "  make test            - Run all backend tests"
	@echo "  make test-watch      - Run tests in watch mode"
	@echo "  make dashboard       - Start metrics dashboard (port 8766)"
	@echo ""
	@echo "Configuration:"
	@echo "  Use .env file for convenient configuration:"
	@echo "    1. cp .env.example .env   (from repo root)"
	@echo "    2. Edit .env with your values"
	@echo "    3. cd backend && make run (auto-loads .env)"
	@echo ""
	@echo "Required environment variables:"
	@echo "  OPENAI_API_KEY       - Your OpenAI API key (for AI features)"
	@echo ""
	@echo "MCP environment variables (for listening mode & tool augmentation):"
	@echo "  MCP_INGRESS_URL      - MCP server URL (e.g. http://your-mcp-server:8080)"
	@echo "  MCP_SECRET_KEY       - Shared secret used to sign JWT tokens for MCP auth"
	@echo "  MCP_DISCOVERY_ENDPOINT - Discovery endpoint path or URL (default: /tools/discovery)"
	@echo ""
	@echo "Optional environment variables:"
	@echo "  OPENAI_MODEL         - Initial model, switchable via UI (default: gpt-3.5-turbo)"
	@echo "  See .env.example in the repo root for all configuration options"
	@echo ""
	@echo "Quick start:"
	@echo "  cp .env.example .env && vim .env"
	@echo "  cd backend && make run"

# Run the backend server
# 1. Sources .env file (if found) so check_var sees existing values
# 2. Prompts for any still-missing variables (user can skip)
# 3. Starts uvicorn — python-dotenv also loads .env as a fallback
run:
	@load_dotenv() { \
		if [ -n "$(DOTENV_FILE)" ]; then \
			echo "Loading .env from $(DOTENV_FILE)"; \
			while IFS= read -r line || [ -n "$$line" ]; do \
				line="$${line%%\#*}"; \
				line="$$(echo "$$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$$//')"; \
				[ -z "$$line" ] && continue; \
				key="$${line%%=*}"; \
				val="$${line#*=}"; \
				val="$$(echo "$$val" | sed 's/^["'"'"']//;s/["'"'"']$$//')"; \
				eval current="\$$$$key"; \
				if [ -z "$$current" ]; then \
					export $$key="$$val"; \
				fi; \
			done < "$(DOTENV_FILE)"; \
			echo ""; \
		fi; \
	}; \
	check_var() { \
		var_name="$$1"; desc="$$2"; skip_msg="$$3"; \
		eval val="\$$$$var_name"; \
		if [ -z "$$val" ]; then \
			echo "$$var_name is not set ($$desc)."; \
			printf "  Enter value (or press Enter to skip): "; \
			read input; \
			if [ -n "$$input" ]; then \
				export $$var_name="$$input"; \
				echo "  -> Set for this session."; \
			else \
				echo "  -> Skipped. $$skip_msg"; \
			fi; \
			echo ""; \
		fi; \
	}; \
	echo ""; \
	echo "=== Voice Assistant Backend ==="; \
	echo ""; \
	load_dotenv; \
	echo "=== Environment Check ==="; \
	echo ""; \
	check_var OPENAI_API_KEY \
		"required for AI features" \
		"AI features will not work without this key."; \
	check_var MCP_INGRESS_URL \
		"required for listening mode & MCP tools" \
		"Listening mode and MCP tools will be disabled."; \
	check_var MCP_SECRET_KEY \
		"shared secret for signing JWT tokens to MCP server" \
		"MCP requests will be sent without authentication."; \
	echo "Starting server on port 8765..."; \
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8765 --reload

# Run all tests
test:
	@echo "Running all backend tests..."
	@uv run pytest -v --tb=short

# Run tests in watch mode
test-watch:
	@echo "Running tests in watch mode..."
	@uv run pytest-watch -- -v --tb=short

# Run metrics dashboard (reads from /tmp conversation export files)
dashboard:
	@echo "Starting Metrics Dashboard on port 8766..."
	@echo "Reading from /tmp/conversation_data_*.json"
	@echo "Open http://localhost:8766 to view"
	@uv run uvicorn app.dashboard.server:dashboard_app --host 0.0.0.0 --port 8766 --reload

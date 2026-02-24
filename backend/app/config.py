"""Application configuration using Pydantic BaseSettings.

Configuration follows 12-factor principle #3:
- Defaults defined in this file
- Override via environment variables (set by setup_env.sh or Kubernetes)
- No .env files needed (use make prod/qa with AWS Secrets Manager)

Usage:
  make prod  # Loads secrets from AWS Secrets Manager (prod)
  make qa    # Loads secrets from AWS Secrets Manager (qa)
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with sensible defaults.

    All settings can be overridden via environment variables.
    setup_env.sh loads secrets from AWS Secrets Manager and exports them.
    """

    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="ignore",
    )

    # OpenAI Configuration (12-Factor: Config from environment)
    # Local dev: source setup_env.sh qa (pulls from AWS Secrets Manager)
    # Production: Loaded from Kubernetes secrets (ArgoCD - see digitalassistantdomain-argo-apps)
    # Optional at import time to allow tests to run without API key
    OPENAI_API_KEY: str | None = None  # Required at runtime for AI features
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    OPENAI_MAX_TOKENS: int = 500
    OPENAI_TEMPERATURE: float = 0.0

    # Database Configuration
    # Use absolute path to ensure database is always in backend/ directory
    # regardless of working directory (works with make prod from any location)
    DATABASE_URL: str = f"sqlite+aiosqlite:///{Path(__file__).parent.parent / 'transcripts.db'}"

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8765  # Using non-standard port to avoid conflicts
    LOG_LEVEL: str = "INFO"

    # Event Bus Configuration
    EVENT_QUEUE_SIZE: int = 1000

    # Business Logic Configuration
    SUMMARY_INTERVAL_SECONDS: int = 5
    TRANSCRIPT_WORDS_PER_SECOND: float = 8.5  # Natural speaking pace (words/second) reported at 3.86 https://pmc.ncbi.nlm.nih.gov/articles/PMC2790192/
    TRANSCRIPT_INITIAL_DELAY: float = 1.0  # Delay before first message (seconds)
    TRANSCRIPT_INTER_LINE_DELAY: float = 0.25  # Delay between lines (seconds)

    # Data File Path
    TRANSCRIPT_FILE_PATH: str = "../Option2_data_file_v2.txt"

    # MCP Configuration (12-Factor: Config from environment)
    # Local dev: source setup_env.sh prod (pulls from AWS Secrets Manager)
    # Production: Loaded from Kubernetes secrets (ArgoCD)
    MCP_SECRET_KEY: str | None = None  # Required at runtime for MCP features
    MCP_SECRET_ALGORITHM: str = "HS256"  # JWT algorithm
    MCP_ENVIRONMENT: str = "prod"  # or "qa"
    MCP_INGRESS_URL: str = "https://grainger-mcp-servers.svc.ue2.prod.mlops.prod.aws.grainger.com"
    MCP_REQUEST_TIMEOUT: float = 90.0  # Increased for Databricks vector search (can take 45-60s under load)

    # Utterance Boundary Detection Configuration
    # Timeouts for adaptive utterance finalization (based on confidence and completeness)
    UTT_SHORT_TIMEOUT_S: float = 1.0        # High-confidence complete (questions, commands)
    UTT_MEDIUM_TIMEOUT_S: float = 2.0       # Medium-confidence (complete statements)
    UTT_LONG_TIMEOUT_S: float = 4.0         # Low-confidence/incomplete phrases
    UTT_HARD_MAX_TIMEOUT_S: float = 5.0     # Force finalization (hard cap)
    UTT_CONFIDENCE_HIGH: float = 0.85       # Threshold for short timeout
    UTT_CONFIDENCE_GOOD: float = 0.70       # Threshold for medium timeout
    UTT_MIN_WORDS_COMPLETE: int = 4         # Minimum words for complete statement
    UTT_MIN_WORDS_QUESTION: int = 3         # Minimum words for complete question
    UTT_MIN_WORDS_COMMAND: int = 3          # Minimum words for complete command

    # Semantic Layer (Optional spaCy — see ADR-025)
    UTT_DISABLE_SPACY_SEMANTIC: bool = False    # Set True to skip semantic analysis
    UTT_SEMANTIC_CONFIDENCE_THRESHOLD: float = 0.85  # Min confidence for semantic override

    # Listening Mode Feature Flags
    LISTENING_MODE_ENABLED: bool = True     # Master toggle for listening mode
    LISTENING_MODE_USE_UTTERANCES: bool = True  # Use utterance-based detection (vs periodic polling)

    # Redis Configuration (12-Factor: Config from environment, Backing Services)
    # Optional: If not set, uses InMemory implementations (local dev only)
    # Local testing: redis://localhost:6379/0 (requires docker-compose up redis)
    # Production: redis://:password@redis-cluster:6379/0 (from Kubernetes secrets)
    REDIS_URL: str | None = None


# Singleton settings instance
settings = Settings()

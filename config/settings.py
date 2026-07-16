"""
Configuration settings for the ApplyPilot.
Manages environment variables, database connections, and application settings.
"""

from typing import List, Optional, Union, Dict, Any
from pydantic_settings import BaseSettings
from pydantic import field_validator, Field, SecretStr

from utils import gemini_api_key_format


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application Configuration
    app_name: str = "ApplyPilot"
    app_version: str = "1.0.0"
    app_description: str = "AI-Powered Job Application Co-Pilot"
    debug: bool = False
    testing: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Authentication & Security
    jwt_secret: str = Field(
        ..., description="JWT secret key (set via JWT_SECRET env var, min 32 chars)"
    )
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    bcrypt_rounds: int = 12
    
    # Google OAuth Configuration
    google_client_id: Optional[str] = Field(
        default=None,
        description="Google OAuth Client ID (from Google Cloud Console)"
    )
    google_client_secret: Optional[str] = Field(
        default=None,
        description="Google OAuth Client Secret (from Google Cloud Console)"
    )
    google_oauth_enabled: bool = Field(
        default=False,
        description="Enable Google OAuth (auto-enabled when client ID/secret are set)"
    )

    # Database Configuration - PostgreSQL
    database_url: str = Field(
        ...,
        description="PostgreSQL connection URL (set via DATABASE_URL env var, e.g., postgresql+asyncpg://user:pass@host:5432/dbname)",
    )

    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    redis_session_db: int = 1

    # Encryption key for API key storage (separate from JWT secret)
    # If not set, falls back to deriving from jwt_secret for backward compatibility.
    # Set a dedicated ENCRYPTION_KEY in production to allow safe JWT secret rotation.
    encryption_key: Optional[str] = Field(
        default=None,
        description="Fernet encryption key for stored API keys (base64url, 32 bytes). "
                    "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"",
    )

    # LLM provider selection (gemini | openai | anthropic | ollama)
    # Default remains Gemini for existing deployments. Other providers use server env keys.
    llm_provider: str = Field(
        default="gemini",
        description="Active LLM provider: gemini, openai, anthropic, or ollama",
    )

    # Gemini Configuration
    # API key is optional - users can provide their own via BYOK (Bring Your Own Key)
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="Google Gemini API key (optional - users can provide their own in Settings)"
    )
    gemini_model: str = "gemini-3.5-flash"
    
    # Vertex AI Configuration (optional Gemini backend — higher rate limits)
    # Requires: gcloud auth application-default login (or GOOGLE_APPLICATION_CREDENTIALS)
    use_vertex_ai: bool = Field(
        default=False,
        description="Use Vertex AI instead of Google AI Studio (requires ADC authentication)"
    )
    vertex_ai_project: Optional[str] = Field(
        default=None,
        description="Google Cloud Project ID for Vertex AI"
    )
    vertex_ai_location: str = Field(
        default="us-central1",
        description="Vertex AI region (e.g., us-central1, europe-west1)"
    )

    # OpenAI (server key; optional — used when llm_provider=openai)
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key for server-side OpenAI provider",
    )
    openai_model: str = Field(
        default="gpt-5.6-luna",
        description="Default OpenAI chat model",
    )

    # Anthropic (server key; optional — used when llm_provider=anthropic)
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for server-side Anthropic provider",
    )
    anthropic_model: str = Field(
        default="claude-sonnet-5",
        description="Default Anthropic Messages model",
    )

    # Ollama (local / self-hosted — used when llm_provider=ollama)
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        description="Ollama base URL (no trailing path)",
    )
    ollama_model: str = Field(
        default="qwen3.6",
        description="Default Ollama model tag",
    )

    # Company research — Google Search grounding (off by default)
    company_research_grounding_enabled: bool = Field(
        default=False,
        description="Enable Google Search grounding for company research LLM calls",
    )
    company_research_grounding_min_confidence: str = Field(
        default="MEDIUM",
        description="Ground when employer confidence is at or below this (HIGH|MEDIUM|LOW)",
    )

    # Hiring outreach — provider web-search grounding (on by default for this feature)
    hiring_outreach_grounding_enabled: bool = Field(
        default=True,
        description="Enable provider web-search grounding for hiring outreach LLM calls",
    )

    base_url: str = "http://localhost:8000"
    security_contact_email: Optional[str] = Field(
        default=None,
        description="Email shown in /.well-known/security.txt for responsible disclosure reports. Defaults to security@<base_url domain> if not set.",
    )

    # Email/SMTP Configuration (Gmail SMTP for GCP deployments)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: Optional[str] = Field(
        default=None,
        description="SMTP username (Gmail address for Gmail SMTP)"
    )
    smtp_password: Optional[SecretStr] = Field(
        default=None,
        description="SMTP password (Gmail App Password - generate at https://myaccount.google.com/apppasswords)"
    )
    smtp_from_email: Optional[str] = Field(
        default=None,
        description="From email address (defaults to smtp_username if not set)"
    )
    smtp_from_name: str = "ApplyPilot"

    # Analytics Configuration (PostHog)
    posthog_api_key: Optional[str] = Field(
        default=None,
        description="PostHog API key for product analytics (get from PostHog dashboard)"
    )
    posthog_host: str = Field(
        default="https://us.i.posthog.com",
        description="PostHog API host (us.i.posthog.com for US, eu.i.posthog.com for EU)"
    )
    posthog_enabled: bool = Field(
        default=True,
        description="Enable PostHog analytics (requires API key)"
    )

    # Cloud Tasks Configuration (async LLM workflow offloading)
    # When cloud_tasks_service_url is set, long AI workflows are dispatched to a
    # Cloud Tasks queue instead of running inline as FastAPI BackgroundTasks.
    # This gives automatic retries, longer timeouts, and decoupled execution.
    cloud_tasks_queue_name: str = Field(
        default="workflow-tasks",
        description="Cloud Tasks queue name for async workflow execution"
    )
    cloud_tasks_location: str = Field(
        default="us-central1",
        description="GCP region where the Cloud Tasks queue lives"
    )
    cloud_tasks_service_url: Optional[str] = Field(
        default=None,
        description="Cloud Run service URL (e.g. https://job-assistant-prod-xxx.run.app). "
                    "When set, workflows are dispatched via Cloud Tasks instead of BackgroundTasks."
    )
    cloud_tasks_service_account: Optional[str] = Field(
        default=None,
        description="Service account email that Cloud Tasks uses to sign OIDC tokens "
                    "(e.g. job-assistant-tasks-sa@project.iam.gserviceaccount.com)"
    )
    cloud_tasks_secret: Optional[str] = Field(
        default=None,
        description="Shared secret sent as X-CloudTasks-Secret header to authenticate "
                    "Cloud Tasks callbacks on the internal execute endpoint."
    )

    # Cloud Scheduler secret for authenticated internal cron endpoints
    cloud_scheduler_secret: Optional[str] = Field(
        default=None,
        description="Shared secret sent as X-Scheduler-Secret header by Cloud Scheduler "
                    "to authenticate periodic maintenance calls (e.g. orphaned session cleanup)."
    )

    # Self-hosted / local deployment flags
    disable_email_verification: bool = Field(
        default=False,
        description="When True, newly registered users are automatically marked as email-verified "
                    "and the email-verified gate on login is skipped. "
                    "Set to True for self-hosted deployments where SMTP is not configured. "
                    "Never set this to True on a public, multi-user deployment."
    )

    @property
    def use_cloud_tasks(self) -> bool:
        """True when all Cloud Tasks settings are configured."""
        return bool(
            self.cloud_tasks_service_url
            and self.cloud_tasks_service_account
            and self.cloud_tasks_secret
        )

    # Logging Configuration
    log_level: str = "INFO"
    log_format: str = "text"  # "json" for production, "text" for development
    log_dir: str = "logs"
    log_file_enabled: bool = True
    log_max_bytes: int = 10 * 1024 * 1024  # 10 MB
    log_backup_count: int = 5
    log_redact_sensitive: bool = True
    slow_request_threshold_ms: float = 5000.0  # 5 seconds

    # User resume files (on-disk; relative paths stored in user_resume_assets)
    user_resume_storage_dir: str = Field(
        default="data/user_resumes",
        description="Directory for persisted resume uploads (created automatically).",
    )

    # Session Configuration
    session_timeout: int = 3600
    session_cookie_name: str = "job_assistant_session"
    session_cookie_secure: bool = True
    session_cookie_httponly: bool = True

    # Cache
    cache_version: str = "v1"

    # CORS Configuration
    cors_origins: Union[str, List[str]] = "http://localhost:3000,http://localhost:8000"
    cors_credentials: bool = True

    # Host Configuration
    allowed_hosts: Union[str, List[str]] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )

    # Development Settings
    reload: bool = True
    workers: int = 1

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v):
        """Validate PostgreSQL database URL format."""
        if not v:
            raise ValueError("Database URL is required")
        # Accept both postgresql:// and postgresql+asyncpg:// formats
        if not (v.startswith("postgresql://") or v.startswith("postgresql+asyncpg://")):
            raise ValueError(
                "Invalid database URL format. Must start with postgresql:// or postgresql+asyncpg://"
            )
        # Auto-convert to asyncpg if needed
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v):
        """Validate JWT secret strength."""
        if not v:
            raise ValueError("JWT secret is required")
        if len(v) < 32:
            raise ValueError("JWT secret must be at least 32 characters long")

        # Check for common weak secrets
        weak_patterns = [
            "1234567890" * 4,  # Repeated numbers
            "abcdefghij" * 4,  # Repeated letters
            "password" * 4,  # Repeated password
            "secret" * 6,  # Repeated secret
            "key" * 8,  # Repeated key
        ]

        if v.lower() in [pattern.lower() for pattern in weak_patterns]:
            raise ValueError(
                "JWT secret is too predictable. Use a cryptographically secure random string"
            )

        # Check for basic entropy (at least 3 different character types)
        has_lower = any(c.islower() for c in v)
        has_upper = any(c.isupper() for c in v)
        has_digit = any(c.isdigit() for c in v)
        has_special = any(not c.isalnum() for c in v)

        char_types = sum([has_lower, has_upper, has_digit, has_special])
        if char_types < 3:
            raise ValueError(
                "JWT secret should contain at least 3 different character types (lowercase, uppercase, digits, special chars)"
            )

        return v

    @field_validator("encryption_key")
    @classmethod
    def validate_encryption_key(cls, v):
        """Validate ENCRYPTION_KEY is a properly formatted Fernet key."""
        if v is None:
            return v
        try:
            from cryptography.fernet import Fernet
            Fernet(v.encode() if isinstance(v, str) else v)
        except Exception:
            raise ValueError(
                "ENCRYPTION_KEY is not a valid Fernet key. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        return v

    @field_validator("gemini_api_key")
    @classmethod
    def validate_gemini_api_key(cls, v):
        """Validate optional server-side Gemini API key shape (Google rotates formats)."""
        if v is None:
            return v
        if not gemini_api_key_format.validate_gemini_api_key(v):
            raise ValueError(
                "GEMINI_API_KEY appears invalid: use a Google Gemini / AI Studio API key "
                "(single line; see https://aistudio.google.com/app/apikey)."
            )
        return v

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        """Restrict llm_provider to the supported allowlist."""
        from utils.llm.constants import VALID_LLM_PROVIDERS

        if v is None or not str(v).strip():
            return "gemini"
        normalized = str(v).strip().lower()
        if normalized not in VALID_LLM_PROVIDERS:
            raise ValueError(
                f"LLM_PROVIDER must be one of: {', '.join(sorted(VALID_LLM_PROVIDERS))}"
            )
        return normalized

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v):
        """Convert comma-separated origins to list."""
        if isinstance(v, list):
            return v
        if not v or not v.strip():
            return []

        # Split by comma and clean up each origin
        origins = [origin.strip() for origin in v.split(",") if origin.strip()]

        # Validate each origin format — wildcards are never allowed
        for origin in origins:
            if not origin.startswith(("http://", "https://")):
                raise ValueError(
                    f"Invalid CORS origin format: {origin}. Must start with http:// or https://"
                )

        return origins

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, v):
        """Convert comma-separated hosts to list."""
        if isinstance(v, list):
            return v
        if not v or not v.strip():
            return ["localhost", "127.0.0.1"]

        # Split by comma and clean up each host
        hosts = [host.strip() for host in v.split(",") if host.strip()]
        return hosts

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v):
        """Ensure BASE_URL uses HTTPS in production-like environments."""
        if v and v.startswith("http://") and "localhost" not in v and "127.0.0.1" not in v:
            raise ValueError(
                f"BASE_URL must use HTTPS in production environments. Got: {v}"
            )
        return v.rstrip("/") if v else v

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.debug and not self.testing

    @property
    def session_cookie_secure_production(self) -> bool:
        """Get secure cookie setting based on environment."""
        return self.session_cookie_secure or self.is_production

    @property
    def is_google_oauth_configured(self) -> bool:
        """Check if Google OAuth is properly configured."""
        return bool(self.google_client_id and self.google_client_secret)


class DatabaseSettings:
    """Database-specific configuration and connection management."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def async_database_url(self) -> str:
        """Get async database URL for SQLAlchemy."""
        url = self.settings.database_url
        # Ensure we're using asyncpg driver
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def sync_database_url(self) -> str:
        """Get sync database URL for Alembic migrations."""
        url = self.settings.database_url
        # Convert to sync driver for migrations
        if "+asyncpg" in url:
            url = url.replace("+asyncpg", "", 1)
        return url

    @property
    def connection_pool_params(self) -> Dict[str, Any]:
        """Get connection pool parameters for SQLAlchemy.

        When PgBouncer is deployed as a sidecar (DATABASE_URL points to 127.0.0.1:5432),
        the app talks to PgBouncer, not Cloud SQL directly. PgBouncer manages the real
        Cloud SQL connections with its own smaller pool (PGBOUNCER_DEFAULT_POOL_SIZE=5).
        Keeping pool_size small here avoids opening too many PgBouncer→Cloud SQL connections.

        Math: 10 Cloud Run instances × (5+5) = 100 connections to PgBouncer,
        but PgBouncer only opens 5 real connections to Cloud SQL per instance → 50 total.
        db-g1-small (100 conn limit) handles this safely with 50% headroom.
        """
        return {
            "pool_size": 5,
            "max_overflow": 5,
            "pool_pre_ping": True,
            "pool_recycle": 1800,
            # Per-connection server-side timeouts (via asyncpg server_settings).
            # statement_timeout aborts any single query running longer than 30s.
            # lock_timeout prevents indefinite waits on row-level locks.
            # idle_in_transaction_session_timeout closes sessions left open in a
            # transaction for more than 2 minutes (guards against leaked sessions).
            "connect_args": {
                "server_settings": {
                    "statement_timeout": "30000",
                    "lock_timeout": "10000",
                    "idle_in_transaction_session_timeout": "120000",
                }
            },
        }

    @property
    def redis_connection_params(self) -> Dict[str, Any]:
        """Get Redis connection parameters."""
        return {
            "decode_responses": True,
            "health_check_interval": 30,
            "socket_keepalive": True,
            "retry_on_timeout": True,
            "max_connections": 10,
        }


class SecuritySettings:
    """Security-related configuration."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def jwt_config(self) -> Dict[str, Any]:
        """Get JWT configuration."""
        return {
            "secret_key": self.settings.jwt_secret,
            "algorithm": self.settings.jwt_algorithm,
            "expire_hours": self.settings.jwt_expiration_hours,
        }


from functools import lru_cache


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.
    
    Uses lru_cache to ensure settings are only loaded once from environment,
    improving performance and consistency across the application.
    """
    return Settings()


@lru_cache()
def get_database_settings() -> DatabaseSettings:
    """Get cached database settings."""
    return DatabaseSettings(get_settings())


@lru_cache()
def get_security_settings() -> SecuritySettings:
    """Get cached security settings."""
    return SecuritySettings(get_settings())


def clear_settings_cache() -> None:
    """
    Clear cached settings. Useful for testing or after environment changes.
    """
    get_settings.cache_clear()
    get_database_settings.cache_clear()
    get_security_settings.cache_clear()


# Export commonly used settings
settings = get_settings()

"""Shared LLM constants — timeouts, retries, and default generation limits."""

# Default generation parameters
DEFAULT_TEMPERATURE: float = 0.7
DEFAULT_MAX_TOKENS: int = 16000

# Timeout and connection constants
DEFAULT_TIMEOUT: int = 180  # 3 minutes for larger prompts
HTTP_CONNECT_TIMEOUT: float = 10.0  # OpenAI / Anthropic / Ollama connect

# Generation parameters (Gemini)
DEFAULT_TOP_P: float = 0.95
DEFAULT_TOP_K: int = 40

# Retry configuration
MAX_RETRIES: int = 3
RETRY_MIN_WAIT: int = 2  # seconds
RETRY_MAX_WAIT: int = 10  # seconds

# Supported provider names (settings allowlist)
VALID_LLM_PROVIDERS: frozenset[str] = frozenset(
    {"gemini", "openai", "anthropic", "ollama"}
)
DEFAULT_LLM_PROVIDER: str = "gemini"

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "sqlite+aiosqlite:///./orca.db"
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    CORS_ORIGINS: str = "http://localhost:8080"
    LOG_LEVEL: str = "INFO"

    INCOIS_API_BASE: str = "https://erddap.incois.gov.in/erddap"
    MOSDAC_API_BASE: str = "https://www.mosdac.gov.in"
    IMD_API_BASE: str = "https://api.imd.gov.in/api/v1"

    IMD_API_KEY: str = ""
    MOSDAC_USERNAME: str = ""
    MOSDAC_PASSWORD: str = ""

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    CHAT_TIMEOUT_SECONDS: float = 8.0
    CHAT_MAX_RETRIES: int = 2
    CHAT_REQUEST_DEADLINE_SECONDS: float = 30.0
    CACHE_STALE_THRESHOLD_SECONDS: int = 3600
    CACHE_DEFAULT_TTL_SECONDS: int = 300
    MAX_CONCURRENT_AGENTS: int = 5
    MAX_EVIDENCE_ITEMS: int = 200
    MAX_AGGREGATED_EVIDENCE: int = 500

    CONNECTOR_TIMEOUT_SECONDS: float = 10.0
    CONNECTOR_MAX_RETRIES: int = 2

    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS: float = 60.0


settings = Settings()

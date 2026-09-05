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
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    CHAT_TIMEOUT_SECONDS: float = 8.0
    CHAT_MAX_RETRIES: int = 2
    CACHE_STALE_THRESHOLD_SECONDS: int = 3600
    MAX_CONCURRENT_AGENTS: int = 5

    CONNECTOR_TIMEOUT_SECONDS: float = 10.0
    CONNECTOR_MAX_RETRIES: int = 2


settings = Settings()

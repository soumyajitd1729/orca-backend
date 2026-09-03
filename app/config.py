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

    INCOIS_API_BASE: str = ""
    MOSDAC_API_BASE: str = ""
    IMD_API_BASE: str = ""


settings = Settings()

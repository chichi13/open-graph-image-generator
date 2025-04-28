from typing import List, Optional, Union

from pydantic import AnyHttpUrl, Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Project Information
    PROJECT_NAME: str = "OG Image Generator"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    LOGGING_LEVEL: str = "INFO"  # Logging level (e.g., DEBUG, INFO, WARNING, ERROR)

    # Uvicorn Settings
    UVICORN_HOST: str = "0.0.0.0"
    UVICORN_PORT: int = 8000
    UVICORN_RELOAD: bool = False

    # Database Settings
    DATABASE_HOST: str = "127.0.0.1"
    DATABASE_PORT: int = 5432
    DATABASE_USER: str = "app"
    DATABASE_PASSWORD: str = "password"
    DATABASE_NAME: str = "ogimagedb"

    # Derived Database URL
    DATABASE_URL: PostgresDsn = Field(
        default=f"postgresql+psycopg2://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}",
        validate_default=False,
    )

    # CORS Origins
    # Accepts comma-separated string from env var, defaults to allow all for dev
    BACKEND_CORS_ORIGINS_STR: str = "*"
    BACKEND_CORS_ORIGINS: List[Union[str, AnyHttpUrl]] = []

    # S3 Storage Settings (AWS S3 or S3-compatible)
    AWS_ENDPOINT_URL: Optional[AnyHttpUrl] = None  # e.g., http://minio:9000
    AWS_ACCESS_KEY: str = "YOUR_ACCESS_KEY"  # Renamed from AWS_ACCESS_KEY_ID
    AWS_SECRET_KEY: str = "YOUR_SECRET_KEY"  # Renamed from AWS_SECRET_ACCESS_KEY
    AWS_BUCKET_NAME: str = "your-bucket-name"  # Renamed from S3_BUCKET_NAME
    CDN_URL: Optional[AnyHttpUrl] = (
        None  # Optional: Base URL for CDN access (e.g., https://cdn.example.com)
    )

    # Other Settings
    CELERY_ENABLED: bool = False  # Enable/disable Celery task queue
    REDIS_URL: str = "redis://localhost:6379/0"

    SCREENSHOT_DEFAULT_TTL: int = 24 * 3600
    MAX_CONCURRENT_TASKS: int = 4

    # Screenshot Service Settings
    # Comma-separated list of allowed domains for screenshots (e.g., "example.com,trusted.net")
    # If empty or not set, all domains are allowed.
    ALLOWED_SCREENSHOT_DOMAINS_STR: Optional[str] = None
    ALLOWED_SCREENSHOT_DOMAINS: Optional[List[str]] = None

    CONTACT_EMAIL: str = "support@kactica.com"

    # Pydantic settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,  # Important for env vars
        extra="ignore",
    )

    # Initialization and Validation
    def __init__(self, **values):
        super().__init__(**values)
        # Recalculate DATABASE_URL after potentially loading individual components from .env
        self.DATABASE_URL = (
            f"postgresql+psycopg2://{self.DATABASE_USER}:"
            f"{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:"
            f"{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )

        if self.BACKEND_CORS_ORIGINS_STR:
            self.BACKEND_CORS_ORIGINS = [
                origin.strip() for origin in self.BACKEND_CORS_ORIGINS_STR.split(",")
            ]

        # Parse allowed screenshot domains string
        if self.ALLOWED_SCREENSHOT_DOMAINS_STR:
            self.ALLOWED_SCREENSHOT_DOMAINS = [
                domain.strip().lower()  # Store as lowercase for case-insensitive matching
                for domain in self.ALLOWED_SCREENSHOT_DOMAINS_STR.split(",")
                if domain.strip()  # Ignore empty strings from trailing commas etc.
            ]

        # Set reload based on environment
        self.UVICORN_RELOAD = self.is_dev()

    def is_dev(self) -> bool:
        return self.ENVIRONMENT == "development"

    def is_prod(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()

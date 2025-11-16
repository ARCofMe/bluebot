"""Application configuration objects and helpers."""

from pydantic_settings import BaseSettings  # <-- updated import

class Settings(BaseSettings):
    """Global application settings loaded from environment/.env."""

    app_name: str = "Teams Bot Service"
    environment: str = "dev"
    debug: bool = True

    # Azure / Bot credentials (placeholders)
    azure_app_id: str | None = None
    azure_app_password: str | None = None
    azure_tenant_id: str | None = None

    # Optional BlueFolder integration
    bluefolder_api_key: str | None = None
    bluefolder_account_name: str | None = None

    class Config:
        """Pydantic metadata for locating the .env file."""
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

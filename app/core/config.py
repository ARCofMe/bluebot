"""Application configuration for the Discord bot."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings."""

    app_name: str = "BlueBot Discord"
    environment: str = "dev"
    debug: str | bool = True

    discord_bot_token: str
    discord_guild_id: int | None = None

    bluefolder_api_key: str | None = None
    bluefolder_account_name: str | None = None
    bluefolder_api_path: str | None = None
    bluefolder_base_url: str | None = None
    bluefolder_host_header: str | None = None
    bluefolder_verify_ssl: bool | None = None
    bluefolder_timeout_seconds: float | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

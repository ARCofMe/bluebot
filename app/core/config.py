"""Application configuration for the Discord bot."""

from __future__ import annotations

import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings."""

    app_name: str = "BlueBot Discord"
    environment: str = "dev"
    debug: str | bool = True

    discord_bot_token: str
    discord_guild_id: int | None = None
    discord_tech_map: str | None = None

    bluefolder_api_key: str | None = None
    bluefolder_account_name: str | None = None
    bluefolder_api_path: str | None = None
    bluefolder_base_url: str | None = None
    bluefolder_host_header: str | None = None
    bluefolder_verify_ssl: bool | None = None
    bluefolder_timeout_seconds: float | None = None
    bluefolder_comment_user_id: int | None = None
    assignment_cache_ttl_seconds: int = 120
    workflow_write_assignment: bool = True
    workflow_write_sr_note: bool = True

    waiver_base_url: str | None = None
    waiver_sr_param: str = "sr"
    waiver_name_param: str = "name"
    waiver_first_name_param: str = "first_name"
    waiver_last_name_param: str = "last_name"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def parsed_discord_tech_map(self) -> dict[str, int]:
        """Decode the Discord-user-to-tech map from JSON."""
        raw = self.discord_tech_map
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except Exception:
            return {}

        result: dict[str, int] = {}
        if isinstance(decoded, dict):
            for key, value in decoded.items():
                try:
                    result[str(key)] = int(value)
                except Exception:
                    continue
        return result


settings = Settings()

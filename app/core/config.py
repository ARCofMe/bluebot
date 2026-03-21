"""Application configuration for the Discord bot."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings."""

    app_name: str = "Parts Cannon"
    environment: str = "dev"
    debug: str | bool = True

    discord_bot_token: str
    discord_guild_id: int | None = None
    discord_tech_map: str | None = None
    discord_tech_role_names: str | None = None
    discord_dispatcher_role_names: str | None = None
    discord_parts_role_names: str | None = None
    dispatcher_alert_channel_id: int | None = None
    dispatcher_alert_on_contact_issue: bool = True
    parts_alert_channel_id: int | None = None
    parts_alert_on_contact_issue: bool = True

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
    workflow_assignment_lookup_days_before: int = 0
    workflow_assignment_lookup_days_after: int = 0
    discord_member_export_path: str = "exports/discord_members.json"
    discord_export_timestamped: bool = True

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

    @staticmethod
    def _parse_role_names(raw: str | None) -> set[str]:
        if not raw:
            return set()
        return {
            part.strip().casefold()
            for part in raw.split(",")
            if part and part.strip()
        }

    @property
    def parsed_discord_tech_roles(self) -> set[str]:
        return self._parse_role_names(self.discord_tech_role_names)

    @property
    def parsed_discord_dispatcher_roles(self) -> set[str]:
        return self._parse_role_names(self.discord_dispatcher_role_names)

    @property
    def parsed_discord_parts_roles(self) -> set[str]:
        return self._parse_role_names(self.discord_parts_role_names)


settings = Settings()


def member_export_path() -> Path:
    return Path(settings.discord_member_export_path).expanduser()


def export_output_path(*, stem_suffix: str = "", extension: str = ".json") -> Path:
    base = member_export_path()
    stem = f"{base.stem}{stem_suffix}"
    if settings.discord_export_timestamped:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"{stem}_{stamp}"
    return base.with_name(f"{stem}{extension}")

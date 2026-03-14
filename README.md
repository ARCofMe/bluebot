# BlueBot Discord Extension

Minimal Python Discord bot that uses the local `bluefolder-api` wrapper to surface BlueFolder data for technicians in the field.

## Features

- Slash-command based Discord bot
- Uses the local `bluefolder-api` repo via `BLUEFOLDER_API_PATH`
- Commands for:
  - `/ping`
  - `/techs`
  - `/assignments_today tech_id:<id>`
  - `/sr sr_id:<id>`

## Quick Start

```bash
cd bluebot-discord-extension
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

## Environment

See `.env.example`.

Important variables:

- `DISCORD_BOT_TOKEN`
- `DISCORD_GUILD_ID` (optional, but recommended while developing)
- `BLUEFOLDER_API_KEY`
- `BLUEFOLDER_ACCOUNT_NAME`
- `BLUEFOLDER_API_PATH`

## Notes

- This bot uses slash commands, so the bot must be invited with the `applications.commands` scope.
- If `DISCORD_GUILD_ID` is set, commands are synced to that guild for faster iteration.

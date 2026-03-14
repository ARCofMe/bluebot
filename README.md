# BlueBot Discord Extension

Minimal Python Discord bot that uses the local `bluefolder-api` wrapper to surface BlueFolder data for technicians in the field.

## Features

- Slash-command based Discord bot
- Uses the local `bluefolder-api` repo via `BLUEFOLDER_API_PATH`
- Phase 1 field-tech commands for schedules, service request lookup, notes, and waiver links

## Quick Start

```bash
cd bluebot-discord-extension
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

## Environment

See `.env.example`.

Important variables:

- `DISCORD_BOT_TOKEN`
- `DISCORD_GUILD_ID` (optional, but recommended while developing)
- `DISCORD_TECH_MAP` JSON mapping of Discord user IDs to BlueFolder tech IDs for `/my_jobs` and `/next_job`
- `BLUEFOLDER_API_KEY`
- `BLUEFOLDER_ACCOUNT_NAME`
- `BLUEFOLDER_BASE_URL` / `BLUEFOLDER_HOST_HEADER` when your working setup uses an IP-based BlueFolder endpoint
- `BLUEFOLDER_API_PATH` (optional override; otherwise the bot looks for a sibling `../bluefolder-api` repo)
- `BLUEFOLDER_COMMENT_USER_ID` fallback BlueFolder user ID for `note_add` when the Discord user is not mapped in `DISCORD_TECH_MAP`
- `SEARCH_LOOKBACK_DAYS` to control how far back the recent SR search commands scan
- `WAIVER_BASE_URL` to enable `/waiver`
- `WAIVER_SR_PARAM`, `WAIVER_NAME_PARAM`, `WAIVER_FIRST_NAME_PARAM`, and `WAIVER_LAST_NAME_PARAM` to control the waiver query-string keys

## Notes

- This bot uses slash commands, so the bot must be invited with the `applications.commands` scope.
- If `DISCORD_GUILD_ID` is set, commands are synced to that guild for faster iteration.
- `requests` is required at runtime because the local `bluefolder-api` wrapper uses it for real HTTP calls; if it is missing, BlueFolder lookups will fail with empty/invalid XML responses.

## Phase 1 Commands

- `/help` shows the current command set.
- `/ping` verifies bot connectivity.
- `/techs` lists active BlueFolder technicians.
- `/my_jobs` shows today's assignments for the mapped Discord user.
- `/next_job` shows the next scheduled assignment for the mapped Discord user.
- `/assignments_today tech_id:<id>` shows a technician's day by BlueFolder ID.
- `/sr sr_id:<id>` shows a service request summary.
- `/customer sr_id:<id>` shows customer details and contacts for the service request.
- `/site sr_id:<id>` shows the site address and site notes.
- `/notes sr_id:<id>` shows the most recent service request comments.
- `/history sr_id:<id>` shows a broader service request history feed.
- `/note_add sr_id:<id> text:<text>` adds an internal service request note.
- `/attachments sr_id:<id>` lists recent service request attachments.
- `/equipment sr_id:<id>` lists equipment for the customer/site.
- `/search_customer text:<text>` searches recent service requests by customer/subject text.
- `/search_address text:<text>` searches recent service requests by address/city/state/zip.
- `/waiver sr_id:<id>` builds a prefilled waiver link when `WAIVER_BASE_URL` is configured.

## Roadmap

### Phase 2

- Add `/equipment`, `/attachments`, and `/history` so techs can inspect assets and prior work in the field.
- Add `/customer_search`, `/phone_search`, and `/address_search` for partial-lookup workflows.
- Add role-aware command gating so dispatcher/admin commands are separated from tech-only commands.

### Phase 3

- Add `/enroute`, `/start`, `/complete`, and `/eta` status workflow commands.
- Write waiver links or signed state back to BlueFolder custom fields.
- Add technician-facing reminders for overdue jobs, closeout tasks, and upcoming assignments.

### Phase 4

- Reuse dispatcher routing services for `/route_today` and route-aware task suggestions.
- Add troubleshooting assistants, policy lookups, and closeout checklists.
- Add service packaging for long-running deployment on Debian or Raspberry Pi.

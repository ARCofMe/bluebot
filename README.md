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
- `ASSIGNMENT_CACHE_TTL_SECONDS` to cache per-tech assignment windows and reduce repeated BlueFolder calls
- `WORKFLOW_WRITE_ASSIGNMENT` to control whether `/eta`, `/enroute`, `/start`, and `/complete` write to assignment records
- `WORKFLOW_WRITE_SR_NOTE` to control whether those workflow commands also append internal service request notes
- `WAIVER_BASE_URL` to enable `/waiver`
- `WAIVER_SR_PARAM`, `WAIVER_NAME_PARAM`, `WAIVER_FIRST_NAME_PARAM`, and `WAIVER_LAST_NAME_PARAM` to control the waiver query-string keys

## Notes

- This bot uses slash commands, so the bot must be invited with the `applications.commands` scope.
- If `DISCORD_GUILD_ID` is set, commands are synced to that guild for faster iteration.
- `requests` is required at runtime because the local `bluefolder-api` wrapper uses it for real HTTP calls; if it is missing, BlueFolder lookups will fail with empty/invalid XML responses.

## Commands

### Health and Setup

- `/help` shows the current command set.
- `/ping` verifies bot connectivity.
- `/bf_status` shows BlueFolder connectivity and config status.

### Technician Day

- `/my_jobs` shows today's assignments for the mapped Discord user.
- `/next_job` shows the next scheduled assignment for the mapped Discord user.
- `/eta sr_id:<id> minutes:<n>` records an ETA update for your assigned job.
- `/enroute sr_id:<id>` records an en-route update for your assigned job.
- `/start sr_id:<id>` records that work has started on your assigned job.
- `/complete sr_id:<id>` completes your assigned assignment in BlueFolder.
- `/waiver sr_id:<id>` builds a prefilled waiver link when `WAIVER_BASE_URL` is configured.

### Service Request Detail

- `/sr sr_id:<id>` shows a service request summary.
- `/customer sr_id:<id>` shows customer details and contacts for the service request.
- `/site sr_id:<id>` shows the site address and site notes.
- `/notes sr_id:<id>` shows the most recent service request comments.
- `/history sr_id:<id>` shows a broader service request history feed.
- `/note_add sr_id:<id> text:<text>` adds an internal service request note.
- `/attachments sr_id:<id>` lists recent service request attachments.
- `/equipment sr_id:<id>` lists equipment for the customer/site.
- `/materials sr_id:<id>` lists recorded materials for the service request.
- `/labor sr_id:<id>` lists recorded labor for the service request.

### Search and Lookup

- `/search_customer text:<text>` searches the BlueFolder customer directory.
- `/search_address text:<text>` is currently limited by available BlueFolder endpoints on this tenant.
- `/user user_id:<id>` looks up a BlueFolder user.
- `/customer_lookup customer_id:<id>` looks up a BlueFolder customer.
- `/techs` lists active BlueFolder technicians.

### Dispatcher Views

- `/assignments_today tech_id:<id>` shows a technician's day by BlueFolder ID.
- `/tech_day tech_id:<id> when:<YYYY-MM-DD>` shows one technician's assignments on a specific day.
- `/tech_loads` shows today's assignment counts by technician.
- `/who_has_sr sr_id:<id>` finds who has a service request assigned in the next 14 days.

Materials and labor are read from the `serviceRequests/get` payload for the SR. On this tenant, standalone `materials/list` and `labor/list` endpoints are not reliable.

## Workflow Data Model

BlueBot does not keep its own database for technician workflow state.

- ETA, en route, and start updates are written to BlueFolder in two places: the assignment comment for the mapped technician's assignment and an internal service request note.
- Complete uses BlueFolder's assignment completion endpoint and also writes an internal service request note.
- The write targets are configuration-driven with `WORKFLOW_WRITE_ASSIGNMENT=true` and `WORKFLOW_WRITE_SR_NOTE=true`.
- The bot's in-memory assignment cache is only a short-lived read cache to reduce repeated BlueFolder calls. It is cleared after workflow writes so the next lookup reflects current BlueFolder state.

This means BlueFolder remains the system of record for ETA, start time, and completion history.

## Planned Enhancements

- Writing waiver links or signed state back to BlueFolder custom fields.
- Technician-facing reminders for overdue jobs, closeout tasks, and upcoming assignments.
- Route-aware dispatcher commands like `/route_today` and task suggestions.
- Troubleshooting helpers, policy lookups, and closeout checklists.
- Packaging for long-running deployment on Debian or Raspberry Pi.

# Parts Cannon Discord Extension

Discord bot for ARCoM technicians, dispatch, parts, and office staff. It uses the local `bluefolder-api` wrapper to read and write BlueFolder workflow data from slash commands.

## What It Does

- Surfaces BlueFolder schedules, service requests, notes, labor, materials, equipment, and customer/site info
- Lets mapped technicians log workflow updates from Discord
- Gives dispatch and parts staff focused summary commands
- Exports Discord member/mapping audits to JSON and ready-to-paste env snippets
- Keeps BlueFolder as the system of record; the bot does not maintain its own workflow database

## Current Command Areas

- General: health, help, BlueFolder status, waiver link generation
- Service Requests: SR detail, customer/site detail, notes/history, troubleshooting, attachments, labor, materials, equipment, customer search, SR search
- Tech Schedules: `my_jobs`, `my_day`, `my_week`, `next_job`, `my_status`, `my_next_packet`
- Workflow Updates: `note_add`, `eta`, `enroute`, `start`, `complete`, `no_answer`, `not_home`, `access_issue`, `missing_part`, `damaged_part`
- Dispatch: `today_board`, `next_openings`, `assignments_today`, `tech_day`, `tech_loads`, `who_has_sr`, `sr_brief`, `export_today_board`
- Parts: `parts_brief`, `parts_notes`
- Mapping/Admin: `who_am_i_mapped_to`, `tech_map_status`, `lookup_member`, `role_audit`, `mapping_drift`, `export_member_map`, `export_mapping_audit`, `suggest_tech_map`

`/help` is access-filtered. Users only see commands they can actually run.

## Access Model

- Admin access: Discord `Manage Server` or one of `DISCORD_ADMIN_ROLE_NAMES`
- Dispatcher access: dispatcher role or admin access
- Parts access: parts role, dispatcher access, or admin access
- Mapped-tech access: user resolves to a BlueFolder tech through `DISCORD_TECH_MAP` or exact-name matching

Write commands that act as the technician require mapped-tech access.

See [access-and-exports.md](/home/ner0tic/Documents/Projects/ARCoM/bluebot-discord-extension/docs/access-and-exports.md) for the current role model and export artifacts.

## Quick Start

```bash
cd /home/ner0tic/Documents/Projects/ARCoM/bluebot-discord-extension
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

## Environment

Copy [`.env.example`](/home/ner0tic/Documents/Projects/ARCoM/bluebot-discord-extension/.env.example) to `.env`.

Important variables:

- `DISCORD_BOT_TOKEN`
- `DISCORD_GUILD_ID`
- `DISCORD_TECH_MAP`
- `DISCORD_ADMIN_ROLE_NAMES`
- `DISCORD_TECH_ROLE_NAMES`
- `DISCORD_DISPATCHER_ROLE_NAMES`
- `DISCORD_PARTS_ROLE_NAMES`
- `DISPATCHER_ALERT_CHANNEL_ID`
- `DISPATCHER_ALERT_ON_CONTACT_ISSUE`
- `PARTS_ALERT_CHANNEL_ID`
- `PARTS_ALERT_ON_CONTACT_ISSUE`
- `DISCORD_MEMBER_EXPORT_PATH`
- `DISCORD_EXPORT_TIMESTAMPED`
- `BLUEFOLDER_API_KEY`
- `BLUEFOLDER_ACCOUNT_NAME`
- `BLUEFOLDER_BASE_URL`
- `BLUEFOLDER_HOST_HEADER`
- `BLUEFOLDER_VERIFY_SSL`
- `BLUEFOLDER_TIMEOUT_SECONDS`
- `BLUEFOLDER_COMMENT_USER_ID`
- `BLUEFOLDER_API_PATH`
- `ASSIGNMENT_CACHE_TTL_SECONDS`
- `WORKFLOW_WRITE_ASSIGNMENT`
- `WORKFLOW_WRITE_SR_NOTE`
- `WORKFLOW_ASSIGNMENT_LOOKUP_DAYS_BEFORE`
- `WORKFLOW_ASSIGNMENT_LOOKUP_DAYS_AFTER`
- `WAIVER_BASE_URL`
- `WAIVER_SR_PARAM`
- `WAIVER_NAME_PARAM`
- `WAIVER_FIRST_NAME_PARAM`
- `WAIVER_LAST_NAME_PARAM`

## Mapping and Role Setup

Minimum useful setup:

1. Set `DISCORD_TECH_MAP` for known technicians.
2. Set role names for admin, dispatcher, tech, and parts if you want role-based access.
3. Enable Discord `Server Members Intent` if you want full guild member exports and mapping suggestions.

Recommended admin workflow:

1. Run `/export_member_map scope:guild`.
2. Run `/suggest_tech_map scope:guild`.
3. Review the generated JSON and env snippet.
4. Paste the suggested `DISCORD_TECH_MAP=...` into `.env`.
5. Restart the bot.

The mapping suggestion flow is conservative:

- exact normalized name matches are suggested automatically
- near matches are exported for review
- ambiguous and unmatched users are called out explicitly

## Write Command Behavior

Technician write commands are preview-first.

- `note_add`
- `no_answer`
- `not_home`
- `access_issue`
- `missing_part`
- `damaged_part`
- `eta`
- `enroute`
- `start`
- `complete`

These commands send a preview unless `confirm:true` is supplied. Example:

```text
/enroute sr_id:12345 minutes:20 confirm:true
```

`/enroute` accepts an optional `minutes` value and records the ETA update in the same action.

## Workflow Storage Model

Parts Cannon does not keep its own workflow database.

- ETA, en route, and start updates can write to BlueFolder assignment comments and internal SR notes
- Complete uses BlueFolder assignment completion and can also add an internal SR note
- Write targets are controlled by `WORKFLOW_WRITE_ASSIGNMENT` and `WORKFLOW_WRITE_SR_NOTE`
- Assignment ownership remains enforced, but the lookup window is configurable with `WORKFLOW_ASSIGNMENT_LOOKUP_DAYS_BEFORE` and `WORKFLOW_ASSIGNMENT_LOOKUP_DAYS_AFTER`
- Dispatcher and parts alert channels can receive contact and parts issue notifications
- The assignment cache is short-lived and is cleared after workflow writes

BlueFolder remains the system of record for technician workflow history.

## Testing

Current lightweight stabilization suite:

```bash
cd /home/ner0tic/Documents/Projects/ARCoM/bluebot-discord-extension
source .venv/bin/activate
pytest tests -q
```

The current tests cover:

- access control helpers
- help visibility by role/mapping
- write-preview behavior for mapped-tech commands

## Notes

- The bot uses slash commands and needs the `applications.commands` scope.
- If `DISCORD_GUILD_ID` is set, command sync is limited to that guild for faster iteration.
- `requests` is still required at runtime because the local `bluefolder-api` wrapper depends on it.
- Generated admin artifacts go under `exports/` and are gitignored.

# Access And Export Notes

## Access Rules

- Admin: Discord `Manage Server` or a configured admin role in `DISCORD_ADMIN_ROLE_NAMES`
- Dispatcher: configured dispatcher role or admin
- Parts: configured parts role, dispatcher, or admin
- Mapped tech: Discord user resolves to a BlueFolder tech through `DISCORD_TECH_MAP` or exact-name matching

Command help and runtime access now use the same policy table in [client.py](/home/ner0tic/Documents/Projects/ARCoM/bluebot-discord-extension/app/bot/client.py).

## Admin Export Commands

- `/export_member_map scope:guild|channel`
  - writes member id/name/role snapshots to JSON
- `/suggest_tech_map scope:guild|channel`
  - writes:
    - suggested exact matches
    - near-match review candidates
    - unmatched Discord users
    - unmatched BlueFolder techs
    - a paste-ready `DISCORD_TECH_MAP=...` env snippet
- `/export_mapping_audit scope:guild|channel`
  - writes a mapping/role audit snapshot
- `/export_today_board`
  - writes a dispatch board snapshot

## Output Files

The base output path is controlled by `DISCORD_MEMBER_EXPORT_PATH`.

Examples:

- `exports/discord_members_20260321_141500.json`
- `exports/discord_members_suggested_map_20260321_141530.json`
- `exports/discord_members_suggested_map_20260321_141530.env`
- `exports/discord_members_mapping_audit_20260321_141545.json`
- `exports/discord_members_today_board_20260321_141600.json`

If `DISCORD_EXPORT_TIMESTAMPED=true`, repeated exports do not overwrite each other.

## Recommended Setup Sequence

1. Enable `Server Members Intent` in the Discord Developer Portal.
2. Set the admin, dispatcher, parts, and tech role-name env vars.
3. Run `/export_member_map`.
4. Run `/suggest_tech_map`.
5. Review near matches and unmatched users.
6. Update `.env` with the final `DISCORD_TECH_MAP`.
7. Restart the bot.

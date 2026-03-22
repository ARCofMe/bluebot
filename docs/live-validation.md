# Live Validation Runbook

Use this after local tests are green and the bot is configured with real Discord and BlueFolder credentials.

## Preconditions

- `.env` is populated with the real Discord and BlueFolder values
- The bot has been invited with `applications.commands`
- Discord `Server Members Intent` is enabled if you plan to validate guild-wide export commands
- `DISCORD_GUILD_ID` is set if you want faster guild-only command sync during validation
- At least one real Discord user exists for each access class:
  - admin
  - dispatcher
  - parts
  - mapped tech
  - plain user with no special role
- At least one safe test service request exists in BlueFolder for read validation
- At least one safe test service request is assigned to the mapped tech for write validation

## Boot Validation

1. Start the bot:

```bash
cd bluebot-discord-extension
source .venv/bin/activate
python -m app.main
```

2. Confirm startup behavior:
   - no immediate crash
   - no command sync exception in logs
   - slash commands appear in the target guild

3. Run:
   - `/ping`
   - `/bf_status`

Expected:
- `/ping` returns `pong`
- `/bf_status` reports `OK: True` and a nonzero active-tech count

Failure signals:
- sync errors on startup
- `/bf_status` showing `OK: False`
- BlueFolder host or SSL values clearly wrong in the output

## Access Validation

Run `/help` and selected commands as each user class.

### Plain User

Expected:
- does not see dispatch, parts, or mapped-tech workflow commands in `/help`
- can still run general read-only commands like `/ping`

### Admin

Expected:
- sees mapping/admin commands in `/help`
- can run:
  - `/export_member_map scope:guild`
  - `/suggest_tech_map scope:guild`
  - `/export_mapping_audit scope:guild`
  - `/lookup_member user:<member>`

### Dispatcher

Expected:
- sees dispatch commands in `/help`
- can run:
  - `/today_board`
  - `/next_openings`
  - `/assignments_today tech_id:<id>`
  - `/tech_day tech_id:<id> when:YYYY-MM-DD`

### Parts

Expected:
- sees parts commands in `/help`
- can run:
  - `/parts_brief sr_id:<id>`
  - `/parts_notes sr_id:<id>`

### Mapped Tech

Expected:
- `/who_am_i_mapped_to` shows a concrete BlueFolder tech mapping
- sees tech schedule and workflow update commands in `/help`
- can run:
  - `/my_jobs`
  - `/my_day date_iso:YYYY-MM-DD`
  - `/my_next_packet`

## Export Validation

Run:

- `/export_member_map scope:guild`
- `/suggest_tech_map scope:guild`
- `/export_mapping_audit scope:guild`
- `/export_today_board`

Expected:
- commands complete without Discord failure banners
- files are written under `exports/`
- timestamped files are unique when `DISCORD_EXPORT_TIMESTAMPED=true`
- suggested map output contains:
  - `matched`
  - `ambiguous`
  - `near_matches`
  - `unmatched_discord`
  - `unmatched_bluefolder`

Failure signals:
- member export fails even though Server Members Intent is enabled
- export file path is unwritable
- env snippet file is missing after `/suggest_tech_map`

## Read Command Validation

Choose one known-good SR and one nonexistent SR id.

Run on the good SR:

- `/sr`
- `/job_packet`
- `/customer`
- `/site`
- `/notes`
- `/history`
- `/attachments`
- `/equipment`
- `/materials`
- `/labor`
- `/troubleshoot`
- `/waiver`

Expected:
- all commands return clean ephemeral responses
- large outputs split into multiple followups instead of failing silently
- `/waiver` returns a prefilled URL with the SR and customer data

Run on the bad SR:

- `/sr sr_id:<bad_id>`
- `/job_packet sr_id:<bad_id>`
- `/waiver sr_id:<bad_id>`

Expected:
- clear user-facing error or not-found response
- no generic Discord "application did not respond" behavior

## Search Validation

Run:

- `/search_customer text:<known customer fragment>`
- `/find_sr text:<known SR fragment>`
- `/search_address text:<anything>`

Expected:
- customer and SR searches return results when known matches exist
- address search either returns supported results or the explicit tenant-limitation message

## Write Validation

Use a safe assigned SR for the mapped tech.

First confirm preview behavior:

- `/note_add ... confirm:false`
- `/eta ... confirm:false`
- `/enroute ... confirm:false`
- `/start ... confirm:false`
- `/complete ... confirm:false`
- `/no_answer ... confirm:false`
- `/not_home ... confirm:false`
- `/access_issue ... confirm:false`
- `/missing_part ... confirm:false`
- `/damaged_part ... confirm:false`

Expected:
- preview text is shown
- no BlueFolder write occurs yet

Then confirm real writes with `confirm:true` for a subset you are comfortable validating.

Recommended minimum:

- `/note_add sr_id:<id> text:<marker> confirm:true`
- `/eta sr_id:<id> minutes:15 confirm:true`
- `/enroute sr_id:<id> minutes:20 confirm:true`
- `/start sr_id:<id> confirm:true`

If you have a disposable validation assignment:

- `/complete sr_id:<id> confirm:true`

Expected:
- the bot confirms the write target and timestamp
- BlueFolder assignment comments and/or SR notes reflect the update
- assignment cache clears cleanly and follow-up reads reflect the new state

## Alert Channel Validation

If alert channels are configured:

- trigger one contact issue command with `confirm:true`
- trigger one parts issue command with `confirm:true`

Expected:
- contact issue posts into the dispatcher alert channel
- parts issue posts into the parts alert channel
- the user response still succeeds even if the alert send fails

Failure signals:
- dispatcher message routed to the parts channel
- parts message labeled as dispatcher
- command reports success but no BlueFolder note exists

## Negative Validation

Run these intentionally bad inputs:

- `/my_day date_iso:not-a-date`
- `/eta minutes:-1`
- `/enroute minutes:-1`
- write command from an unmapped tech
- dispatch command from a plain user
- admin export command from a non-admin

Expected:
- immediate validation/access error
- no generic Discord failure banner

## Sign-Off Checklist

- startup and sync succeeded
- access boundaries behaved correctly
- exports wrote valid files
- read commands worked on good and bad SR ids
- search commands behaved as expected
- preview-first behavior worked
- selected writes succeeded in BlueFolder
- alert channels behaved correctly
- no generic Discord failure banners observed

If any step fails, capture:

- the exact slash command input
- the exact Discord response text
- relevant bot log lines
- whether BlueFolder reflected the action

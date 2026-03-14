"""Discord client and slash commands."""

from __future__ import annotations

from datetime import date, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from app.core.config import settings
from app.services.bluefolder_service import BlueFolderService


class BlueBotDiscord(commands.Bot):
    """Discord bot wired to BlueFolder helpers."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.bluefolder = BlueFolderService()

    async def setup_hook(self) -> None:
        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


bot = BlueBotDiscord()


def _my_tech_id(interaction: discord.Interaction) -> int | None:
    names = [
        getattr(interaction.user, "display_name", None),
        getattr(interaction.user, "global_name", None),
        getattr(interaction.user, "name", None),
    ]
    return bot.bluefolder.resolve_tech_id(
        interaction.user.id,
        [name for name in names if name],
    )


def _my_tech_help() -> str:
    return (
        "Your Discord user is not mapped to a BlueFolder tech yet. "
        "Set `DISCORD_TECH_MAP` in `.env` or use `/assignments_today tech_id:<id>`."
    )


def _parse_iso_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


@bot.tree.command(description="Basic bot connectivity check.")
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("pong", ephemeral=True)


@bot.tree.command(name="help", description="List BlueBot slash commands.")
async def help_command(interaction: discord.Interaction) -> None:
    lines = [
        "/help - show this command list",
        "/ping - verify bot connectivity",
        "/techs - list active BlueFolder technicians",
        "/my_jobs - today's assignments for your mapped tech",
        "/next_job - your next scheduled assignment today",
        "/assignments_today tech_id - today's assignments for a tech",
        "/sr sr_id - service request summary",
        "/customer sr_id - customer and contact details",
        "/site sr_id - site address and site notes",
        "/notes sr_id - recent service request notes",
        "/history sr_id - broader service request history",
        "/eta sr_id minutes - update ETA on your assigned job",
        "/enroute sr_id - mark yourself en route on your assigned job",
        "/start sr_id - mark yourself started on your assigned job",
        "/complete sr_id - complete your assigned job",
        "/note_add sr_id text - add an internal service request note",
        "/attachments sr_id - recent service request attachments",
        "/equipment sr_id - customer equipment for the job site",
        "/materials sr_id - materials recorded against the service request",
        "/labor sr_id - labor recorded against the service request",
        "/search_customer text - search the BlueFolder customer directory",
        "/search_address text - address search is limited on this BlueFolder tenant",
        "/user user_id - BlueFolder user lookup",
        "/customer_lookup customer_id - BlueFolder customer lookup",
        "/tech_loads - today's assignment counts by tech",
        "/tech_day tech_id date - assignments for one tech on a specific day",
        "/who_has_sr sr_id - find who has a service request in the next 14 days",
        "/bf_status - BlueFolder connectivity/config status",
        "/waiver sr_id - generate the prefilled waiver link",
    ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="techs", description="List active BlueFolder technicians.")
async def techs(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_list = bot.bluefolder.list_active_techs()
    if not tech_list:
        await interaction.followup.send("No active technicians found.", ephemeral=True)
        return

    lines = [f"{t['id']} - {t['name']}" for t in tech_list[:25]]
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="my_jobs", description="Show today's assignments for your mapped technician account.")
async def my_jobs(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    assignments = bot.bluefolder.get_assignments_for_user_today(tech_id)
    if not assignments:
        await interaction.followup.send("No assignments found for you today.", ephemeral=True)
        return

    lines = []
    for idx, item in enumerate(assignments[:15], start=1):
        start = item.get("start_display") or "unscheduled"
        sr_id = item.get("service_request_id") or "?"
        subject = item.get("subject") or "Service Request"
        lines.append(f"{idx}. {start} - SR {sr_id} - {subject}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="next_job", description="Show your next scheduled assignment today.")
async def next_job(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    assignments = bot.bluefolder.get_assignments_for_user_today(tech_id)
    if not assignments:
        await interaction.followup.send("No assignments found for you today.", ephemeral=True)
        return

    item = assignments[0]
    lines = [
        f"SR {item.get('service_request_id') or '?'}",
        f"Start: {item.get('start_display') or item.get('start') or 'unscheduled'}",
        f"End: {item.get('end_display') or item.get('end') or 'n/a'}",
        f"Subject: {item.get('subject') or 'Service Request'}",
    ]
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="assignments_today", description="Show today's assignments for a technician.")
@app_commands.describe(tech_id="BlueFolder technician user ID")
async def assignments_today(interaction: discord.Interaction, tech_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    assignments = bot.bluefolder.get_assignments_for_user_today(tech_id)
    if not assignments:
        await interaction.followup.send(f"No assignments found today for tech `{tech_id}`.", ephemeral=True)
        return

    lines = []
    for idx, item in enumerate(assignments[:15], start=1):
        sr_id = item.get("service_request_id") or "?"
        start = item.get("start_display") or item.get("start") or "unscheduled"
        subject = item.get("subject") or "Service Request"
        lines.append(f"{idx}. SR {sr_id} - {start} - {subject}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="sr", description="Look up a BlueFolder service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def sr(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_service_request(sr_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for `{sr_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"Service request `{sr_id}` not found.", ephemeral=True)
        return

    lines = [
        f"SR {item['id']}",
        f"Subject: {item.get('subject') or 'n/a'}",
        f"Status: {item.get('status') or 'n/a'}",
        f"Priority: {item.get('priority') or 'n/a'}",
    ]
    if item.get("address"):
        lines.append(f"Address: {item['address']}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="customer", description="Show customer details and contacts for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def customer(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_service_request(sr_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for `{sr_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"Service request `{sr_id}` not found.", ephemeral=True)
        return

    lines = [
        f"Customer: {item.get('customer_name') or 'n/a'}",
        f"Phone: {item.get('customer_phone') or 'n/a'}",
        f"Email: {item.get('customer_email') or 'n/a'}",
    ]
    for contact in item.get("contacts", [])[:3]:
        bits = [contact["name"]]
        if contact.get("title"):
            bits.append(contact["title"])
        if contact.get("phone"):
            bits.append(contact["phone"])
        if contact.get("email"):
            bits.append(contact["email"])
        prefix = "Primary Contact" if contact.get("is_primary") else "Contact"
        lines.append(f"{prefix}: {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="site", description="Show site address and site notes for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def site(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_service_request(sr_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for `{sr_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"Service request `{sr_id}` not found.", ephemeral=True)
        return

    lines = [
        f"Site: {item.get('site_name') or 'n/a'}",
        f"Address: {item.get('address') or 'n/a'}",
    ]
    if item.get("site_notes"):
        lines.append(f"Site Notes: {item['site_notes']}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="notes", description="Show recent notes for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def notes(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    comments = bot.bluefolder.get_service_request_notes(sr_id)
    if not comments:
        await interaction.followup.send(f"No recent notes found for `{sr_id}`.", ephemeral=True)
        return

    blocks = []
    for idx, comment in enumerate(comments, start=1):
        date = comment.get("dateCreated") or "unknown"
        author = comment.get("author") or "Unknown"
        text = comment.get("text") or ""
        entry_type = comment.get("entryType") or "Note"
        block = "\n".join(
            [
                f"**{idx}. {entry_type}**",
                f"`{date}` by **{author}**",
                text,
            ]
        )
        blocks.append(block)
    await interaction.followup.send("\n\n---\n\n".join(blocks), ephemeral=True)


@bot.tree.command(name="history", description="Show broader service request history.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def history(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    entries = bot.bluefolder.get_service_request_history(sr_id, limit=10)
    if not entries:
        await interaction.followup.send(f"No history found for `{sr_id}`.", ephemeral=True)
        return

    blocks = []
    for idx, entry in enumerate(entries, start=1):
        blocks.append(
            "\n".join(
                [
                    f"**{idx}. {entry.get('entryType') or 'History'}**",
                    f"`{entry.get('dateCreated') or 'unknown'}` by **{entry.get('author') or 'Unknown'}**",
                    entry.get("text") or "",
                ]
            )
        )
    await interaction.followup.send("\n\n---\n\n".join(blocks), ephemeral=True)


@bot.tree.command(name="note_add", description="Add an internal note to a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", text="Note text to append")
async def note_add(interaction: discord.Interaction, sr_id: int, text: str) -> None:
    await interaction.response.defer(ephemeral=True)
    result = bot.bluefolder.add_service_request_note(
        sr_id,
        text,
        user_id=_my_tech_id(interaction),
        visible_to_customer=False,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not add note to `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    await interaction.followup.send(f"Added note to service request `{sr_id}`.", ephemeral=True)


@bot.tree.command(name="eta", description="Record an ETA update for your assigned service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", minutes="Minutes until arrival")
async def eta(interaction: discord.Interaction, sr_id: int, minutes: int) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    if minutes < 0:
        await interaction.followup.send("ETA minutes must be zero or greater.", ephemeral=True)
        return

    result = bot.bluefolder.mark_eta(sr_id, user_id=tech_id, minutes=minutes)
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not update ETA for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        "\n".join(
            [
                f"Updated ETA for service request `{sr_id}`.",
                f"Stored as: {result.get('stored_as')}",
                f"ETA: {result.get('eta_minutes')} minutes",
            ]
        ),
        ephemeral=True,
    )


@bot.tree.command(name="enroute", description="Mark yourself en route for your assigned service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def enroute(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    result = bot.bluefolder.mark_enroute(sr_id, user_id=tech_id)
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not mark `{sr_id}` en route: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        "\n".join(
            [
                f"Marked service request `{sr_id}` en route.",
                f"Stored as: {result.get('stored_as')}",
                f"Time: {result.get('timestamp')}",
            ]
        ),
        ephemeral=True,
    )


@bot.tree.command(name="start", description="Mark yourself started on your assigned service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def start(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    result = bot.bluefolder.mark_start(sr_id, user_id=tech_id)
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not mark `{sr_id}` started: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        "\n".join(
            [
                f"Marked service request `{sr_id}` started.",
                f"Stored as: {result.get('stored_as')}",
                f"Started: {result.get('started_at')}",
            ]
        ),
        ephemeral=True,
    )


@bot.tree.command(name="complete", description="Complete your assigned service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def complete(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    result = bot.bluefolder.mark_complete(sr_id, user_id=tech_id)
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not complete `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        "\n".join(
            [
                f"Completed assignment for service request `{sr_id}`.",
                f"Stored as: {result.get('stored_as')}",
                f"Completed: {result.get('completed_at')}",
            ]
        ),
        ephemeral=True,
    )


@bot.tree.command(name="attachments", description="List recent attachments for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def attachments(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.get_service_request_attachments(sr_id)
    if not rows:
        await interaction.followup.send(f"No attachments found for `{sr_id}`.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        when = row.get("postedOn") or row.get("dateCreated") or "unknown"
        bits = [row.get("fileName") or "attachment", f"type={row.get('fileType') or 'n/a'}", when]
        if row.get("description"):
            bits.append(row["description"])
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="equipment", description="List customer equipment for a service request site.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def equipment(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.get_service_request_equipment(sr_id)
    if not rows:
        await interaction.followup.send(f"No equipment found for `{sr_id}`.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [row.get("name") or "Equipment"]
        if row.get("model"):
            bits.append(f"model={row['model']}")
        if row.get("serialNumber"):
            bits.append(f"serial={row['serialNumber']}")
        if row.get("installDate"):
            bits.append(f"installed={row['installDate']}")
        if row.get("manufacturer"):
            bits.append(f"mfr={row['manufacturer']}")
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="materials", description="List materials recorded against a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def materials(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.get_service_request_materials(sr_id)
    if not rows:
        await interaction.followup.send(f"No materials found for `{sr_id}`.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [row.get("itemName") or row.get("description") or "Material"]
        if row.get("quantity"):
            bits.append(f"qty={row['quantity']}")
        if row.get("unitPrice"):
            bits.append(f"unit={row['unitPrice']}")
        if row.get("total"):
            bits.append(f"total={row['total']}")
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="labor", description="List labor recorded against a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def labor(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.get_service_request_labor(sr_id)
    if not rows:
        await interaction.followup.send(f"No labor found for `{sr_id}`.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [row.get("date") or "unknown date"]
        if row.get("hours"):
            bits.append(f"hours={row['hours']}")
        if row.get("rate"):
            bits.append(f"rate={row['rate']}")
        if row.get("total"):
            bits.append(f"total={row['total']}")
        if row.get("description"):
            bits.append(row["description"])
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="search_customer", description="Search the BlueFolder customer directory.")
@app_commands.describe(text="Customer or subject text")
async def search_customer(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.search_recent_service_requests(text, field="customer")
    if not rows:
        await interaction.followup.send(f"No customers matched `{text}`.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [f"Customer {row.get('id')}", row.get("subject") or "Customer"]
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="search_address", description="Address search is limited on this BlueFolder tenant.")
@app_commands.describe(text="Address, city, state, or zip text")
async def search_address(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.search_recent_service_requests(text, field="address")
    if not rows:
        await interaction.followup.send(
            "Address search is not fully supported by the BlueFolder endpoints available on this tenant yet.",
            ephemeral=True,
        )
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [f"SR {row.get('id')}", row.get("subject") or "Service Request"]
        if row.get("address"):
            bits.append(row["address"])
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="user", description="Look up a BlueFolder user.")
@app_commands.describe(user_id="BlueFolder user ID")
async def user(interaction: discord.Interaction, user_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_user(user_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for user `{user_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"User `{user_id}` not found.", ephemeral=True)
        return

    lines = [
        f"User {item['id']}",
        f"Name: {item.get('name') or 'n/a'}",
        f"Email: {item.get('email') or 'n/a'}",
        f"Type: {item.get('user_type') or 'n/a'}",
        f"Active: {item.get('is_active')}",
    ]
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="customer_lookup", description="Look up a BlueFolder customer.")
@app_commands.describe(customer_id="BlueFolder customer ID")
async def customer_lookup(interaction: discord.Interaction, customer_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_customer_summary(customer_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for customer `{customer_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"Customer `{customer_id}` not found.", ephemeral=True)
        return

    lines = [
        f"Customer {item['id']}",
        f"Name: {item.get('name') or 'n/a'}",
        f"Type: {item.get('type') or 'n/a'}",
        f"Inactive: {item.get('inactive')}",
    ]
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="bf_status", description="Show BlueFolder connectivity/config status.")
async def bf_status(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    status = bot.bluefolder.bluefolder_status()
    lines = [
        f"OK: {status.get('ok')}",
        f"Base URL: {status.get('base_url') or 'n/a'}",
        f"Host Header: {status.get('host_header') or 'n/a'}",
        f"Verify SSL: {status.get('verify_ssl')}",
    ]
    if status.get("ok"):
        lines.append(f"Active Techs: {status.get('active_tech_count')}")
    else:
        lines.append(f"Error: {status.get('error') or 'unknown'}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="tech_loads", description="Show today's assignment counts by technician.")
async def tech_loads(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.get_dispatch_loads_for_day(date.today(), limit=15)
    if not rows:
        await interaction.followup.send("No technician load data available.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [
            row["tech_name"],
            f"jobs={row['assignment_count']}",
        ]
        if row.get("first_start"):
            bits.append(f"first={row['first_start']}")
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="tech_day", description="Show assignments for a technician on a specific day.")
@app_commands.describe(
    tech_id="BlueFolder technician user ID",
    when="Date in YYYY-MM-DD format",
)
async def tech_day(interaction: discord.Interaction, tech_id: int, when: str) -> None:
    await interaction.response.defer(ephemeral=True)
    day = _parse_iso_date(when)
    if not day:
        await interaction.followup.send("Use YYYY-MM-DD for the date.", ephemeral=True)
        return

    assignments = bot.bluefolder.get_assignments_for_user_day(tech_id, day)
    if not assignments:
        await interaction.followup.send(
            f"No assignments found for tech `{tech_id}` on `{when}`.",
            ephemeral=True,
        )
        return

    lines = []
    for idx, item in enumerate(assignments[:20], start=1):
        bits = [
            f"SR {item.get('service_request_id') or '?'}",
            item.get("start_display") or item.get("start") or "unscheduled",
            item.get("subject") or "Service Request",
        ]
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="who_has_sr", description="Find who has a service request in the next 14 days.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def who_has_sr(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.find_sr_assignment_window(
        sr_id,
        start_day=date.today(),
        end_day=date.today() + timedelta(days=14),
    )
    if not rows:
        await interaction.followup.send(
            f"No active-tech assignment found in the next 14 days for `{sr_id}`.",
            ephemeral=True,
        )
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [row["tech_name"]]
        if row.get("start"):
            bits.append(f"start={row['start']}")
        if row.get("end"):
            bits.append(f"end={row['end']}")
        if row.get("subject"):
            bits.append(row["subject"])
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="waiver", description="Generate a prefilled waiver link for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def waiver(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    result = bot.bluefolder.build_waiver_link(sr_id)
    if result.get("error"):
        await interaction.followup.send(
            f"Could not build waiver link for `{sr_id}`: {result['error']}",
            ephemeral=True,
        )
        return

    lines = [
        f"SR {result['sr_id']}",
        f"Customer: {result['customer_name']}",
        result["url"],
    ]
    await interaction.followup.send("\n".join(lines), ephemeral=True)

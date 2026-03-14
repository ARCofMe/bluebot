"""Discord client and slash commands."""

from __future__ import annotations

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
        "/note_add sr_id text - add an internal service request note",
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

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


@bot.tree.command(description="Basic bot connectivity check.")
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("pong", ephemeral=True)


@bot.tree.command(name="techs", description="List active BlueFolder technicians.")
async def techs(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_list = bot.bluefolder.list_active_techs()
    if not tech_list:
        await interaction.followup.send("No active technicians found.", ephemeral=True)
        return

    lines = [f"{t['id']} - {t['name']}" for t in tech_list[:25]]
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
        start = item.get("start") or "unscheduled"
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

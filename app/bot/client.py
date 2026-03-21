"""Discord client and slash commands."""

from __future__ import annotations

from datetime import date, timedelta
from difflib import SequenceMatcher
import json
import re

import discord
from discord import app_commands
from discord.ext import commands

from app.core.config import export_output_path, settings
from app.services.bluefolder_service import BlueFolderService


class PartsCannonDiscord(commands.Bot):
    """Discord bot wired to BlueFolder helpers."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.bluefolder = BlueFolderService()

    async def setup_hook(self) -> None:
        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


bot = PartsCannonDiscord()
_DISCORD_MESSAGE_LIMIT = 2000


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


def _normalize_name(raw: str | None) -> str:
    text = " ".join(str(raw or "").split()).strip().casefold()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return text


def _member_name_candidates_from_record(member: dict[str, object]) -> list[str]:
    candidates: list[str] = []
    for raw in [member.get("display_name"), member.get("global_name"), member.get("username")]:
        normalized = _normalize_name(str(raw or ""))
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _chunk_lines(lines: list[str], *, limit: int = _DISCORD_MESSAGE_LIMIT) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + (1 if current else 0)
        if current and current_len + line_len > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))
    return chunks


def _help_lines() -> list[str]:
    sections = {
        "General": [
            "/bf_status - BlueFolder connectivity/config status",
            "/help - show this command list",
            "/ping - verify bot connectivity",
            "/waiver sr_id - generate the prefilled waiver link",
        ],
        "Mapping And Admin": [
            "/export_member_map scope - export Discord user ids/names for env mapping",
            "/lookup_member user - inspect one Discord member's BlueFolder mapping state",
            "/suggest_tech_map scope - suggest DISCORD_TECH_MAP from Discord names vs BlueFolder techs",
            "/tech_map_status scope - audit mapping coverage for guild/channel members",
            "/who_am_i_mapped_to - show your Discord to BlueFolder tech mapping status",
        ],
        "Tech Schedules": [
            "/assignments_today tech_id - today's assignments for a tech",
            "/my_jobs - today's assignments for your mapped tech",
            "/next_job - your next scheduled assignment today",
            "/tech_day tech_id date - assignments for one tech on a specific day",
            "/tech_loads - today's assignment counts by tech",
            "/techs - list active BlueFolder technicians",
            "/who_has_sr sr_id - find who has a service request in the next 14 days",
        ],
        "Service Requests": [
            "/attachments sr_id - recent service request attachments",
            "/customer sr_id - customer and contact details",
            "/equipment sr_id - customer equipment for the job site",
            "/history sr_id - broader service request history",
            "/labor sr_id - labor recorded against the service request",
            "/materials sr_id - materials recorded against the service request",
            "/notes sr_id - recent service request notes",
            "/search_address text - address search is limited on this BlueFolder tenant",
            "/search_customer text - search the BlueFolder customer directory",
            "/site sr_id - site address and site notes",
            "/sr sr_id - service request summary",
            "/troubleshoot sr_id - pull recent diagnosis/work context",
            "/user user_id - BlueFolder user lookup",
            "/customer_lookup customer_id - BlueFolder customer lookup",
        ],
        "Workflow Updates": [
            "/access_issue sr_id details - log an access problem",
            "/complete sr_id - complete your assigned job",
            "/damaged_part sr_id details - log a damaged part issue",
            "/enroute sr_id [minutes] - mark yourself en route and optionally record ETA",
            "/eta sr_id minutes - update ETA on your assigned job",
            "/missing_part sr_id details - log a missing part issue",
            "/no_answer sr_id [details] - log that the customer did not answer",
            "/not_home sr_id [details] - log that the customer was not home",
            "/note_add sr_id text - add an internal service request note",
            "/start sr_id - mark yourself started on your assigned job",
        ],
    }

    lines = ["**Parts Cannon Commands**"]
    for title in sorted(sections):
        lines.append("")
        lines.append(f"**{title}**")
        lines.extend(sorted(sections[title]))
    return lines


def _matching_techs_for_member_record(
    member: dict[str, object],
    techs: list[dict[str, object]],
) -> list[dict[str, object]]:
    techs_by_name: dict[str, list[dict[str, object]]] = {}
    for tech in techs:
        normalized = _normalize_name(str(tech.get("name") or ""))
        if not normalized:
            continue
        techs_by_name.setdefault(normalized, []).append(tech)

    unique_matches: dict[int, dict[str, object]] = {}
    for candidate in _member_name_candidates_from_record(member):
        for tech in techs_by_name.get(candidate, []):
            tech_id = int(tech.get("id") or 0)
            if tech_id:
                unique_matches[tech_id] = tech
    return list(unique_matches.values())


def _near_match_techs_for_member_record(
    member: dict[str, object],
    techs: list[dict[str, object]],
    *,
    threshold: float = 0.84,
) -> list[dict[str, object]]:
    candidates = _member_name_candidates_from_record(member)
    scored: list[tuple[float, dict[str, object]]] = []
    for tech in techs:
        tech_name = _normalize_name(str(tech.get("name") or ""))
        if not tech_name:
            continue
        best = max((SequenceMatcher(None, candidate, tech_name).ratio() for candidate in candidates), default=0.0)
        if best >= threshold:
            scored.append((best, tech))

    scored.sort(key=lambda item: (-item[0], str(item[1].get("name") or "")))
    unique: dict[int, dict[str, object]] = {}
    for score, tech in scored[:5]:
        tech_id = int(tech.get("id") or 0)
        if tech_id and tech_id not in unique:
            unique[tech_id] = {
                "id": tech_id,
                "name": tech.get("name"),
                "score": round(score, 3),
            }
    return list(unique.values())


def _name_candidates(member: discord.Member) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for raw in [member.display_name, member.global_name, member.name]:
        normalized = _normalize_name(raw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)
    return candidates


def _build_tech_map_suggestion(
    members: list[dict[str, object]],
    techs: list[dict[str, object]],
) -> dict[str, object]:
    suggested_map: dict[str, int] = {}
    matched: list[dict[str, object]] = []
    ambiguous: list[dict[str, object]] = []
    near_matches: list[dict[str, object]] = []
    unmatched_discord: list[dict[str, object]] = []
    matched_tech_ids: set[int] = set()

    for member in members:
        unique_matches = _matching_techs_for_member_record(member, techs)

        if len(unique_matches) == 1:
            tech = unique_matches[0]
            tech_id = int(tech["id"])
            suggested_map[str(member["discord_user_id"])] = tech_id
            matched_tech_ids.add(tech_id)
            matched.append(
                {
                    "discord_user_id": member["discord_user_id"],
                    "display_name": member.get("display_name"),
                    "username": member.get("username"),
                    "bluefolder_user_id": tech_id,
                    "bluefolder_name": tech.get("name"),
                }
            )
        elif len(unique_matches) > 1:
            ambiguous.append(
                {
                    "discord_user_id": member["discord_user_id"],
                    "display_name": member.get("display_name"),
                    "username": member.get("username"),
                    "candidate_bluefolder_users": [
                        {"id": int(tech["id"]), "name": tech.get("name")}
                        for tech in unique_matches
                    ],
                }
            )
        else:
            nearby = _near_match_techs_for_member_record(member, techs)
            if nearby:
                near_matches.append(
                    {
                        "discord_user_id": member["discord_user_id"],
                        "display_name": member.get("display_name"),
                        "username": member.get("username"),
                        "candidate_bluefolder_users": nearby,
                    }
                )
            unmatched_discord.append(member)

    unmatched_bluefolder = [
        {"id": int(tech["id"]), "name": tech.get("name"), "email": tech.get("email")}
        for tech in techs
        if int(tech.get("id") or 0) not in matched_tech_ids
    ]

    return {
        "suggested_discord_tech_map": suggested_map,
        "suggested_discord_tech_map_env": f"DISCORD_TECH_MAP={json.dumps(suggested_map, separators=(',', ':'))}",
        "matched": matched,
        "ambiguous": ambiguous,
        "near_matches": near_matches,
        "unmatched_discord": unmatched_discord,
        "unmatched_bluefolder": unmatched_bluefolder,
    }


def _require_guild_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.manage_guild)


async def _collect_members(
    interaction: discord.Interaction,
    *,
    scope: str,
) -> list[dict[str, object]]:
    guild = interaction.guild
    if guild is None:
        return []

    members: list[discord.Member]
    if scope == "channel":
        channel = interaction.channel
        members = list(getattr(channel, "members", []) or [])
    else:
        members = [member async for member in guild.fetch_members(limit=None)]

    exported: list[dict[str, object]] = []
    for member in sorted(members, key=lambda item: (item.display_name.casefold(), item.name.casefold(), item.id)):
        if member.bot:
            continue
        exported.append(
            {
                "discord_user_id": str(member.id),
                "username": member.name,
                "display_name": member.display_name,
                "global_name": member.global_name,
            }
        )
    return exported


def _alert_tech_label(interaction: discord.Interaction) -> str:
    discord_name = (
        getattr(interaction.user, "display_name", None)
        or getattr(interaction.user, "global_name", None)
        or getattr(interaction.user, "name", None)
        or "Unknown tech"
    )
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        return discord_name

    tech_name = None
    for tech in bot.bluefolder.list_active_techs():
        if tech.get("id") == tech_id:
            tech_name = tech.get("name")
            break
    if tech_name:
        return f"{discord_name} ({tech_name} / BlueFolder {tech_id})"
    return f"{discord_name} (BlueFolder {tech_id})"


def _discord_member_record(interaction: discord.Interaction) -> dict[str, object]:
    return {
        "discord_user_id": str(interaction.user.id),
        "username": interaction.user.name,
        "display_name": getattr(interaction.user, "display_name", interaction.user.name),
        "global_name": getattr(interaction.user, "global_name", None),
    }


def _discord_member_record_from_member(member: discord.abc.User) -> dict[str, object]:
    return {
        "discord_user_id": str(member.id),
        "username": member.name,
        "display_name": getattr(member, "display_name", member.name),
        "global_name": getattr(member, "global_name", None),
    }


async def _send_channel_alert(
    interaction: discord.Interaction,
    *,
    title: str,
    sr_id: int,
    note_text: str,
    channel_id: int | None,
    enabled: bool,
    customer_name: str | None = None,
    address: str | None = None,
) -> str | None:
    if not enabled:
        return None
    if not channel_id:
        return None

    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            return "Dispatcher alert channel could not be loaded."

    lines = [
        f"**{title}**",
        f"Tech: {_alert_tech_label(interaction)}",
        f"SR: {sr_id}",
    ]
    if customer_name:
        lines.append(f"Customer: {customer_name}")
    if address:
        lines.append(f"Address: {address}")
    lines.append(f"Update: {note_text}")
    try:
        await channel.send("\n".join(lines))
    except Exception:
        return "Dispatcher alert could not be sent."
    return f"Dispatcher alert sent to <#{channel_id}>."


@bot.tree.command(description="Basic bot connectivity check.")
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("pong", ephemeral=True)


@bot.tree.command(name="help", description="List Parts Cannon slash commands.")
async def help_command(interaction: discord.Interaction) -> None:
    chunks = _chunk_lines(_help_lines())
    await interaction.response.send_message(chunks[0], ephemeral=True)
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)


@bot.tree.command(name="who_am_i_mapped_to", description="Show your Discord to BlueFolder tech mapping status.")
async def who_am_i_mapped_to(interaction: discord.Interaction) -> None:
    record = _discord_member_record(interaction)
    techs = bot.bluefolder.list_active_techs()
    direct_map = settings.parsed_discord_tech_map.get(str(interaction.user.id))
    matched_techs = _matching_techs_for_member_record(record, techs)

    lines = [
        f"Discord user: {record['display_name']} (@{record['username']})",
        f"Discord ID: {interaction.user.id}",
    ]
    if direct_map:
        mapped_tech = next((tech for tech in techs if int(tech.get('id') or 0) == int(direct_map)), None)
        if mapped_tech:
            lines.append(f"Mapped via `DISCORD_TECH_MAP`: {mapped_tech['name']} (BlueFolder {mapped_tech['id']})")
        else:
            lines.append(f"Mapped via `DISCORD_TECH_MAP`: BlueFolder {direct_map} (not found in active tech list)")
    else:
        lines.append("Mapped via `DISCORD_TECH_MAP`: no")

    if len(matched_techs) == 1:
        tech = matched_techs[0]
        lines.append(f"Name-based match: {tech['name']} (BlueFolder {tech['id']})")
    elif len(matched_techs) > 1:
        lines.append(
            "Name-based matches: " + ", ".join(f"{tech['name']} ({tech['id']})" for tech in matched_techs[:5])
        )
    else:
        lines.append("Name-based match: none")

    if not direct_map and len(matched_techs) != 1:
        lines.append("Ask an admin to run `/suggest_tech_map` or update `DISCORD_TECH_MAP`.")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="tech_map_status", description="Show Discord-to-BlueFolder tech mapping coverage.")
@app_commands.describe(scope="Audit all guild members or just members visible in this channel.")
@app_commands.choices(
    scope=[
        app_commands.Choice(name="guild", value="guild"),
        app_commands.Choice(name="channel", value="channel"),
    ]
)
async def tech_map_status(
    interaction: discord.Interaction,
    scope: app_commands.Choice[str],
) -> None:
    if not _require_guild_admin(interaction):
        await interaction.response.send_message(
            "You need `Manage Server` permission to audit tech mappings.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    records = await _collect_members(interaction, scope=scope.value)
    techs = bot.bluefolder.list_active_techs()
    active_tech_ids = {int(tech.get("id") or 0) for tech in techs}
    configured_map = settings.parsed_discord_tech_map

    explicit_mapped = 0
    auto_resolvable = 0
    ambiguous = 0
    near_match_only = 0
    unmatched = 0
    stale_mapped = 0
    sample_lines: list[str] = []

    for member in records:
        discord_user_id = str(member["discord_user_id"])
        mapped_tech_id = configured_map.get(discord_user_id)
        matches = _matching_techs_for_member_record(member, techs)

        if mapped_tech_id:
            explicit_mapped += 1
            if int(mapped_tech_id) not in active_tech_ids:
                stale_mapped += 1
                sample_lines.append(
                    f"stale map: {member.get('display_name') or member.get('username')} -> BlueFolder {mapped_tech_id}"
                )
            continue
        if len(matches) == 1:
            auto_resolvable += 1
            if len(sample_lines) < 8:
                tech = matches[0]
                sample_lines.append(
                    f"auto match: {member.get('display_name') or member.get('username')} -> {tech.get('name')} ({tech.get('id')})"
                )
        elif len(matches) > 1:
            ambiguous += 1
            if len(sample_lines) < 8:
                sample_lines.append(
                    f"ambiguous: {member.get('display_name') or member.get('username')}"
                )
        else:
            nearby = _near_match_techs_for_member_record(member, techs)
            if nearby:
                near_match_only += 1
                if len(sample_lines) < 8:
                    best = nearby[0]
                    sample_lines.append(
                        f"near match: {member.get('display_name') or member.get('username')} -> {best.get('name')} ({best.get('id')}, score {best.get('score')})"
                    )
                continue
            unmatched += 1
            if len(sample_lines) < 8:
                sample_lines.append(
                    f"unmatched: {member.get('display_name') or member.get('username')}"
                )

    lines = [
        f"Scope: {scope.value}",
        f"Discord members checked: {len(records)}",
        f"Active BlueFolder techs: {len(techs)}",
        f"Explicitly mapped in env: {explicit_mapped}",
        f"Auto-resolvable by exact name: {auto_resolvable}",
        f"Ambiguous exact-name matches: {ambiguous}",
        f"Near-match review candidates: {near_match_only}",
        f"Unmatched: {unmatched}",
    ]
    if stale_mapped:
        lines.append(f"Mapped to inactive/missing BlueFolder IDs: {stale_mapped}")
    if sample_lines:
        lines.append("")
        lines.append("Examples:")
        lines.extend(sample_lines)

    for idx, chunk in enumerate(_chunk_lines(lines)):
        if idx == 0:
            await interaction.followup.send(chunk, ephemeral=True)
        else:
            await interaction.followup.send(chunk, ephemeral=True)


@bot.tree.command(name="lookup_member", description="Inspect one Discord member's BlueFolder mapping status.")
@app_commands.describe(user="Discord member to inspect.")
async def lookup_member(
    interaction: discord.Interaction,
    user: discord.Member,
) -> None:
    if not _require_guild_admin(interaction):
        await interaction.response.send_message(
            "You need `Manage Server` permission to inspect another member's mapping.",
            ephemeral=True,
        )
        return

    techs = bot.bluefolder.list_active_techs()
    record = _discord_member_record_from_member(user)
    direct_map = settings.parsed_discord_tech_map.get(str(user.id))
    matched_techs = _matching_techs_for_member_record(record, techs)

    lines = [
        f"Discord user: {record['display_name']} (@{record['username']})",
        f"Discord ID: {user.id}",
    ]
    if direct_map:
        mapped_tech = next((tech for tech in techs if int(tech.get('id') or 0) == int(direct_map)), None)
        if mapped_tech:
            lines.append(f"Mapped via `DISCORD_TECH_MAP`: {mapped_tech['name']} (BlueFolder {mapped_tech['id']})")
        else:
            lines.append(f"Mapped via `DISCORD_TECH_MAP`: BlueFolder {direct_map} (not found in active tech list)")
    else:
        lines.append("Mapped via `DISCORD_TECH_MAP`: no")

    if len(matched_techs) == 1:
        tech = matched_techs[0]
        lines.append(f"Name-based match: {tech['name']} (BlueFolder {tech['id']})")
    elif len(matched_techs) > 1:
        lines.append(
            "Name-based matches: " + ", ".join(f"{tech['name']} ({tech['id']})" for tech in matched_techs[:5])
        )
    else:
        lines.append("Name-based match: none")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="export_member_map", description="Export Discord user ids and names to a JSON file.")
@app_commands.describe(scope="Export all guild members or just members visible in this channel.")
@app_commands.choices(
    scope=[
        app_commands.Choice(name="guild", value="guild"),
        app_commands.Choice(name="channel", value="channel"),
    ]
)
async def export_member_map(
    interaction: discord.Interaction,
    scope: app_commands.Choice[str],
) -> None:
    if not _require_guild_admin(interaction):
        await interaction.response.send_message(
            "You need `Manage Server` permission to export member ids.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    records = await _collect_members(interaction, scope=scope.value)
    export_file = export_output_path()
    export_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "guild_id": str(interaction.guild_id or ""),
        "scope": scope.value,
        "member_count": len(records),
        "members": records,
        "discord_tech_map_template": {item["discord_user_id"]: None for item in records},
    }
    export_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    await interaction.followup.send(
        f"Wrote {len(records)} member records to `{export_file}`.",
        ephemeral=True,
    )


@bot.tree.command(name="suggest_tech_map", description="Suggest a DISCORD_TECH_MAP by matching Discord names to BlueFolder techs.")
@app_commands.describe(scope="Compare either all guild members or just members visible in this channel.")
@app_commands.choices(
    scope=[
        app_commands.Choice(name="guild", value="guild"),
        app_commands.Choice(name="channel", value="channel"),
    ]
)
async def suggest_tech_map(
    interaction: discord.Interaction,
    scope: app_commands.Choice[str],
) -> None:
    if not _require_guild_admin(interaction):
        await interaction.response.send_message(
            "You need `Manage Server` permission to build a tech-map suggestion.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    records = await _collect_members(interaction, scope=scope.value)
    techs = bot.bluefolder.list_active_techs()
    suggestion = _build_tech_map_suggestion(records, techs)

    export_file = export_output_path()
    export_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "guild_id": str(interaction.guild_id or ""),
        "scope": scope.value,
        "member_count": len(records),
        "bluefolder_tech_count": len(techs),
        **suggestion,
    }
    suggestion_path = export_output_path(stem_suffix="_suggested_map")
    suggestion_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    env_path = export_output_path(stem_suffix="_tech_map", extension=".env")
    env_path.write_text(f"{suggestion['suggested_discord_tech_map_env']}\n", encoding="utf-8")

    await interaction.followup.send(
        (
            f"Wrote suggested tech map to `{suggestion_path}` and env snippet to `{env_path}`. "
            f"Matched {len(suggestion['matched'])}, ambiguous {len(suggestion['ambiguous'])}, "
            f"near matches {len(suggestion['near_matches'])}, "
            f"unmatched Discord {len(suggestion['unmatched_discord'])}, "
            f"unmatched BlueFolder {len(suggestion['unmatched_bluefolder'])}."
        ),
        ephemeral=True,
    )


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


@bot.tree.command(name="troubleshoot", description="Show recent troubleshooting context for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def troubleshoot(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    result = bot.bluefolder.build_troubleshooting_summary(sr_id)
    if result.get("error"):
        await interaction.followup.send(
            f"Could not build troubleshooting summary for `{sr_id}`: {result['error']}",
            ephemeral=True,
        )
        return

    lines = [
        f"SR {result['sr_id']}",
        f"Subject: {result.get('subject') or 'n/a'}",
    ]
    if result.get("customer_name"):
        lines.append(f"Customer: {result['customer_name']}")
    if result.get("address"):
        lines.append(f"Address: {result['address']}")

    sections = result.get("sections") or {}
    if sections:
        label_map = {
            "complaint": "Complaint",
            "diagnosis": "Diagnosis",
            "work_performed": "Work Performed",
            "parts_needed": "Parts Needed",
            "parts_used": "Parts Used",
        }
        for key in ("complaint", "diagnosis", "work_performed", "parts_needed", "parts_used"):
            if sections.get(key):
                lines.append(f"{label_map[key]}: {sections[key]}")
    else:
        lines.append("No structured troubleshooting sections found in recent labor or history.")

    recent_notes = result.get("recent_notes") or []
    if recent_notes:
        latest = recent_notes[0]
        lines.append(
            f"Latest History: {(latest.get('entryType') or 'Note')} | {latest.get('dateCreated') or 'unknown'}"
        )
        if latest.get("text"):
            lines.append(f"Latest Text: {latest['text'][:250]}")

    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="no_answer", description="Log that the customer did not answer.")
@app_commands.describe(sr_id="BlueFolder service request ID", details="Optional extra detail")
async def no_answer(interaction: discord.Interaction, sr_id: int, details: str | None = None) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    result = bot.bluefolder.log_contact_issue(
        sr_id,
        user_id=tech_id,
        issue_type="no_answer",
        details=details,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not log no-answer for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    alert_status = await _send_channel_alert(
        interaction,
        title="Customer No Answer",
        sr_id=sr_id,
        note_text=result.get("note_text") or "",
        channel_id=settings.dispatcher_alert_channel_id,
        enabled=settings.dispatcher_alert_on_contact_issue,
        customer_name=result.get("customer_name"),
        address=result.get("address"),
    )
    response_lines = [
        f"Logged no-answer for service request `{sr_id}`.",
        f"Time: {result.get('logged_at')}",
        result.get("note_text") or "",
    ]
    if alert_status:
        response_lines.append(alert_status)
    await interaction.followup.send(
        "\n".join(response_lines),
        ephemeral=True,
    )


@bot.tree.command(name="not_home", description="Log that the customer was not home at arrival.")
@app_commands.describe(sr_id="BlueFolder service request ID", details="Optional extra detail")
async def not_home(interaction: discord.Interaction, sr_id: int, details: str | None = None) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    result = bot.bluefolder.log_contact_issue(
        sr_id,
        user_id=tech_id,
        issue_type="not_home",
        details=details,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not log not-home for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    alert_status = await _send_channel_alert(
        interaction,
        title="Customer Not Home",
        sr_id=sr_id,
        note_text=result.get("note_text") or "",
        channel_id=settings.dispatcher_alert_channel_id,
        enabled=settings.dispatcher_alert_on_contact_issue,
        customer_name=result.get("customer_name"),
        address=result.get("address"),
    )
    response_lines = [
        f"Logged not-home for service request `{sr_id}`.",
        f"Time: {result.get('logged_at')}",
        result.get("note_text") or "",
    ]
    if alert_status:
        response_lines.append(alert_status)
    await interaction.followup.send(
        "\n".join(response_lines),
        ephemeral=True,
    )


@bot.tree.command(name="access_issue", description="Log an access problem for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", details="Access problem details")
async def access_issue(interaction: discord.Interaction, sr_id: int, details: str) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    result = bot.bluefolder.log_contact_issue(
        sr_id,
        user_id=tech_id,
        issue_type="access_issue",
        details=details,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not log access issue for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    alert_status = await _send_channel_alert(
        interaction,
        title="Access Issue",
        sr_id=sr_id,
        note_text=result.get("note_text") or "",
        channel_id=settings.dispatcher_alert_channel_id,
        enabled=settings.dispatcher_alert_on_contact_issue,
        customer_name=result.get("customer_name"),
        address=result.get("address"),
    )
    response_lines = [
        f"Logged access issue for service request `{sr_id}`.",
        f"Time: {result.get('logged_at')}",
        result.get("note_text") or "",
    ]
    if alert_status:
        response_lines.append(alert_status)
    await interaction.followup.send(
        "\n".join(response_lines),
        ephemeral=True,
    )


@bot.tree.command(name="missing_part", description="Log a missing part issue for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", details="Missing part details")
async def missing_part(interaction: discord.Interaction, sr_id: int, details: str) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    result = bot.bluefolder.log_parts_issue(
        sr_id,
        user_id=tech_id,
        issue_type="missing_part",
        details=details,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not log missing-part issue for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    alert_status = await _send_channel_alert(
        interaction,
        title="Missing Part",
        sr_id=sr_id,
        note_text=result.get("note_text") or "",
        channel_id=settings.parts_alert_channel_id,
        enabled=settings.parts_alert_on_contact_issue,
        customer_name=result.get("customer_name"),
        address=result.get("address"),
    )
    response_lines = [
        f"Logged missing-part issue for service request `{sr_id}`.",
        f"Time: {result.get('logged_at')}",
        result.get("note_text") or "",
    ]
    if alert_status:
        response_lines.append(alert_status)
    await interaction.followup.send("\n".join(response_lines), ephemeral=True)


@bot.tree.command(name="damaged_part", description="Log a damaged part issue for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", details="Damaged part details")
async def damaged_part(interaction: discord.Interaction, sr_id: int, details: str) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    result = bot.bluefolder.log_parts_issue(
        sr_id,
        user_id=tech_id,
        issue_type="damaged_part",
        details=details,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not log damaged-part issue for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    alert_status = await _send_channel_alert(
        interaction,
        title="Damaged Part",
        sr_id=sr_id,
        note_text=result.get("note_text") or "",
        channel_id=settings.parts_alert_channel_id,
        enabled=settings.parts_alert_on_contact_issue,
        customer_name=result.get("customer_name"),
        address=result.get("address"),
    )
    response_lines = [
        f"Logged damaged-part issue for service request `{sr_id}`.",
        f"Time: {result.get('logged_at')}",
        result.get("note_text") or "",
    ]
    if alert_status:
        response_lines.append(alert_status)
    await interaction.followup.send("\n".join(response_lines), ephemeral=True)


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


@bot.tree.command(name="enroute", description="Mark yourself en route and optionally record ETA.")
@app_commands.describe(sr_id="BlueFolder service request ID", minutes="Optional ETA in minutes")
async def enroute(interaction: discord.Interaction, sr_id: int, minutes: int | None = None) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    if minutes is not None and minutes < 0:
        await interaction.followup.send("ETA minutes must be zero or greater.", ephemeral=True)
        return

    result = bot.bluefolder.mark_enroute(sr_id, user_id=tech_id, minutes=minutes)
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not mark `{sr_id}` en route: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    response_lines = [
        f"Marked service request `{sr_id}` en route.",
        f"Stored as: {result.get('stored_as')}",
        f"Time: {result.get('timestamp')}",
    ]
    if minutes is not None:
        response_lines.append(f"ETA: {result.get('eta_minutes')} minutes")
    await interaction.followup.send(
        "\n".join(response_lines),
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
